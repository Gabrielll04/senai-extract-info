"""Orquestra: PDF -> OCR -> interpretação -> linhas da planilha + conferência."""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

from . import ocr as ocr_mod
from .parser import (Corrida, Documento, eh_recibo_uber, eh_relatorio,
                     interpretar_recibo_uber, interpretar_relatorio, recibo_completo)
from .planilha import Linha

_RE_POSSIVEL_CORRIDA = re.compile(r"Obrigado por viajar|Quil[ôo]metros|99\s*T[áa]xi|\b99Pop\b", re.I)


def _ler_corridas(doc: Documento, paginas, visao) -> None:
    for p in paginas:
        if not eh_recibo_uber(p.texto):
            if not eh_relatorio(p.texto) and _RE_POSSIVEL_CORRIDA.search(p.texto):
                doc.avisos_uber.append(
                    f"pág. {p.numero}: parece recibo de corrida, mas não foi reconhecido como Uber - conferir")
            continue

        corridas = interpretar_recibo_uber(p.texto, p.numero)
        if not recibo_completo(corridas):
            # 2ª tentativa: outro modo de segmentação do Tesseract
            for psm in (6, 11):
                tentativa = interpretar_recibo_uber(ocr_mod.ocr(p.imagem, psm=psm), p.numero)
                if recibo_completo(tentativa):
                    corridas = tentativa
                    break
        if not recibo_completo(corridas) and visao is not None:
            lidas = visao.ler_recibo_corrida(p.imagem)
            if lidas:
                corridas = [Corrida(d, km, p.numero, fonte=visao.nome) for d, km in lidas]
        for c in corridas:
            if c.data is None or c.km is None:
                falta = " e ".join(x for x, v in (("data", c.data), ("km", c.km)) if v is None)
                doc.avisos_uber.append(f"pág. {p.numero}: recibo Uber sem {falta} legível - conferir")
            doc.corridas.append(c)

    # Conferência com o valor de "Taxi" lançado no relatório
    validas = [c for c in doc.corridas if c.km is not None and c.data is not None]
    soma_recibos = round(sum(c.valor or 0 for c in doc.corridas), 2)
    if doc.valor_taxi_relatorio is not None:
        if not doc.corridas:
            doc.avisos_gerais.append(
                f"Relatório lança Táxi R$ {doc.valor_taxi_relatorio:.2f}, mas nenhum recibo Uber "
                "foi reconhecido - conferir")
        elif abs(soma_recibos - doc.valor_taxi_relatorio) > 0.05:
            doc.avisos_uber.append(
                f"Soma dos recibos Uber (R$ {soma_recibos:.2f}) difere do Táxi lançado no relatório "
                f"(R$ {doc.valor_taxi_relatorio:.2f}) - pode faltar recibo")
    elif validas:
        doc.avisos_uber.append("Recibos Uber encontrados, mas sem lançamento de Táxi lido no relatório - conferir")


def processar_pdf(caminho: Path, dpi: int = ocr_mod.DPI_PADRAO, visao=None,
                  pasta_texto: Path | None = None) -> Documento:
    doc = Documento(arquivo=caminho.name)
    paginas = ocr_mod.ler_paginas(str(caminho), dpi)
    if pasta_texto is not None:  # diagnóstico: texto bruto do OCR
        pasta_texto.mkdir(parents=True, exist_ok=True)
        with open(pasta_texto / f"{caminho.stem}.txt", "w", encoding="utf-8") as f:
            for p in paginas:
                f.write(f"\n===== página {p.numero} =====\n{p.texto}")

    def reocr(pagina, dpi_novo: int, psm: int) -> str:
        return ocr_mod.ocr(ocr_mod.renderizar_pagina(str(caminho), pagina.numero, dpi_novo), psm=psm)

    interpretar_relatorio(doc, paginas, reocr=reocr)
    _ler_corridas(doc, paginas, visao)
    return doc


def _mes_ano(it):
    """(mês, ano) de um Trecho (dia pode faltar) ou de uma Corrida."""
    if hasattr(it, "mes"):
        return it.mes, it.ano
    return (it.data.month, it.data.year) if it.data is not None else (None, None)


def _km_por_mes(itens) -> dict[int, float]:
    meses: dict[int, float] = defaultdict(float)
    for it in itens:
        mes, _ = _mes_ano(it)
        if mes is not None and it.km is not None:
            meses[mes] += it.km
    return {m: round(v, 2) for m, v in sorted(meses.items())}


def _anos(itens) -> set[int]:
    return {_mes_ano(it)[1] for it in itens if _mes_ano(it)[1] is not None}


def linhas_do_documento(doc: Documento, uber_tipo_frota=None, uber_ano_frota=None) -> list[Linha]:
    linhas = []
    if doc.trechos or doc.avisos_carro:
        obs = doc.avisos_gerais + doc.avisos_carro
        if len(_anos(doc.trechos)) > 1:
            obs.append(f"Trajetos em anos diferentes: {sorted(_anos(doc.trechos))}")
        linhas.append(Linha("PLACA", doc.viagem, doc.num_pessoal, _km_por_mes(doc.trechos),
                            "; ".join(obs)))
    if doc.corridas:
        obs = doc.avisos_gerais + doc.avisos_uber
        if len(_anos(doc.corridas)) > 1:
            obs.append(f"Corridas em anos diferentes: {sorted(_anos(doc.corridas))}")
        linhas.append(Linha("UBER", doc.viagem, doc.num_pessoal, _km_por_mes(doc.corridas),
                            "; ".join(obs), uber_tipo_frota, uber_ano_frota))
    return linhas


CABECALHO_CONFERENCIA = ["arquivo", "viagem", "nº pessoal", "nome", "tipo", "data",
                         "km", "valor (R$)", "placa", "página", "fonte", "aviso"]


def linhas_conferencia(doc: Documento) -> list[list]:
    base = [doc.arquivo, doc.viagem, doc.num_pessoal, doc.nome]
    out = []
    for t in doc.trechos:
        out.append(base + ["PLACA", t.rotulo_data, t.km, "", t.placa or "", t.pagina, "ocr", ""])
    for c in doc.corridas:
        out.append(base + ["UBER", f"{c.data:%d/%m/%Y}" if c.data else "", c.km if c.km is not None else "",
                           c.valor if c.valor is not None else "", "", c.pagina, c.fonte, ""])
    for tipo, avisos in (("GERAL", doc.avisos_gerais), ("PLACA", doc.avisos_carro),
                         ("UBER", doc.avisos_uber)):
        for a in avisos:
            out.append(base + [tipo, "", "", "", "", "", "", a])
    return out


def gravar_conferencia(caminho: Path, linhas: list[list]) -> None:
    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(CABECALHO_CONFERENCIA)
        for l in linhas:
            w.writerow([f"{v:g}".replace(".", ",") if isinstance(v, float) else v for v in l])
