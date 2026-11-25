"""Configura as DLLs locais antes de importar o WeasyPrint no Windows."""

import os
from pathlib import Path
from xml.etree import ElementTree


def configurar_bibliotecas_pdf() -> None:
    if os.name != "nt":
        return
    runtime = Path(__file__).resolve().parent / ".runtime" / "ucrt64"
    diretorio_dlls = runtime / "bin"
    if diretorio_dlls.is_dir():
        configurados = os.environ.get("WEASYPRINT_DLL_DIRECTORIES", "")
        diretorios = [str(diretorio_dlls)]
        if configurados:
            diretorios.append(configurados)
        os.environ["WEASYPRINT_DLL_DIRECTORIES"] = os.pathsep.join(diretorios)

        # Mantém também o cache de fontes dentro do projeto.
        fontes = runtime / "etc" / "fonts" / "fonts.conf"
        if fontes.is_file() and "FONTCONFIG_FILE" not in os.environ:
            cache = runtime.parent / "cache" / "fontconfig"
            cache.mkdir(parents=True, exist_ok=True)
            config = runtime.parent / "fontconfig.conf"
            raiz = ElementTree.Element("fontconfig")
            ElementTree.SubElement(raiz, "cachedir").text = cache.as_posix()
            ElementTree.SubElement(raiz, "include").text = fontes.as_posix()
            ElementTree.ElementTree(raiz).write(config, encoding="utf-8", xml_declaration=True)
            os.environ["FONTCONFIG_FILE"] = str(config)
            os.environ.setdefault("FONTCONFIG_PATH", str(fontes.parent))
