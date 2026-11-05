import os
import glob
import re
import chromadb
from chromadb.utils import embedding_functions

# Desativa alertas de links simbólicos no Windows
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# 1. Configurar modelo de embeddings
emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="intfloat/multilingual-e5-small",
    device="cpu"  # altere para "cuda" se tiver configurado PyTorch com GPU
)

# 2. Conectar ao ChromaDB persistente
cliente = chromadb.PersistentClient(path="./BancoDados")
collection = cliente.get_or_create_collection(
    name="documentos_rag",
    embedding_function=emb_fn
)

def parse_arquivo(conteudo: str):
    """Separa o cabeçalho do texto principal sem quebrar em títulos com dois pontos (:)."""
    padrao = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
    match = re.search(padrao, conteudo, re.DOTALL)
    
    metadados = {}
    if match:
        meta_raw, texto = match.groups()
        for linha in meta_raw.strip().splitlines():
            linha = linha.strip()
            if ":" in linha:
                chave, valor = linha.split(":", 1)
                metadados[chave.strip()] = valor.strip()
    else:
        texto = conteudo

    return metadados, texto.strip()

def dividir_em_frases(texto: str):
    """Divide o texto em frases individuais pela pontuação (. ! ?) ou quebras de linha."""
    frases = re.split(r'(?<=[.!?])\s+|\n+', texto)
    return [f.strip() for f in frases if len(f.strip()) > 5]

# 3. Ler todos os ficheiros da pasta ./Documentos
pasta_docs = "./Documentos"
arquivos = glob.glob(os.path.join(pasta_docs, "*.txt"))

docs_para_inserir = []
metas_para_inserir = []
ids_para_inserir = []

for caminho_arq in arquivos:
    nome_base = os.path.splitext(os.path.basename(caminho_arq))[0]
    
    with open(caminho_arq, "r", encoding="utf-8") as f:
        conteudo = f.read()

    meta, texto = parse_arquivo(conteudo)
    meta["arquivo_origem"] = nome_base

    frases = dividir_em_frases(texto)
    
    for idx, frase in enumerate(frases):
        docs_para_inserir.append(f"passage: {frase}")
        
        meta_frase = meta.copy()
        meta_frase["frase_id"] = idx
        metas_para_inserir.append(meta_frase)
        
        ids_para_inserir.append(f"{nome_base}_f{idx}")

# 4. Inserir em lote no banco vetorial
if docs_para_inserir:
    collection.upsert(
        documents=docs_para_inserir,
        metadatas=metas_para_inserir,
        ids=ids_para_inserir
    )
    print(f"Sucesso: {len(docs_para_inserir)} frases indexadas a partir de {len(arquivos)} ficheiros.")
else:
    print("Nenhum ficheiro encontrado na pasta ./Documentos.")