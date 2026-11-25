"""Instala Pango e dependências oficiais do MSYS2 somente em .runtime/.

Execute com Python 3.14+ (suporte nativo a arquivos .tar.zst).
"""

import hashlib
import io
import json
from pathlib import Path
import re
import struct
import sys
import tarfile
from urllib.request import urlopen


REPOSITORIO = "https://repo.msys2.org/mingw/ucrt64/"
DESTINO = Path(__file__).resolve().parent / ".runtime"


def instalar():
    if sys.platform != "win32" or struct.calcsize("P") != 8:
        raise RuntimeError("Este instalador requer Windows com Python de 64 bits.")
    if sys.version_info < (3, 14):
        raise RuntimeError("Execute este instalador com Python 3.14 ou superior para ler pacotes .tar.zst.")
    DESTINO.mkdir(exist_ok=True)
    print("Consultando o repositório oficial do MSYS2...", flush=True)
    with urlopen(REPOSITORIO + "ucrt64.db", timeout=60) as resposta:
        indice = resposta.read()
    pacotes = {}
    with tarfile.open(fileobj=io.BytesIO(indice), mode="r:*") as arquivo:
        for membro in arquivo:
            if membro.name.endswith("/desc"):
                conteudo = arquivo.extractfile(membro).read().decode("utf-8")
                partes = conteudo.strip().split("\n\n")
                dados = {}
                for parte in partes:
                    linhas = parte.splitlines()
                    dados[linhas[0].strip("%")] = linhas[1:]
                pacotes[dados["NAME"][0]] = dados

    selecionados = {}

    def incluir(nome):
        nome = re.split(r"[<>=]", nome)[0]
        if nome in selecionados:
            return
        if nome not in pacotes:
            raise RuntimeError(f"Dependência não encontrada no repositório: {nome}")
        dados = pacotes[nome]
        selecionados[nome] = dados
        for dependencia in dados.get("DEPENDS", []):
            incluir(dependencia)

    incluir("mingw-w64-ucrt-x86_64-pango")
    total = sum(int(p["CSIZE"][0]) for p in selecionados.values())
    print(f"Instalando {len(selecionados)} pacotes ({total / 1024**2:.1f} MB) em {DESTINO}", flush=True)
    manifesto = []
    for nome, pacote in selecionados.items():
        filename = pacote["FILENAME"][0]
        print(f"Baixando {filename}", flush=True)
        with urlopen(REPOSITORIO + filename, timeout=120) as resposta:
            conteudo = resposta.read()
        esperado = pacote["SHA256SUM"][0]
        if hashlib.sha256(conteudo).hexdigest() != esperado:
            raise RuntimeError(f"SHA256 inválido para {filename}")
        with tarfile.open(fileobj=io.BytesIO(conteudo), mode="r:*") as arquivo:
            # Mantém somente arquivos do prefixo UCRT64, com extração segura.
            membros = [m for m in arquivo if m.name.startswith("ucrt64/")]
            arquivo.extractall(DESTINO, members=membros, filter="data")
        manifesto.append({"pacote": nome, "arquivo": filename, "sha256": esperado})
    (DESTINO / "manifesto.json").write_text(json.dumps(manifesto, indent=2), encoding="utf-8")
    print("Bibliotecas nativas instaladas.", flush=True)


if __name__ == "__main__":
    instalar()
