# Niksen BAT — Monitoramento de Bem-Estar no Trabalho com Agentes Inteligentes

Projeto acadêmico (**Challenge 2 — Agente Inteligente, PUC-Campinas**) para coleta anônima e geração de relatórios exploratórios sobre sinais de esgotamento no trabalho com base no questionário **BAT-12** (*Burnout Assessment Tool*).

> **Aviso experimental:** Este software tem caráter exclusivamente acadêmico e exploratório. Os resultados gerados **não constituem diagnóstico clínico** e não substituem a avaliação de um profissional de saúde qualificado.

---

## Arquitetura do Projeto

O sistema é composto por dois agentes de IA local (executados via **Ollama**) integrados por um banco **SQLite**, uma base de conhecimento vetorial (**ChromaDB / RAG**) e um orquestrador em **LangGraph**:

1. **Agente 1 — Coletor BAT-12 (`agente1.py`):** conduz uma conversa livre e anônima no terminal cobrindo os 12 itens do BAT-12 (Exaustão, Distanciamento Mental, Prejuízo Cognitivo e Prejuízo Emocional), aplica travas de validação e protocolo de risco, e salva os scores e registros no SQLite (`burnout_prototype.db`).
2. **Base de Conhecimento / RAG (`ingestao.py` e `rag.py`):** indexa os documentos de referência em `./Documentos` (pilares do BAT, metodologia, playbook de intervenções e NR-01) no ChromaDB (`./BancoDados`) usando o modelo de embeddings `intfloat/multilingual-e5-small`.
3. **Agente 2 — Analista e Gerador de Relatório (`criaDoc.py`):** consulta os dados consolidados da equipe no SQLite, recupera o contexto técnico via RAG, aciona opcionalmente a API externa de gráficos (`cliente_graficos.py`), gera a análise estruturada com Pydantic e exporta o relatório completo em PDF (`Jinja2` + `WeasyPrint`).
4. **Orquestrador (`comunicacao_agentes.py`):** executa o fluxo ponta a ponta (`Agente 1 -> SQLite -> Agente 2`) usando **LangGraph**.

---

## Pré-requisitos

