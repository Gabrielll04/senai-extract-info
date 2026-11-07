#!/usr/bin/env python3
"""Extrai distâncias percorridas (carro próprio e Uber) de PDFs digitalizados
de prestação de contas de viagem e lança na planilha de gases de efeito estufa.

Uso:
    python extrair_viagens.py PASTA_OU_PDFS... -o planilha.xlsx
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from extrator import ocr
from extrator.planilha import gravar
from extrator.processar import (gravar_conferencia, linhas_conferencia,
                                linhas_do_documento, processar_pdf)
from extrator.visao import obter_extrator_visao

# Valores do modelo para as linhas UBER (o recibo não informa o veículo).
UBER_TIPO_FROTA_PADRAO = "Automóvel flex a gasolina"
UBER_ANO_FROTA_PADRAO = 2016
NOME_PLANILHA_PADRAO = "planilha_GEE.xlsx"

NOMES_MES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def listar_pdfs(entradas: list[str]) -> list[Path]:
    pdfs = []
    for e in entradas:
        p = Path(e)
        if p.is_dir():
            pdfs += sorted(x for x in p.iterdir() if x.suffix.lower() == ".pdf")
        elif p.suffix.lower() == ".pdf" and p.exists():
            pdfs.append(p)
        else:
            print(f"[aviso] ignorado (não é PDF/pasta): {e}", file=sys.stderr)
    return pdfs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entradas", nargs="+", help="PDFs ou pastas com PDFs")
    ap.add_argument("-o", "--saida",
                    help=f"planilha .xlsx (criada se não existir). Padrão: {NOME_PLANILHA_PADRAO} "
                         "na pasta dos PDFs")
    ap.add_argument("--tesseract", help="pasta de instalação do Tesseract ou caminho do tesseract.exe (se não for encontrado sozinho)")
    ap.add_argument("--dpi", type=int, default=ocr.DPI_PADRAO, help="resolução do OCR (padrão 300)")
    ap.add_argument("--uber-tipo-frota", default=UBER_TIPO_FROTA_PADRAO,
                    help=f"'Tipo da frota' nas linhas UBER (padrão: {UBER_TIPO_FROTA_PADRAO})")
    ap.add_argument("--uber-ano-frota", type=int, default=UBER_ANO_FROTA_PADRAO,
                    help=f"'Ano da frota' nas linhas UBER (padrão: {UBER_ANO_FROTA_PADRAO})")
    ap.add_argument("--visao", help="provedor de IA com visão para 2ª leitura (ainda não configurado)")
    args = ap.parse_args(argv)

    ocr.configurar_tesseract(args.tesseract)
    ocr.verificar_tesseract()
    visao = obter_extrator_visao(args.visao)

    pdfs = listar_pdfs(args.entradas)
    if not pdfs:
        print("Nenhum PDF encontrado.", file=sys.stderr)
        return 1

    if args.saida:
        saida = Path(args.saida)
    else:
        primeira = Path(args.entradas[0])
        saida = (primeira if primeira.is_dir() else primeira.parent) / NOME_PLANILHA_PADRAO
    if saida.suffix.lower() != ".xlsx":
        print(f"A saída deve ser um arquivo .xlsx: {saida}", file=sys.stderr)
        return 1
    linhas, conferencia, com_aviso = [], [], 0
    for i, pdf in enumerate(pdfs, 1):
        print(f"[{i}/{len(pdfs)}] {pdf.name} ...", flush=True)
        try:
            doc = processar_pdf(pdf, args.dpi, visao)
        except Exception as e:  # um PDF ruim não interrompe o lote
            print(f"    ERRO ao processar: {e}", file=sys.stderr)
            conferencia.append([pdf.name, "", "", "", "GERAL", "", "", "", "", "", "", f"ERRO: {e}"])
            com_aviso += 1
            continue
        novas = linhas_do_documento(doc, args.uber_tipo_frota, args.uber_ano_frota)
        linhas += novas
        conferencia += linhas_conferencia(doc)
        print(f"    viagem {doc.viagem} | nº pessoal {doc.num_pessoal} | "
              f"{len(doc.trechos)} trajeto(s) de carro | {len(doc.corridas)} recibo(s) Uber")
        for l in novas:
            meses = ", ".join(f"{NOMES_MES[m - 1]}: {km:g} km" for m, km in l.km_por_mes.items())
            print(f"    -> {l.tipo}: {meses or '(sem km)'}")
            if l.observacoes:
                print(f"       OBS: {l.observacoes}")
        if not novas:
            print("    -> nenhum deslocamento de carro ou Uber encontrado")
        if doc.avisos_gerais or doc.avisos_carro or doc.avisos_uber or not novas:
            com_aviso += 1

    gravadas, ignoradas = gravar(saida, linhas)
    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    rel = saida.with_name(f"conferencia_{saida.stem}_{carimbo}.csv")
    gravar_conferencia(rel, conferencia)

    print()
    print(f"Planilha: {saida}  ({len(gravadas)} linha(s) gravada(s))")
    for l in ignoradas:
        print(f"  [ignorada] {l.tipo} viagem {l.evidencia} já existe na planilha")
    print(f"Relatório de conferência: {rel}")
    if com_aviso:
        print(f"ATENÇÃO: {com_aviso} documento(s) com avisos - veja a coluna Observações e o relatório.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
