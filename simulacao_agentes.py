"""Fixtures explícitas de teste. Não são avaliações ou recomendações reais."""

import json

import ollama


def coletar_simulado():
    import agente1
    import database

    sessao = agente1.Sessao(str(database.DB_PATH), "SIMULACAO - dados ficticios")
    notas = (2, 3, 2, 3, 2, 3, 3, 2, 3, 2, 3, 2)
    sessao.valores = dict(zip(agente1.CAMPOS_BAT, notas))
    sessao.executar_ferramenta("finalizar_coleta", {})
    if not sessao.concluida:
        raise RuntimeError("Não foi possível salvar a coleta simulada.")
    return sessao


def resposta_ollama_simulada(**kwargs):
    if "tools" in kwargs:
        return ollama.ChatResponse(message=ollama.Message(
            role="assistant", content="",
            tool_calls=[ollama.Message.ToolCall(function=ollama.Message.ToolCall.Function(
                name="solicitar_grafico_evolucao_api", arguments={},
            ))],
        ))
    conteudo = {
        "analise_scores_e_historico": "SIMULAÇÃO: resposta fixa para verificar a comunicação entre os agentes.",
        "pontos_de_atencao": ["SIMULAÇÃO: não constitui interpretação clínica dos dados."],
        "conclusao_individual": "SIMULAÇÃO: fluxo de integração executado com respostas artificiais.",
    }
    return ollama.ChatResponse(message=ollama.Message(
        role="assistant", content=json.dumps(conteudo, ensure_ascii=False),
    ))