- **Python 3.10 ou superior**
- **Ollama** instalado ([ollama.com](https://ollama.com/))
- **Modelo LLM baixado no Ollama:**
  ```bash
  ollama pull hf.co/bartowski/Qwen_Qwen3-8B-GGUF:Q3_K_M
  ```
- **Bibliotecas nativas do sistema para o WeasyPrint** (necessárias para gerar PDF):
  - **Linux (Ubuntu/Debian):**
    ```bash
    sudo apt-get update
    sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libgdk-pixbuf-2.0-0 libffi-dev shared-mime-info
    ```
  - **Windows:** instale o GTK3/Pango seguindo a [documentação oficial do WeasyPrint](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows).
- *(Opcional)* **API externa de gráficos** disponível em `http://127.0.0.1:8000` (endpoint `POST /graficos/evolucao-score`). Se a API não estiver no ar, o Agente 2 trata a falha automaticamente e gera o PDF normalmente sem o gráfico de evolução.

---

## Instalação

1. **Crie e ative um ambiente virtual Python:**
   - **Linux / macOS:**
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```
   - **Windows (PowerShell):**
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     ```

2. **Instale as dependências Python:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Certifique-se de que o servidor Ollama está rodando e o modelo foi baixado:**
   ```bash
   ollama serve
   ```
   Em outro terminal:
   ```bash
   ollama pull hf.co/bartowski/Qwen_Qwen3-8B-GGUF:Q3_K_M
   ```

---

## Preparação Inicial (RAG e Banco de Dados)

### 1. Indexar os documentos do RAG
Execute a ingestão para popular a base vetorial em `./BancoDados` a partir dos arquivos em `./Documentos`:
```bash
python ingestao.py
```
> Na primeira execução, o modelo de embeddings `intfloat/multilingual-e5-small` será baixado automaticamente (executado em CPU para preservar a VRAM da GPU para o LLM).

Para testar a recuperação semântica isoladamente (sem chamar o LLM):
```bash
python rag.py
```

### 2. Inicializar o banco SQLite
O banco `burnout_prototype.db` é criado automaticamente ao rodar os scripts, mas você também pode inicializá-lo manualmente:
```bash
python database.py
```

---

## Como Executar

### Opção 1: Fluxo Completo com LangGraph (Recomendado)
Executa o **Agente 1** (conversa no terminal) e, ao finalizar a coleta, aciona automaticamente o **Agente 2** para gerar o PDF da equipe:
```bash
python comunicacao_agentes.py
```

Argumentos opcionais:
```bash
# Pula a coleta do Agente 1 e gera direto o PDF da equipe com ID 1
python comunicacao_agentes.py --equipe 1

# Define um caminho customizado para o banco SQLite e a pasta de saída dos PDFs
python comunicacao_agentes.py --banco ./burnout_prototype.db --saida ./relatorios
```

### Opção 2: Executar os Agentes Separadamente

- **Somente Agente 1 (Coleta BAT-12):**
  ```bash
  python agente1.py
  ```

- **Somente Agente 2 (Geração do Relatório PDF da Equipe):**
  ```bash
  # Abre menu interativo no terminal para escolher a equipe
  python criaDoc.py

  # Ou informa diretamente o ID da equipe no SQLite
  python criaDoc.py --equipe 1
  ```
  O PDF é salvo como `relatorio_<Nome_da_Equipe>_<YYYY-MM-DD>.pdf`.

---

## Scripts Auxiliares e Testes

- **Popular o banco com dados fictícios** *(útil para testar o Agente 2 rapidamente; recria `burnout_prototype.db` do zero com 1 equipe, histórico e 3 membros)*:
  ```bash
  python populaDataset.py
  ```
- **Limpar e recriar o banco SQLite vazio:**
  ```bash
  python LimpaDB.py
  ```
- **Executar o teste de integração ponta a ponta** *(simula uma conversa completa do Agente 1 na equipe dedicada `equipe_teste_integracao`, valida o SQLite e gera o PDF pelo Agente 2 sem apagar dados existentes)*:
  ```bash
  python teste_integracao.py
  ```

---

## Variáveis de Ambiente (Opcionais)

| Variável | Padrão | Descrição |
| :--- | :--- | :--- |
| `LOCAL_MODEL` | `hf.co/bartowski/Qwen_Qwen3-8B-GGUF:Q3_K_M` | Modelo Ollama utilizado pelo Agente 1 |
| `OLLAMA_URL` | `http://localhost:11434` | Endereço do servidor Ollama (Agente 1) |
| `CONTEXTO_LOCAL` | `8192` | Tamanho da janela de contexto (`num_ctx`) do Agente 1 |
| `PERIODO` | `trimestre` | Formato do período salvo nas avaliações: `trimestre` (ex.: `2026-T4`) ou `mes` (ex.: `2026-11`) |
| `GRAFICOS_API_URL` | `http://127.0.0.1:8000` | URL base da API externa de geração de gráficos |
| `PASTA_DADOS` | `dados` | Pasta de saída para logs quando `MODO_AUDITORIA=True` no Agente 1 |

---

## Estrutura de Arquivos

| Arquivo / Pasta | Descrição |
| :--- | :--- |
| `comunicacao_agentes.py` | Orquestrador LangGraph (`Agente 1 -> SQLite -> Agente 2`) |
| `agente1.py` | Agente 1 — entrevista conversacional BAT-12, validações e persistência |
| `criaDoc.py` | Agente 2 — consulta RAG, chamada ao LLM com Tool Calling e geração do PDF da equipe |
| `database.py` | Schema e operações de leitura/escrita no SQLite (`burnout_prototype.db`) |
| `ingestao.py` | Indexação dos documentos de `./Documentos` no ChromaDB (`./BancoDados`) |
| `rag.py` | Módulo de busca semântica com limiar de similaridade e filtro por tema |
| `cliente_graficos.py` | Cliente HTTP para a API externa de gráficos de evolução temporal |
| `relatorio_individual.py` | Template e gerador de PDF individual experimental |
| `populaDataset.py` | Popula o SQLite com dados sintéticos para testes |
| `LimpaDB.py` | Remove o banco SQLite atual e recria as tabelas vazias |
| `teste_integracao.py` | Teste automatizado ponta a ponta (`Agente 1 -> SQLite -> Agente 2`) |
| `Documentos/` | Base documental em Markdown (BAT, intervenções e NR-01) usada pelo RAG |
| `BancoDados/` | Armazenamento persistente do ChromaDB gerado por `ingestao.py` |
| `requirements.txt` | Dependências Python do projeto |
