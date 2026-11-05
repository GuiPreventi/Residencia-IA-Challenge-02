# Vetorização RAG com ChromaDB

Pipeline de **busca semântica** em documentos de texto, usando [ChromaDB](https://www.trychroma.com/) como banco vetorial e o modelo multilíngue [`intfloat/multilingual-e5-small`](https://huggingface.co/intfloat/multilingual-e5-small) para gerar embeddings. É a etapa de *retrieval* de um sistema **RAG** (Retrieval-Augmented Generation): ele encontra os trechos mais relevantes para uma pergunta, que depois podem ser entregues a um LLM.

## Visão geral

O projeto tem dois scripts com responsabilidades separadas:

| Script | Função |
|--------|--------|
| `ingestao.py` | Lê os arquivos `.txt` da pasta `Documentos/`, extrai metadados, divide o texto em frases e indexa tudo no ChromaDB |
| `rag.py` | Conecta ao banco já indexado e executa buscas semânticas, com filtro opcional por tema |

```
Documentos/*.txt ──► ingestao.py ──► BancoDados/ (ChromaDB) ──► rag.py ──► frases mais relevantes
```

## Como funciona

### Ingestão (`ingestao.py`)

1. Percorre todos os arquivos `.txt` em `./Documentos`.
2. Separa o **cabeçalho de metadados** (bloco entre `---`) do texto principal.
3. Divide o texto em **frases** (por `.`, `!`, `?` ou quebra de linha), descartando fragmentos com 5 caracteres ou menos.
4. Adiciona o prefixo `passage: ` a cada frase, como o modelo E5 espera para documentos.
5. Grava tudo com `upsert`, guardando junto os metadados do cabeçalho, o nome do arquivo de origem (`arquivo_origem`) e a posição da frase (`frase_id`).

Cada frase recebe um ID no formato `<nome_do_arquivo>_f<indice>`. Como o `upsert` é usado, rodar a ingestão novamente atualiza as frases existentes em vez de gerar erro de duplicidade.

### Consulta (`rag.py`)

1. Carrega a coleção `documentos_rag` com o **mesmo modelo de embeddings** da ingestão (obrigatório, senão os vetores não são comparáveis).
2. Adiciona o prefixo `query: ` à pergunta, como o modelo E5 espera para buscas.
3. Retorna as `n` frases mais próximas semanticamente, opcionalmente filtrando pelo metadado `tema`.

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

Na primeira execução, o modelo de embeddings é baixado automaticamente do Hugging Face.

## Formato dos documentos

Coloque arquivos `.txt` (UTF-8) na pasta `Documentos/`. Cada arquivo pode começar com um cabeçalho de metadados no formato `chave: valor`, entre linhas `---`:

```text
---
tema: saude
titulo: Ergonomia no trabalho
---
A regra 20-20-20 recomenda olhar para algo a 20 pés de distância por 20 segundos a cada 20 minutos.
Fazer pausas regulares ajuda a reduzir o cansaço visual.
```

- Todas as chaves do cabeçalho viram metadados de cada frase do arquivo.
- O metadado `tema` é o usado pelo filtro do `rag.py`.
- Arquivos sem cabeçalho também funcionam, mas ficam sem `tema` e não aparecem em buscas filtradas.

## Uso

**1. Indexar os documentos**

```bash
python ingestao.py
```

Saída esperada:

```
Sucesso: 42 frases indexadas a partir de 3 ficheiros.
```

**2. Consultar a base**

```bash
python rag.py
```

O script executa uma pergunta de teste e mostra as frases recuperadas:

```
--- Frases Recuperadas ---

[Origem: ergonomia | Frase ID: 0 | Tema: saude]
Texto: passage: A regra 20-20-20 recomenda olhar para algo a 20 pés de distância...
```

**3. Usar em seu próprio código**

```python
from rag import consultar_base

# Busca simples
resultado = consultar_base("Como evitar cansaço visual?", n_resultados=3)

# Busca filtrada por tema
resultado = consultar_base("Como evitar cansaço visual?", filtro_tema="saude")

for doc, meta in zip(resultado["documents"][0], resultado["metadatas"][0]):
    print(meta["arquivo_origem"], doc)
```

## Estrutura do projeto

```
.
├── Documentos/      # Arquivos .txt a serem indexados (entrada)
├── BancoDados/      # Banco vetorial persistido (gerado pela ingestão)
├── ingestao.py      # Indexação dos documentos
├── rag.py           # Consulta semântica
└── README.md
```

## Configuração

| Parâmetro | Onde | Descrição |
|-----------|------|-----------|
| `model_name` | `ingestao.py` e `rag.py` | Modelo de embeddings (deve ser igual nos dois) |
| `device` | `ingestao.py` e `rag.py` | `"cpu"` ou `"cuda"` (GPU com PyTorch configurado) |
| `path` | `PersistentClient` | Pasta onde o banco é salvo |
| `pasta_docs` | `ingestao.py` | Pasta de origem dos documentos |
| `n_resultados` | `consultar_base` | Quantidade de frases retornadas (padrão: 3) |
| `filtro_tema` | `consultar_base` | Restringe a busca a um valor do metadado `tema` |

## Limitações e pontos de atenção

- **Granularidade por frase:** frases isoladas podem perder contexto (pronomes, referências a frases anteriores). Para respostas mais completas, considere agrupar frases vizinhas em *chunks* ou recuperar também a frase anterior e a seguinte usando `frase_id`.
- **Frases removidas continuam no banco:** o `upsert` atualiza e insere, mas não apaga. Se você encurtar um arquivo ou removê-lo, as frases antigas permanecem indexadas. Para reindexar do zero, apague a pasta `BancoDados/` e rode a ingestão de novo.
- **Ordem de execução:** o `rag.py` usa `get_collection`, que falha se a coleção não existir. Rode `ingestao.py` antes.
- **Prefixo no texto:** o prefixo `passage: ` é gravado junto com a frase, então aparece no texto recuperado. Se quiser exibir sem ele, remova-o ao imprimir (`doc.removeprefix("passage: ")`).
- **Sem geração de resposta:** o projeto cobre apenas a recuperação. A integração com um LLM é o próximo passo.

## Próximos passos

- Integrar um LLM para gerar respostas a partir das frases recuperadas (RAG completo)
- Suportar outros formatos (PDF, Markdown, DOCX)
- Chunking por parágrafo ou janela deslizante de frases
- Interface de linha de comando ou API para as consultas

## Licença

Distribuído sob a licença MIT. Veja o arquivo `LICENSE` para mais detalhes.
