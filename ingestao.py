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

# 2. Conectar ao ChromaDB persistente com métrica de COSSENO
cliente = chromadb.PersistentClient(path="./BancoDados")
collection = cliente.get_or_create_collection(
    name="documentos_rag",
    embedding_function=emb_fn,
    metadata={"hnsw:space": "cosine"}  # Garante compatibilidade com (1.0 - dist)
)


def parse_arquivo(conteudo: str) -> tuple[dict, str]:
    """Separa o cabeçalho frontmatter (---) do texto principal."""
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


def dividir_em_chunks(texto: str, tamanho_max: int = 500, overlap: int = 100) -> list[str]:
    """
    Agrupa parágrafos em blocos de até `tamanho_max` caracteres com sobreposição (overlap),
    preservando o contexto técnico para o Agente 2.
    """
    paragrafos = [p.strip() for p in re.split(r"\n\s*\n+", texto) if len(p.strip()) > 10]
    chunks = []
    bloco_atual = ""

    for paragrafo in paragrafos:
        # Se um único parágrafo for maior que tamanho_max, quebra com janela deslizante
        if len(paragrafo) > tamanho_max:
            if bloco_atual:
                chunks.append(bloco_atual.strip())
                bloco_atual = ""
            inicio = 0
            while inicio < len(paragrafo):
                fim = inicio + tamanho_max
                chunks.append(paragrafo[inicio:fim].strip())
                inicio += tamanho_max - overlap
            continue

        # Se couber no bloco atual, concatena
        if len(bloco_atual) + len(paragrafo) + 2 <= tamanho_max:
            bloco_atual = f"{bloco_atual}\n\n{paragrafo}".strip() if bloco_atual else paragrafo
        else:
            chunks.append(bloco_atual.strip())
            # Mantém um pedaço do final do bloco anterior como overlap
            trecho_overlap = bloco_atual[-overlap:].strip() if overlap > 0 else ""
            bloco_atual = f"{trecho_overlap}\n\n{paragrafo}".strip() if trecho_overlap else paragrafo

    if bloco_atual:
        chunks.append(bloco_atual.strip())

    return chunks


def executar_ingestao(pasta_docs: str = "./Documentos") -> None:
    # 3. Ler todos os arquivos .txt e .md da pasta ./Documentos
    arquivos = (
        glob.glob(os.path.join(pasta_docs, "*.txt"))
        + glob.glob(os.path.join(pasta_docs, "*.md"))
    )

    if not arquivos:
        print(f"Nenhum arquivo .txt ou .md encontrado na pasta {pasta_docs}.")
        return

    docs_para_inserir = []
    metas_para_inserir = []
    ids_para_inserir = []

    for caminho_arq in arquivos:
        nome_base = os.path.splitext(os.path.basename(caminho_arq))[0]

        with open(caminho_arq, "r", encoding="utf-8") as f:
            conteudo = f.read()

        meta, texto = parse_arquivo(conteudo)
        meta["arquivo_origem"] = nome_base

        chunks = dividir_em_chunks(texto, tamanho_max=500, overlap=100)

        for idx, chunk in enumerate(chunks):
            docs_para_inserir.append(f"passage: {chunk}")

            meta_chunk = meta.copy()
            meta_chunk["chunk_id"] = idx
            metas_para_inserir.append(meta_chunk)

            ids_para_inserir.append(f"{nome_base}_c{idx}")

    # 4. Inserir em lote no banco vetorial
    if docs_para_inserir:
        collection.upsert(
            documents=docs_para_inserir,
            metadatas=metas_para_inserir,
            ids=ids_para_inserir
        )
        print(f"Sucesso: {len(docs_para_inserir)} chunks indexados a partir de {len(arquivos)} arquivos.")


if __name__ == "__main__":
    executar_ingestao()
