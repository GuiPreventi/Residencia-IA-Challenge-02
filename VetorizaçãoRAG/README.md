# Indexação e Busca Semântica com ChromaDB

Exemplo simples de **indexação e busca semântica** de documentos usando [ChromaDB](https://www.trychroma.com/) e o modelo de embeddings multilíngue [`intfloat/multilingual-e5-small`](https://huggingface.co/intfloat/multilingual-e5-small). É um ponto de partida para construir um pipeline de **RAG** (Retrieval-Augmented Generation).

## Como funciona

1. Define o modelo de embeddings (`multilingual-e5-small`) via `SentenceTransformerEmbeddingFunction`.
2. Cria um cliente persistente do ChromaDB, que salva os dados na pasta `./BancoDados`.
3. Cria (ou recupera) a coleção `documentos_rag`, equivalente a uma tabela em um banco SQL.
4. Insere documentos com seus metadados e IDs. Os embeddings são gerados automaticamente.
5. Faz uma consulta em linguagem natural e retorna o documento mais semanticamente próximo.

## Pré-requisitos

- Python 3.9+
- pip

## Instalação

```bash
git clone https://github.com/seu-usuario/seu-repositorio.git
cd seu-repositorio

python -m venv venv
source venv/bin/activate   # Linux/macOS
venv\Scripts\activate      # Windows

pip install chromadb sentence-transformers
```

## Uso

```bash
python indexacao.py
```

Na primeira execução, o modelo de embeddings será baixado automaticamente do Hugging Face.

### Exemplo de saída

A consulta `"Como configurar um servidor linux?"` retorna o documento mais relevante:

```
[['Para configurar o servidor Linux, edite o arquivo do systemd']]
```

Note que a busca é **semântica**: ela encontra o documento correto pelo significado, mesmo sem coincidência exata de palavras.

## Estrutura do projeto

```
.
├── indexacao.py     # Script de indexação e consulta
├── BancoDados/      # Banco vetorial persistido (gerado na execução)
└── README.md
```

## Configuração

| Parâmetro | Onde | Descrição |
|-----------|------|-----------|
| `model_name` | `SentenceTransformerEmbeddingFunction` | Modelo de embeddings utilizado |
| `device` | `SentenceTransformerEmbeddingFunction` | `"cpu"` ou `"cuda"` (GPU) |
| `path` | `PersistentClient` | Pasta onde o banco é salvo |
| `n_results` | `collection.query` | Quantidade de resultados retornados |

## Observações

- Os IDs (`doc_1`, `doc_2`) devem ser únicos. Rodar o script duas vezes com os mesmos IDs pode gerar avisos ou erros de duplicidade; use `collection.upsert(...)` no lugar de `add` para evitar isso.
- O modelo E5 foi treinado esperando prefixos nos textos (`"query: "` para buscas e `"passage: "` para documentos). Adicioná-los pode melhorar a qualidade da recuperação.
- Adicione `BancoDados/` ao `.gitignore` se não quiser versionar o banco vetorial.

## Próximos passos

- Carregar documentos de arquivos (PDF, TXT, Markdown) com divisão em *chunks*
- Filtrar buscas por metadados (ex.: `where={"tema": "ti"}`)
- Integrar com um LLM para gerar respostas a partir dos trechos recuperados (RAG completo)
