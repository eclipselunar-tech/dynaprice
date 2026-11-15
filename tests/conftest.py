"""
conftest.py — preparação compartilhada pelos testes (pytest lê este arquivo sozinho).

Segurança: os testes NUNCA usam os bancos de verdade nem o modelo salvo.
    - O banco simulado é COPIADO para uma pasta temporária.
    - O modelo é salvo numa pasta temporária (não sobrescreve dynaprice_ia/modelos/).
"""

import shutil
import sqlite3
from pathlib import Path

import pytest

import dynaprice_ia.integracao as integracao
import dynaprice_ia.modelo as modelo

PASTA_PROJETO = Path(__file__).resolve().parent.parent
BANCO_SIMULADO = PASTA_PROJETO / "dados_sinteticos" / "dynaprice_teste_sintetico.db"


@pytest.fixture(scope="session")
def banco_teste(tmp_path_factory):
    """Cópia temporária do banco simulado + modelo treinado numa pasta temporária."""
    if not BANCO_SIMULADO.exists():
        pytest.skip("Rode antes: python dados_sinteticos/gerar_dados_sinteticos.py")
    pasta = tmp_path_factory.mktemp("dynaprice")
    copia = pasta / "banco_teste.db"
    shutil.copyfile(BANCO_SIMULADO, copia)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(modelo, "PASTA_MODELOS", pasta / "modelos")
        mp.setattr(integracao, "_modelos_em_memoria", {})
        yield copia


@pytest.fixture
def con(banco_teste):
    """Conexão de leitura com o banco de teste, para conferir o que foi gravado."""
    conexao = sqlite3.connect(banco_teste)
    conexao.row_factory = sqlite3.Row
    yield conexao
    conexao.close()


@pytest.fixture
def banco_quase_vazio(tmp_path, banco_teste):
    """
    Banco com a estrutura do grupo, mas só 1 produto e 3 dias de vendas:
    simula o sistema recém-começado (não dá para treinar modelo).
    """
    # Copia só a ESTRUTURA (tabelas, view, triggers, índices) do banco de teste, sem os dados.
    copia = tmp_path / "quase_vazio.db"
    origem = sqlite3.connect(banco_teste)
    comandos = [sql for (sql,) in origem.execute(
        "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'")]
    origem.close()
    c = sqlite3.connect(copia)
    for sql in comandos:
        c.execute(sql)
    c.execute("INSERT INTO produtos (codigo_barras, nome, preco_atual, estoque_atual) "
              "VALUES ('T-1', 'Produto teste', 10.0, 50)")
    for dia in ("2026-11-08", "2026-11-09", "2026-11-10"):
        cur = c.execute("INSERT INTO vendas (data_hora, valor_total) VALUES (?, 20)", (f"{dia} 10:00:00",))
        c.execute("INSERT INTO itens_venda (id_venda, id_produto, quantidade, preco_unitario, subtotal) "
                  "VALUES (?, 1, 2, 10.0, 20.0)", (cur.lastrowid,))
    c.commit()
    c.close()
    return copia
