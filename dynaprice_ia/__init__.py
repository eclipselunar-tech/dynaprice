"""
dynaprice_ia — Módulo de Inteligência Artificial do DynaPrice.

Prevê a demanda dos produtos (scikit-learn) e sugere um preço, respeitando
um limite de variação. NÃO altera o preço do produto: só sugere e registra
a análise na tabela analises_ia. Quem aplica o preço é a aplicação principal.

Uso:
    from dynaprice_ia import recalcular_preco
    resultado = recalcular_preco(4)
    resultado = recalcular_preco(4, caminho_banco="caminho/do/banco.db")

    from dynaprice_ia import avaliar_promocao       # só leitura, não grava nada
    avaliacao = avaliar_promocao(6, desconto_percentual=15, dias=7)
"""

from .erros import (BancoNaoEncontrado, DadosInsuficientes, ErroDynaPriceIA,
                    ProdutoInativo, ProdutoNaoEncontrado)
from .integracao import recalcular_preco, retreinar_modelo
from .promocao import avaliar_promocao

__all__ = [
    "recalcular_preco", "retreinar_modelo", "avaliar_promocao",
    "ErroDynaPriceIA", "BancoNaoEncontrado", "ProdutoNaoEncontrado",
    "ProdutoInativo", "DadosInsuficientes",
]
