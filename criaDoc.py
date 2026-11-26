import argparse
import json
import os
from cliente_graficos import gerar_grafico_evolucao
import ollama
from jinja2 import Template
from pydantic import BaseModel
from ambiente_pdf import configurar_bibliotecas_pdf
from database import buscar_dados_equipe_para_relatorio, init_db, listar_equipes
from datetime import date
import re


# =====================================================================
# 2. SCHEMA DE SAÍDA DO AGENTE 2 (Apenas a parte analítica)
# =====================================================================
class AnaliseAgente2(BaseModel):
    analise_scores_e_historico: str
    pontos_de_atencao: list[str]
    conclusao_grupo: str


class AnaliseIndividual(BaseModel):
    analise_scores_e_historico: str
    pontos_de_atencao: list[str]
    conclusao_individual: str


# =====================================================================
# 4. CHAMADA AO QWEN 3 8B (AGENTE 2)
# =====================================================================

def buscar_contexto_completo_rag(
    dados_grupo: dict,
    mostrar_bastidores: bool = True,
) -> tuple[str, list[str]]:
    """Executa buscas separadas por tema no RAG para garantir BAT, Playbook e NR-01 no prompt."""
    from rag import buscar_contexto_rag

    pilares = dados_grupo.get("pilares", {})
    if pilares:
        pilar_critico, info = max(
            pilares.items(),
            key=lambda item: item[1].get("score") or 0
        )
        score_critico = info.get("score", 0)
        tema_bat = "pilares_bat"
        query_bat = f"Interpretação do pilar {pilar_critico} do BAT com score {score_critico:.2f}, sintomas, pontos de corte e correlações."
        query_intervencoes = f"Intervenções organizacionais recomendadas quando o pilar {pilar_critico} do BAT está elevado ({score_critico:.2f})."
    else:
        tema_bat = "metodologia_bat"
        query_bat = "Interpretação geral do Burnout Assessment Tool (BAT), pontos de corte e limitações."
        query_intervencoes = "Principais causas organizacionais do burnout e intervenções recomendadas."

    query_nr01 = "Obrigações da NR-01 no Gerenciamento de Riscos Ocupacionais (GRO) para riscos psicossociais e plano de ação."

    buscas = [
        ("REFERÊNCIAS DO BAT", query_bat, tema_bat, 3),
        ("PLAYBOOK DE INTERVENÇÕES ORGANIZACIONAIS", query_intervencoes, "intervencoes", 3),
        ("DIRETRIZES DA NR-01", query_nr01, "nr01", 2),
    ]

    blocos_contexto = []
    fontes_unicas = []

    for titulo, query, tema, n_cand in buscas:
        if mostrar_bastidores:
            print(f"\n--- Buscando tema: {tema} ---")

        contexto, fontes = buscar_contexto_rag(
            pergunta=query,
            n_candidatos=n_cand,
            filtro_tema=tema,
            mostrar_bastidores=mostrar_bastidores,
        )

        if fontes:  # Só adiciona o bloco se encontrou trechos acima do limiar
            blocos_contexto.append(f"### {titulo}\n{contexto}")
            for f in fontes:
                if f not in fontes_unicas:
                    fontes_unicas.append(f)

    if not blocos_contexto:
        return "Nenhum material de referência específico encontrado na base de conhecimento.", []

    return "\n\n".join(blocos_contexto), fontes_unicas



MODELO_LLM = os.environ.get("OLLAMA_MODEL", "hf.co/bartowski/Qwen_Qwen3-8B-GGUF:Q3_K_M")


