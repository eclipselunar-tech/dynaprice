"""
Testes automáticos do módulo dynaprice_ia.

Como rodar (na pasta do projeto):
    python -m pytest -v

Cada função "test_..." confere UMA regra. Se alguma regra for quebrada no
futuro (por exemplo, alguém mudar o código e o preço passar a variar 15%),
o teste correspondente falha e mostra o que deu errado.
"""

import json
import math
import sqlite3

import pandas as pd
import pytest

from dynaprice_ia import (BancoNaoEncontrado, ProdutoInativo, ProdutoNaoEncontrado,
                          recalcular_preco)
from dynaprice_ia.config import LIMITE_VARIACAO_PRECO
from dynaprice_ia.conexao import buscar_vendas
from dynaprice_ia.recomendacao import (SEM_ESTOQUE, arredondar_preco_varejo,
                                       calcular_variacao, recomendar_preco)

# IDs do banco simulado (ver dados_sinteticos/gerar_dados_sinteticos.py)
CAFE, SABONETE, BISCOITO_LANCAMENTO, SUCO_INATIVO, AZEITE_SEM_VENDAS = 3, 9, 13, 14, 15
CHAVES_RETORNO = {"produto_id", "preco_atual", "preco_sugerido", "demanda_prevista", "confianca",
                  "id_analise", "situacao", "motivo", "variacao_percentual", "cobertura_dias"}


# ---------------------------------------------------------------------------
# Erros tratados
# ---------------------------------------------------------------------------
def test_produto_inexistente_gera_erro(banco_teste):
    with pytest.raises(ProdutoNaoEncontrado):
        recalcular_preco(9999, banco_teste)


def test_produto_inativo_gera_erro(banco_teste):
    with pytest.raises(ProdutoInativo):
        recalcular_preco(SUCO_INATIVO, banco_teste)


def test_banco_inexistente_gera_erro_e_nao_cria_arquivo(tmp_path):
    caminho = tmp_path / "nao_existe.db"
    with pytest.raises(BancoNaoEncontrado):
        recalcular_preco(1, caminho)
    assert not caminho.exists()


@pytest.mark.parametrize("valor", ["abc", None, 2.5j, True, 3.7])
def test_produto_id_invalido_gera_erro(banco_teste, valor):
    with pytest.raises(ValueError):
        recalcular_preco(valor, banco_teste)


# ---------------------------------------------------------------------------
# Poucos dados -> preço mantido e confiança baixa
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("produto_id", [BISCOITO_LANCAMENTO, AZEITE_SEM_VENDAS])
def test_pouco_historico_mantem_preco(banco_teste, produto_id):
    r = recalcular_preco(produto_id, banco_teste)
    assert r["situacao"] == "POUCO_HISTORICO"
    assert r["preco_sugerido"] == r["preco_atual"]
    assert r["confianca"] == pytest.approx(0.1)


def test_produto_com_quase_nenhuma_venda_mantem_preco(banco_teste):
    """40 dias de histórico, mas vendeu em 1 dia só: não pode receber corte de preço."""
    from dynaprice_ia.integracao import _obter_modelo
    dias = pd.date_range("2026-10-02", periods=40, freq="D")
    historico = pd.DataFrame({
        "id_produto": 99, "data": dias, "quantidade": [3] + [0] * 39, "preco": 10.0,
        "dia_semana": dias.day_of_week, "mes": dias.month, "preco_relativo": 1.0,
        "media_7d": 0.0, "media_28d": 0.0,
    })
    produto = {"id_produto": 99, "preco_atual": 10.0, "estoque_atual": 100}
    r = recomendar_preco(_obter_modelo(banco_teste), produto, historico)
    assert r["situacao"] == "POUCO_HISTORICO" and r["preco_sugerido"] == 10.0


