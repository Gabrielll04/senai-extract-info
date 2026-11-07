"""Testes do interpretador com textos de OCR sintéticos (dados fictícios)."""
import unittest
from datetime import date
from types import SimpleNamespace

from extrator.parser import (Documento, eh_recibo_uber, eh_relatorio, interpretar_recibo_uber,
                             interpretar_relatorio, normalizar_placa, numero_br)
from extrator.processar import linhas_do_documento

PAG1 = """CFP - 2.60 - REGISTRO
Data: 30/05/2026
FULANO DE TAL SILVA
1234567 |
Suporte Téc Educação Viagem: 2111000001
Cálculo de despesas/comprovante de despesas de viagem
de FULANO DE TAL SILVA para viagem 2111000001 de 08/05/2026 até 02/06/2026
"""
PAG2 = """FULANO DE TAL SILVA
Liquidação/viagem: 2111000001
Nº pessoal: 1234567
30 de maio de 2026 Trajeto total (km) 225
De: SENAI A Para: SENAI B
km/mi.: 225
Marca do veículo: FIAT UNO Placa de veículo: TKC9C7O0
2 de junho de 2026 Trajeto total (km) 1.020
De: SENAI B Para: SENAI A
kmy/mi.: 1.020
Marca do veículo: FIAT UNO Placa de veículo: TKC9C70
08/05/26 006 30550 Taxi 55,96 Ed
- Recibos emitidos pela internet das empresas de táxi (ex.: Uber)
"""
UBER = """27 de mai. de 2026
Uber 8:03
Obrigado por viajar, Fulano
Total R$ 31,99
Mastercard Credit --.8959 R$ 31,99
27/5/2026 8:15
Informações da viagem
Black
=> 2.66 Quilômetros, 10 minutes
"""


def pag(n, t):
    return SimpleNamespace(numero=n, texto=t, imagem=None)


class TestParser(unittest.TestCase):
    def test_numero_br(self):
        self.assertEqual(numero_br("1.577,81"), 1577.81)
        self.assertEqual(numero_br("1.020"), 1020)
        self.assertEqual(numero_br("12,5"), 12.5)
        self.assertEqual(numero_br("225"), 225)

    def test_placa(self):
        self.assertEqual(normalizar_placa("TKC9C7O0"), "TKC9C70")
        self.assertEqual(normalizar_placa("EZw7968"), "EZW7968")

    def test_classificacao(self):
        self.assertTrue(eh_relatorio(PAG2))
        self.assertFalse(eh_recibo_uber(PAG2))  # rodapé cita Uber
        self.assertTrue(eh_recibo_uber(UBER))
        self.assertFalse(eh_recibo_uber("Você viajou com Fulano\nGanhos da Uber\nTotal da Uber R$ 9,59"))

    def test_relatorio(self):
        doc = Documento("x.pdf")
        interpretar_relatorio(doc, [pag(1, PAG1), pag(2, PAG2)])
        self.assertEqual(doc.viagem, 2111000001)
        self.assertEqual(doc.num_pessoal, 1234567)
        self.assertEqual(doc.nome, "FULANO DE TAL SILVA")
        self.assertEqual([(t.data, t.km) for t in doc.trechos],
                         [(date(2026, 5, 30), 225), (date(2026, 6, 2), 1020)])
        self.assertEqual(doc.valor_taxi_relatorio, 55.96)
        self.assertEqual(doc.avisos_gerais + doc.avisos_carro, [])

    def test_recibo_uber(self):
        [c] = interpretar_recibo_uber(UBER, 4)
        self.assertEqual((c.data, c.km, c.valor), (date(2026, 5, 27), 2.66, 31.99))

    def test_soma_por_mes_sem_misturar_carro_e_uber(self):
        doc = Documento("x.pdf")
        interpretar_relatorio(doc, [pag(1, PAG1), pag(2, PAG2)])
        doc.corridas += interpretar_recibo_uber(UBER, 4)
        doc.corridas += interpretar_recibo_uber(UBER.replace("2.66", "2.41").replace("27 de mai.", "1 de jun."), 7)
        placa, uber = linhas_do_documento(doc)
        self.assertEqual((placa.tipo, placa.km_por_mes), ("PLACA", {5: 225, 6: 1020}))
        self.assertEqual((uber.tipo, uber.km_por_mes), ("UBER", {5: 2.66, 6: 2.41}))

    def test_trajeto_ilegivel_gera_aviso(self):
        doc = Documento("x.pdf")
        ruim = PAG2.replace("2 de junho de 2026 Trajeto", "2 de jun#o de 2026 Trajeto")
        interpretar_relatorio(doc, [pag(1, PAG1), pag(2, ruim)])
        self.assertEqual(len(doc.trechos), 1)
        self.assertTrue(any("não lido" in a for a in doc.avisos_carro))


if __name__ == "__main__":
    unittest.main()
