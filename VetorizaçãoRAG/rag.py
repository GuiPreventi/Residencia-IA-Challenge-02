import os
import re
import chromadb
from chromadb.utils import embedding_functions
import ollama

# Desativa alertas de symlinks no Windows
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# Otimizações de VRAM para o servidor do Ollama (Flash Attention + Cache KV quantizado em 8-bit)
os.environ["OLLAMA_FLASH_ATTENTION"] = "1"
os.environ["OLLAMA_KV_CACHE_TYPE"] = "q8_0"

# -------------------------------------------------------------
# 1. CONFIGURAÇÃO DO MODELO LOCAL (8B em 3-bit), EMBEDDINGS E CHROMADB
# -------------------------------------------------------------
MODELO_LLM = "hf.co/bartowski/Qwen_Qwen3-8B-GGUF:Q3_K_M"

# Mantém o e5-small na CPU para deixar 100% da VRAM dedicada ao LLM
emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="intfloat/multilingual-e5-small",
    device="cpu"
)

cliente = chromadb.PersistentClient(path="./BancoDados")
collection = cliente.get_collection(
    name="documentos_rag",
    embedding_function=emb_fn
)

# -------------------------------------------------------------
# 2. REGRAS E GUARDIÃO DE SEGURANÇA
# -------------------------------------------------------------
SINAIS_DE_CRISE = [
    "me matar", "suicid", "tirar minha vida", "acabar com tudo",
    "não quero mais viver", "nao quero mais viver", "quero morrer",
    "me machucar", "sumir para sempre"
]

TEXTO_CRISE = (
    "Sinto muito que você esteja passando por isso. Você não precisa enfrentar isso sozinho(a). "
    "Converse agora com o CVV pelo telefone 188 (ligação gratuita, 24 horas) ou pelo chat em cvv.org.br. "
    "Em caso de emergência, ligue 192 (SAMU) ou vá ao pronto-socorro mais próximo."
)

INSTRUCAO_COLABORADOR = """Você é um agente de apoio ao bem-estar no trabalho.
Responda em português, de forma acolhedora e breve (até 5 frases).
Regras:
- Use APENAS as informações presentes no CONTEXTO.
- Não faça diagnósticos nem prescreva medicamentos.
- Sugira no máximo uma prática por vez.
- Se a MENSAGEM DO USUÁRIO não tiver relação com burnout, estresse, saúde mental ou bem-estar no trabalho,
  ou se o CONTEXTO não ajudar a respondê-la, responda EXATAMENTE e somente com: FORA_DO_ESCOPO
- No final, finalize com "Fonte:" seguido da fonte citada no contexto.
/no_think"""

# Marcador que o LLM devolve quando a pergunta não tem a ver com o tema
MARCADOR_FORA_ESCOPO = "FORA_DO_ESCOPO"

# Similaridade mínima do MELHOR trecho para considerar a pergunta dentro do tema.
# O e5 gera scores altos até para assuntos sem relação; calibre com os logs dos bastidores.
LIMIAR_SIMILARIDADE = 0.80

SEM_CONTEXTO = (
    "Desculpe, essa pergunta foge do tema da minha base (burnout e bem-estar no trabalho), "
    "então não tenho o que responder sobre isso. "
    "Se quiser, posso ajudar com algo relacionado a estresse, cansaço ou sobrecarga no trabalho."
)

def limpar_resposta(texto: str) -> str:
    """Remove qualquer bloco <think>...</think> que o Qwen3 possa emitir."""
    texto = re.sub(r"<think>.*?</think>", "", texto, flags=re.DOTALL)
    texto = re.sub(r"^.*?</think>", "", texto, flags=re.DOTALL)  # </think> órfão
    return texto.strip()