def test_banco_recem_comecado_nao_quebra(banco_quase_vazio):
    """Sem vendas suficientes para treinar, devolve o preço atual em vez de dar erro."""
    r = recalcular_preco(1, banco_quase_vazio)
    assert r["situacao"] == "POUCO_HISTORICO"
    assert r["preco_sugerido"] == r["preco_atual"] == 10.0


# ---------------------------------------------------------------------------
# Formato do retorno (o que o Seven recebe)
# ---------------------------------------------------------------------------
def test_retorno_tem_as_chaves_combinadas(banco_teste):
    assert set(recalcular_preco(CAFE, banco_teste)) == CHAVES_RETORNO


def test_retorno_vira_json_sem_erro(banco_teste):
    """O Flask (jsonify) não aceita tipos do numpy; aqui garantimos tipos comuns do Python."""
    json.dumps(recalcular_preco(CAFE, banco_teste))


# ---------------------------------------------------------------------------
# Regras de preço
# ---------------------------------------------------------------------------
def test_nenhum_produto_ativo_passa_do_limite(banco_teste, con):
    ativos = [l["id_produto"] for l in con.execute("SELECT id_produto FROM produtos WHERE ativo = 1")]
    for produto_id in ativos:
        r = recalcular_preco(produto_id, banco_teste)
        variacao = abs(r["preco_sugerido"] / r["preco_atual"] - 1)
        assert variacao <= LIMITE_VARIACAO_PRECO + 1e-9, f"produto {produto_id} variou {variacao:.1%}"


def test_estoque_baixo_sobe_e_estoque_parado_desce(banco_teste):
    """No banco simulado, o café tem estoque para ~4 dias e o sabonete para ~80 dias."""
    assert recalcular_preco(CAFE, banco_teste)["situacao"] == "SUBIR"
    assert recalcular_preco(SABONETE, banco_teste)["situacao"] == "DESCER"


def test_variacao_proporcional_e_limitada():
    assert calcular_variacao(0) == pytest.approx(LIMITE_VARIACAO_PRECO)       # estoque acabando
    assert calcular_variacao(15) == 0                                          # equilibrado
    assert calcular_variacao(1000) == pytest.approx(-LIMITE_VARIACAO_PRECO)   # estoque enorme
    assert 0 < calcular_variacao(5) < calcular_variacao(2)                     # proporcional


@pytest.mark.parametrize("preco", [2.79, 4.49, 10.49, 27.59, 42.09, 199.90])
def test_arredondamento_termina_em_9_e_respeita_limite(preco):
    minimo, maximo = preco * 0.9, preco * 1.1
    for fator in (0.92, 0.97, 1.03, 1.08):
        sugerido = arredondar_preco_varejo(preco * fator, minimo, maximo)
        assert minimo - 1e-9 <= sugerido <= maximo + 1e-9
        assert round(sugerido * 100) % 10 == 9


def test_estoque_zero_mantem_preco(banco_teste):
    from dynaprice_ia.integracao import _obter_modelo
    from dynaprice_ia.preparacao import montar_tabela_diaria
    c = sqlite3.connect(banco_teste)
    produtos = pd.read_sql("SELECT * FROM produtos", c)
    historico = montar_tabela_diaria(buscar_vendas(c, CAFE), produtos[produtos.id_produto == CAFE])
    c.close()
    produto = produtos[produtos.id_produto == CAFE].iloc[0].to_dict() | {"estoque_atual": 0}
    r = recomendar_preco(_obter_modelo(banco_teste), produto, historico)
    assert r["situacao"] == SEM_ESTOQUE and r["preco_sugerido"] == r["preco_atual"]


