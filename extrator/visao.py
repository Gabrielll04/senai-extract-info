"""Ponto de extensão para uma IA com visão (segunda opinião sobre o OCR).

O OCR (Tesseract) é o caminho principal. Quando uma página relevante não é
lida com segurança, o processamento chama o extrator de visão, se houver um
configurado. Para ligar um provedor (Claude, Google, Azure etc.), implemente
`ExtratorVisao` e registre-o em `obter_extrator_visao`.

Enquanto nenhum provedor estiver configurado, essas páginas são marcadas para
conferência manual na coluna "Observações" e no relatório de conferência.
"""
from __future__ import annotations

from datetime import date
from typing import Protocol

from PIL import Image


class ExtratorVisao(Protocol):
    nome: str

    def ler_recibo_corrida(self, imagem: Image.Image) -> list[tuple[date | None, float | None]]:
        """Retorna [(data da corrida, km percorridos), ...] de um recibo Uber/táxi."""
        ...


def obter_extrator_visao(provedor: str | None) -> ExtratorVisao | None:
    if not provedor:
        return None
    raise SystemExit(
        f"Provedor de visão '{provedor}' ainda não implementado. "
        "Veja extrator/visao.py."
    )
