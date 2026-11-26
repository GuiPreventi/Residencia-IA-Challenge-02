"""Dados e respostas de modelos destes testes são sempre simulados."""

import io
from pathlib import Path
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from urllib.error import URLError
from unittest.mock import patch

from fastapi.testclient import TestClient
from pypdf import PdfReader

import agente1
from api import app
import comunicacao_agentes as comunicacao
import database
from simulacao_agentes import coletar_simulado


class ComunicacaoTests(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.raiz = Path(self.pasta.name)
        patcher = patch.object(database, "DB_PATH", self.raiz / "teste.db")
        patcher.start()
        self.addCleanup(patcher.stop)
        database.init_db()
        self.cliente_api = TestClient(app)

        def transporte_api(pedido, **kwargs):
            resposta = self.cliente_api.post("/graficos/evolucao-score", content=pedido.data,
                                            headers={"Content-Type": "application/json"})
            self.assertEqual(resposta.status_code, 200)
            return io.BytesIO(resposta.content)

        transporte = patch("cliente_graficos.urlopen", side_effect=transporte_api)
        transporte.start()
        self.addCleanup(transporte.stop)

    def fluxo(self, **kwargs):
        return comunicacao.criar_fluxo(pasta_saida=self.raiz, saida=lambda *a: None, **kwargs)

    def test_coleta_salva_aciona_agente2_e_pdf_real(self):
        resultado = self.fluxo(simulado=True).invoke({})
        self.assertEqual(resultado["status"], "concluido", resultado.get("erro"))
        self.assertEqual(resultado["dados"]["id_avaliacao"], resultado["id_avaliacao"])
        self.assertEqual(len(resultado["dados"]["respostas"]), 12)
        self.assertIsNone(resultado["dados"]["margem_erro"])
        self.assertIsNone(resultado["grafico_b64"])
        texto = "\n".join(p.extract_text() for p in PdfReader(resultado["pdf"]).pages)
        self.assertIn("SIMULAÇÃO DE TESTE", texto)
        self.assertIn("Histórico insuficiente", texto)
        self.assertIn("Margens de erro não calculadas", texto)
        with database.get_connection() as conn:
            textos = conn.execute("SELECT Resposta, JustificativaAgente FROM Respostas").fetchall()
        self.assertTrue(all(not r[0] and not r[1] for r in textos))

    def test_consentimento_negado_nao_aciona_agente2(self):
        with patch("agente1.criar_cliente", return_value=object()), \
                patch("criaDoc.executar_agente_2") as analisar:
            resultado = self.fluxo(entrada=lambda pergunta: "n").invoke({})
        self.assertEqual(resultado["status"], "coleta_nao_salva")
        analisar.assert_not_called()
        self.assertNotIn("id_avaliacao", resultado)

    def test_encerramento_por_risco_nao_aciona_agente2(self):
        sessao = agente1.Sessao(str(database.DB_PATH), "Teste")
        sessao.encerrar_por_risco()
        with patch("agente1.criar_cliente", return_value=object()), \
                patch("agente1.conversar", return_value=sessao), \
                patch("criaDoc.executar_agente_2") as analisar:
            resultado = self.fluxo().invoke({})
        self.assertEqual(resultado["status"], "coleta_nao_salva")
        analisar.assert_not_called()

    def test_falha_na_gravacao_faz_rollback_e_nao_aciona_agente2(self):
        with patch("database.salvar_avaliacao_agente1", side_effect=sqlite3.IntegrityError("falha simulada")), \
                patch("criaDoc.executar_agente_2") as analisar:
            resultado = self.fluxo(simulado=True).invoke({})
        self.assertEqual(resultado["status"], "falha")
        analisar.assert_not_called()
        with database.get_connection() as conn:
            for tabela in ("Usuario", "Avaliacao", "Respostas", "Equipe"):
                self.assertEqual(conn.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0], 0)

    def test_falha_do_agente2_preserva_id_para_retomar(self):
        with patch("criaDoc.executar_agente_2", side_effect=RuntimeError("Ollama indisponível")):
            resultado = self.fluxo(simulado=True).invoke({})
        self.assertEqual(resultado["status"], "falha")
        id_avaliacao = resultado["id_avaliacao"]
        self.assertEqual(database.buscar_avaliacao_individual(id_avaliacao)["id_avaliacao"], id_avaliacao)
        with patch("simulacao_agentes.coletar_simulado") as coleta:
            retomado = self.fluxo(simulado=True).invoke({"id_avaliacao": id_avaliacao})
        coleta.assert_not_called()
        self.assertEqual(retomado["status"], "concluido", retomado.get("erro"))
        with database.get_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM Avaliacao").fetchone()[0], 1)

    def test_nao_mistura_dados_de_outra_pessoa(self):
        primeira = coletar_simulado()
        segunda = coletar_simulado()
        resultado = self.fluxo(simulado=True).invoke({"id_avaliacao": primeira.id_avaliacao})
        self.assertEqual(resultado["status"], "concluido", resultado.get("erro"))
        self.assertEqual(resultado["dados"]["identificador"], primeira.id)
        texto = "\n".join(p.extract_text() for p in PdfReader(resultado["pdf"]).pages)
        self.assertNotIn(segunda.id, texto)
        self.assertEqual(len(resultado["dados"]["historico"]), 1)

    def test_historico_individual_usa_api_real_e_incorpora_png(self):
        sessao = coletar_simulado()
        with database.get_connection() as conn:
            uid = conn.execute("SELECT IdUsuario FROM Avaliacao WHERE IdAvaliacao = ?", (sessao.id_avaliacao,)).fetchone()[0]
        id_atual = database.salvar_avaliacao_agente1(uid, "2026-T4", 3.0, None, {}, {}, [])
        cliente_api = TestClient(app)

        def chamar_api(pedido, **kwargs):
            resposta = cliente_api.post("/graficos/evolucao-score", content=pedido.data,
                                        headers={"Content-Type": "application/json"})
            self.assertEqual(resposta.status_code, 200)
            return io.BytesIO(resposta.content)

        with patch("cliente_graficos.urlopen", side_effect=chamar_api):
            resultado = self.fluxo(simulado=True).invoke({"id_avaliacao": id_atual})
        self.assertEqual(resultado["status"], "concluido", resultado.get("erro"))
        self.assertTrue(resultado["grafico_b64"])
        self.assertTrue(any(len(p.images) for p in PdfReader(resultado["pdf"]).pages))

    def test_coleta_parcial_nao_inventa_itens_ou_margem(self):
        sessao = agente1.Sessao(str(database.DB_PATH), "Parcial simulada")
        campo = next(iter(agente1.CAMPOS_BAT))
        sessao.valores[campo] = 3
        sessao.pulados = set(agente1.CAMPOS_BAT) - {campo}
        sessao.executar_ferramenta("finalizar_coleta", {})
        self.assertTrue(sessao.concluida)
        dados = database.buscar_avaliacao_individual(sessao.id_avaliacao)
        self.assertEqual(dados["itens_faltantes"], 11)
        self.assertEqual(len(dados["respostas"]), 1)
        self.assertIsNone(dados["margem_erro"])

    def test_avaliacao_inexistente_nao_inicia_analise(self):
        with patch("criaDoc.executar_agente_2") as analisar:
            resultado = self.fluxo(simulado=True).invoke({"id_avaliacao": 999})
        self.assertEqual(resultado["status"], "falha")
        analisar.assert_not_called()

    def test_api_indisponivel_nao_inventa_grafico(self):
        with patch("cliente_graficos.urlopen", side_effect=URLError("API indisponível simulada")):
            resultado = self.fluxo(simulado=True).invoke({})
        self.assertEqual(resultado["status"], "concluido", resultado.get("erro"))
        self.assertIsNone(resultado["grafico_b64"])

    def test_json_invalido_do_modelo_nao_vira_analise_ou_pdf(self):
        sessao = coletar_simulado()
        resposta = SimpleNamespace(message=SimpleNamespace(tool_calls=[], content="JSON INVALIDO SIMULADO"))
        with patch("criaDoc.buscar_contexto_completo_rag", return_value=("", [])), \
                patch("criaDoc.ollama.chat", return_value=resposta) as modelo:
            resultado = self.fluxo().invoke({"id_avaliacao": sessao.id_avaliacao})
        self.assertEqual(resultado["status"], "falha")
        self.assertNotIn("pdf", resultado)
        self.assertNotIn("analise", resultado)
        self.assertEqual(modelo.call_count, 4)

    def test_migracao_idempotente_preserva_dados(self):
        equipe = database.criar_equipe("Equipe preservada")
        with database.get_connection() as conn:
            conn.execute("ALTER TABLE Avaliacao DROP COLUMN ItensFaltantes")
        database.init_db()
        database.init_db()
        self.assertEqual(database.listar_equipes()[0]["id"], equipe)
        with database.get_connection() as conn:
            colunas = {r["name"] for r in conn.execute("PRAGMA table_info(Avaliacao)")}
        self.assertIn("ItensFaltantes", colunas)