# ---------------------------------------------------------------------------
# Gravação no banco
# ---------------------------------------------------------------------------
def test_grava_uma_linha_correta_em_analises_ia(banco_teste, con):
    antes = con.execute("SELECT COUNT(*) FROM analises_ia").fetchone()[0]
    r = recalcular_preco(CAFE, banco_teste)
    assert con.execute("SELECT COUNT(*) FROM analises_ia").fetchone()[0] == antes + 1

    linha = con.execute("SELECT * FROM analises_ia WHERE id_analise = ?", (r["id_analise"],)).fetchone()
    assert linha["id_produto"] == CAFE
    assert linha["preco_analisado"] == r["preco_atual"]
    assert linha["preco_recomendado"] == r["preco_sugerido"]
    assert linha["demanda"] == r["demanda_prevista"]
    assert 0 <= linha["confianca"] <= 1
    assert "DADOS SIMULADOS" in linha["modelo"]


def test_nao_altera_preco_estoque_historico_nem_etiquetas(banco_teste, con):
    """Regra do grupo: o módulo de IA só SUGERE. Quem muda preço e etiqueta é o Seven."""
    def foto():
        return (
            con.execute("SELECT id_produto, preco_atual, estoque_atual FROM produtos ORDER BY 1").fetchall(),
            con.execute("SELECT COUNT(*) FROM historico_precos").fetchone()[0],
            con.execute("SELECT COUNT(*) FROM etiquetas").fetchone()[0],
            con.execute("SELECT COUNT(*) FROM atualizacoes_etiqueta").fetchone()[0],
        )
    antes = [list(map(tuple, foto()[0])), *foto()[1:]]
    for produto_id in (CAFE, SABONETE, BISCOITO_LANCAMENTO):
        recalcular_preco(produto_id, banco_teste)
    depois = [list(map(tuple, foto()[0])), *foto()[1:]]
    assert antes == depois


def test_sem_problemas_de_chave_estrangeira(banco_teste, con):
    recalcular_preco(CAFE, banco_teste)
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []


# ---------------------------------------------------------------------------
# Compatibilidade com o banco ANTIGO do repositório (sem vendas.status nem a view)
# ---------------------------------------------------------------------------
def test_le_vendas_do_banco_antigo_sem_view(tmp_path):
    c = sqlite3.connect(tmp_path / "antigo.db")
    c.executescript("""
        CREATE TABLE produtos (id_produto INTEGER PRIMARY KEY, preco_atual REAL);
        CREATE TABLE vendas (id_venda INTEGER PRIMARY KEY, data_hora TEXT, valor_total REAL);
        CREATE TABLE itens_venda (id_item INTEGER PRIMARY KEY, id_venda INT, id_produto INT,
                                  quantidade INT, preco_unitario REAL, subtotal REAL);
        INSERT INTO produtos VALUES (1, 5.0);
        INSERT INTO vendas VALUES (1, '2026-11-10 10:00:00', 10.0);
        INSERT INTO itens_venda VALUES (1, 1, 1, 2, 5.0, 10.0);
    """)
    vendas = buscar_vendas(c)
    c.close()
    assert len(vendas) == 1 and vendas["quantidade"].iloc[0] == 2


def test_banco_com_status_sem_view_ignora_canceladas(tmp_path):
    c = sqlite3.connect(tmp_path / "sem_view.db")
    c.executescript("""
        CREATE TABLE vendas (id_venda INTEGER PRIMARY KEY, data_hora TEXT, valor_total REAL, status TEXT);
        CREATE TABLE itens_venda (id_item INTEGER PRIMARY KEY, id_venda INT, id_produto INT,
                                  quantidade INT, preco_unitario REAL, subtotal REAL);
        INSERT INTO vendas VALUES (1, '2026-11-10 10:00:00', 10.0, 'ATIVA');
        INSERT INTO vendas VALUES (2, '2026-11-10 11:00:00', 50.0, 'CANCELADA');
        INSERT INTO itens_venda VALUES (1, 1, 1, 2, 5.0, 10.0);
        INSERT INTO itens_venda VALUES (2, 2, 1, 10, 5.0, 50.0);
    """)
    vendas = buscar_vendas(c)
    c.close()
    assert vendas["quantidade"].sum() == 2  # a venda cancelada (10 unidades) ficou de fora
