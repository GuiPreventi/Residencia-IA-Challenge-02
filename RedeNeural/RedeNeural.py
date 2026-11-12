import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from matplotlib.lines import Line2D
import matplotlib.patches as mpatches

# 1. Carregar o dataset original
df = pd.read_csv('enriched_employee_dataset_limpo.csv')

# 2. Selecionar as features (X) e o target (y)
features = [
    'Work Hours per Week',
    'Sleep Hours',
    'Work-Life Balance Score',
    'Manager Support Score',
    'Deadline Pressure Score',
    'Recognition Frequency',
]
target = 'Burn Rate'

# .values extrai os dados como arrays NumPy
X = df[features].values
y = df[target].values

# 3. Dividir em Treino (70%), Validação (15%) e Teste (15%)
# Primeiro separa 70% treino e 30% temporário
X_train, X_temp, y_train, y_temp = train_test_split(
    X, y, test_size=0.30, random_state=42
)

# Depois divide os 30% temporários ao meio (15% validação e 15% teste)
X_val, X_test, y_val, y_test = train_test_split(
    X_temp, y_temp, test_size=0.50, random_state=42
)

# 4. Padronização das features (StandardScaler)
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(
    X_train
)  # Calcula média/desvio e transforma
X_val_scaled = scaler.transform(X_val)  # Apenas aplica a regra do treino
X_test_scaled = scaler.transform(X_test)  # Apenas aplica a regra do treino

# 5. Conversão para Tensores do PyTorch
X_train_tensor = torch.tensor(X_train_scaled, dtype=torch.float32)
y_train_tensor = torch.tensor(y_train, dtype=torch.float32).unsqueeze(1)

X_val_tensor = torch.tensor(X_val_scaled, dtype=torch.float32)
y_val_tensor = torch.tensor(y_val, dtype=torch.float32).unsqueeze(1)

X_test_tensor = torch.tensor(X_test_scaled, dtype=torch.float32)
y_test_tensor = torch.tensor(y_test, dtype=torch.float32).unsqueeze(1)

# 6. Emparelhar X e y com TensorDataset
train_dataset = TensorDataset(X_train_tensor, y_train_tensor)
val_dataset = TensorDataset(X_val_tensor, y_val_tensor)
test_dataset = TensorDataset(X_test_tensor, y_test_tensor)

# 7. Criar os DataLoaders para fatiar em mini-batches
batch_size = 64

train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)
test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False)

# Conferência das dimensões (shapes)
print(f'Treino:    X={X_train_tensor.shape}, y={y_train_tensor.shape}')
print(f'Validação: X={X_val_tensor.shape}, y={y_val_tensor.shape}')
print(f'Teste:     X={X_test_tensor.shape}, y={y_test_tensor.shape}')

# Conferindo o funcionamento do DataLoader
print(f'Total de pacotes (batches) no treino: {len(train_loader)}')
for X_batch, y_batch in train_loader:
  print(f'Formato de 1 pacote: X={X_batch.shape}, y={y_batch.shape}')
  break

## == Definição da Rede Neural = ##

# 1. Definição da Arquitetura da Rede Neural
class BurnoutNet(nn.Module):

  def __init__(self, qtd_features=6):
    super().__init__()

    # Arquitetura em funil usando potências de 2: 6 -> 16 -> 8 -> 1
    self.camadas = nn.Sequential(
        nn.Linear(qtd_features, 16),  # Camada de entrada -> 1ª camada oculta
        nn.ReLU(),  # Ativação não linear
        nn.Linear(16, 8),  # 1ª camada oculta -> 2ª camada oculta
        nn.ReLU(),  # Ativação não linear
        nn.Linear(8, 1),  # 2ª camada oculta -> Saída (Linear pura)
    )

  def forward(self, x):
    # Define o fluxo dos dados da entrada até a previsão
    return self.camadas(x)


# 2. Instanciar o modelo, a função de perda e o otimizador
modelo = BurnoutNet(qtd_features=6)
criterio_loss = nn.MSELoss()
otimizador = optim.Adam(modelo.parameters(), lr=0.001)

