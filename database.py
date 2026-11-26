import sqlite3
from pathlib import Path
import json
from contextlib import nullcontext

DB_PATH = Path("burnout_prototype.db")


# =====================================================================
# FUNÇÕES DE ESCRITA (Admin e Agente 1)
# =====================================================================
def criar_equipe(nome: str, id_calendario: str | None = None, id_teams: str | None = None) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO Equipe (NomeEquipe, IdCalendarioGoogle, IdEquipeTeams) VALUES (?, ?, ?)",
            (nome, id_calendario, id_teams),
        )
        return cur.lastrowid


def listar_equipes() -> list[dict]:
    """Retorna as equipes cadastradas no banco em ordem de criação, com contagem de avaliações."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                e.IdEquipe,
                e.NomeEquipe,
                COUNT(DISTINCT CASE WHEN u.IsRH = 0 AND a.IdAvaliacao IS NOT NULL THEN u.IdUsuario END) AS MembrosAvaliados,
                COUNT(CASE WHEN u.IsRH = 0 THEN a.IdAvaliacao END) AS TotalAvaliacoes
            FROM Equipe e
            LEFT JOIN Usuario u ON u.IdEquipe = e.IdEquipe
            LEFT JOIN Avaliacao a ON a.IdUsuario = u.IdUsuario
            GROUP BY e.IdEquipe, e.NomeEquipe
            ORDER BY e.IdEquipe ASC
            """
        ).fetchall()
        return [
            {
                "id": r["IdEquipe"],
                "nome": r["NomeEquipe"],
                "membros_avaliados": r["MembrosAvaliados"],
                "total_avaliacoes": r["TotalAvaliacoes"],
            }
            for r in rows
        ]


def criar_usuario(login: str, senha: str, id_equipe: int | None = None, is_rh: int = 0) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO Usuario (Login, Senha, IsRH, IdEquipe) VALUES (?, ?, ?, ?)",
            (login, senha, is_rh, id_equipe),
        )
        return cur.lastrowid


def salvar_avaliacao_agente1(
    id_usuario: int,
    data: str,
    score_geral: float | None,
    margem_erro_geral: float | None,
    score_pilares: dict,
    margem_erro_pilares: dict,
    respostas: list[dict],
    itens_faltantes: int = 0,
    _conn: sqlite3.Connection | None = None,
) -> int:
    """Salva a avaliação individual e todas as respostas do Agente 1 na mesma transação."""
    with (get_connection() if _conn is None else nullcontext(_conn)) as conn:
        cur = conn.execute(
            """
            INSERT INTO Avaliacao (
                IdUsuario, Data, ScoreGeral, MargemErroGeral, ScorePilaresJSON, MargemErroPilaresJSON,
                ItensFaltantes
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                id_usuario,
                data,
                score_geral,
                margem_erro_geral,
                json.dumps(score_pilares, ensure_ascii=False),
                json.dumps(margem_erro_pilares, ensure_ascii=False),
                itens_faltantes,
            ),
        )
        id_avaliacao = cur.lastrowid

        for r in respostas:
            conn.execute(
                """
                INSERT INTO Respostas (
                    IdAvaliacao, Pilar, Pergunta, Resposta, Nota, JustificativaAgente
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    id_avaliacao,
                    r["pilar"],
                    r["pergunta"],
                    r["resposta"],
                    r["nota"],
                    r["justificativa"],
                ),
            )
        return id_avaliacao


