import argparse
import json
import os
import ollama
from jinja2 import Template
from pydantic import BaseModel
from ambiente_pdf import configurar_bibliotecas_pdf

configurar_bibliotecas_pdf()

from weasyprint import HTML
from database import buscar_dados_equipe_para_relatorio
from cliente_graficos import gerar_grafico_evolucao
from datetime import date
import re




# =====================================================================
# 1. SCHEMA DE SAÍDA DO AGENTE 2 (Apenas a parte analítica)
# =====================================================================
class AnaliseAgente2(BaseModel):
    analise_scores_e_historico: str
    analise_prazos_e_carga_horaria: str | None = None  # Pode vir vazio (null)
    pontos_de_atencao: list[str]
    conclusao_grupo: str

# =====================================================================
# 2. CHAMADA AO QWEN 3 8B (AGENTE 2)
# =====================================================================
def executar_agente_2(dados_grupo: dict) -> AnaliseAgente2:
    prompt = f"""
    Você é o Agente 2, um analista de dados organizacionais focado em bem-estar e prevenção de burnout.
    Analise os dados JSON abaixo referentes ao grupo avaliado pelo instrumento BAT (Burnout Assessment Tool, escala de 1 a 5).

    Regras:
    - Não faça diagnósticos clínicos. Trate os números como indicadores exploratórios.
    - Correlacione a evolução dos scores com os prazos, carga horária e reuniões do grupo.
    - Seja objetivo, técnico e escreva em português do Brasil.
    - Se algum dado estiver ausente ou nulo (como histórico, prazos ou carga horária), NÃO invente informações. Retorne null no campo correspondente ou informe explicitamente que não há dados suficientes para aquela análise.

    Dados do Grupo:
    {json.dumps(dados_grupo, ensure_ascii=False, indent=2)}
    """

    response = ollama.chat(
        model=os.environ.get("OLLAMA_MODEL", "hf.co/bartowski/Qwen_Qwen3-8B-GGUF:Q3_K_M"),
        messages=[{"role": "user", "content": prompt}],
        format=AnaliseAgente2.model_json_schema(),
        think=False,
        options={"temperature": 0.2},
    )
    return AnaliseAgente2.model_validate_json(response.message.content)