# Conferir a estrutura e o total de parâmetros (pesos + vieses) treináveis
print(modelo)
total_params = sum(p.numel() for p in modelo.parameters() if p.requires_grad)
print(f'\nTotal de parâmetros treináveis: {total_params}')

# 3. Teste rápido de passagem (Forward Pass) com 1 batch do train_loader
for X_batch, y_batch in train_loader:
  previsoes_iniciais = modelo(X_batch)  # Chama o método forward()
  loss_inicial = criterio_loss(previsoes_iniciais, y_batch)

  print(f'Formato da entrada (X_batch): {X_batch.shape}')
  print(f'Formato da saída (previsões): {previsoes_iniciais.shape}')
  print(f'Loss inicial (antes de treinar): {loss_inicial.item():.4f}')
  break




## == Treinamento da Rede Neural = ##
# 1. Configurações do treinamento
epocas = 30
historico_treino = []
historico_val = []

# 2. Laço principal (percorre o dataset inteiro 30 vezes)
for epoca in range(1, epocas + 1):

  # ==========================================
  # FASE 1: TREINAMENTO (A rede ajusta os pesos)
  # ==========================================
  modelo.train()  # Coloca a rede em modo de treino
  soma_loss_treino = 0.0

  for X_batch, y_batch in train_loader:
    otimizador.zero_grad()  # Passo 1: Limpa gradientes da rodada anterior
    previsoes = modelo(X_batch)  # Passo 2: Passa os dados para frente (Forward)
    loss = criterio_loss(previsoes, y_batch)  # Passo 3: Calcula o erro (MSE)
    loss.backward()  # Passo 4: Calcula as derivadas (Backpropagation)
    otimizador.step()  # Passo 5: Gira os 257 "botões" (atualiza pesos)

    soma_loss_treino += loss.item()

  # Calcula a média do erro entre todos os 237 pacotes da época
  media_loss_treino = soma_loss_treino / len(train_loader)
  historico_treino.append(media_loss_treino)

  # ==========================================
  # FASE 2: VALIDAÇÃO (Prova sem alterar pesos)
  # ==========================================
  modelo.eval()  # Coloca a rede em modo de avaliação
  soma_loss_val = 0.0

  with torch.no_grad():  # Desliga o cálculo de gradientes (economiza memória)
    for X_batch, y_batch in val_loader:
      previsoes_val = modelo(X_batch)
      loss_val = criterio_loss(previsoes_val, y_batch)
      soma_loss_val += loss_val.item()

  media_loss_val = soma_loss_val / len(val_loader)
  historico_val.append(media_loss_val)

  # Exibe o progresso a cada 5 épocas
  if epoca % 5 == 0 or epoca == 1:
    print(
        f"Época [{epoca:02d}/{epocas}] | "
        f"Loss Treino: {media_loss_treino:.5f} | "
        f"Loss Validação: {media_loss_val:.5f}"
    )

    ##=== Avaliação Final no Conjunto de Teste = ##
# ==========================================
# PARTE 4: AVALIAÇÃO NO CONJUNTO DE TESTE
# ==========================================
modelo.eval()  # Coloca a rede em modo de avaliação
lista_previsoes = []
lista_reais = []

with torch.no_grad():  # Desliga gradientes para inferência rápida
  for X_batch, y_batch in test_loader:
    previsoes_teste = modelo(X_batch)

    # Converte os tensores do PyTorch para arrays NumPy e guarda nas listas
    lista_previsoes.append(previsoes_teste.numpy())
    lista_reais.append(y_batch.numpy())

# Empilha todos os pacotes (batches) em duas matrizes únicas de 3.244 linhas
y_pred_teste = np.vstack(lista_previsoes)
y_real_teste = np.vstack(lista_reais)

# Cálculo das métricas definitivas
mse = mean_squared_error(y_real_teste, y_pred_teste)
rmse = np.sqrt(mse)
mae = mean_absolute_error(y_real_teste, y_pred_teste)
r2 = r2_score(y_real_teste, y_pred_teste)