def executar_agente_2(
    dados_grupo: dict,
    contexto_rag: str,
    max_tentativas: int = 3,
    individual: bool = False,
) -> tuple[AnaliseAgente2 | AnaliseIndividual, str | None]:
    """
    Executa o Agente 2 com suporte a Tool Calling para a API de gráficos.
    Retorna: (AnaliseAgente2, grafico_b64)
    """
    grafico_capturado: str | None = None

    # --- Definição da Tool que o Agente pode chamar ---
    def solicitar_grafico_evolucao_api() -> str:
        """
        Chama a API externa para gerar o gráfico de evolução temporal do score geral do grupo (BAT).
        Use esta ferramenta quando houver histórico com 2 ou mais medições para enriquecer o relatório.
        """
        nonlocal grafico_capturado
        try:
            grafico_capturado = gerar_grafico_evolucao(dados_grupo.get("historico"), individual=individual)
            if grafico_capturado:
                return "Sucesso: o gráfico de evolução temporal foi gerado pela API externa e anexado ao relatório."
            return "Aviso: a API informou que não há medições suficientes para gerar o gráfico."
        except RuntimeError as e:
            grafico_capturado = None
            return f"Aviso: a API externa de gráficos está indisponível ({e}). Prossiga com a análise sem o gráfico."

    if individual:
        solicitar_grafico_evolucao_api.__doc__ = (
            "Solicita à API o gráfico do histórico individual recebido. Use com pelo menos duas medições."
        )
    sujeito = "à avaliação individual fornecida, sem inferir resultados de equipe" if individual else "ao grupo"
    schema = AnaliseIndividual if individual else AnaliseAgente2
    prompt = f"""
    Você é o Agente 2, um analista de dados organizacionais focado em bem-estar e prevenção de burnout.
    Analise os dados JSON abaixo referentes {sujeito}, pelo instrumento BAT (escala de 1 a 5).

    Você possui a ferramenta `solicitar_grafico_evolucao_api` para gerar o gráfico de evolução temporal
    via API externa. Se houver 2 ou mais registros no campo "historico", chame essa ferramenta
    antes de redigir sua análise final.

    Use o MATERIAL DE REFERÊNCIA abaixo para embasar sua interpretação técnica (pontos de corte,
    significado dos pilares, NR-01 e recomendações práticas de intervenção).

    === MATERIAL DE REFERÊNCIA (RAG) ===
    {contexto_rag}
    ====================================

    Regras:
    - Não faça diagnósticos clínicos. Trate os números como indicadores exploratórios.
    - Relacione os scores fornecidos com o histórico e os pilares do BAT.
    - A análise individual é somente um protótipo exploratório, sem diagnóstico nem classificação clínica.
    - Se houver itens faltantes, informe que o resultado é parcial. Não crie margens de erro.
    - Se algum dado estiver ausente ou nulo, não invente informações.
    - Seja conciso e direto: máximo de 1 parágrafo curto (3 a 4 frases) para a análise, até 5 itens curtos em pontos de atenção e 1 parágrafo curto para a conclusão.
    - Escreva em português do Brasil.

    Dados recebidos:
    {json.dumps(dados_grupo, ensure_ascii=False, indent=2)}
    """

    messages = [{"role": "user", "content": prompt}]

    # -----------------------------------------------------------------
    # ETAPA 1: O Agente decide se precisa chamar a Tool da API
    # -----------------------------------------------------------------
    print("   [Agente 2] Avaliando necessidade de chamar ferramentas (Tools)...")
    resp_tool = ollama.chat(
        model=MODELO_LLM,
        messages=messages,
        tools=[solicitar_grafico_evolucao_api],
        think=False,
        keep_alive="5m",
        options={
            "temperature": 0.1,
            "num_ctx": 8192,
        },
    )

    messages.append(resp_tool.message)

    if resp_tool.message.tool_calls:
        for tool_call in resp_tool.message.tool_calls:
            nome_tool = tool_call.function.name
            print(f"   [Agente 2] Decidiu chamar a tool: {nome_tool}")
            if nome_tool == "solicitar_grafico_evolucao_api":
                resultado_tool = solicitar_grafico_evolucao_api()
                print(f"   [Tool -> Agente 2] {resultado_tool}")
                messages.append({
                    "role": "tool",
                    "tool_name": nome_tool,
                    "content": resultado_tool,
                })
    else:
        print("   [Agente 2] Optou por não chamar nenhuma ferramenta.")

    # -----------------------------------------------------------------
    # ETAPA 2: Geração da análise final em JSON estruturado (Pydantic)
    # -----------------------------------------------------------------
    messages.append({
        "role": "user",
        "content": "Agora gere a análise final estritamente no formato JSON solicitado.",
    })

    ultimo_erro = None
    for tentativa in range(1, max_tentativas + 1):
        response = ollama.chat(
            model=MODELO_LLM,
            messages=messages,
            format=schema.model_json_schema(),
            think=False,
            keep_alive="5m",
            options={
                "temperature": 0.2,
                "num_ctx": 8192,
                "num_predict": 1536,
                "repeat_penalty": 1.15,
            },
        )
        try:
            analise = schema.model_validate_json(response.message.content)
            return analise, grafico_capturado
        except Exception as e:
            ultimo_erro = e
            print(f"   [Aviso] Tentativa {tentativa}/{max_tentativas} retornou JSON incompleto. Tentando novamente...")

    raise RuntimeError(f"Agente 2 falhou após {max_tentativas} tentativas: {ultimo_erro}")

