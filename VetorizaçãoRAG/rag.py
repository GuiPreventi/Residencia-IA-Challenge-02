import os
import chromadb
from chromadb.utils import embedding_functions

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# 1. Configurar o mesmo modelo de embeddings
emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="intfloat/multilingual-e5-small",
    device="cpu"  # altere para "cuda" se utilizar GPU
)

# 2. Conectar à base de dados persistente
cliente = chromadb.PersistentClient(path="./BancoDados")

# 3. Carregar a coleção indexada
collection = cliente.get_collection(
    name="documentos_rag",
    embedding_function=emb_fn
)

def consultar_base(pergunta: str, n_resultados: int = 3, filtro_tema: str = None):
    """Executa a busca semântica adicionando o prefixo 'query: '."""
    query_formatada = f"query: {pergunta}"
    
    parametros = {
        "query_texts": [query_formatada],
        "n_results": n_resultados
    }
    
    if filtro_tema:
        parametros["where"] = {"tema": filtro_tema}
        
    return collection.query(**parametros)

if __name__ == "__main__":
    pergunta_teste = "Qual é o tempo de pausa recomendado para evitar cansaço visual?"
    resultado = consultar_base(pergunta_teste, n_resultados=2)
    
    print("\n--- Frases Recuperadas ---")
    for doc, meta in zip(resultado["documents"][0], resultado["metadatas"][0]):
        print(f"\n[Origem: {meta.get('arquivo_origem')} | Frase ID: {meta.get('frase_id')} | Tema: {meta.get('tema')}]")
        print(f"Texto: {doc}")