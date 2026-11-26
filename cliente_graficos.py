"""Cliente HTTP usado pelo Agente 2; não depende de Matplotlib ou FastAPI."""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def gerar_grafico_evolucao(historico: list[dict] | None, *, individual: bool = False) -> str | None:
    """Mantém o contrato original, delegando a geração à API externa."""
    base_url = os.environ.get("GRAFICOS_API_URL", "http://127.0.0.1:8000").rstrip("/")
    dados = {"historico": historico}
    if individual:
        dados["escopo"] = "individual"
    pedido = Request(
        f"{base_url}/graficos/evolucao-score",
        data=json.dumps(dados, ensure_ascii=False, allow_nan=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(pedido, timeout=30) as resposta:
            resultado = json.load(resposta)
    except HTTPError as exc:
        try:
            detalhe = exc.read().decode("utf-8", errors="replace")
        finally:
            exc.close()
        raise RuntimeError(f"API de gráficos retornou HTTP {exc.code}: {detalhe}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Não foi possível acessar a API de gráficos em {base_url}: {exc}") from exc
    except (ValueError, UnicodeError) as exc:
        raise RuntimeError("A API de gráficos retornou uma resposta JSON inválida.") from exc

    if not isinstance(resultado, dict) or "grafico_b64" not in resultado:
        raise RuntimeError("Resposta da API de gráficos sem o campo grafico_b64.")
    grafico = resultado["grafico_b64"]
    if grafico is not None and (not isinstance(grafico, str) or not grafico):
        raise RuntimeError("Campo grafico_b64 inválido na resposta da API.")
    return grafico
