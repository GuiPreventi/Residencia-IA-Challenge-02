import os
import chromadb
from chromadb.utils import embedding_functions

# Desativa alertas de symlinks no Windows
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# -------------------------------------------------------------
# 1. CONFIGURAÇÃO DE EMBEDDINGS E CHROMADB
# -------------------------------------------------------------
# Mantém o e5-small na CPU para deixar 100% da VRAM livre para o Qwen 3 8B
emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="intfloat/multilingual-e5-small",
    device="cpu"
)

cliente = chromadb.PersistentClient(path="./BancoDados")
collection = cliente.get_or_create_collection(
    name="documentos_rag",
    embedding_function=emb_fn,
    metadata={"hnsw:space": "cosine"}
)

# Limiar recalibrado para queries técnicas mais longas (distância de cosseno)
LIMIAR_PADRAO = 0.65


# -------------------------------------------------------------
# 2. FUNÇÕES DE RECUPERAÇÃO E FORMATAÇÃO (RETRIEVER)
# -------------------------------------------------------------
def consultar_com_limiar(
    pergunta: str,
    n_candidatos: int = 5,
    limiar_similaridade: float = LIMIAR_PADRAO,
    filtro_tema: str | None = None,
) -> list[dict]:
    """Busca trechos na base vetorial e descarta os que ficarem abaixo do limiar."""
    parametros = {
        "query_texts": [f"query: {pergunta}"],
        "n_results": n_candidatos,
        "include": ["documents", "metadatas", "distances"],
    }

    if filtro_tema:
        parametros["where"] = {"tema": filtro_tema}

    res = collection.query(**parametros)

    docs = res["documents"][0] if res["documents"] else []
    metas = res["metadatas"][0] if res["metadatas"] else []
    distancias = res["distances"][0] if res["distances"] else []

    resultados_filtrados = []
    for doc, meta, dist in zip(docs, metas, distancias):
        similaridade = 1.0 - dist
        if similaridade >= limiar_similaridade:
            resultados_filtrados.append({
                "texto": doc,
                "metadados": meta,
                "similaridade": round(similaridade, 4),
                "distancia": round(dist, 4),
            })

    return resultados_filtrados


def montar_contexto_e_fontes(trechos_encontrados: list[dict]) -> tuple[str, list[str]]:
    """Formata os trechos aprovados para o prompt e retorna também a lista única de fontes."""
    linhas = []
    fontes_unicas = []

    for item in trechos_encontrados:
        fonte = item["metadados"].get("fonte") or item["metadados"].get("arquivo_origem", "Base Interna")
        texto_limpo = item["texto"].replace("passage: ", "").strip()

        linhas.append(f"[Fonte: {fonte}]\n{texto_limpo}")
        if fonte not in fontes_unicas:
            fontes_unicas.append(fonte)

    return "\n\n---\n\n".join(linhas), fontes_unicas


def buscar_contexto_rag(
    pergunta: str,
    n_candidatos: int = 4,
    limiar_similaridade: float = LIMIAR_PADRAO,
    filtro_tema: str | None = None,
    mostrar_bastidores: bool = False,
) -> tuple[str, list[str]]:
    """
    Função principal para ser importada pelo Agente 2.
    Retorna: (texto_contexto, lista_de_fontes)
    """
    achados = consultar_com_limiar(
        pergunta=pergunta,
        n_candidatos=n_candidatos,
        limiar_similaridade=limiar_similaridade,
        filtro_tema=filtro_tema,
    )

    if mostrar_bastidores:
        print(f"\n🔎 [RAG] Trechos recuperados: {len(achados)} (limiar: {limiar_similaridade * 100:.0f}%)")
        for i, a in enumerate(achados, 1):
            origem = a["metadados"].get("arquivo_origem", "desconhecido")
            print(f"   [{i}] Similaridade: {a['similaridade'] * 100:.1f}% | Origem: {origem}")

    if not achados:
        return "Nenhum material de referência específico encontrado na base de conhecimento.", []

    return montar_contexto_e_fontes(achados)


# -------------------------------------------------------------
# 3. TESTE RÁPIDO ISOLADO (SEM CHAMAR LLM)
# -------------------------------------------------------------
if __name__ == "__main__":
    consulta_teste = "Como interpretar score elevado no pilar Exaustão do BAT e intervenções para excesso de reuniões?"
    contexto, fontes = buscar_contexto_rag(consulta_teste, mostrar_bastidores=True)
    print("\n=== CONTEXTO RETORNADO ===")
    print(contexto)
    print("\n=== FONTES ===")
    print(fontes)
