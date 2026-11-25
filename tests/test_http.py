"""Verifica o cliente contra um servidor Uvicorn real, em porta temporária."""

import base64
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.error import URLError
from urllib.request import urlopen

from PIL import Image

from cliente_graficos import gerar_grafico_evolucao


class HttpRealTests(unittest.TestCase):
    def test_cliente_recebe_png_por_http(self):
        raiz = Path(__file__).resolve().parents[1]
        with socket.socket() as porta_livre:
            porta_livre.bind(("127.0.0.1", 0))
            porta = porta_livre.getsockname()[1]
        base_url = f"http://127.0.0.1:{porta}"
        with tempfile.TemporaryDirectory() as pasta:
            ambiente = dict(os.environ, MPLCONFIGDIR=pasta)
            with tempfile.TemporaryFile() as log:
                processo = subprocess.Popen(
                    [sys.executable, "-B", "-m", "uvicorn", "api:app", "--host", "127.0.0.1", "--port", str(porta)],
                    cwd=raiz, env=ambiente, stdout=log, stderr=log,
                )
                try:
                    limite = time.monotonic() + 25
                    while True:
                        try:
                            with urlopen(base_url + "/health", timeout=1) as resposta:
                                self.assertEqual(json.load(resposta), {"status": "ok"})
                            break
                        except (URLError, TimeoutError):
                            if processo.poll() is not None or time.monotonic() >= limite:
                                log.seek(0)
                                self.fail("API não iniciou: " + log.read().decode(errors="replace"))
                            time.sleep(0.1)
                    with patch.dict(os.environ, {"GRAFICOS_API_URL": base_url}):
                        grafico = gerar_grafico_evolucao([
                            {"data": "2026-10", "score_geral": 2.75},
                            {"data": "Atual", "score_geral": 2.97},
                        ])
                        self.assertIsNone(gerar_grafico_evolucao([]))
                    with Image.open(io.BytesIO(base64.b64decode(grafico, validate=True))) as imagem:
                        self.assertEqual(imagem.format, "PNG")
                        self.assertEqual(imagem.size, (1050, 450))
                        imagem.verify()
                finally:
                    processo.terminate()
                    try:
                        processo.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        processo.kill()
                        processo.wait(timeout=5)