def salvar_coleta_agente1(id_anonimo, equipe, periodo, score_geral, score_pilares,
                         respostas, itens_faltantes):
    """Salva equipe, usuário, avaliação e respostas em uma única transação."""
    nome = " ".join(str(equipe).split()).strip()
    with get_connection() as conn:
        linha = conn.execute(
            "SELECT IdEquipe FROM Equipe WHERE LOWER(TRIM(NomeEquipe)) = LOWER(?)", (nome,)
        ).fetchone()
        id_equipe = linha["IdEquipe"] if linha else conn.execute(
            "INSERT INTO Equipe (NomeEquipe) VALUES (?)", (nome,)
        ).lastrowid
        id_usuario = conn.execute(
            "INSERT INTO Usuario (Login, Senha, IdEquipe) VALUES (?, ?, ?)",
            (id_anonimo, "-", id_equipe),
        ).lastrowid
        id_avaliacao = salvar_avaliacao_agente1(
            id_usuario, periodo, score_geral, None, score_pilares,
            {p: None for p in score_pilares}, respostas,
            itens_faltantes=itens_faltantes, _conn=conn,
        )
    return id_avaliacao


def buscar_avaliacao_individual(id_avaliacao: int) -> dict:
    """Lê exclusivamente a avaliação solicitada e o histórico desse usuário até ela."""
    with get_connection() as conn:
        row = conn.execute(
            """SELECT a.*, u.Login, e.NomeEquipe FROM Avaliacao a
               JOIN Usuario u ON u.IdUsuario = a.IdUsuario
               LEFT JOIN Equipe e ON e.IdEquipe = u.IdEquipe
               WHERE a.IdAvaliacao = ?""", (id_avaliacao,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Avaliação {id_avaliacao} não encontrada.")
        scores = json.loads(row["ScorePilaresJSON"] or "{}")
        margens = json.loads(row["MargemErroPilaresJSON"] or "{}")
        historico = conn.execute(
            """SELECT Data, ScoreGeral FROM Avaliacao
               WHERE IdUsuario = ? AND IdAvaliacao <= ? ORDER BY IdAvaliacao""",
            (row["IdUsuario"], id_avaliacao),
        ).fetchall()
        respostas = conn.execute(
            "SELECT Pilar, Pergunta, Nota FROM Respostas WHERE IdAvaliacao = ? ORDER BY IdRespostas",
            (id_avaliacao,),
        ).fetchall()
        return {
            "id_avaliacao": id_avaliacao, "identificador": row["Login"],
            "equipe": row["NomeEquipe"], "periodo": row["Data"],
            "score_geral": row["ScoreGeral"], "margem_erro": row["MargemErroGeral"],
            "itens_faltantes": row["ItensFaltantes"],
            "pilares": {p: {"score": v, "margem_erro": margens.get(p)} for p, v in scores.items()},
            "historico": [{"data": h["Data"], "score_geral": h["ScoreGeral"]} for h in historico],
            "respostas": [{"pilar": r["Pilar"], "pergunta": r["Pergunta"], "nota": r["Nota"]}
                          for r in respostas],
        }


# =====================================================================
# FUNÇÕES DE LEITURA E ESCRITA DO AGENTE 2
# =====================================================================
def buscar_dados_equipe_para_relatorio(id_equipe: int) -> dict:
    """Busca os dados do banco, consolida os scores do grupo e monta o dicionário para o Agente 2 e o PDF."""
    with get_connection() as conn:
        equipe = conn.execute(
            "SELECT * FROM Equipe WHERE IdEquipe = ?", (id_equipe,)
        ).fetchone()
        if not equipe:
            raise ValueError(f"Equipe {id_equipe} não encontrada.")

        # 1. Histórico anterior da equipe (para o gráfico temporal)
        historico_rows = conn.execute(
            "SELECT DataRelatorio, ScoreGeral FROM RelatorioEquipe WHERE IdEquipe = ? ORDER BY DataRelatorio ASC",
            (id_equipe,),
        ).fetchall()
        historico_grupo = [
            {"data": row["DataRelatorio"], "score_geral": row["ScoreGeral"]}
            for row in historico_rows
        ]

        # 2. Membros da equipe (ignora usuários marcados como RH)
        usuarios = conn.execute(
            "SELECT IdUsuario, Login FROM Usuario WHERE IdEquipe = ? AND IsRH = 0",
            (id_equipe,),
        ).fetchall()

        membros = []
        for idx, user in enumerate(usuarios, start=1):
            avaliacoes = conn.execute(
                "SELECT * FROM Avaliacao WHERE IdUsuario = ? ORDER BY Data ASC",
                (user["IdUsuario"],),
            ).fetchall()

            if not avaliacoes:
                continue

            ultima = avaliacoes[-1]
            scores_p = json.loads(ultima["ScorePilaresJSON"]) if ultima["ScorePilaresJSON"] else {}
            margens_p = json.loads(ultima["MargemErroPilaresJSON"]) if ultima["MargemErroPilaresJSON"] else {}

            pilares_formatados = {
                pilar: {"score": scores_p.get(pilar), "margem_erro": margens_p.get(pilar)}
                for pilar in scores_p
            }

            respostas_rows = conn.execute(
                "SELECT Pergunta, Resposta, Nota, JustificativaAgente FROM Respostas WHERE IdAvaliacao = ?",
                (ultima["IdAvaliacao"],),
            ).fetchall()

            membros.append({
                "identificador": f"Membro {idx:02d}",
                "score_geral": ultima["ScoreGeral"],
                "margem_erro": ultima["MargemErroGeral"],
                "pilares": pilares_formatados,
                "historico": [
                    {"data": a["Data"], "score_geral": a["ScoreGeral"]}
                    for a in avaliacoes
                ],
                "interacoes_agente_1": [
                    {
                        "pergunta": r["Pergunta"],
                        "resposta": r["Resposta"],
                        "nota": r["Nota"],
                        "justificativa": r["JustificativaAgente"],
                    }
                    for r in respostas_rows
                ],
            })

        # 3. Consolida o score geral e os pilares do grupo a partir da última avaliação de cada membro
        scores_validos = [m["score_geral"] for m in membros if m["score_geral"] is not None]
        score_medio_grupo = sum(scores_validos) / len(scores_validos) if scores_validos else None

        pilares_grupo = {}
        nomes_pilares = [
            "Exaustão",
            "Distanciamento Mental",
            "Prejuízo Cognitivo",
            "Prejuízo Emocional",
        ]
        for pilar in nomes_pilares:
            vals = [
                m["pilares"][pilar]["score"]
                for m in membros
                if pilar in m["pilares"] and m["pilares"][pilar]["score"] is not None
            ]
            if vals:
                pilares_grupo[pilar] = {
                    "score": sum(vals) / len(vals),
                    "margem_erro": 0.20,  # Placeholder para o cálculo real da margem de erro do grupo
                }

        # Adiciona o ponto atual no histórico para o gráfico exibir a tendência até o ciclo presente
        if score_medio_grupo is not None:
            historico_grupo.append({"data": "Atual", "score_geral": round(score_medio_grupo, 2)})

        return {
            "grupo": {
                "nome": equipe["NomeEquipe"],
                "score_geral": score_medio_grupo,
                "margem_erro": 0.20 if score_medio_grupo is not None else None,
                "pilares": pilares_grupo,
                "historico": historico_grupo,
            },
            "membros": membros,
        }


def salvar_relatorio_agente2(
    id_equipe: int,
    data_relatorio: str,
    score_geral: float | None,
    margem_erro_geral: float | None,
    score_pilares: dict,
    margem_erro_pilares: dict,
    analise: str,
    conclusao: str,
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO RelatorioEquipe (
                IdEquipe, DataRelatorio, ScoreGeral, MargemErroGeral,
                ScorePilaresJSON, MargemErroPilaresJSON,
                AnaliseAgente, ConclusaoAgente
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                id_equipe,
                data_relatorio,
                score_geral,
                margem_erro_geral,
                json.dumps(score_pilares, ensure_ascii=False),
                json.dumps(margem_erro_pilares, ensure_ascii=False),
                analise,
                conclusao,
            ),
        )
        return cur.lastrowid


# =====================================================================
# EXCLUSÃO EM CASCATA (LGPD)
# =====================================================================
def deletar_usuario(id_usuario: int) -> None:
    """Apaga o usuário e, automaticamente, todas as suas avaliações e respostas."""
    with get_connection() as conn:
        conn.execute("DELETE FROM Usuario WHERE IdUsuario = ?", (id_usuario,))


class ConexaoSQLite(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def get_connection() -> sqlite3.Connection:
    """Abre uma conexão configurada com o SQLite."""
    conn = sqlite3.connect(DB_PATH, factory=ConexaoSQLite)
    conn.row_factory = sqlite3.Row  # Permite acessar colunas pelo nome: row["NomeEquipe"]
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def init_db() -> None:
    """Cria as tabelas do banco caso ainda não existam."""
    schema_sql = """
    CREATE TABLE IF NOT EXISTS Equipe (
        IdEquipe INTEGER PRIMARY KEY AUTOINCREMENT,
        NomeEquipe TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS Usuario (
        IdUsuario INTEGER PRIMARY KEY AUTOINCREMENT,
        Login TEXT NOT NULL UNIQUE,
        Senha TEXT NOT NULL,
        IsRH INTEGER NOT NULL DEFAULT 0, -- 0 = Colaborador, 1 = RH
        IdEquipe INTEGER,
        FOREIGN KEY (IdEquipe) REFERENCES Equipe(IdEquipe) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS Avaliacao (
        IdAvaliacao INTEGER PRIMARY KEY AUTOINCREMENT,
        IdUsuario INTEGER NOT NULL,
        Data TEXT NOT NULL, -- Formato recomendado: YYYY-MM-DD
        ScoreGeral REAL,
        MargemErroGeral REAL,
        ScorePilaresJSON TEXT,      -- Ex: {"Exaustão": 3.8, "Distanciamento Mental": 3.1, ...}
        MargemErroPilaresJSON TEXT, -- Ex: {"Exaustão": 0.4, "Distanciamento Mental": 0.3, ...}
        FOREIGN KEY (IdUsuario) REFERENCES Usuario(IdUsuario) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS Respostas (
        IdRespostas INTEGER PRIMARY KEY AUTOINCREMENT,
        IdAvaliacao INTEGER NOT NULL,
        Pilar TEXT NOT NULL,
        Pergunta TEXT NOT NULL,
        Resposta TEXT NOT NULL,
        Nota INTEGER NOT NULL,
        JustificativaAgente TEXT NOT NULL,
        FOREIGN KEY (IdAvaliacao) REFERENCES Avaliacao(IdAvaliacao) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS RelatorioEquipe (
        IdRelatorio INTEGER PRIMARY KEY AUTOINCREMENT,
        IdEquipe INTEGER NOT NULL,
        DataRelatorio TEXT NOT NULL, -- Formato recomendado: YYYY-MM ou YYYY-MM-DD
        ScoreGeral REAL,
        MargemErroGeral REAL,
        ScorePilaresJSON TEXT,
        MargemErroPilaresJSON TEXT,
        AnaliseAgente TEXT,
        ConclusaoAgente TEXT,
        FOREIGN KEY (IdEquipe) REFERENCES Equipe(IdEquipe) ON DELETE CASCADE
    );
    """

    with get_connection() as conn:
        conn.executescript(schema_sql)
        colunas = [c["name"] for c in conn.execute("PRAGMA table_info(Avaliacao)")]
        if "ItensFaltantes" not in colunas:
            conn.execute("ALTER TABLE Avaliacao ADD COLUMN ItensFaltantes INTEGER DEFAULT 0")
        colunas_equipe = {c["name"] for c in conn.execute("PRAGMA table_info(Equipe)")}
        for coluna in ("IdCalendarioGoogle", "IdEquipeTeams"):
            if coluna not in colunas_equipe:
                conn.execute(f"ALTER TABLE Equipe ADD COLUMN {coluna} TEXT")


if __name__ == "__main__":
    init_db()
    print(f"Banco de dados criado/verificado com sucesso em: {DB_PATH.resolve()}")
