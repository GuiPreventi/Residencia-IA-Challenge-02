"""API independente para o gráfico de evolução temporal usado pelo Agente 2."""

import base64
import io
from threading import Lock

from fastapi import FastAPI
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from pydantic import BaseModel, ConfigDict, Field


app = FastAPI(title="API de gráficos do Agente 2", version="1.0.0")
_render_lock = Lock()  # Matplotlib não é seguro para renderizações simultâneas em threads.


class Medicao(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    # Aceita os rótulos já usados pelo banco: YYYY-MM, YYYY-MM-DD e "Atual".
    data: str = Field(min_length=1, max_length=100, pattern=r"\S")
    score_geral: float | None = Field(default=None, ge=1, le=5)


class PedidoGrafico(BaseModel):
    model_config = ConfigDict(extra="forbid")

    historico: list[Medicao] | None = Field(default=None, max_length=1000)


class RespostaGrafico(BaseModel):
    grafico_b64: str | None
    formato: str = "png"
    mensagem: str | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/graficos/evolucao-score", response_model=RespostaGrafico)
def gerar_grafico_evolucao(pedido: PedidoGrafico) -> RespostaGrafico:
    """Recebe o histórico em ordem temporal e retorna o PNG codificado em Base64."""
    historico = [item for item in (pedido.historico or []) if item.score_geral is not None]
    if len(historico) < 2:
        return RespostaGrafico(
            grafico_b64=None,
            mensagem="Histórico insuficiente: são necessárias pelo menos 2 medições com score.",
        )

    # Posições numéricas preservam também rótulos de data repetidos.
    posicoes = list(range(len(historico)))
    datas = [item.data for item in historico]
    scores = [item.score_geral for item in historico]

    with _render_lock:
        figura = Figure(figsize=(7, 3))
        FigureCanvasAgg(figura)
        try:
            eixo = figura.subplots()
            eixo.plot(posicoes, scores, marker="o", color="#2b6cb0", linewidth=2.5)
            eixo.fill_between(posicoes, scores, color="#2b6cb0", alpha=0.1)
            # Evita sobreposição de texto em históricos longos.
            passo = max(1, (len(historico) + 7) // 8)
            marcas = list(range(0, len(historico), passo))
            if marcas[-1] != len(historico) - 1:
                marcas.append(len(historico) - 1)
            eixo.set_xticks(marcas, [datas[i] for i in marcas])
            eixo.set_ylim(1, 5)
            eixo.axhline(2.59, color="#dd6b20", linestyle="--", linewidth=1,
                         label="Zona de Atenção (Ref. Externa)")
            eixo.axhline(3.02, color="#c53030", linestyle="--", linewidth=1,
                         label="Zona Crítica (Ref. Externa)")
            eixo.set_title("Evolução Temporal do Score Geral do Grupo (BAT)", fontsize=11, pad=10)
            eixo.set_ylabel("Score (1 a 5)")
            eixo.grid(axis="y", linestyle=":", alpha=0.6)
            eixo.legend(fontsize=8, loc="upper left")
            figura.tight_layout()
            with io.BytesIO() as buffer:
                figura.savefig(buffer, format="png", dpi=150)
                grafico_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
        finally:
            figura.clear()

    return RespostaGrafico(grafico_b64=grafico_b64)
