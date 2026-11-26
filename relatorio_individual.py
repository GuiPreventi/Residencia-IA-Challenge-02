"""PDF do protótipo individual; não agrega nem exibe avaliações de outras pessoas."""

from pathlib import Path

from jinja2 import Environment, select_autoescape


TEMPLATE = """
<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<style>
@page { size: A4; margin: 18mm; }
body { font: 11px sans-serif; line-height: 1.5; color: #24344b; }
h1 { color: #1a365d; font-size: 20px; } h2 { color: #2b6cb0; font-size: 14px; }
.aviso { background: #fff5e5; border-left: 4px solid #dd6b20; padding: 12px; }
table { border-collapse: collapse; width: 100%; } td, th { border: 1px solid #cbd5e0; padding: 6px; text-align: left; }
img { max-width: 100%; } .muted { color: #607080; }
</style>
<h1>Protótipo de relatório individual BAT</h1>
{% if simulado %}<p class="aviso"><strong>SIMULAÇÃO DE TESTE</strong> — Dados e respostas
dos modelos são fictícios. Nenhum Ollama ou documento RAG real foi consultado.</p>{% endif %}
<p class="aviso">Uso exploratório e experimental. A avaliação individual com BAT-12 não
deve ser usada para diagnóstico. Este documento não substitui avaliação profissional.</p>
<p><strong>Código anônimo:</strong> {{ dados.identificador }}<br>
<strong>Avaliação:</strong> {{ dados.id_avaliacao }}<br>
<strong>Equipe informada:</strong> {{ dados.equipe or 'Não informada' }}<br>
<strong>Período:</strong> {{ dados.periodo }}</p>
<h2>Dados salvos pelo agente 1</h2>
<p><strong>Score:</strong> {{ '%.2f'|format(dados.score_geral) if dados.score_geral is not none else 'Indisponível' }}<br>
<strong>Itens sem resposta:</strong> {{ dados.itens_faltantes }} de 12.</p>
{% if dados.itens_faltantes %}<p class="aviso">Resultado parcial: não representa o BAT-12 completo.</p>{% endif %}
<p class="muted">Margens de erro não calculadas pelo projeto. Não foram estimadas neste relatório.</p>
<table><tr><th>Pilar</th><th>Score registrado</th></tr>
{% for nome, pilar in dados.pilares.items() %}<tr><td>{{ nome }}</td>
<td>{{ '%.2f'|format(pilar.score) if pilar.score is not none else 'Indisponível' }}</td></tr>{% endfor %}</table>
<h2>Histórico individual</h2>
{% if grafico_b64 %}<img src="data:image/png;base64,{{ grafico_b64 }}" alt="Evolução individual">
{% elif medicoes_validas < 2 %}<p>Histórico insuficiente para gráfico: são necessárias duas medições com score.</p>
{% else %}<p>Não foi gerado gráfico para esta execução.</p>{% endif %}
<h2>Análise do agente 2</h2><p>{{ analise.analise_scores_e_historico }}</p>
<ul>{% for ponto in analise.pontos_de_atencao %}<li>{{ ponto }}</li>{% endfor %}</ul>
<p>{{ analise.conclusao_individual }}</p>
<h2>Referências consultadas</h2>
{% if fontes %}<ul>{% for fonte in fontes %}<li>{{ fonte }}</li>{% endfor %}</ul>
{% else %}<p>Nenhuma fonte real recuperada nesta execução.</p>{% endif %}
<h2>Itens registrados</h2><table><tr><th>Item BAT</th><th>Nota</th></tr>
{% for resposta in dados.respostas %}<tr><td>{{ resposta.pergunta }}</td><td>{{ resposta.nota }}</td></tr>{% endfor %}</table>
<p class="muted">O texto livre da conversa não é persistido nem incluído no PDF.</p>
</html>
"""


def gerar_pdf_individual(dados, analise, grafico_b64, fontes, pasta_saida, *, simulado=False) -> str:
    from ambiente_pdf import configurar_bibliotecas_pdf

    configurar_bibliotecas_pdf()
    from weasyprint import HTML

    pasta = Path(pasta_saida)
    pasta.mkdir(parents=True, exist_ok=True)
    nome = f"relatorio_individual_{dados['id_avaliacao']}.pdf"
    destino = pasta / nome
    ambiente = Environment(autoescape=select_autoescape(default_for_string=True))
    html = ambiente.from_string(TEMPLATE).render(
        dados=dados, analise=analise, grafico_b64=grafico_b64, fontes=fontes,
        simulado=simulado,
        medicoes_validas=sum(h['score_geral'] is not None for h in dados['historico']),
    )
    HTML(string=html).write_pdf(destino)
    return str(destino.resolve())
