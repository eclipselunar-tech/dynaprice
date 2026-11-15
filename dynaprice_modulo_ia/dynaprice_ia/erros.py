"""
erros.py — Erros "com nome" do módulo de IA.

Por que criar erros próprios?
    Assim quem chama o módulo (o Seven) consegue saber EXATAMENTE o que deu
    errado e mostrar uma mensagem adequada ao usuário. Exemplo:

        try:
            resultado = recalcular_preco(99)
        except ProdutoNaoEncontrado:
            print("Esse produto não existe")
"""


class ErroDynaPriceIA(Exception):
    """Erro base: todos os erros do módulo herdam deste (dá para capturar todos de uma vez)."""


class BancoNaoEncontrado(ErroDynaPriceIA):
    """O arquivo do banco de dados não existe no caminho configurado."""


class ProdutoNaoEncontrado(ErroDynaPriceIA):
    """Não existe produto com o ID informado."""


class ProdutoInativo(ErroDynaPriceIA):
    """O produto existe, mas está desativado (ativo = 0); não faz sentido recalcular o preço."""


class DadosInsuficientes(ErroDynaPriceIA):
    """O banco inteiro tem vendas de menos para treinar o modelo (ex.: sistema recém-começado).
    O recalcular_preco trata esse caso sozinho: mantém o preço com confiança baixa."""
