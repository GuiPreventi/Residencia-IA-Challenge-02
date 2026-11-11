# Agente de Apoio ao Bem-Estar no Trabalho (RAG Local)

Agente conversacional **100% local** que responde dúvidas sobre burnout, estresse e bem-estar no trabalho usando **RAG** (Retrieval-Augmented Generation). Os documentos são indexados em um banco vetorial ([ChromaDB](https://www.trychroma.com/)) com embeddings multilíngues ([`intfloat/multilingual-e5-small`](https://huggingface.co/intfloat/multilingual-e5-small)), e as respostas são geradas por um LLM rodando localmente via [Ollama](https://ollama.com/) ([Qwen3 8B](https://huggingface.co/bartowski/Qwen_Qwen3-8B-GGUF), quantização Q3_K_M).

Nenhum dado sai da sua máquina.

## Visão geral

| Script | Função |
|--------|--------|
| `ingestao.py` | Lê os `.txt` da pasta `Documentos/`, extrai metadados, divide o texto em frases e indexa no ChromaDB |
| `rag.py` | Agente interativo: guardião de segurança, busca vetorial com limiar de similaridade e geração da resposta com o LLM local |

### Fluxo de uma pergunta

```
Pergunta do usuário
      │
      ▼
┌──────────────────┐  sinal de crise?  ┌────────────────────────────┐
│ Guardião de      │ ────── sim ─────► │ Mensagem de acolhimento    │
│ segurança        │                   │ com CVV (188) e SAMU (192) │
└──────────────────┘                   └────────────────────────────┘
      │ não
      ▼
┌──────────────────┐  nenhum trecho    ┌────────────────────────────┐
│ Busca vetorial   │  acima do limiar? │ Resposta padrão de         │
│ (ChromaDB + E5)  │ ────── sim ─────► │ "fora do tema"             │
└──────────────────┘                   └────────────────────────────┘
      │ não
      ▼
┌──────────────────┐  responde         ┌────────────────────────────┐
│ LLM local        │  FORA_DO_ESCOPO?  │ Resposta padrão de         │
│ (Ollama + Qwen3) │ ────── sim ─────► │ "fora do tema"             │
└──────────────────┘                   └────────────────────────────┘
      │ não
      ▼
Resposta acolhedora, baseada apenas no contexto, com a fonte citada
```

## Como funciona

### Ingestão (`ingestao.py`)

1. Percorre todos os arquivos `.txt` em `./Documentos`.
2. Separa o **cabeçalho de metadados** (bloco entre `---`) do texto principal.
3. Divide o texto em **frases** (por `.`, `!`, `?` ou quebra de linha), descartando fragmentos com 5 caracteres ou menos.
4. Adiciona o prefixo `passage: ` a cada frase, como o modelo E5 espera para documentos.
5. Grava tudo com `upsert`, guardando os metadados do cabeçalho, o nome do arquivo (`arquivo_origem`) e a posição da frase (`frase_id`).

Cada frase recebe um ID no formato `<nome_do_arquivo>_f<indice>`. Como o `upsert` é usado, rodar a ingestão novamente atualiza as frases existentes sem erro de duplicidade.

### Agente (`rag.py`)

1. **Guardião de segurança:** se a mensagem contém sinais de crise (ex.: ideação suicida ou autolesão), o agente **não consulta o LLM** e responde imediatamente com uma mensagem de acolhimento e os contatos do CVV (188) e SAMU (192).
2. **Busca vetorial:** recupera até 4 trechos candidatos e descarta os que ficam abaixo do `LIMIAR_SIMILARIDADE` (padrão `0.80`). Se nenhum passar, responde que a pergunta foge do tema.
3. **Geração:** os trechos aprovados são enviados ao LLM como `CONTEXTO`, junto com instruções para responder de forma breve (até 5 frases), acolhedora, sem diagnósticos ou prescrições, usando **apenas** o contexto e citando a fonte.
4. **Segunda barreira de escopo:** se o LLM concluir que a pergunta não tem relação com o tema, ele devolve o marcador `FORA_DO_ESCOPO` e o agente exibe a resposta padrão de fora do tema.

## Pré-requisitos

- Python 3.9+
- [Ollama](https://ollama.com/download) instalado e em execução
- GPU com VRAM suficiente para o modelo é recomendada (o modelo Q3_K_M de 8B ocupa em torno de 4 a 5 GB), mas não obrigatória. O embedding roda na CPU para deixar a VRAM livre para o LLM.

## Instalação

```bash
git clone https://github.com/seu-usuario/seu-repositorio.git
cd seu-repositorio

python -m venv venv
source venv/bin/activate   # Linux/macOS
venv\Scripts\activate      # Windows

pip install chromadb sentence-transformers ollama
```

Baixe o modelo no Ollama:

```bash
ollama pull hf.co/bartowski/Qwen_Qwen3-8B-GGUF:Q3_K_M
```

> **Importante:** as variáveis `OLLAMA_FLASH_ATTENTION=1` e `OLLAMA_KV_CACHE_TYPE=q8_0` (que reduzem o uso de VRAM) são definidas dentro do `rag.py`, mas variáveis de ambiente do script **não afetam um servidor Ollama que já está rodando**. Para que tenham efeito, defina-as no ambiente do servidor antes de iniciá-lo (por exemplo, nas variáveis de ambiente do sistema no Windows, ou `OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 ollama serve` no Linux/macOS) e reinicie o Ollama.

## Formato dos documentos

Coloque arquivos `.txt` (UTF-8) em `Documentos/`. Cada arquivo pode começar com um cabeçalho de metadados no formato `chave: valor`, entre linhas `---`:

```text
---
tema: burnout
fonte: Organização Mundial da Saúde
---
O burnout é uma síndrome resultante de estresse crônico no trabalho que não foi administrado com sucesso.
Pausas regulares ao longo do dia ajudam a reduzir o cansaço mental.
```

| Chave | Uso |
|-------|-----|
| `fonte` | Citada na resposta do agente (`[Fonte: ...]`). Se ausente, usa "Base Interna" |
| `tema` | Permite filtrar a busca por tema (parâmetro `filtro_tema`) |
| outras | Qualquer chave adicional vira metadado de cada frase do arquivo |

Arquivos sem cabeçalho funcionam, mas ficam sem `fonte` e `tema`.

## Uso

**1. Indexar os documentos**

```bash
python ingestao.py
```

```
Sucesso: 42 frases indexadas a partir de 3 ficheiros.
```

**2. Iniciar o agente**

Com o Ollama em execução:

```bash
python rag.py
```

```
Agente de Apoio Local ativo (hf.co/bartowski/Qwen_Qwen3-8B-GGUF:Q3_K_M). Digite 'sair' para encerrar.

Você: Estou muito cansado e sobrecarregado no trabalho, o que posso fazer?

📏 Melhor similaridade bruta: 84.2% (limiar: 80%)

🔎 Trechos recuperados: 2
   [1] Similaridade: 84.2% | Origem: burnout
   [2] Similaridade: 81.7% | Origem: pausas

Agente:
Sinto muito que você esteja se sentindo assim...
```

O modo interativo exibe os "bastidores" (similaridade e origem dos trechos), útil para calibrar o limiar.

**3. Usar em seu próprio código**

```python
from rag import responder_usuario

print(responder_usuario("Como evitar o burnout?"))
```

## Estrutura do projeto

```
.
├── Documentos/      # Arquivos .txt a serem indexados (entrada)
├── BancoDados/      # Banco vetorial persistido (gerado pela ingestão)
├── ingestao.py      # Indexação dos documentos
├── rag.py           # Agente: guardião + busca + LLM local
└── README.md
```

## Configuração

Parâmetros principais em `rag.py`:

| Parâmetro | Descrição |
|-----------|-----------|
| `MODELO_LLM` | Modelo do Ollama usado na geração |
| `LIMIAR_SIMILARIDADE` | Similaridade mínima (0 a 1) do trecho para ser considerado relevante. O padrão é `0.80` |
| `SINAIS_DE_CRISE` | Lista de termos que acionam o guardião de segurança |
| `TEXTO_CRISE` | Mensagem exibida em caso de sinal de crise |
| `INSTRUCAO_COLABORADOR` | Prompt de sistema que define o comportamento do agente |
| `SEM_CONTEXTO` | Resposta padrão para perguntas fora do tema |
| `n_candidatos` | Quantidade de trechos buscados (em `responder_usuario`, padrão 4) |
| `num_ctx` | Janela de contexto do LLM (padrão 2048) |
| `device` | `"cpu"` ou `"cuda"` para o modelo de embeddings (deve ser compatível entre ingestão e consulta) |

## Limitações e pontos de atenção

- **O guardião de crise é baseado em palavras-chave.** Ele cobre frases explícitas, mas pode não detectar expressões indiretas ou variações. Revise e amplie a lista `SINAIS_DE_CRISE`. Este projeto **não substitui** atendimento profissional.
- **O agente não faz diagnóstico nem prescreve tratamento.** Conteúdo de saúde mental deve ser revisado por profissionais da área antes de ser usado em produção.
- **O "percentual de similaridade" não é cosseno exato.** O ChromaDB usa distância L2 por padrão, e o código calcula `1 - distância`. Por isso o limiar precisa ser calibrado com os logs dos bastidores. Para usar similaridade de cosseno, crie a coleção com `metadata={"hnsw:space": "cosine"}` (exige recriar o banco).
- **Granularidade por frase:** frases isoladas podem perder contexto. Considere agrupar frases vizinhas ou recuperar também a anterior e a seguinte via `frase_id`.
- **Frases removidas continuam no banco:** o `upsert` não apaga. Se encurtar ou remover um arquivo, apague a pasta `BancoDados/` e rode a ingestão novamente.
- **Ordem de execução:** o `rag.py` usa `get_collection`, que falha se a coleção não existir. Rode `ingestao.py` antes.
- **Quantização agressiva:** o Q3_K_M economiza VRAM, mas pode reduzir a qualidade das respostas em relação a quantizações maiores (Q4 ou Q5).

## Próximos passos

- Suporte a outros formatos de documento (PDF, Markdown, DOCX)
- Chunking por parágrafo ou janela deslizante de frases
- Memória de conversa (histórico de mensagens)
- Interface web (Streamlit, Gradio) ou API
- Avaliação sistemática da qualidade das respostas e do limiar

## Licença

Distribuído sob a licença MIT. Veja o arquivo `LICENSE` para mais detalhes.
