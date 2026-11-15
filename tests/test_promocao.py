"""
Testes da avaliação de promoções (avaliar_promocao). Separados dos testes antigos.

Como rodar (na pasta do projeto):
    python -m pytest -v

Usam as mesmas preparações do conftest.py: cópia temporária do banco simulado
e modelo salvo numa pasta temporária (nenhum arquivo do projeto é alterado).
"""

import json
import sqlite3

import pandas as pd
import pytest

from dynaprice_ia import ProdutoInativo, ProdutoNaoEncontrado, avaliar_promocao
from dynaprice_ia.conexao import buscar_vendas, data_ultima_venda
from dynaprice_ia.elasticidade import estimar_elasticidade
from dynaprice_ia.preparacao import montar_tabela_diaria

# IDs do banco simulado (ver dados_sinteticos/gerar_dados_sinteticos.py)
CAFE, REFRIGERANTE, AGUA, CERVEJA, LEITE, IOGURTE, CHOCOLATE = 3, 4, 5, 6, 7, 8, 11
BISCOITO_LANCAMENTO, SUCO_INATIVO, AZEITE_SEM_VENDAS = 13, 14, 15
CHAVES = {"produto_id", "nome", "preco_atual", "preco_promocional", "demanda_sem_promocao",
          "demanda_com_promocao", "receita_sem", "receita_com", "variacao_receita_percentual",
          "cobertura_estoque_dias", "veredito", "motivo",
          "desconto_percentual", "dias", "elasticidade_estimada"}


# ---------------------------------------------------------------------------
# Erros tratados
# ---------------------------------------------------------------------------
def test_produto_inexistente(banco_teste):
    with pytest.raises(ProdutoNaoEncontrado):
        avaliar_promocao(9999, 10, 7, banco_teste)


def test_suco_inativo(banco_teste):
    with pytest.raises(ProdutoInativo):
        avaliar_promocao(SUCO_INATIVO, 10, 7, banco_teste)


@pytest.mark.parametrize("desconto", [0, 51, -5, "abc", True, None, float("nan")])
def test_desconto_invalido(banco_teste, desconto):
    with pytest.raises(ValueError):
        avaliar_promocao(IOGURTE, desconto, 7, banco_teste)


@pytest.mark.parametrize("dias", [0, 31, 2.5, "sete", True])
def test_dias_invalido(banco_teste, dias):
    with pytest.raises(ValueError):
        avaliar_promocao(IOGURTE, 10, dias, banco_teste)


# ---------------------------------------------------------------------------
# Poucos dados -> "arriscado", sem inventar previsão com promoção
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("produto_id", [BISCOITO_LANCAMENTO, AZEITE_SEM_VENDAS])
def test_pouco_historico_e_arriscado(banco_teste, produto_id):
    r = avaliar_promocao(produto_id, 10, 7, banco_teste)
    assert r["veredito"] == "arriscado"
    assert r["demanda_com_promocao"] is None and r["receita_com"] is None
    assert "histórico" in r["motivo"]


# ---------------------------------------------------------------------------
# Formato do retorno
# ---------------------------------------------------------------------------
def test_retorno_tem_as_chaves_e_vira_json(banco_teste):
    r = avaliar_promocao(IOGURTE, 15, 7, banco_teste)
    assert set(r) == CHAVES
    json.dumps(r)  # o Flask (jsonify) não aceita tipos do numpy
    assert r["preco_promocional"] == pytest.approx(r["preco_atual"] * 0.85, abs=0.01)


def test_motivo_avisa_que_nao_e_lucro_e_que_dados_sao_simulados(banco_teste):
    motivo = avaliar_promocao(IOGURTE, 15, 7, banco_teste)["motivo"]
    assert "não de lucro" in motivo and "SIMULADOS" in motivo