# =====================================================================
# 3. TEMPLATE HTML COM OS 4 BLOCOS (BLOCO 0 AO BLOCO 3)
# =====================================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="utf-8">
    <style>
        @page { size: A4; margin: 18mm; }
        body { font-family: sans-serif; font-size: 11px; line-height: 1.5; color: #2d3748; }
        h1 { color: #1a365d; font-size: 20px; border-bottom: 2px solid #1a365d; padding-bottom: 6px; }
        h2 { color: #2b6cb0; font-size: 15px; margin-top: 20px; border-bottom: 1px solid #cbd5e0; padding-bottom: 4px; }
        h3 { color: #2d3748; font-size: 13px; margin-top: 14px; }
        .bloco-aviso { background: #fff5f5; border-left: 4px solid #c53030; padding: 12px; margin-bottom: 20px; font-size: 10.5px; }
        .aviso-individual { background: #fefcbf; border-left: 4px solid #d69e2e; padding: 10px; margin-bottom: 14px; font-size: 10.5px; }
        .card-score { background: #edf2f7; padding: 12px; border-radius: 6px; margin: 10px 0; }
        .analise-box { background: #f7fafc; border: 1px solid #e2e8f0; padding: 12px; border-radius: 6px; margin-top: 10px; }
        .vazio { color: #718096; font-style: italic; }
        table { width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 10.5px; }
        th, td { border: 1px solid #cbd5e0; padding: 6px 8px; text-align: left; }
        th { background: #edf2f7; color: #1a365d; }
        .grafico { text-align: center; margin: 15px 0; }
        .grafico img { max-width: 100%; border: 1px solid #e2e8f0; border-radius: 4px; }
        .page-break { page-break-before: always; }
        .qa-card { border: 1px solid #e2e8f0; border-left: 3px solid #2b6cb0; padding: 8px 12px; margin-bottom: 10px; background: #ffffff; }
        .nota-badge { display: inline-block; background: #2b6cb0; color: white; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 10px; }
    </style>
</head>
<body>

    <h1>Relatório de Monitoramento BAT — {{ grupo.nome or "Grupo não identificado" }}</h1>

    <!-- BLOCO 0: AVISOS E LIMITAÇÕES -->
    <div class="bloco-aviso">
        <strong>Bloco 0 — Aviso Experimental e Limitações Metodológicas:</strong><br>
        Este software é um <strong>experimento</strong> e seus resultados devem ser interpretados apenas como um possível indicativo exploratório, <strong>não substituindo</strong> em hipótese alguma o acompanhamento ou avaliação de um profissional de saúde qualificado. Além disso, as notas de corte de referência do BAT (Burnout Assessment Tool) foram estabelecidas com base em grupos populacionais diferentes do Brasil; portanto, os valores apresentados podem não estar 100% condizentes com a realidade local.
    </div>

    <!-- BLOCO 1: FOCO NO GRUPO -->
    <h2>Bloco 1 — Visão Geral do Grupo</h2>

    <div class="card-score">
        <strong>Grupo:</strong> {{ grupo.nome or "Não informado" }}<br>
        <strong>Score Geral do BAT (Grupo):</strong>
        {% if grupo.score_geral is not none %}
            {{ "%.2f"|format(grupo.score_geral) }}
            {% if grupo.margem_erro is not none %}
                &plusmn; {{ "%.2f"|format(grupo.margem_erro) }}
            {% endif %}
        {% else %}
            <span class="vazio">Dados insuficientes para cálculo.</span>
        {% endif %}
    </div>

    <h3>Scores por Pilar (Grupo)</h3>
    {% if grupo.pilares %}
        <table>
            <thead>
                <tr><th>Pilar do BAT</th><th>Score</th><th>Margem de Erro</th></tr>
            </thead>
            <tbody>
                {% for nome_pilar, dados_pilar in grupo.pilares.items() %}
                <tr>
                    <td>{{ nome_pilar }}</td>
                    <td>{{ "%.2f"|format(dados_pilar.score) if dados_pilar.score is not none else "N/A" }}</td>
                    <td>{{ "± %.2f"|format(dados_pilar.margem_erro) if dados_pilar.margem_erro is not none else "N/A" }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    {% else %}
        <p class="vazio">Scores por pilar não disponíveis para este grupo.</p>
    {% endif %}

    {% if grafico_b64 %}
        <div class="grafico">
            <img src="data:image/png;base64,{{ grafico_b64 }}" alt="Evolução Temporal do Grupo">
        </div>
    {% else %}
        <p class="vazio">Histórico insuficiente para gerar gráfico de evolução temporal (mínimo de 2 medições).</p>
    {% endif %}

    <h3>Prazos de Atividades e Carga Horária</h3>
    {% if grupo.rotina_e_prazos %}
        <ul>
            <li><strong>Carga Horária Média:</strong> {{ grupo.rotina_e_prazos.carga_horaria_media_semanal or "Não informada" }}</li>
            <li><strong>Reuniões:</strong> {{ grupo.rotina_e_prazos.reunioes_semanais or "Não informadas" }}</li>
        </ul>

        {% if grupo.rotina_e_prazos.proximos_prazos %}
            <table>
                <thead>
                    <tr><th>Entrega / Atividade</th><th>Prazo</th><th>Status</th></tr>
                </thead>
                <tbody>
                    {% for item in grupo.rotina_e_prazos.proximos_prazos %}
                    <tr>
                        <td>{{ item.entrega or "Sem descrição" }}</td>
                        <td>{{ item.prazo or "Não definido" }}</td>
                        <td>{{ item.status or "N/A" }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        {% else %}
            <p class="vazio">Nenhum prazo de entrega registrado para este período.</p>
        {% endif %}
    {% else %}
        <p class="vazio">Dados de rotina, carga horária e prazos não fornecidos.</p>
    {% endif %}

    <h3>Análise e Conclusão do Agente 2</h3>
    {% if analise %}
        <div class="analise-box">
            {% if analise.analise_scores_e_historico %}
                <p><strong>Análise de Scores e Histórico:</strong> {{ analise.analise_scores_e_historico }}</p>
            {% endif %}

            {% if analise.analise_prazos_e_carga_horaria %}
                <p><strong>Análise de Prazos e Carga Horária:</strong> {{ analise.analise_prazos_e_carga_horaria }}</p>
            {% else %}
                <p class="vazio">Análise de prazos e carga horária não realizada por ausência de dados.</p>
            {% endif %}

            {% if analise.pontos_de_atencao %}
                <p><strong>Pontos de Atenção:</strong></p>
                <ul>
                    {% for ponto in analise.pontos_de_atencao %}
                    <li>{{ ponto }}</li>
                    {% endfor %}
                </ul>
            {% endif %}

            {% if analise.conclusao_grupo %}
                <p><strong>Conclusão sobre o Grupo:</strong> {{ analise.conclusao_grupo }}</p>
            {% endif %}
        </div>
    {% else %}
        <p class="vazio">Análise do Agente 2 indisponível.</p>
    {% endif %}

    <!-- BLOCO 2: FOCO INDIVIDUAL -->
    <div class="page-break"></div>
    <h2>Bloco 2 — Visão Individual (Indicativo Exploratório)</h2>

    <div class="aviso-individual">
        <strong>Nota sobre o BAT-12:</strong> A versão reduzida (BAT-12) <strong>não é recomendada para uso ou diagnóstico individual</strong>. Os dados abaixo são exibidos estritamente como indicativos exploratórios dentro do contexto do grupo.
    </div>

    {% if membros %}
        {% for membro in membros %}
        <h3>
            {{ membro.identificador or "Membro sem identificação" }} —
            {% if membro.score_geral is not none %}
                Score Geral: {{ "%.2f"|format(membro.score_geral) }}
                {% if membro.margem_erro is not none %}
                    &plusmn; {{ "%.2f"|format(membro.margem_erro) }}
                {% endif %}
            {% else %}
                <span class="vazio">Score indisponível</span>
            {% endif %}
        </h3>

        {% if membro.pilares %}
            <table>
                <thead>
                    <tr><th>Pilar do BAT</th><th>Score Individual</th><th>Margem de Erro</th></tr>
                </thead>
                <tbody>
                    {% for nome_pilar, dados_pilar in membro.pilares.items() %}
                    <tr>
                        <td>{{ nome_pilar }}</td>
                        <td>{{ "%.2f"|format(dados_pilar.score) if dados_pilar.score is not none else "N/A" }}</td>
                        <td>{{ "± %.2f"|format(dados_pilar.margem_erro) if dados_pilar.margem_erro is not none else "N/A" }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        {% else %}
            <p class="vazio">Scores individuais por pilar não disponíveis.</p>
        {% endif %}

        {% if membro.historico %}
            <p><strong>Histórico no grupo:</strong>
                {% for h in membro.historico %}
                    {{ h.data }}: <strong>{{ "%.2f"|format(h.score_geral) if h.score_geral is not none else "N/A" }}</strong>{% if not loop.last %} &rarr; {% endif %}
                {% endfor %}
            </p>
        {% else %}
            <p class="vazio">Sem histórico anterior registrado neste grupo.</p>
        {% endif %}
        {% endfor %}
    {% else %}
        <p class="vazio">Nenhum dado individual disponível para este relatório.</p>
    {% endif %}

    <!-- BLOCO 3: EXPLICABILIDADE -->
    <div class="page-break"></div>
    <h2>Bloco 3 — Explicabilidade (Avaliação do Agente 1)</h2>
    <p>Registro detalhado das perguntas conduzidas pelo Agente 1, respostas coletadas, notas atribuídas e respectivas justificativas.</p>

    {% if membros %}
        {% for membro in membros %}
            <h3>Registros — {{ membro.identificador or "Membro sem identificação" }}</h3>
            {% if membro.interacoes_agente_1 %}
                {% for qa in membro.interacoes_agente_1 %}
                <div class="qa-card">
                    <p><strong>Pergunta (Agente 1):</strong> {{ qa.pergunta or "Não registrada" }}</p>
                    <p><strong>Resposta do Usuário:</strong> "{{ qa.resposta or "Sem resposta" }}"</p>
                    <p>
                        <span class="nota-badge">Nota: {{ qa.nota if qa.nota is not none else "N/A" }} / 5</span>
                        &nbsp; <strong>Justificativa:</strong> {{ qa.justificativa or "Justificativa não fornecida." }}
                    </p>
                </div>
                {% endfor %}
            {% else %}
                <p class="vazio">Nenhuma interação registrada com o Agente 1 para este membro.</p>
            {% endif %}
        {% endfor %}
    {% else %}
        <p class="vazio">Nenhum registro de explicabilidade disponível.</p>
    {% endif %}

</body>
</html>
"""

# =====================================================================
# 4. EXECUÇÃO DO PIPELINE (GRÁFICO OBTIDO VIA API)
# =====================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gera o relatório BAT com gráfico obtido pela API.")
    parser.add_argument("--sem-analise", action="store_true",
                        help="Gera o PDF sem chamar Ollama; a ausência de análise é indicada no relatório.")
    parser.add_argument("--equipe", type=int, default=1, help="ID da equipe no banco (padrão: 1).")
    args = parser.parse_args()
    dados = buscar_dados_equipe_para_relatorio(id_equipe=args.equipe)
    print("1. Solicitando gráfico temporal à API...")
    grafico_b64 = gerar_grafico_evolucao(dados["grupo"]["historico"])

    if args.sem_analise:
        print("2. Análise textual desativada explicitamente (--sem-analise).")
        analise_agente_2 = None
    else:
        print("2. Chamando Qwen 3 8B (Agente 2) para gerar a análise...")
        analise_agente_2 = executar_agente_2(dados["grupo"])

    print("3. Renderizando HTML e gerando PDF...")
    html_final = Template(HTML_TEMPLATE).render(
        grupo=dados["grupo"],
        membros=dados["membros"],
        grafico_b64=grafico_b64,
        analise=analise_agente_2,
    )

    nome_grupo = dados["grupo"]["nome"] or "grupo_sem_nome"
    nome_limpo = re.sub(r"[^\w\-]+", "_", nome_grupo).strip("_")
    data_hoje = date.today().strftime("%Y-%m-%d")  # Ex: 2026-11-24

    nome_arquivo = f"relatorio_{nome_limpo}_{data_hoje}.pdf"

    HTML(string=html_final).write_pdf(nome_arquivo)
    print(f"Sucesso! Arquivo salvo como: {nome_arquivo}")