print('\n--- RESULTADOS FINAIS NO CONJUNTO DE TESTE ---')
print(f'MSE  (Erro Quadrático Médio):      {mse:.4f}')
print(f'RMSE (Raiz do Erro Quadrático):    {rmse:.4f}')
print(f'MAE  (Erro Médio Absoluto):        {mae:.4f}')
print(f'R²   (Coeficiente Determinação):   {r2:.4f} ({r2 * 100:.1f}%)')

# ==========================================
# GERAÇÃO DOS 3 GRÁFICOS DE DIAGNÓSTICO
# ==========================================
fig, axes = plt.subplots(1, 3, figsize=(18, 5))

# Gráfico 1: Curva de Aprendizado (Treino vs. Validação)
axes[0].plot(
    range(1, epocas + 1),
    historico_treino,
    label='Treino (MSE)',
    marker='o',
    markersize=3,
)
axes[0].plot(
    range(1, epocas + 1),
    historico_val,
    label='Validação (MSE)',
    marker='s',
    markersize=3,
)
axes[0].set_title('1. Curva de Aprendizado')
axes[0].set_xlabel('Época')
axes[0].set_ylabel('Loss (MSE)')
axes[0].legend()
axes[0].grid(True, alpha=0.3)

# Gráfico 2: Real vs. Previsto
axes[1].scatter(
    y_real_teste,
    y_pred_teste,
    alpha=0.25,
    s=12,
    color='royalblue',
    label='Previsões',
)
axes[1].plot(
    [0, 1],
    [0, 1],
    color='red',
    linestyle='--',
    linewidth=2,
    label='Previsão Perfeita (y = x)',
)
axes[1].set_title('2. Real vs. Previsto (Teste)')
axes[1].set_xlabel('Burn Rate Real')
axes[1].set_ylabel('Burn Rate Previsto')
axes[1].set_xlim(-0.05, 1.05)
axes[1].set_ylim(-0.05, 1.05)
axes[1].legend()
axes[1].grid(True, alpha=0.3)

# Gráfico 3: Análise de Resíduos (Erro = Real - Previsto)
residuos = y_real_teste - y_pred_teste
axes[2].scatter(y_pred_teste, residuos, alpha=0.25, s=12, color='darkorange')
axes[2].axhline(0, color='red', linestyle='--', linewidth=2, label='Erro Zero')
axes[2].set_title('3. Análise de Resíduos (Teste)')
axes[2].set_xlabel('Burn Rate Previsto')
axes[2].set_ylabel('Resíduo (Real - Previsto)')
axes[2].legend()
axes[2].grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('diagnostico_burnout.png', dpi=150)  # Salva a imagem na pasta


##=== Desenho da Arquitetura e Pesos = ##

# 1. Extrair os pesos treinados de cada camada Linear (índices 0, 2 e 4 do Sequential)
w1 = modelo.camadas[0].weight.detach().numpy()  # Formato: (16, 6)
w2 = modelo.camadas[2].weight.detach().numpy()  # Formato: (8, 16)
w3 = modelo.camadas[4].weight.detach().numpy()  # Formato: (1, 8)
pesos_camadas = [w1, w2, w3]

# 2. Calcular a "força" de cada neurônio (soma dos pesos absolutos conectados a ele)
imp_entrada = np.sum(np.abs(w1), axis=0)
imp_oculta1 = np.sum(np.abs(w1), axis=1) + np.sum(np.abs(w2), axis=0)
imp_oculta2 = np.sum(np.abs(w2), axis=1) + np.sum(np.abs(w3), axis=0)
imp_saida = np.sum(np.abs(w3), axis=1)

importancias = [imp_entrada, imp_oculta1, imp_oculta2, imp_saida]
arquitetura = [6, 16, 8, 1]
nomes_camadas = [
    'Entrada\n(6 features)',
    'Oculta 1\n(16 neurônios)',
    'Oculta 2\n(8 neurônios)',
    'Saída\n(1 previsão)',
]

# 3. Configurar a área do desenho
fig, ax = plt.subplots(figsize=(14, 9))
ax.axis('off')

x_camadas = [0.24, 0.48, 0.72, 0.88]
posicoes_neuronios = []

