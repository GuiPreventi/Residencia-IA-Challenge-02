import chromadb
from chromadb.utils import embedding_functions

# Define o modelo para gerar embedding
emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="intfloat/multilingual-e5-small",
    device="cpu" # pode usar "cpu" ou "cuda"
)

# cria cliente do chromadb
cliente = chromadb.PersistentClient(path="./BancoDados")

# Cria a colção (tipo a tabela sql), define qual vai ser o modelo de criação de embedding
collection = cliente.get_or_create_collection(name="documentos_rag", embedding_function=emb_fn)

# Faz a inserção
collection.add(
    documents=[
        "Para configurar o servidor Linux, edite o arquivo do systemd",
        "A receita de poke leva salmão cru, arroz japonês e cream cheese"
    ],
    metadatas=[{"tema": "ti"}, {"tema":"culinaria"}],
    ids=["doc_1", "doc_2"]
)

resultados = collection.query(
    query_texts=["Como configurar um servidor linux?"],
    n_results=1
)

print(resultados["documents"])
