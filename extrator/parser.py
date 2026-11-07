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
from difflib import get_close_matches

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
    """Deslocamento com veículo próprio (seção Trajeto do relatório).

    Para a planilha bastam mês e ano; o dia é guardado só para conferência
    (pode ficar vazio se o OCR não o ler)."""
    ano: int
    mes: int
    dia: int | None
    km: float
    pagina: int
    placa: str | None = None

    @property
    def data(self) -> date | None:
        try:
            return date(self.ano, self.mes, self.dia) if self.dia else None
        except ValueError:
            return None

    @property
    def rotulo_data(self) -> str:
        return f"{self.dia:02d}/{self.mes:02d}/{self.ano}" if self.dia else f"??/{self.mes:02d}/{self.ano}"


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
    periodo: tuple[date, date] | None = None   # "de dd/mm/aaaa até dd/mm/aaaa"
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
# Âncora de cada trajeto: "Trajeto total (km)" (tolerante a erros de OCR)
_RE_ANCORA = re.compile(r"Tra[jiy]\w{0,4}\s+t[o0]ta\w?", re.I)
_RE_KM_APOS_ANCORA = re.compile(r"\A[^\d\n]{0,20}?(\d[\d.,]*)")
# Data por extenso; o dia é opcional (pode vir ilegível: "P de fevereiro")
_RE_DATA_TRAJETO = re.compile(r"(?:(\d{1,2})\s*)?de\s+([A-Za-zçÇ]{4,})\s+de\s+(\d{4})", re.I)
_RE_MARCA = re.compile(r"Marca do ve", re.I)
_RE_PERIODO = re.compile(r"para viagem\s+\d+\s+de\s+(\d{2})/(\d{2})/(\d{4})\s+at\S*\s+(\d{2})/(\d{2})/(\d{4})", re.I)
_NOMES_MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
                "agosto", "setembro", "outubro", "novembro", "dezembro"]
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


def _mes_por_nome(palavra: str) -> int | None:
    palavra = palavra.lower().replace("ç", "c")
    nomes = [n.replace("ç", "c") for n in _NOMES_MESES]
    achado = get_close_matches(palavra, nomes, n=1, cutoff=0.75)
    return nomes.index(achado[0]) + 1 if achado else None


def _data_do_trajeto(trecho_texto: str):
    """Última data por extenso do trecho de texto -> (dia|None, mes, ano) ou None."""
    for m in reversed(list(_RE_DATA_TRAJETO.finditer(trecho_texto))):
        mes = _mes_por_nome(m.group(2))
        ano = int(m.group(3))
        if mes and 2000 <= ano <= 2100:
            dia = int(m.group(1)) if m.group(1) and 1 <= int(m.group(1)) <= 31 else None
            return dia, mes, ano
    return None


@dataclass
class _Bloco:
    km_total: float | None
    km_mi: float | None
    data: tuple | None      # (dia|None, mes, ano)
    placa: str | None


def _blocos(texto: str) -> tuple[list[_Bloco], int]:
    """Blocos da seção "Trajeto" de um texto de OCR, e quantos trajetos a
    página parece ter (contando também as linhas "km/mi.", "Marca", "Placa").

    Cada bloco é ancorado em "Trajeto total (km)": a data é a última data por
    extenso antes da âncora e os km são o número logo após ela; o "km/mi." e a
    placa vêm do texto entre esta âncora e a próxima."""
    blocos = []
    ancoras = list(_RE_ANCORA.finditer(texto))
    for i, a in enumerate(ancoras):
        antes = texto[ancoras[i - 1].end() if i else 0:a.start()]
        depois = texto[a.end():ancoras[i + 1].start() if i + 1 < len(ancoras) else len(texto)]
        depois_sem_km = re.sub(r"\A\s*\(?\s*k\w{0,2}\s*\)?", "", depois)
        m = _RE_KM_APOS_ANCORA.match(depois_sem_km)
        km_total = numero_br(m.group(1)) if m else None
        m = _RE_KM_MI.search(depois)
        km_mi = numero_br(m.group(1)) if m else None
        m = _RE_PLACA.search(depois)
        placa = normalizar_placa(m.group(1)) if m else None
        blocos.append(_Bloco(km_total, km_mi, _data_do_trajeto(antes), placa))
    esperado = max(len(ancoras), len(_RE_KM_MI.findall(texto)), len(_RE_MARCA.findall(texto)),
                   len(_RE_PLACA.findall(texto)))
    return blocos, esperado