for idx_c, qtd_n in enumerate(arquitetura):
  y_coords = np.linspace(0.90, 0.16, qtd_n) if qtd_n > 1 else [0.53]
  posicoes_neuronios.append([(x_camadas[idx_c], y) for y in y_coords])

max_peso = max(np.max(np.abs(w)) for w in pesos_camadas)

# 4. Desenhar as conexões (linhas) primeiro para ficarem atrás dos neurônios
for idx_c, matriz_w in enumerate(pesos_camadas):
  origem = posicoes_neuronios[idx_c]
  destino = posicoes_neuronios[idx_c + 1]

  for i_dest, (x2, y2) in enumerate(destino):
    for i_orig, (x1, y1) in enumerate(origem):
      peso = matriz_w[i_dest, i_orig]
      intensidade = abs(peso) / max_peso

      cor_linha = (
          '#1f77b4' if peso >= 0 else '#d62728'
      )  # Azul (+), Vermelho (-)
      espessura = 0.4 + 3.2 * (intensidade**1.3)
      transparencia = 0.10 + 0.75 * (intensidade**1.1)

      ax.plot(
          [x1, x2],
          [y1, y2],
          color=cor_linha,
          linewidth=espessura,
          alpha=transparencia,
          zorder=1,
      )

# 5. Desenhar os neurônios (círculos) pintados pela soma dos pesos
cmap = plt.cm.YlOrRd
for idx_c, coords in enumerate(posicoes_neuronios):
  imp = importancias[idx_c]
  imp_norm = (
      0.15 + 0.80 * (imp - imp.min()) / (imp.max() - imp.min() + 1e-8)
      if len(imp) > 1
      else [0.75]
  )

  for idx_n, (x, y) in enumerate(coords):
    circulo = plt.Circle(
        (x, y),
        radius=0.018,
        facecolor=cmap(imp_norm[idx_n]),
        edgecolor='#222222',
        linewidth=1.3,
        zorder=3,
    )
    ax.add_patch(circulo)

    if idx_c == 0:
      ax.text(
          x - 0.03,
          y,
          features[idx_n],
          ha='right',
          va='center',
          fontsize=10,
          fontweight='bold',
          color='#222222',
      )
    elif idx_c == len(arquitetura) - 1:
      ax.text(
          x + 0.03,
          y,
          'Burn Rate\n(Previsto)',
          ha='left',
          va='center',
          fontsize=10,
          fontweight='bold',
          color='#222222',
      )

# 6. Títulos e legenda
for idx_c, nome in enumerate(nomes_camadas):
  ax.text(
      x_camadas[idx_c],
      0.97,
      nome,
      ha='center',
      va='center',
      fontsize=11,
      fontweight='bold',
  )

legenda = [
    Line2D(
        [0], [0], color='#1f77b4', lw=3, label='Peso Positivo (+) — Estimula'
    ),
    Line2D([0], [0], color='#d62728', lw=3, label='Peso Negativo (-) — Inibe'),
    Line2D(
        [0],
        [0],
        color='gray',
        lw=3.5,
        label='Linha grossa = Peso mais forte',
    ),
    mpatches.Patch(
        facecolor=cmap(0.85),
        edgecolor='#222222',
        label='Neurônio escuro = Maior soma de pesos',
    ),
    mpatches.Patch(
        facecolor=cmap(0.20),
        edgecolor='#222222',
        label='Neurônio claro = Menor soma de pesos',
    ),
]
ax.legend(
    handles=legenda,
    loc='lower center',
    bbox_to_anchor=(0.5, 0.01),
    ncol=2,
    frameon=True,
    fontsize=9.5,
)

plt.title(
    'Arquitetura Treinada: BurnoutNet (6 → 16 → 8 → 1)',
    fontsize=14,
    fontweight='bold',
    pad=12,
)
ax.set_xlim(0.0, 1.0)
ax.set_ylim(0.0, 1.03)
plt.tight_layout()
plt.savefig('arquitetura_rede_neural.png', dpi=150, bbox_inches='tight')
print("Desenho salvo como 'arquitetura_rede_neural.png'!")
