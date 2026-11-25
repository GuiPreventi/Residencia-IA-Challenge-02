import argparse
from database import (  # Ajuste para o nome do seu arquivo do banco, se diferente
    DB_PATH,
    init_db,
    criar_equipe,
    criar_usuario,
    salvar_avaliacao_agente1,
    salvar_relatorio_agente2,
)

parser = argparse.ArgumentParser(description="Cria dados fictícios para testar o Agente 2.")
parser.add_argument("--recriar", action="store_true", help="Apaga o banco existente antes de popular.")
args = parser.parse_args()

if DB_PATH.exists():
    if not args.recriar:
        raise SystemExit("Banco existente preservado. Use --recriar apenas para substituir os dados.")
    DB_PATH.unlink()

init_db()

# 1. Cria a equipe
id_eq = criar_equipe(
    "Squad Alpha - Engenharia",
    id_calendario="squad.alpha@group.calendar.google.com",
    id_teams="teams-channel-alpha-01",
)

# 2. Cria histórico anterior da equipe (para gerar o gráfico temporal no Bloco 1)
historico_anterior = [
    ("2026-08", 2.15, 0.22),
    ("2026-09", 2.40, 0.21),
    ("2026-10", 2.75, 0.20),
]
for data_rel, score, margem in historico_anterior:
    salvar_relatorio_agente2(
        id_equipe=id_eq,
        data_relatorio=data_rel,
        score_geral=score,
        margem_erro_geral=margem,
        score_pilares={},
        margem_erro_pilares={},
        analise="Relatório histórico anterior.",
        conclusao="Acompanhamento de rotina.",
    )

# 3. Cria 3 membros com histórico individual e múltiplas respostas do Agente 1
membros_teste = [
    {
        "login": "membro_alpha_01",
        "avaliacao_anterior": ("2026-10-20", 2.70),
        "atual": {
            "score_geral": 3.30,
            "margem": 0.35,
            "pilares": {"Exaustão": 3.9, "Distanciamento Mental": 3.2, "Prejuízo Cognitivo": 3.1, "Prejuízo Emocional": 3.0},
            "margens": {"Exaustão": 0.4, "Distanciamento Mental": 0.32, "Prejuízo Cognitivo": 0.30, "Prejuízo Emocional": 0.35},
            "respostas": [
                {
                    "pilar": "Exaustão",
                    "pergunta": "Como você tem se sentido em relação ao seu nível de energia no final do expediente?",
                    "resposta": "Tenho terminado o dia completamente esgotado, sem energia nem para atividades pessoais.",
                    "nota": 4,
                    "justificativa": "Relato explícito de esgotamento severo com impacto fora do trabalho.",
                },
                {
                    "pilar": "Prejuízo Cognitivo",
                    "pergunta": "Você tem notado dificuldade para manter o foco em tarefas complexas?",
                    "resposta": "Sim, com tantas reuniões picadas acabo perdendo o fio da meada no código.",
                    "nota": 3,
                    "justificativa": "Indica lapsos moderados de atenção associados à fragmentação da rotina.",
                },
            ],
        },
    },
    {
        "login": "membro_alpha_02",
        "avaliacao_anterior": ("2026-10-20", 2.35),
        "atual": {
            "score_geral": 2.65,
            "margem": 0.30,
            "pilares": {"Exaustão": 3.1, "Distanciamento Mental": 2.8, "Prejuízo Cognitivo": 2.4, "Prejuízo Emocional": 2.3},
            "margens": {"Exaustão": 0.35, "Distanciamento Mental": 0.28, "Prejuízo Cognitivo": 0.25, "Prejuízo Emocional": 0.30},
            "respostas": [
                {
                    "pilar": "Distanciamento Mental",
                    "pergunta": "Como você percebe seu entusiasmo com as entregas atuais da equipe?",
                    "resposta": "Gosto do projeto, mas o excesso de reuniões no fim da tarde tem me desanimado.",
                    "nota": 3,
                    "justificativa": "Sinal inicial de distanciamento ligado à gestão de tempo, mantendo vínculo com o projeto.",
                },
            ],
        },
    },
    {
        "login": "membro_alpha_03",
        "avaliacao_anterior": ("2026-10-20", 2.50),
        "atual": {
            "score_geral": 2.95,
            "margem": 0.32,
            "pilares": {"Exaustão": 3.5, "Distanciamento Mental": 2.9, "Prejuízo Cognitivo": 2.8, "Prejuízo Emocional": 2.6},
            "margens": {"Exaustão": 0.38, "Distanciamento Mental": 0.30, "Prejuízo Cognitivo": 0.29, "Prejuízo Emocional": 0.31},
            "respostas": [
                {
                    "pilar": "Exaustão",
                    "pergunta": "Você sente que consegue descansar adequadamente entre um dia de trabalho e outro?",
                    "resposta": "Tenho dormido pouco porque fico pensando nos prazos da próxima release.",
                    "nota": 4,
                    "justificativa": "Indica dificuldade de desconexão e recuperação prejudicada por pressão de prazos.",
                },
            ],
        },
    },
]

for m in membros_teste:
    uid = criar_usuario(m["login"], "senha_hash_123", id_equipe=id_eq)

    # Salva avaliação do mês passado (para aparecer histórico individual no Bloco 2)
    data_ant, score_ant = m["avaliacao_anterior"]
    salvar_avaliacao_agente1(uid, data_ant, score_ant, 0.30, {}, {}, [])

    # Salva avaliação atual completa
    at = m["atual"]
    salvar_avaliacao_agente1(
        id_usuario=uid,
        data="2026-11-24",
        score_geral=at["score_geral"],
        margem_erro_geral=at["margem"],
        score_pilares=at["pilares"],
        margem_erro_pilares=at["margens"],
        respostas=at["respostas"],
    )

print("Banco populado com sucesso com histórico de 4 meses e 3 membros!")
