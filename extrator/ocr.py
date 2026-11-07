"""Renderização das páginas do PDF e OCR local (Tesseract)."""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass

import pymupdf
import pytesseract
from PIL import Image

DPI_PADRAO = 300


@dataclass
class Pagina:
    numero: int          # 1-based
    texto: str
    imagem: Image.Image  # mantida para reprocessamento (OCR mais forte / visão)


_PASTAS_WINDOWS = [
    r"C:\Program Files\Tesseract-OCR",
    r"C:\Program Files (x86)\Tesseract-OCR",
    os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR"),
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR"),
]
_EXECUTAVEIS = ("tesseract.exe", "tesseract")


def _executavel_na_pasta(pasta: str) -> str | None:
    for nome in _EXECUTAVEIS:
        c = os.path.join(pasta, nome)
        if os.path.isfile(c):
            return c
    return None


def configurar_tesseract(caminho: str | None) -> None:
    """Define o executável do Tesseract: o informado (arquivo .exe ou a pasta
    de instalação), o do PATH ou uma das pastas padrão do Windows."""
    if caminho:
        caminho = os.path.expandvars(caminho.strip().strip('"'))
        if os.path.isdir(caminho):
            exe = _executavel_na_pasta(caminho)
            if not exe:
                raise SystemExit(
                    f"A pasta informada em --tesseract existe, mas não contém tesseract.exe:\n"
                    f"  {caminho}\nConfira se é a pasta onde o Tesseract foi instalado "
                    f"(normalmente termina em 'Tesseract-OCR').")
            caminho = exe
        elif not os.path.isfile(caminho):
            raise SystemExit(
                f"O caminho informado em --tesseract não existe:\n  {caminho}\n"
                f"Confira se o nome está completo (ex.: ...\\Tesseract-OCR\\tesseract.exe).")
        pytesseract.pytesseract.tesseract_cmd = caminho
        return
    if shutil.which("tesseract"):
        return
    for pasta in _PASTAS_WINDOWS:
        exe = _executavel_na_pasta(pasta)
        if exe:
            pytesseract.pytesseract.tesseract_cmd = exe
            return


def verificar_tesseract() -> str:
    try:
        versao = str(pytesseract.get_tesseract_version())
    except pytesseract.TesseractNotFoundError as e:
        procurados = "\n".join(f"  {p}" for p in _PASTAS_WINDOWS)
        raise SystemExit(
            "Tesseract não encontrado. Ele não está no PATH nem nas pastas padrão:\n"
            f"{procurados}\n"
            "Instale-o (com o idioma português) ou informe a pasta de instalação com "
            "--tesseract \"C:\\...\\Tesseract-OCR\". Veja o README."
        ) from e
    if "por" not in pytesseract.get_languages(config=""):
        tessdata = os.path.join(os.path.dirname(pytesseract.pytesseract.tesseract_cmd), "tessdata")
        raise SystemExit(
            "O Tesseract está instalado, mas sem o idioma português ('por').\n"
            "Reinstale marcando 'Portuguese' em 'Additional language data', ou baixe o arquivo\n"
            "por.traineddata (https://github.com/tesseract-ocr/tessdata_fast) e copie para:\n"
            f"  {tessdata}"
        )
    return versao


def renderizar(pdf_path: str, dpi: int = DPI_PADRAO):
    """Gera (numero_pagina, imagem em tons de cinza) para cada página."""
    with pymupdf.open(pdf_path) as doc:
        for i, page in enumerate(doc, start=1):
            pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
            yield i, Image.frombytes("L", (pix.width, pix.height), pix.samples)


def renderizar_pagina(pdf_path: str, numero: int, dpi: int) -> Image.Image:
    with pymupdf.open(pdf_path) as doc:
        pix = doc[numero - 1].get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
        return Image.frombytes("L", (pix.width, pix.height), pix.samples)


def ocr(imagem: Image.Image, psm: int = 4) -> str:
    return pytesseract.image_to_string(imagem, lang="por", config=f"--psm {psm}")


def _poucas_palavras(texto: str) -> bool:
    return len(re.findall(r"[A-Za-zÀ-ú]{3,}", texto)) < 15


def corrigir_rotacao(imagem: Image.Image) -> Image.Image:
    """Usa a detecção de orientação do Tesseract para desvirar a página."""
    try:
        osd = pytesseract.image_to_osd(imagem, config="--psm 0")
    except pytesseract.TesseractError:
        return imagem
    m = re.search(r"Rotate: (\d+)", osd)
    angulo = int(m.group(1)) if m else 0
    return imagem.rotate(-angulo, expand=True) if angulo else imagem


def ler_paginas(pdf_path: str, dpi: int = DPI_PADRAO) -> list[Pagina]:
    paginas = []
    for numero, img in renderizar(pdf_path, dpi):
        texto = ocr(img)
        if _poucas_palavras(texto):
            # Página possivelmente digitalizada de lado/de cabeça para baixo.
            girada = corrigir_rotacao(img)
            if girada is not img:
                texto2 = ocr(girada)
                if len(texto2) > len(texto):
                    img, texto = girada, texto2
        paginas.append(Pagina(numero, texto, img))
    return paginas