def _consenso(votos: list):
    """Valor com pelo menos 2 votos e mais votos que qualquer outro; senão None."""
    contagem = Counter(v for v in votos if v is not None).most_common()
    if not contagem:
        return None
    valor, n = contagem[0]
    if n >= 2 and (len(contagem) == 1 or n > contagem[1][1]):
        return valor
    return None


def ler_trajetos(textos, pagina: int, periodo=None) -> tuple[list[Trecho], list[str]]:
    """Consolida as leituras (uma ou mais passadas de OCR da mesma página).

    O km de cada trajeto aparece duas vezes ("Trajeto total" e "km/mi.") em
    cada leitura; só é lançado quando há consenso (>= 2 leituras iguais e
    maioria). Sem consenso o trajeto NÃO é lançado e gera aviso."""
    if isinstance(textos, str):
        textos = [textos]
    leituras = [_blocos(t) for t in textos]
    esperado = max((e for _, e in leituras), default=0)
    if esperado == 0:
        return [], []
    alinhadas = [b for b, _ in leituras if len(b) == esperado]
    avisos = []
    if not alinhadas:
        maior = max(len(b) for b, _ in leituras)
        alinhadas = [b for b, _ in leituras if len(b) == maior]
        avisos.append(f"pág. {pagina}: {esperado - maior} trajeto(s) não lido(s) - conferir")
    mesmo_mes = periodo and (periodo[0].year, periodo[0].month) == (periodo[1].year, periodo[1].month)

    trechos = []
    for i in range(len(alinhadas[0])):
        bl = [b[i] for b in alinhadas]
        ref = f"pág. {pagina}, {i + 1}º trajeto"
        votos_km = [v for b in bl for v in (b.km_total, b.km_mi)]
        km = _consenso(votos_km)
        mes_ano = _consenso([b.data[1:] for b in bl if b.data] * 2)  # data: 1 voto forte por leitura
        if mes_ano is None and mesmo_mes:
            mes_ano = (periodo[0].month, periodo[0].year)  # viagem inteira no mesmo mês
        dia, _ = _mais_comum([b.data[0] for b in bl if b.data and b.data[1:] == mes_ano])

        if km is None:
            lidos = sorted({f"{v:g}" for v in votos_km if v is not None})
            avisos.append(f"{ref}: km sem confirmação (lido: {', '.join(lidos) or 'nada'}) "
                          "- NÃO lançado, conferir")
            continue
        if mes_ano is None:
            avisos.append(f"{ref}: data ilegível ({km:g} km NÃO lançados) - conferir")
            continue
        placa, _ = _mais_comum([b.placa for b in bl])
        trechos.append(Trecho(mes_ano[1], mes_ano[0], dia, km, pagina, placa))
    return trechos, avisos


# Leituras extras (dpi, modo de segmentação) usadas quando falta consenso
RELEITURAS = [(300, 6), (400, 6), (400, 4), (250, 4), (350, 6), (200, 4)]


def interpretar_relatorio(doc: Documento, paginas, reocr=None) -> None:
    """`reocr(pagina, dpi, psm) -> texto` permite reler páginas sem consenso."""
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

    # Período da viagem (usado se o mês de algum trajeto ficar ilegível)
    m = _RE_PERIODO.search(texto)
    if m:
        d1, d2 = _data_numerica(*m.groups()[:3]), _data_numerica(*m.groups()[3:])
        if d1 and d2:
            doc.periodo = (d1, d2)

    # Trajetos de carro
    for p in rel:
        textos = [p.texto]
        trechos, avisos = ler_trajetos(textos, p.numero, doc.periodo)
        if avisos and reocr is not None:
            # Sem consenso: novas leituras da página em outros modos/resoluções.
            for dpi, psm in RELEITURAS:
                textos.append(reocr(p, dpi, psm))
                trechos, avisos = ler_trajetos(textos, p.numero, doc.periodo)
                if not avisos:
                    break
        doc.trechos += trechos
        doc.avisos_carro += avisos

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
