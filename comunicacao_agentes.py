"""Orquestrador em LangGraph: Agente 1 (coleta) -> SQLite -> Agente 2 (PDF geral da equipe)."""

import argparse
from pathlib import Path
import sys
from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph

import agente1
import criaDoc
import database


class Estado(TypedDict, total=False):
    id_equipe: int
    id_avaliacao: int
    status: str
    erro: str
    pdf: str


def criar_fluxo(*, pasta_saida: str | Path = ".", entrada=input, saida=print):
    """Monta o grafo LangGraph: START -> agente_1 -> agente_2 -> END.

    O estado compartilhado trafega apenas os IDs salvos (id_equipe e id_avaliacao),
    nunca o texto livre da conversa.
    """
    def executar_agente_1(estado: Estado) -> Estado:
        saida("[LangGraph] agente_1: iniciando coleta")
        sessao = agente1.conversar(
            agente1.criar_cliente(),
            entrada=entrada,
            saida=saida,
        )
        if (
            sessao is None
            or not sessao.concluida
            or sessao.id_avaliacao is None
            or sessao.id_equipe is None
        ):
            return {"status": "coleta_nao_salva"}

        saida(
            f"[LangGraph] coleta salva: avaliação {sessao.id_avaliacao} "
            f"(equipe ID {sessao.id_equipe} — {sessao.equipe})"
        )
        return {
            "id_avaliacao": sessao.id_avaliacao,
            "id_equipe": sessao.id_equipe,
            "status": "coleta_salva",
        }

    def executar_agente_2(estado: Estado) -> Estado:
        id_equipe = estado["id_equipe"]
        saida(f"[LangGraph] agente_2: gerando relatório geral da equipe {id_equipe}")
        pdf = criaDoc.gerar_relatorio_equipe(id_equipe=id_equipe, pasta_saida=pasta_saida)
        saida(f"[LangGraph] PDF geral da equipe gerado: {pdf}")
        return {"pdf": pdf, "status": "concluido"}

    def proteger(funcao):
        def executar(estado: Estado) -> Estado:
            try:
                return funcao(estado)
            except Exception as erro:
                return {"status": "falha", "erro": f"{type(erro).__name__}: {erro}"}
        return executar

    grafo = StateGraph(Estado)
    grafo.add_node("agente_1", proteger(executar_agente_1))
    grafo.add_node("agente_2", proteger(executar_agente_2))

    grafo.add_conditional_edges(
        START,
        lambda e: "agente_2" if e.get("id_equipe") else "agente_1",
    )
    grafo.add_conditional_edges(
        "agente_1",
        lambda e: "agente_2" if e.get("status") == "coleta_salva" else END,
    )
    grafo.add_edge("agente_2", END)
    return grafo.compile()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--equipe",
        type=int,
        default=None,
        help="ID da equipe para pular o Agente 1 e gerar direto o relatório no Agente 2.",
    )
    parser.add_argument("--banco", type=Path, help="Caminho do banco SQLite.")
    parser.add_argument("--saida", type=Path, default=Path("."), help="Pasta de saída para o PDF.")
    args = parser.parse_args()

    if args.banco:
        database.DB_PATH = args.banco
    database.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    database.init_db()

    estado_inicial: Estado = {"id_equipe": args.equipe} if args.equipe is not None else {}
    try:
        resultado = criar_fluxo(pasta_saida=args.saida).invoke(estado_inicial)
    except (KeyboardInterrupt, EOFError):
        print("Execução interrompida.")
        return 1

    if resultado.get("status") == "falha":
        print("Falha no fluxo:", resultado.get("erro"), file=sys.stderr)
        if resultado.get("id_equipe"):
            print(
                f"A coleta permanece salva na equipe {resultado['id_equipe']}. "
                f"Use --equipe {resultado['id_equipe']} para gerar o relatório novamente."
            )
        return 1

    if resultado.get("status") == "coleta_nao_salva":
        print("Coleta não salva; o Agente 2 não foi acionado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
