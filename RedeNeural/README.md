# Previsão de Burnout com Rede Neural (PyTorch)

Este projeto implementa uma **Rede Neural Artificial para Regressão** utilizando **PyTorch** para estimar a taxa de esgotamento profissional (*Burn Rate*) de colaboradores com base em 6 indicadores de rotina e ambiente de trabalho.

O foco do projeto é consolidar os fundamentos de aprendizado profundo aplicado a dados tabulares — desde o pré-processamento estatístico e fatiamento em *mini-batches* até o treinamento com *backpropagation*, avaliação de métricas de regressão e visualização dos pesos aprendidos.

---

## Estrutura dos Dados

O modelo utiliza o conjunto de dados `enriched_employee_dataset_limpo.csv` (21.626 registros), filtrando **6 variáveis de entrada (*features*)** para prever **1 variável alvo (*target*)**:

### Variáveis de Entrada ($X$)
| Variável | Descrição | Escala / Unidade |
| :--- | :--- | :--- |
| `Work Hours per Week` | Carga horária semanal de trabalho | Horas ($35$ a $59$) |
| `Sleep Hours` | Média de horas de sono por noite | Horas ($3.4$ a $9.1$) |
| `Work-Life Balance Score` | Percepção de equilíbrio entre vida pessoal e trabalho | Nota ($1$ a $5$) |
| `Manager Support Score` | Nível de suporte recebido pela liderança direta | Nota ($1$ a $5$) |
| `Deadline Pressure Score` | Nível de pressão por prazos e entregas | Nota ($1$ a $5$) |
| `Recognition Frequency` | Frequência de reconhecimento no ambiente de trabalho | Escala ($0$ a $5$) |

### Variável Alvo ($y$)
* **`Burn Rate`**: Índice contínuo que mede o nível de esgotamento profissional no intervalo de **$0.0$** (ausência de burnout) a **$1.0$** (esgotamento severo).

---

## Como o Projeto Funciona

O pipeline do script `RedeNeural.py` está dividido em 5 etapas:

1. **Divisão e Padronização dos Dados:**
   * Os dados são divididos em **70% Treino** (15.138 amostras), **15% Validação** (3.244 amostras) e **15% Teste** (3.244 amostras).
   * Aplica-se o `StandardScaler` ($z = \frac{x - \mu}{\sigma}$) ajustado exclusivamente nos dados de treino para colocar todas as variáveis na mesma escala (média $0$ e desvio padrão $1$), evitando vazamento de dados (*data leakage*).
   * Os tensores (`torch.float32`) são empacotados com `TensorDataset` e divididos em pacotes de 64 amostras (`batch_size=64`) via `DataLoader`.

2. **Arquitetura da Rede (`BurnoutNet`):**
   * **Camada de Entrada:** 6 neurônios (correspondentes às 6 *features*).
   * **1ª Camada Oculta:** 16 neurônios totalmente conectados (`nn.Linear`) + ativação **ReLU**.
   * **2ª Camada Oculta:** 8 neurônios totalmente conectados (`nn.Linear`) + ativação **ReLU** (estrutura em funil com potências de 2).
   * **Camada de Saída:** 1 neurônio com saída **Linear** para regressão contínua.
   * **Total de parâmetros treináveis:** 257 (pesos e vieses).

3. **Treinamento e Validação:**
   * **Função de Perda (*Loss*):** Erro Quadrático Médio (`nn.MSELoss`).
   * **Otimizador:** `Adam` com taxa de aprendizado inicial $\alpha = 0.001$.
   * **Ciclo:** 30 épocas completas, alternando entre atualização de pesos no treino (`modelo.train()`) e monitoramento sem gradientes na validação (`modelo.eval()` com `torch.no_grad()`).

4. **Avaliação Desacoplada (Conjunto de Teste):**
   * Ao final do treino, o modelo é avaliado nos 3.244 registros inéditos de teste, gerando os seguintes indicadores típicos:
     * **MSE (Erro Quadrático Médio):** $\approx 0.0143$
     * **RMSE (Raiz do Erro Quadrático Médio):** $\approx 0.1197$
     * **MAE (Erro Médio Absoluto):** $\approx 0.0965$ (erro médio inferior a $10\%$ na escala de $0$ a $1$)
     * **$R^2$ (Coeficiente de Determinação):** $\approx 0.625$ ($62,5\%$ da variabilidade explicada pelas 6 variáveis)

5. **Diagnóstico Visual e Visualização da Arquitetura:**
   * **`diagnostico_burnout.png`**: Gera 3 gráficos lado a lado (Curva de Aprendizado Treino vs. Validação, Dispersão Real vs. Previsto e Análise de Resíduos).
   * **`arquitetura_rede_neural.png`**: Desenha o grafo da rede treinada colorindo os neurônios pela soma da magnitude dos pesos e destacando as conexões positivas (azul) e negativas (vermelho).

---

## Pré-requisitos e Instalação

O projeto é leve e **roda integralmente em CPU** (não exige placa de vídeo/GPU dedicada). É necessário apenas ter o **Python 3.8+** instalado.

### 1. Clonar o repositório (ou acessar a pasta do projeto)
```bash
git clone <url-do-seu-repositorio>
cd RedeNeural
```

### 2. Criar e ativar um ambiente virtual (`.venv`)

**No Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**No Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Instalar as dependências
Com o ambiente virtual ativado, instale as bibliotecas necessárias:
```bash
pip install torch pandas numpy scikit-learn matplotlib
```

---

## Como Executar

Certifique-se de que o arquivo `enriched_employee_dataset_limpo.csv` está no mesmo diretório que o script `RedeNeural.py` e execute:

```bash
python3 RedeNeural.py
```

### Saídas geradas após a execução
1. **No terminal:** Dimensões dos tensores, resumo da arquitetura, evolução da *Loss* (treino e validação) a cada 5 épocas e as métricas finais (`MSE`, `RMSE`, `MAE` e $R^2$) no conjunto de teste.
2. **Imagens salvas na pasta do projeto:**
   * `diagnostico_burnout.png`
   * `arquitetura_rede_neural.png`

Para abrir as imagens geradas diretamente pelo terminal no Linux:
```bash
xdg-open diagnostico_burnout.png
xdg-open arquitetura_rede_neural.png
```

---

## Estrutura de Arquivos

```text
RedeNeural/
├── enriched_employee_dataset_limpo.csv   # Dataset utilizado no treinamento e avaliação
├── RedeNeural.py                         # Código completo (dados, modelo, treino e gráficos)
├── diagnostico_burnout.png               # Gráficos de curva de aprendizado, dispersão e resíduos
├── arquitetura_rede_neural.png           # Representação visual dos neurônios e pesos treinados
└── README.md                             # Documentação do projeto
```