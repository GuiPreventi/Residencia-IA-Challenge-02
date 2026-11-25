# API externa do Agente 2

Serviço HTTP independente para gerar o gráfico **Evolução Temporal do Score Geral do Grupo (BAT)**. O agente envia o histórico e recebe um PNG em Base64, pronto para o relatório. A API não precisa de SQLite, Ollama ou WeasyPrint.

## Instalar e iniciar a API

Use Python 3.10 ou superior. No Windows, recomenda-se **Python 3.14** para também instalar as bibliotecas nativas de PDF com o instalador incluído.

```powershell
git clone --branch api-externa-agente2 --single-branch https://github.com/GuiPreventi/Residencia-IA-Challenge-02.git
cd Residencia-IA-Challenge-02
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Deixe esse terminal aberto. Em Linux/macOS, use `.venv/bin/python` no lugar de `.\.venv\Scripts\python.exe` nos comandos deste documento.

- Documentação interativa: http://127.0.0.1:8000/docs
- Contrato OpenAPI: http://127.0.0.1:8000/openapi.json
- Disponibilidade: `GET /health`, com resposta `{"status": "ok"}`.

## Gerar um gráfico

`POST /graficos/evolucao-score`, com `Content-Type: application/json`:

```json
{
  "historico": [
    {"data": "2026-08", "score_geral": 2.15},
    {"data": "2026-09", "score_geral": 2.40},
    {"data": "2026-10", "score_geral": 2.75},
    {"data": "Atual", "score_geral": 2.97}
  ]
}
```

Resposta HTTP 200 (`...` representa o restante do Base64):

```json
{"grafico_b64": "iVBORw0KGgo...", "formato": "png", "mensagem": null}
```

Teste no segundo terminal PowerShell para salvar e abrir a imagem:

```powershell
$body = @{
    historico = @(
        @{ data = '2026-10'; score_geral = 2.75 }
        @{ data = 'Atual'; score_geral = 2.97 }
    )
} | ConvertTo-Json -Depth 4
$resultado = Invoke-RestMethod -Method Post `
    -Uri 'http://127.0.0.1:8000/graficos/evolucao-score' `
    -ContentType 'application/json' -Body $body
$arquivo = Join-Path $PWD 'grafico.png'
[IO.File]::WriteAllBytes($arquivo, [Convert]::FromBase64String($resultado.grafico_b64))
Invoke-Item $arquivo
```

Envie o histórico em ordem temporal: a ordem recebida é preservada, inclusive os rótulos `YYYY-MM`, `YYYY-MM-DD` e `Atual`. A escala é de 1 a 5. Scores nulos são ignorados; histórico nulo, ausente ou com menos de duas medições válidas retorna HTTP 200 com `grafico_b64: null` e uma mensagem. Entradas inválidas retornam HTTP 422. São aceitas até 1.000 medições por chamada.

O gráfico mantém as cores, o título e as referências 2,59 e 3,02 do agente original.

## Integrar com o agente

Inclua `cliente_graficos.py` junto do agente e substitua a geração local por:

```python
from cliente_graficos import gerar_grafico_evolucao

grafico_b64 = gerar_grafico_evolucao(dados["grupo"]["historico"])
```

O cliente usa somente a biblioteca padrão, tem timeout de 30 segundos e retorna `str | None`. Em falhas de comunicação ou respostas inválidas, lança `RuntimeError`. O template pode continuar usando `<img src="data:image/png;base64,{{ grafico_b64 }}">`.

A versão de `criaDoc.py` deste repositório já faz essa chamada. Ela ocorre no pipeline Python do agente; o modelo Ollama realiza a análise textual.

Para uma API hospedada em outro servidor, configure no terminal do agente:

```powershell
$env:GRAFICOS_API_URL = 'https://seu-servidor.exemplo'
```

A configuração padrão escuta somente na máquina local. Para publicar o serviço, configure a hospedagem e o acesso externo conforme o ambiente do projeto.

## Gerar o relatório PDF de exemplo

Com a API rodando, no segundo terminal:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-agente.txt
.\.venv\Scripts\python.exe instalar_bibliotecas_pdf.py
.\.venv\Scripts\python.exe populaDataset.py
.\.venv\Scripts\python.exe criaDoc.py --sem-analise
```

`instalar_bibliotecas_pdf.py` é destinado ao **Windows x64 com Python 3.14+**. Obtém Pango e suas dependências do repositório oficial do MSYS2, verifica o SHA256 de cada pacote e instala em `.runtime/`. Não altera o PATH global. `ambiente_pdf.py` configura as DLLs e o cache de fontes automaticamente. As bibliotecas e o ambiente virtual não são versionados; execute a instalação no computador onde rodará o PDF.

Em Linux/macOS, instale as dependências nativas segundo a [documentação do WeasyPrint](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation) em vez de executar o instalador para Windows.

`populaDataset.py` cria um banco SQLite de demonstração com 3 membros e histórico do grupo. Preserva um banco existente e só o substitui com `--recriar`. O banco `burnout_prototype.db` e o PDF são criados na pasta atual, não são versionados e não são necessários para executar apenas a API.

`--sem-analise` gera o PDF sem chamar Ollama e indica no documento que a análise está indisponível. Não são inventadas análises. Para a análise real, instale e inicie Ollama, baixe o modelo e execute sem essa opção:

```powershell
ollama pull hf.co/bartowski/Qwen_Qwen3-8B-GGUF:Q3_K_M
.\.venv\Scripts\python.exe criaDoc.py
```

Opcionalmente, selecione outro modelo e outra equipe:

```powershell
$env:OLLAMA_MODEL = 'seu-modelo-instalado'
.\.venv\Scripts\python.exe criaDoc.py --equipe 1
```

O modelo escolhido deve suportar a saída JSON estruturada usada pelo agente.

## Testes

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Os seis testes verificam PNG válido, integração com histórico do banco, dados inválidos, histórico insuficiente, falhas do cliente e uma chamada HTTP real. O teste HTTP inicia e encerra sua própria API em uma porta temporária; não exige um servidor previamente rodando nem deixa o serviço ativo. Não precisa de Ollama ou das bibliotecas de PDF. O GitHub Actions executa a suíte em Python 3.10 e 3.14.

## Arquivos

| Arquivo | Função |
| --- | --- |
| `api.py` | Endpoint FastAPI e geração do PNG |
| `cliente_graficos.py` | Cliente HTTP para integrar ao agente |
| `criaDoc.py` | Pipeline de análise, chamada à API e geração do PDF |
| `database.py` | Acesso ao SQLite e consolidação do grupo |
| `populaDataset.py` | Dados fictícios para testar o relatório |
| `ambiente_pdf.py` | Configuração das bibliotecas nativas no Windows |
| `instalar_bibliotecas_pdf.py` | Instalação local de Pango e dependências |
| `requirements.txt` | Dependências da API |
| `requirements-agente.txt` | Dependências opcionais do relatório e Ollama |
| `requirements-dev.txt` | Dependências dos testes |
| `tests/` | Testes da API, cliente, banco e HTTP |