# ---------------------------------------------------------------------------
# Somente leitura: NADA muda no banco
# ---------------------------------------------------------------------------
def test_nao_grava_nada_no_banco(banco_teste, con):
    tabelas = [t for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]

    def foto():
        contagens = {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tabelas}
        produtos = [tuple(l) for l in con.execute("SELECT * FROM produtos ORDER BY id_produto")]
        return contagens, produtos

    antes = foto()
    for produto_id, desconto, dias in [(IOGURTE, 15, 7), (CERVEJA, 30, 14), (BISCOITO_LANCAMENTO, 10, 7)]:
        avaliar_promocao(produto_id, desconto, dias, banco_teste)
    assert foto() == antes


# ---------------------------------------------------------------------------
# Coerência do efeito do desconto
# ---------------------------------------------------------------------------
def test_desconto_maior_gera_demanda_maior(banco_teste):
    demandas = [avaliar_promocao(IOGURTE, d, 7, banco_teste)["demanda_com_promocao"] for d in (5, 15, 30)]
    sem = avaliar_promocao(IOGURTE, 5, 7, banco_teste)["demanda_sem_promocao"]
    assert sem < demandas[0] < demandas[1] < demandas[2]


@pytest.mark.parametrize("produto_id, elasticidade_real", [
    (CAFE, -0.9), (REFRIGERANTE, -1.6), (CERVEJA, -1.8), (LEITE, -0.5), (IOGURTE, -1.4), (CHOCOLATE, -1.5),
])
def test_elasticidade_estimada_proxima_da_simulada(banco_teste, produto_id, elasticidade_real):
    """Nos dados simulados sabemos a resposta certa; o método precisa chegar perto (±0.3)."""
    c = sqlite3.connect(banco_teste)
    produtos = pd.read_sql("SELECT * FROM produtos", c)
    historico = montar_tabela_diaria(buscar_vendas(c, produto_id),
                                     produtos[produtos.id_produto == produto_id],
                                     data_referencia=data_ultima_venda(c))
    c.close()
    estimativa = estimar_elasticidade(historico)
    assert estimativa["confiavel"]
    assert estimativa["elasticidade"] == pytest.approx(elasticidade_real, abs=0.3)


# ---------------------------------------------------------------------------
# Um caso de cada veredito
# ---------------------------------------------------------------------------
def test_leite_nao_vale_a_pena(banco_teste):
    """Leite é essencial (vende quase igual com desconto): a receita cai."""
    r = avaliar_promocao(LEITE, 15, 7, banco_teste)
    assert r["veredito"] == "não vale a pena"
    assert r["receita_com"] < r["receita_sem"]


def test_cerveja_com_estoque_curto_nao_vale(banco_teste):
    """Estoque da cerveja (150) já acaba sem promoção: desconto só vende o mesmo mais barato."""
    r = avaliar_promocao(CERVEJA, 15, 7, banco_teste)
    assert r["veredito"] == "não vale a pena"
    assert "SEM promoção" in r["motivo"]


def test_iogurte_com_estoque_alto_vale_a_pena(banco_teste):
    """Iogurte reage a desconto e tem estoque de sobra (600)."""
    r = avaliar_promocao(IOGURTE, 15, 7, banco_teste)
    assert r["veredito"] == "vale a pena"
    assert r["receita_com"] > r["receita_sem"]


def test_desconto_fora_do_historico_no_maximo_arriscado(banco_teste):
    """45% de desconto: nenhuma promoção do histórico chegou perto, então nunca é 'vale a pena'."""
    r = avaliar_promocao(IOGURTE, 45, 7, banco_teste)
    assert r["veredito"] in ("arriscado", "não vale a pena")


def test_falta_de_estoque_durante_a_promocao_e_arriscado(banco_teste):
    """Água, 20% por 10 dias: sem promoção vende ~200 (estoque 270 dá), com promoção ~291
    (estoque NÃO dá). A receita sobe, mas o estoque acaba antes do fim -> arriscado."""
    r = avaliar_promocao(AGUA, 20, 10, banco_teste)
    assert r["veredito"] == "arriscado"
    assert r["receita_com"] > r["receita_sem"]
    assert r["demanda_sem_promocao"] <= 270 < r["demanda_com_promocao"]
    assert "acaba em" in r["motivo"]
