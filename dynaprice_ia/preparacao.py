"""
preparacao.py — ETAPA 2: transformar as vendas em uma tabela que o modelo entende.

O modelo NÃO entende "cupons de venda". Ele precisa de uma tabela onde:
  - cada LINHA é um produto em um dia;
  - há uma coluna com a RESPOSTA certa (quantas unidades vendeu naquele dia);
  - há colunas com PISTAS (features) que ajudam a explicar essa resposta.

Exemplo do resultado:

  id_produto  data        quantidade  preco  dia_semana  mes  preco_relativo  media_7d  media_28d
  4           2026-07-04  19          9.99   5 (sáb)     7    0.97            12.4      11.8

Regra de ouro usada aqui (evitar "vazamento" de informação):
    As médias móveis usam SÓ os dias ANTERIORES ao dia da linha. Se usássemos
    o próprio dia, o modelo "colaria" a resposta da prova e pareceria ótimo no
    teste, mas falharia na vida real, onde o futuro ainda não aconteceu.
"""

import pandas as pd

from .config import JANELA_CURTA, JANELA_LONGA, MIN_DIAS_HISTORICO

# Nomes das colunas que o modelo vai usar como pistas (features).
FEATURES = ["dia_semana", "mes", "preco_relativo", "media_7d", "media_28d"]
ALVO = "quantidade"  # o que o modelo tenta prever


def montar_tabela_diaria(vendas: pd.DataFrame, produtos: pd.DataFrame,
                         data_referencia=None) -> pd.DataFrame:
    """
    Monta a tabela "produto x dia" com a quantidade vendida e as features.

    vendas          -> saída de conexao.buscar_vendas (só vendas ATIVAS)
    produtos        -> saída de conexao.listar_produtos (precisamos saber quem está inativo)
    data_referencia -> o "hoje" dos dados. Se não for informado, usa o último dia
                       com venda em `vendas`. Ao analisar UM produto só, informe a
                       data da última venda do BANCO INTEIRO (conexao.data_ultima_venda);
                       senão, os dias recentes sem venda desse produto seriam ignorados.
    """
    if vendas.empty:
        return pd.DataFrame(columns=["id_produto", "data", ALVO, "preco", *FEATURES])

    vendas = vendas.copy()
    vendas["data"] = vendas["data_hora"].dt.normalize()   # tira a hora, fica só o dia
    vendas["receita"] = vendas["quantidade"] * vendas["preco_unitario"]

    # ---- Passo 1: somar tudo o que cada produto vendeu em cada dia ----
    por_dia = vendas.groupby(["id_produto", "data"]).agg(
        quantidade=("quantidade", "sum"),
        receita=("receita", "sum"),
    )
    # Preço do dia = receita / quantidade (se houve 2 preços no mesmo dia, dá a média ponderada)
    por_dia["preco"] = por_dia["receita"] / por_dia["quantidade"]
    por_dia = por_dia.drop(columns="receita").reset_index()

    # "Hoje" para os dados = último dia com venda registrada no banco.
    if data_referencia is None:
        data_referencia = por_dia["data"].max()
    data_referencia = max(pd.Timestamp(data_referencia).normalize(), por_dia["data"].max())
    inativos = set(produtos.loc[produtos["ativo"] == 0, "id_produto"])

    tabelas = []
    for id_produto, grupo in por_dia.groupby("id_produto"):
        # ---- Passo 2: criar TODOS os dias, inclusive os sem venda ----
        # Vai do primeiro dia de venda do produto até a data de referência.
        # Produto INATIVO vai só até a última venda dele: os dias depois que
        # ele saiu de linha não são "demanda zero", ele simplesmente não estava à venda.
        fim = grupo["data"].max() if id_produto in inativos else data_referencia
        todos_os_dias = pd.date_range(grupo["data"].min(), fim, freq="D")

        t = grupo.set_index("data").reindex(todos_os_dias)
        t.index.name = "data"
        t["id_produto"] = id_produto
        t["quantidade"] = t["quantidade"].fillna(0)  # dia sem venda = vendeu 0
        # ---- Passo 3: preço em dia sem venda = último preço conhecido ----
        t["preco"] = t["preco"].ffill()

        # ---- Passo 4: features ----
        t["dia_semana"] = t.index.day_of_week  # 0 = segunda ... 6 = domingo
        t["mes"] = t.index.month             # 1 = janeiro ... 12 = dezembro
        # Preço relativo: 1.10 = 10% mais caro que o normal desse produto.
        t["preco_relativo"] = t["preco"] / t["preco"].mean()
        # Médias móveis com shift(1): olham só para os dias ANTERIORES (sem vazamento).
        anteriores = t["quantidade"].shift(1)
        t["media_7d"] = anteriores.rolling(JANELA_CURTA, min_periods=JANELA_CURTA).mean()
        t["media_28d"] = anteriores.rolling(JANELA_LONGA, min_periods=JANELA_LONGA).mean()

        tabelas.append(t.reset_index())

    tabela = pd.concat(tabelas, ignore_index=True)
    colunas = ["id_produto", "data", ALVO, "preco", *FEATURES]
    return tabela[colunas]


def tabela_para_treino(tabela: pd.DataFrame) -> pd.DataFrame:
    """
    Remove as linhas que ainda não têm histórico suficiente para calcular as
    médias (os primeiros 28 dias de cada produto). Sem isso o modelo receberia
    pistas "vazias".
    """
    return tabela.dropna(subset=FEATURES).reset_index(drop=True)


def resumo_historico(tabela: pd.DataFrame, produtos: pd.DataFrame) -> pd.DataFrame:
    """
    Diz, para cada produto, quantos dias de histórico ele tem e se é
    "pouco histórico" (menos de MIN_DIAS_HISTORICO dias).
    Produtos sem nenhuma venda aparecem com 0 dias.
    """
    resumo = tabela.groupby("id_produto").agg(
        dias_historico=("data", "count"),
        dias_com_venda=("quantidade", lambda q: int((q > 0).sum())),
    )
    resumo = produtos[["id_produto", "nome", "ativo"]].merge(
        resumo, left_on="id_produto", right_index=True, how="left"
    ).fillna({"dias_historico": 0, "dias_com_venda": 0})
    resumo[["dias_historico", "dias_com_venda"]] = resumo[["dias_historico", "dias_com_venda"]].astype(int)
    resumo["pouco_historico"] = resumo["dias_historico"] < MIN_DIAS_HISTORICO
    return resumo
