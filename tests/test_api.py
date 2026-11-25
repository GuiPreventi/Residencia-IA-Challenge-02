import base64
from contextlib import contextmanager
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from fastapi.testclient import TestClient
from PIL import Image

from api import app
from cliente_graficos import gerar_grafico_evolucao
import database


class ApiGraficoTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_png_compativel_com_relatorio_e_cliente(self):
        historico = [
            {"data": "2026-08", "score_geral": 2.15},
            {"data": "2026-09", "score_geral": 2.40},
            {"data": "Atual", "score_geral": 2.97},
        ]
        resposta = self.client.post("/graficos/evolucao-score", json={"historico": historico})
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        png = base64.b64decode(dados["grafico_b64"], validate=True)
        with Image.open(io.BytesIO(png)) as imagem:
            self.assertEqual(imagem.format, "PNG")
            self.assertEqual(imagem.size, (1050, 450))
            imagem.verify()
        # O cliente retorna exatamente o valor que o template HTML espera.
        with patch("cliente_graficos.urlopen", return_value=io.BytesIO(resposta.content)) as chamada:
            self.assertEqual(gerar_grafico_evolucao(historico), dados["grafico_b64"])
        self.assertEqual(chamada.call_args.args[0].method, "POST")
        self.assertEqual(json.loads(chamada.call_args.args[0].data), {"historico": historico})

    def test_historico_do_banco_inclui_ponto_atual(self):
        # Banco temporário: não executa o script que apaga e repopula o banco.
        abrir_conexao = database.get_connection

        @contextmanager
        def conexao_de_teste():
            conexao = abrir_conexao()
            try:
                with conexao:
                    yield conexao
            finally:
                conexao.close()

        with tempfile.TemporaryDirectory() as pasta:
            with patch.object(database, "DB_PATH", Path(pasta) / "teste.db"), \
                    patch.object(database, "get_connection", side_effect=conexao_de_teste):
                database.init_db()
                equipe = database.criar_equipe("Equipe de teste")
                usuario = database.criar_usuario("teste", "hash_teste", id_equipe=equipe)
                database.salvar_relatorio_agente2(equipe, "2026-10", 2.75, .2, {}, {}, "", "")
                database.salvar_avaliacao_agente1(usuario, "2026-11-24", 2.97, .2, {}, {}, [])
                historico = database.buscar_dados_equipe_para_relatorio(equipe)["grupo"]["historico"]
        self.assertEqual(historico[-1], {"data": "Atual", "score_geral": 2.97})
        resposta = self.client.post("/graficos/evolucao-score", json={"historico": historico})
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(base64.b64decode(resposta.json()["grafico_b64"]).startswith(b"\x89PNG\r\n\x1a\n"))

    def test_historico_insuficiente_e_scores_nulos(self):
        for historico in (None, [], [{"data": "Atual", "score_geral": 3}],
                          [{"data": "2026-08", "score_geral": None},
                           {"data": "Atual", "score_geral": 3}]):
            with self.subTest(historico=historico):
                resposta = self.client.post("/graficos/evolucao-score", json={"historico": historico})
                self.assertEqual(resposta.status_code, 200)
                self.assertIsNone(resposta.json()["grafico_b64"])

    def test_dados_invalidos_retornam_422(self):
        for medicao in ({"data": "Atual", "score_geral": 6},
                        {"data": "Atual", "score_geral": 0},
                        {"data": "Atual", "score_geral": "NaN"},
                        {"data": "  ", "score_geral": 3},
                        {"score_geral": 3}):
            with self.subTest(medicao=medicao):
                resposta = self.client.post("/graficos/evolucao-score", json={"historico": [medicao]})
                self.assertEqual(resposta.status_code, 422)

    def test_cliente_distingue_falha_de_historico_insuficiente(self):
        falhas = [URLError("Conexão recusada"), TimeoutError(),
                  HTTPError("http://localhost", 422, "Dados inválidos", {}, io.BytesIO(b'{}'))]
        for falha in falhas:
            with self.subTest(falha=falha):
                with patch("cliente_graficos.urlopen", side_effect=falha):
                    with self.assertRaises(RuntimeError):
                        gerar_grafico_evolucao([])
        with patch("cliente_graficos.urlopen", return_value=io.BytesIO(b'{"grafico_b64": null}')):
            self.assertIsNone(gerar_grafico_evolucao([]))


if __name__ == "__main__":
    unittest.main()
