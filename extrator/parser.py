"""Interpretação do texto (OCR) dos documentos de prestação de contas de viagem.

Estrutura esperada de cada PDF:
  * Relatório SAP "Cálculo de despesas/comprovante de despesas de viagem"
    (páginas iniciais): nome, nº pessoal, nº da viagem e seção "Trajeto" com
    os deslocamentos de carro (data, "Trajeto total (km)", placa).
  * Anexos digitalizados: recibos de Uber ("Obrigado por viajar",
    "X Quilômetros"), notas fiscais, mapas etc.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

MESES = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}
_MES_RE = r"(jan\w*|fev\w*|mar\w*|abr\w*|mai\w*|jun\w*|jul\w*|ago\w*|set\w*|out\w*|nov\w*|dez\w*)"


# --------------------------------------------------------------------------- #
# Estruturas
# --------------------------------------------------------------------------- #
@dataclass
class Trecho:
    """Deslocamento com veículo próprio (seção Trajeto do relatório)."""
    data: date
    km: float
    pagina: int
    placa: str | None = None


@dataclass
class Corrida:
    """Corrida de aplicativo (recibo Uber)."""
    data: date | None
    km: float | None
    pagina: int
    valor: float | None = None
    fonte: str = "ocr"


@dataclass
class Documento:
    arquivo: str
    viagem: int | None = None
    nome: str | None = None
    num_pessoal: int | None = None
    trechos: list[Trecho] = field(default_factory=list)
    corridas: list[Corrida] = field(default_factory=list)
    valor_taxi_relatorio: float | None = None
    avisos_carro: list[str] = field(default_factory=list)
    avisos_uber: list[str] = field(default_factory=list)
    avisos_gerais: list[str] = field(default_factory=list)

    @property
    def placas(self) -> list[str]:
        return sorted({t.placa for t in self.trechos if t.placa})


# --------------------------------------------------------------------------- #
# Utilitários
# --------------------------------------------------------------------------- #
def numero_br(txt: str) -> float | None:
    """Converte número em formato brasileiro ('1.577,81', '225', '12,5')."""
    txt = txt.strip().strip(".,")
    if not txt:
        return None
    if "," in txt:
        txt = txt.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", txt):
        txt = txt.replace(".", "")  # ponto como separador de milhar
    try:
        return float(txt)
    except ValueError:
        return None


def numero_decimal(txt: str) -> float | None:
    """Número cujo separador ('.' ou ',') é sempre decimal (ex.: '2.66' km do Uber)."""
    try:
        return float(txt.replace(",", "."))
    except ValueError:
        return None


def _data_extenso(dia: str, mes: str, ano: str) -> date | None:
    m = MESES.get(mes[:3].lower())
    try:
        return date(int(ano), m, int(dia)) if m else None
    except ValueError:
        return None


def _data_numerica(dia: str, mes: str, ano: str) -> date | None:
    ano_i = int(ano)
    if ano_i < 100:
        ano_i += 2000
    try:
        return date(ano_i, int(mes), int(dia))
    except ValueError:
        return None


def _mais_comum(valores: list):
    valores = [v for v in valores if v is not None]
    if not valores:
        return None, False
    contagem = Counter(valores)
    valor, _ = contagem.most_common(1)[0]
    return valor, len(contagem) > 1


def normalizar_placa(txt: str) -> str | None:
    """Corrige confusões típicas do OCR em placas (padrão antigo e Mercosul)."""
    t = re.sub(r"[^A-Za-z0-9]", "", txt).upper()
    if len(t) < 7:
        return None
    t = t[:7]
    letras = {"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z", "6": "G"}
    numeros = {"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "S": "5",
               "B": "8", "Z": "2", "G": "6", "T": "7"}
    p = [letras.get(c, c) for c in t[:3]]
    p.append(numeros.get(t[3], t[3]))
    p.append(t[4])  # letra (Mercosul) ou número (antiga)
    p += [numeros.get(c, c) for c in t[5:7]]
    placa = "".join(p)
    return placa if re.fullmatch(r"[A-Z]{3}\d[A-Z0-9]\d{2}", placa) else None


# --------------------------------------------------------------------------- #
# Classificação de páginas
# --------------------------------------------------------------------------- #
_RE_RELATORIO = re.compile(
    r"Liquida\S*\s*/\s*viagem|C[áa]lculo de despesas|N\S{0,2}\s*pessoal", re.I)
_RE_UBER_MARCA = re.compile(r"\bUber\b", re.I)
_RE_UBER_RECIBO = re.compile(r"Obrigado por viajar|Quil[ôo]metros|Informa\S+ da viagem", re.I)


def eh_relatorio(texto: str) -> bool:
    return bool(_RE_RELATORIO.search(texto))


def eh_recibo_uber(texto: str) -> bool:
    if eh_relatorio(texto):  # o rodapé do relatório cita "Uber"
        return False
    return bool(_RE_UBER_MARCA.search(texto) and _RE_UBER_RECIBO.search(texto))


# --------------------------------------------------------------------------- #
# Relatório SAP
# --------------------------------------------------------------------------- #
_RE_VIAGEM = [
    re.compile(r"Viagem\s*[:;]\s*(\d{8,12})", re.I),
    re.compile(r"para viagem\s+(\d{8,12})", re.I),
    re.compile(r"Liquida\S*\s*/\s*viagem\s*[:;]?\s*(\d{8,12})", re.I),
]
_RE_NUM_PESSOAL = re.compile(r"N\S{0,2}\s*pessoal\s*[:;]?\s*(\d{5,10})", re.I)
_RE_NOME = re.compile(r"\bde\s+([A-ZÀ-Ú][A-ZÀ-Ú .'-]{3,}?)\s+para viagem", re.I)
_RE_TRAJETO = re.compile(
    r"(\d{1,2})\s+de\s+" + _MES_RE + r"\s+de\s+(\d{4})\s+"
    r"Trajeto\s+total\s*\(?\s*km\s*\)?\s*[:.]?\s*(\d[\d.,]*)", re.I)
_RE_TRAJETO_SOLTO = re.compile(r"Trajeto\s+total", re.I)
_RE_KM_MI = re.compile(r"\bk\w{0,2}\s*/\s*mi\.?\s*[:;]?\s*(\d[\d.,]*)", re.I)
_RE_PLACA = re.compile(r"Placa de ve\S*\s*[:;]?\s*([A-Za-z0-9]{7,9})", re.I)
_RE_TAXI = re.compile(r"\d{5}\s+T[áa]xi\s+(\d[\d.]*,\d{2})", re.I)


def _num_pessoal_pagina1(texto: str, nome: str | None) -> int | None:
    """Número logo abaixo do nome do colaborador, no topo da 1ª página."""
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]
    for i, linha in enumerate(linhas):
        if nome and nome.split()[0].upper() in linha.upper() and i + 1 < len(linhas):
            m = re.match(r"^(\d{5,10})\b", linhas[i + 1])
            if m:
                return int(m.group(1))
    return None


def interpretar_relatorio(doc: Documento, paginas) -> None:
    rel = [p for p in paginas if eh_relatorio(p.texto)]
    if not rel:
        doc.avisos_gerais.append("Relatório SAP de despesas não identificado no PDF")
        return
    texto = "\n".join(p.texto for p in rel)

    # Nº da viagem (evidência)
    candidatos = [int(m.group(1)) for r in _RE_VIAGEM for m in r.finditer(texto)]
    doc.viagem, divergente = _mais_comum(candidatos)
    if doc.viagem is None:
        doc.avisos_gerais.append("Nº da viagem não lido")
    elif divergente:
        doc.avisos_gerais.append(
            f"Nº da viagem lido com divergência ({sorted(set(candidatos))}); usado {doc.viagem}")

    # Nome
    m = _RE_NOME.search(texto)
    if m:
        doc.nome = re.sub(r"\s+", " ", m.group(1)).strip()

    # Nº pessoal (descrição do passageiro)
    candidatos = [int(m.group(1)) for m in _RE_NUM_PESSOAL.finditer(texto)]
    n1 = _num_pessoal_pagina1(rel[0].texto, doc.nome)
    if n1:
        candidatos.append(n1)
    doc.num_pessoal, divergente = _mais_comum(candidatos)
    if doc.num_pessoal is None:
        doc.avisos_gerais.append("Nº pessoal (descrição do passageiro) não lido")
    elif divergente:
        doc.avisos_gerais.append(
            f"Nº pessoal lido com divergência ({sorted(set(candidatos))}); usado {doc.num_pessoal}")

    # Trajetos de carro
    for p in rel:
        trajetos = list(_RE_TRAJETO.finditer(p.texto))
        placas = [normalizar_placa(m.group(1)) for m in _RE_PLACA.finditer(p.texto)]
        kms_conf = [numero_br(m.group(1)) for m in _RE_KM_MI.finditer(p.texto)]
        soltos = len(_RE_TRAJETO_SOLTO.findall(p.texto))

        if soltos != len(trajetos):
            doc.avisos_carro.append(
                f"pág. {p.numero}: {soltos - len(trajetos)} trajeto(s) não lido(s) - conferir")
        for i, m in enumerate(trajetos):
            dia, mes, ano, km_txt = m.groups()
            d = _data_extenso(dia, mes, ano)
            km = numero_br(km_txt)
            if d is None or km is None:
                doc.avisos_carro.append(f"pág. {p.numero}: trajeto ilegível '{m.group(0)}'")
                continue
            if len(kms_conf) == len(trajetos) and kms_conf[i] is not None and kms_conf[i] != km:
                doc.avisos_carro.append(
                    f"pág. {p.numero}: trajeto de {d:%d/%m/%Y} com 'Trajeto total' {km:g} "
                    f"diferente de 'km/mi.' {kms_conf[i]:g} - conferir")
            placa = placas[i] if len(placas) == len(trajetos) else None
            doc.trechos.append(Trecho(d, km, p.numero, placa))
        if trajetos and len(kms_conf) != len(trajetos):
            doc.avisos_carro.append(
                f"pág. {p.numero}: não foi possível conferir 'km/mi.' de todos os trajetos")

    # Valor de "Taxi" no relatório (para conferir os recibos Uber)
    valores = [numero_br(m.group(1)) for m in _RE_TAXI.finditer(texto)]
    valores = [v for v in valores if v is not None]
    if valores:
        doc.valor_taxi_relatorio = round(sum(valores), 2)


# --------------------------------------------------------------------------- #
# Recibos Uber
# --------------------------------------------------------------------------- #
_RE_UBER_KM = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:Quil[ôo]metros|km\b)", re.I)
_RE_UBER_DATA_EXT = re.compile(r"(\d{1,2})\s+de\s+" + _MES_RE + r"\.?\s+de\s+(\d{4})", re.I)
_RE_UBER_DATA_NUM = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_RE_UBER_TOTAL = re.compile(r"\bTotal\s+R\s*\$\s*(\d[\d.]*,\d{2})")


def interpretar_recibo_uber(texto: str, pagina: int) -> list[Corrida]:
    kms = [numero_decimal(m.group(1)) for m in _RE_UBER_KM.finditer(texto)]
    datas = [_data_extenso(*m.groups()) for m in _RE_UBER_DATA_EXT.finditer(texto)]
    if not datas:
        datas = [_data_numerica(*m.groups()) for m in _RE_UBER_DATA_NUM.finditer(texto)]
    totais = [numero_br(m.group(1)) for m in _RE_UBER_TOTAL.finditer(texto)]

    n = max(len(kms), 1)
    corridas = []
    for i in range(n):
        corridas.append(Corrida(
            data=datas[i] if i < len(datas) else (datas[0] if len(datas) == 1 and n == 1 else None),
            km=kms[i] if i < len(kms) else None,
            pagina=pagina,
            valor=totais[i] if i < len(totais) else None,
        ))
    return corridas


def recibo_completo(corridas: list[Corrida]) -> bool:
    return bool(corridas) and all(c.data and c.km is not None for c in corridas)