# -------------------------------------------------------------
# 3. FUNÇÕES DE RECUPERAÇÃO, CONTEXTO E GERAÇÃO LOCAL
# -------------------------------------------------------------
def consultar_com_limiar(
    pergunta: str, 
    n_candidatos: int = 5, 
    limiar_similaridade: float = 0.70, 
    filtro_tema: str = None
):
    """Busca trechos na base vetorial e descarta os que ficarem abaixo do limiar."""
    parametros = {
        "query_texts": [f"query: {pergunta}"],
        "n_results": n_candidatos,
        "include": ["documents", "metadatas", "distances"]
    }
    
    if filtro_tema:
        parametros["where"] = {"tema": filtro_tema}
        
    res = collection.query(**parametros)
    
    docs = res["documents"][0]
    metas = res["metadatas"][0]
    distancias = res["distances"][0]
    
    if distancias:
        print(f"\n📏 Melhor similaridade bruta: {(1.0 - min(distancias)) * 100:.1f}% (limiar: {limiar_similaridade * 100:.0f}%)")
    
    resultados_filtrados = []
    for doc, meta, dist in zip(docs, metas, distancias):
        similaridade = 1.0 - dist
        if similaridade >= limiar_similaridade:
            resultados_filtrados.append({
                "texto": doc,
                "metadados": meta,
                "similaridade": round(similaridade, 4),
                "distancia": round(dist, 4)
            })
            
    return resultados_filtrados

def tem_sinal_de_crise(mensagem: str) -> bool:
    """Verifica se a mensagem contém gatilhos de emergência."""
    m = mensagem.lower()
    return any(sinal in m for sinal in SINAIS_DE_CRISE)

def montar_contexto(trechos_encontrados: list) -> str:
    """Formata os trechos aprovados com as respetivas fontes."""
    linhas = []
    for item in trechos_encontrados:
        fonte = item["metadados"].get("fonte", "Base Interna")
        texto_limpo = item["texto"].replace("passage: ", "").strip()
        linhas.append(f"[Fonte: {fonte}] {texto_limpo}")
    return "\n\n".join(linhas)

def responder_usuario(mensagem: str, mostrar_bastidores: bool = False) -> str:
    """Fluxo principal do RAG: Guardião -> Busca Vetorial -> LLM Local (Ollama)."""
    if tem_sinal_de_crise(mensagem):
        return TEXTO_CRISE

    achados = consultar_com_limiar(
        pergunta=mensagem,
        n_candidatos=4,
        limiar_similaridade=LIMIAR_SIMILARIDADE
    )

    if mostrar_bastidores:
        print(f"\n🔎 Trechos recuperados: {len(achados)}")
        for i, a in enumerate(achados, 1):
            origem = a["metadados"].get("arquivo_origem", "desconhecido")
            print(f"   [{i}] Similaridade: {a['similaridade'] * 100:.1f}% | Origem: {origem}")

    if not achados:
        return SEM_CONTEXTO

    contexto = montar_contexto(achados)
    prompt_usuario = f"CONTEXTO:\n{contexto}\n\nMENSAGEM DO USUÁRIO:\n{mensagem}"

    try:
        resposta = ollama.chat(
            model=MODELO_LLM,
            messages=[
                {"role": "system", "content": INSTRUCAO_COLABORADOR},
                {"role": "user", "content": prompt_usuario}
            ],
            think=False,
            keep_alive="5m",
            options={
                "temperature": 0.2,
                "num_ctx": 2048,
                "num_gpu": 99
            }
        )
        texto = limpar_resposta(resposta["message"]["content"])

        if MARCADOR_FORA_ESCOPO in texto:
            return SEM_CONTEXTO
        return texto

    except Exception as e:
        return f"Erro ao comunicar com o Ollama local ({MODELO_LLM}): {e}"

# -------------------------------------------------------------
# 4. BLOCO DE EXECUÇÃO INTERATIVO
# -------------------------------------------------------------
if __name__ == "__main__":
    print(f"Agente de Apoio Local ativo ({MODELO_LLM}). Digite 'sair' para encerrar.\n")
    while True:
        duvida = input("Você: ")
        if duvida.strip().lower() == "sair":
            break
        resposta = responder_usuario(duvida, mostrar_bastidores=True)
        print(f"\nAgente:\n{resposta}\n" + "-" * 50 + "\n")