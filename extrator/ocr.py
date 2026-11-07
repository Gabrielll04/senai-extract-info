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


_CAMINHOS_WINDOWS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
]


def configurar_tesseract(caminho: str | None) -> None:
    """Define o executável do Tesseract: o informado, o do PATH ou o local
    padrão de instalação no Windows."""
    if caminho:
        pytesseract.pytesseract.tesseract_cmd = caminho
        return
    if shutil.which("tesseract"):
        return
    for c in _CAMINHOS_WINDOWS:
        if os.path.isfile(c):
            pytesseract.pytesseract.tesseract_cmd = c
            return


def verificar_tesseract() -> str:
    try:
        versao = str(pytesseract.get_tesseract_version())
    except pytesseract.TesseractNotFoundError as e:
        raise SystemExit(
            "Tesseract não encontrado. Instale-o (com o idioma português) ou "
            "informe o caminho com --tesseract. Veja o README."
        ) from e
    if "por" not in pytesseract.get_languages(config=""):
        raise SystemExit(
            "O Tesseract está instalado, mas sem o idioma português ('por'). "
            "Instale o pacote de idioma. Veja o README."
        )
    return versao


def renderizar(pdf_path: str, dpi: int = DPI_PADRAO):
    """Gera (numero_pagina, imagem em tons de cinza) para cada página."""
    with pymupdf.open(pdf_path) as doc:
        for i, page in enumerate(doc, start=1):
            pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
            yield i, Image.frombytes("L", (pix.width, pix.height), pix.samples)


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
