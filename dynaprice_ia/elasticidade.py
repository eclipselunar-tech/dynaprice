"""
elasticidade.py — Mede o quanto as vendas de UM produto reagem ao preço.

O que é elasticidade-preço?
    É a "sensibilidade" das vendas ao preço. Exemplo: elasticidade -1.8 quer dizer
    que, se o preço CAIR 1%, as vendas SOBEM ~1.8%. Perto de 0 = produto essencial
    (arroz, leite: vende quase igual com ou sem desconto). Bem negativo = produto
    que reage muito a promoção (cerveja, refrigerante).

Por que um cálculo separado do modelo de demanda (Random Forest)?
    Testamos: a Random Forest prevê bem a demanda "normal", mas quase não enxerga o
    efeito do preço e NÃO consegue prever fora dos preços que já viu (ex.: um desconto
    de 30% maior que qualquer promoção do histórico). Para avaliar promoções, usamos
    então uma Regressão de Poisson, que tem a forma certa para esse problema:

        log(vendas do dia) = base + efeito do dia da semana + efeito do mês
                             + ELASTICIDADE x log(preço relativo)

    - "dia da semana" e "mês" entram para SEPARAR o efeito do preço do efeito da
      estação (senão um preço alto no verão pareceria "vender mais").
    - "Poisson" porque vendas são contagens (0, 1, 2, 3...), como na simulação.
    - O número que nos interessa é o coeficiente do log(preço): a elasticidade.

    O cálculo é refeito a cada consulta (leva milissegundos) e NÃO salva nenhum
    arquivo de modelo. O modelo de demanda existente não é alterado.
"""

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import PoissonRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

ELASTICIDADE_MINIMA = -4.0       # limite de segurança: reações mais extremas que isso são cortadas
MIN_DIAS_PARA_ESTIMAR = 30       # dias de histórico necessários para estimar
VARIACAO_MINIMA_DO_PRECO = 0.02  # se o preço quase nunca mudou, não dá para medir o efeito dele


def estimar_elasticidade(historico_produto: pd.DataFrame) -> dict:
    """
    Estima a elasticidade-preço de um produto a partir do histórico diário
    (saída de preparacao.montar_tabela_diaria para UM produto).

    Devolve:
        elasticidade          -> ex.: -1.8 (None se não deu para estimar)
        preco_relativo_minimo -> menor preço já praticado, relativo ao preço médio
                                 (ex.: 0.77 = 23% abaixo da média). Descontos que levem
                                 o preço abaixo disso estão FORA do que o histórico mostra.
        confiavel             -> True se a estimativa pode ser usada
        motivo                -> explicação em texto quando não for confiável
    """
    h = historico_produto.dropna(subset=["preco_relativo", "quantidade"])
    h = h[h["preco_relativo"] > 0]
    resultado = {
        "elasticidade": None,
        "preco_relativo_minimo": float(h["preco_relativo"].min()) if len(h) else None,
        "confiavel": False,
        "motivo": "",
    }

    if len(h) < MIN_DIAS_PARA_ESTIMAR:
        resultado["motivo"] = f"Histórico curto demais ({len(h)} dias) para medir o efeito do preço."
        return resultado

    log_preco = np.log(h["preco_relativo"])
    if log_preco.std() < VARIACAO_MINIMA_DO_PRECO:
        resultado["motivo"] = "O preço quase não mudou no histórico; não dá para medir o efeito dele."
        return resultado

    X = h[["dia_semana", "mes"]].assign(log_preco=log_preco)
    modelo = Pipeline([
        # dia da semana e mês viram colunas "sim/não"; log_preco passa direto (fica por último)
        ("preparo", ColumnTransformer(
            [("categorias", OneHotEncoder(drop="first"), ["dia_semana", "mes"])],
            remainder="passthrough",
        )),
        ("regressao", PoissonRegressor(alpha=1e-6, max_iter=1000)),
    ]).fit(X, h["quantidade"])

    elasticidade = float(modelo.named_steps["regressao"].coef_[-1])  # coeficiente do log_preco

    if elasticidade > 0:
        # Preço maior vendendo MAIS não faz sentido econômico: o histórico não permite medir direito.
        resultado.update(elasticidade=round(elasticidade, 3),
                         motivo="O histórico indicou que preço maior vende mais (sem sentido); "
                                "estimativa descartada.")
        return resultado

    resultado.update(elasticidade=round(max(elasticidade, ELASTICIDADE_MINIMA), 3), confiavel=True)
    return resultado
