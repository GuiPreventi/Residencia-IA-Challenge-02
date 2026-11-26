"""Protótipo terminal: LangGraph coordena coleta salva -> agente 2 -> PDF individual."""

import argparse
from pathlib import Path
import sys
from typing_extensions import TypedDict
from unittest.mock import patch

from langgraph.graph import END, START, StateGraph

import agente1
import criaDoc
import database
from relatorio_individual import gerar_pdf_individual


class Estado(TypedDict, total=False):
    id_avaliacao: int
    status: str
    erro: str
    dados: dict
    contexto: str
    fontes: list[str]
    analise: dict
    grafico_b64: str | None
    pdf: str


def criar_fluxo(*, simulado=False, pasta_saida="relatorios", entrada=input, saida=print):
    """O estado compartilhado contém o ID salvo, nunca o texto livre da conversa."""
    def coleta(estado):
        saida("[LangGraph] agente_1: iniciando coleta" + (" SIMULADA" if simulado else ""))
        if simulado:
            from simulacao_agentes import coletar_simulado
            sessao = coletar_simulado()
        else:
            termo = agente1.TERMO_CONSENTIMENTO.replace(
                "- Os resultados só aparecem em relatórios POR EQUIPE (médias), nunca individuais.\n"
                "  Equipes com poucas respostas não aparecem sozinhas no relatório.",
                "- Este protótipo gera um PDF INDIVIDUAL experimental após salvar a coleta.\n"
                "  Não se trata de diagnóstico. Nenhum resultado de outra pessoa é incluído.",
            )
            sessao = agente1.conversar(agente1.criar_cliente(), entrada=entrada, saida=saida,
                                      termo_consentimento=termo)
        if sessao is None or not sessao.concluida or sessao.id_avaliacao is None:
            return {"status": "coleta_nao_salva"}
        # O ID só é definido pelo agente 1 após o commit da transação SQLite.
        saida(f"[LangGraph] coleta salva: avaliação {sessao.id_avaliacao}")
        return {"id_avaliacao": sessao.id_avaliacao, "status": "coleta_salva"}

    def ler_avaliacao(estado):
        dados = database.buscar_avaliacao_individual(estado["id_avaliacao"])
        return {"dados": dados, "status": "avaliacao_carregada"}

    def consultar_rag(estado):
        if simulado:
            return {"contexto": "SIMULAÇÃO: nenhum documento de referência real consultado.", "fontes": []}
        contexto, fontes = criaDoc.buscar_contexto_completo_rag(estado["dados"])
        return {"contexto": contexto, "fontes": fontes}

    def analisar(estado):
        saida("[LangGraph] agente_2: analisando exclusivamente a avaliação salva")
        if simulado:
            from simulacao_agentes import resposta_ollama_simulada
            with patch("criaDoc.ollama.chat", side_effect=resposta_ollama_simulada):
                analise, grafico = criaDoc.executar_agente_2(estado["dados"], estado["contexto"], individual=True)
        else:
            analise, grafico = criaDoc.executar_agente_2(estado["dados"], estado["contexto"], individual=True)
        return {"analise": analise.model_dump(), "grafico_b64": grafico, "status": "analisada"}

    def gerar_pdf(estado):
        pdf = gerar_pdf_individual(
            estado["dados"], criaDoc.AnaliseIndividual.model_validate(estado["analise"]),
            estado["grafico_b64"], estado["fontes"], pasta_saida, simulado=simulado,
        )
        saida(f"[LangGraph] PDF gerado: {pdf}")
        return {"pdf": pdf, "status": "concluido"}

    def proteger(funcao):
        def executar(estado):
            try:
                return funcao(estado)
            except Exception as erro:
                # Erro não vira análise inventada; o ID permite retomar após a falha.
                return {"status": "falha", "erro": f"{type(erro).__name__}: {erro}"}
        return executar

    grafo = StateGraph(Estado)
    for nome, funcao in (("agente_1", coleta), ("ler_avaliacao", ler_avaliacao),
                         ("rag", consultar_rag), ("agente_2", analisar), ("pdf", gerar_pdf)):
        grafo.add_node(nome, proteger(funcao))
    grafo.add_conditional_edges(START, lambda e: "ler_avaliacao" if e.get("id_avaliacao") else "agente_1")
    grafo.add_conditional_edges("agente_1", lambda e: "ler_avaliacao" if e.get("status") == "coleta_salva" else END)
    for atual, proximo in (("ler_avaliacao", "rag"), ("rag", "agente_2"), ("agente_2", "pdf")):
        grafo.add_conditional_edges(atual, lambda e, destino=proximo: END if e.get("status") == "falha" else destino)
    grafo.add_edge("pdf", END)
    return grafo.compile()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulado", action="store_true", help="Usa coleta e modelos fictícios, identificados no PDF.")
    parser.add_argument("--avaliacao", type=int, help="Retoma uma avaliação já salva sem repetir a coleta.")
    parser.add_argument("--banco", type=Path, help="Caminho do SQLite.")
    parser.add_argument("--saida", type=Path, help="Pasta para os PDFs.")
    args = parser.parse_args()
    if args.simulado:
        print("SIMULAÇÃO DE TESTE: dados e respostas artificiais; nenhum Ollama ou RAG real será consultado.")
        database.DB_PATH = args.banco or Path("simulacao/burnout_prototype.db")
    elif args.banco:
        database.DB_PATH = args.banco
    database.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    database.init_db()
    saida = args.saida or Path("relatorios/simulacao" if args.simulado else "relatorios")
    estado = {"id_avaliacao": args.avaliacao} if args.avaliacao else {}
    try:
        resultado = criar_fluxo(simulado=args.simulado, pasta_saida=saida).invoke(estado)
    except (KeyboardInterrupt, EOFError):
        print("Execução interrompida. Nenhuma análise será inventada.")
        return 1
    if resultado["status"] == "falha":
        print("Falha no fluxo:", resultado["erro"], file=sys.stderr)
        if resultado.get("id_avaliacao"):
            print(f"A avaliação {resultado['id_avaliacao']} permanece salva. Use --avaliacao para retomar.")
        return 1
    if resultado["status"] == "coleta_nao_salva":
        print("Coleta não salva; o agente 2 não foi acionado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
