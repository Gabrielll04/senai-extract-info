"""Gravação na planilha seguindo o modelo (cria se não existir, senão acrescenta)."""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

MODELO = Path(__file__).resolve().parent.parent / "modelo" / "modelo_planilha.xlsx"
PRIMEIRA_LINHA_DADOS = 4
COL_MES_JAN = 6          # F
COL_OBS = 18             # R (mesclada com S)
COR_TIPO = {"PLACA": "FFFFFF00", "UBER": "FFBDD7EE"}  # cores usadas no modelo


@dataclass
class Linha:
    tipo: str                    # "PLACA" ou "UBER"
    evidencia: int | None
    passageiro: int | None
    km_por_mes: dict[int, float]  # mês (1-12) -> km
    observacoes: str = ""
    tipo_frota: str | None = None
    ano_frota: int | None = None


def _borda():
    fino = Side(style="thin")
    return Border(left=fino, right=fino, top=fino, bottom=fino)


def abrir_ou_criar(caminho: Path):
    if not caminho.exists():
        caminho.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(MODELO, caminho)
    return openpyxl.load_workbook(caminho)


def chaves_existentes(ws) -> set[tuple[str, int]]:
    chaves = set()
    for row in ws.iter_rows(min_row=PRIMEIRA_LINHA_DADOS, max_col=2, values_only=True):
        tipo, evid = row
        if tipo and evid is not None:
            try:
                chaves.add((str(tipo).strip().upper(), int(evid)))
            except (TypeError, ValueError):
                pass
    return chaves


def _proxima_linha(ws) -> int:
    ultima = PRIMEIRA_LINHA_DADOS - 1
    for r in range(PRIMEIRA_LINHA_DADOS, ws.max_row + 1):
        if any(ws.cell(r, c).value not in (None, "") for c in range(1, COL_OBS + 1)):
            ultima = r
    return ultima + 1


def escrever_linha(ws, r: int, linha: Linha) -> None:
    fill = PatternFill("solid", fgColor=COR_TIPO.get(linha.tipo, "FFFFFFFF"))
    fonte = Font(name="Calibri Light", size=11)
    valores = {1: linha.tipo, 2: linha.evidencia, 3: linha.passageiro,
               4: linha.tipo_frota, 5: linha.ano_frota, COL_OBS: linha.observacoes or None}
    for mes, km in linha.km_por_mes.items():
        valores[COL_MES_JAN + mes - 1] = round(km, 2)

    for c in range(1, COL_OBS + 2):  # A..S
        cel = ws.cell(r, c)
        cel.value = valores.get(c)
        cel.fill, cel.font, cel.border = fill, fonte, _borda()
        if c in (1, 5):
            cel.alignment = Alignment(horizontal="center")
        elif c in (2, 3, 4):
            cel.alignment = Alignment(horizontal="left")
        elif c == COL_OBS:
            cel.alignment = Alignment(horizontal="left", wrap_text=True, vertical="top")
        elif COL_MES_JAN <= c < COL_OBS:
            cel.number_format = "0.00"
    ws.merge_cells(start_row=r, start_column=COL_OBS, end_row=r, end_column=COL_OBS + 1)


def gravar(caminho: Path, linhas: list[Linha]) -> tuple[list[Linha], list[Linha]]:
    """Acrescenta as linhas. Retorna (gravadas, ignoradas por já existirem)."""
    wb = abrir_ou_criar(caminho)
    ws = wb.worksheets[0]
    existentes = chaves_existentes(ws)
    r = _proxima_linha(ws)
    gravadas, ignoradas = [], []
    for linha in linhas:
        chave = (linha.tipo, linha.evidencia)
        if linha.evidencia is not None and chave in existentes:
            ignoradas.append(linha)
            continue
        escrever_linha(ws, r, linha)
        existentes.add(chave)
        gravadas.append(linha)
        r += 1
    try:
        wb.save(caminho)
    except PermissionError as e:
        raise SystemExit(
            f"Não foi possível salvar '{caminho}'. A planilha está aberta no Excel? "
            "Feche-a e rode novamente."
        ) from e
    return gravadas, ignoradas