# =====================================================================
# 5. TEMPLATE HTML COM OS 4 BLOCOS (BLOCO 0 AO BLOCO 3)
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
        <p class="vazio">Gráfico de evolução temporal indisponível.</p>
    {% endif %}


    <h3>Análise e Conclusão do Agente 2</h3>
    {% if analise %}
        <div class="analise-box">
            {% if analise.analise_scores_e_historico %}
                <p><strong>Análise de Scores e Histórico:</strong> {{ analise.analise_scores_e_historico }}</p>
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

        {% if fontes_rag %}
            <p style="font-size: 10px; color: #555; margin-top: 10px;">
                <strong>Referências consultadas (RAG):</strong> {{ fontes_rag | join('; ') }}
            </p>
        {% endif %}


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

def selecionar_equipe_menu(entrada=input, saida=print) -> int | None:
    """Exibe um menu no terminal com as equipes cadastradas no SQLite e retorna o IdEquipe escolhido."""
    init_db()
    equipes = listar_equipes()
    if not equipes:
        saida("Nenhuma equipe encontrada no banco de dados. Execute o Agente 1 ou cadastre uma equipe primeiro.")
        return None

    saida("\n=== Seleção de Equipe para Relatório (Agente 2) ===")
    for idx, eq in enumerate(equipes, start=1):
        membros = eq.get("membros_avaliados", 0)
        avals = eq.get("total_avaliacoes", 0)
        lbl_m = "membro avaliado" if membros == 1 else "membros avaliados"
        lbl_a = "avaliação" if avals == 1 else "avaliações"
        saida(f"  {idx}. {eq['nome']} (ID {eq['id']} | {membros} {lbl_m}, {avals} {lbl_a})")
    saida("  0. Sair")

    while True:
        try:
            bruto = entrada("\nEscolha o número da equipe para gerar o relatório: ").strip()
        except (KeyboardInterrupt, EOFError):
            saida("")
            return None

        if not bruto:
            continue
        resp = bruto.lower()
        if resp in ("0", "sair", "exit", "quit"):
            return None
        if resp.isdigit():
            indice = int(resp)
            if 1 <= indice <= len(equipes):
                escolhida = equipes[indice - 1]
                saida(f"Equipe selecionada: {escolhida['nome']} (ID {escolhida['id']})\n")
                return escolhida["id"]
        else:
            for eq in equipes:
                if eq["nome"].strip().lower() == resp:
                    saida(f"Equipe selecionada: {eq['nome']} (ID {eq['id']})\n")
                    return eq["id"]

        saida(f"Opção inválida. Digite um número de 1 a {len(equipes)} (ou 0 para sair).")


# =====================================================================
# 6. EXECUÇÃO DO PIPELINE
# =====================================================================
if __name__ == "__main__":
    configurar_bibliotecas_pdf()
    from weasyprint import HTML
    parser = argparse.ArgumentParser(description="Gera relatório de monitoramento BAT em PDF via Agente 2.")
    parser.add_argument(
        "--equipe",
        type=int,
        default=None,
        help="ID da equipe no SQLite para geração direta do relatório (se omitido, abre o menu no terminal).",
    )
    args = parser.parse_args()

    id_equipe = args.equipe
    if id_equipe is None:
        id_equipe = selecionar_equipe_menu()
        if id_equipe is None:
            print("Operação cancelada.")
            raise SystemExit(0)

    print(f"0. Buscando dados da equipe {id_equipe} no SQLite...")
    dados = buscar_dados_equipe_para_relatorio(id_equipe=id_equipe)

    print("1. Consultando base de conhecimento (RAG por tema)...")
    contexto_rag, fontes_rag = buscar_contexto_completo_rag(
        dados["grupo"],
        mostrar_bastidores=True,
    )

    print("2. Chamando Qwen 3 8B (Agente 2) com RAG e Tool da API...")
    analise_agente_2, grafico_b64 = executar_agente_2(dados["grupo"], contexto_rag)

    print("3. Renderizando HTML e gerando PDF...")
    html_final = Template(HTML_TEMPLATE).render(
        grupo=dados["grupo"],
        membros=dados["membros"],
        grafico_b64=grafico_b64,
        analise=analise_agente_2,
        fontes_rag=fontes_rag,
    )

    nome_grupo = dados["grupo"]["nome"] or "grupo_sem_nome"
    nome_limpo = re.sub(r"[^\w\-]+", "_", nome_grupo).strip("_")
    data_hoje = date.today().strftime("%Y-%m-%d")
    nome_arquivo = f"relatorio_{nome_limpo}_{data_hoje}.pdf"

    HTML(string=html_final).write_pdf(nome_arquivo)
    print(f"Sucesso! Arquivo salvo como: {nome_arquivo}")
