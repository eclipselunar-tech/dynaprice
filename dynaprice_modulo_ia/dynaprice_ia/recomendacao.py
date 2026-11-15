"""
recomendacao.py — ETAPA 4: transformar a demanda prevista em um PREÇO SUGERIDO.

Ideia central (regra de demanda x estoque):
    1. O modelo prevê quantas unidades vão vender nos próximos 7 dias.
    2. Calculamos a COBERTURA: para quantos dias o estoque atual dá.
         cobertura = estoque_atual / demanda_diária_prevista
    3. Regra:
         cobertura < 7 dias   -> vai faltar produto  -> SOBE o preço
         7 a 30 dias          -> equilibrado         -> MANTÉM
         cobertura > 30 dias  -> estoque parado      -> DESCE o preço
    4. O ajuste é PROPORCIONAL e nunca passa de ±10% (LIMITE_VARIACAO_PRECO):
         - para subir:  cobertura 7 dias -> 0%  ...  cobertura 0 dia  -> +10%
         - para descer: cobertura 30 dias -> 0% ... cobertura 60+ dias -> -10%
    5. Arredonda para terminar em 9 centavos (padrão do varejo), sem furar o limite.

Por que essa regra e não "o modelo escolhe o preço que dá mais lucro"?
    - Não temos o CUSTO dos produtos, então não dá para calcular lucro.
    - O teste da etapa 3 mostrou que o modelo enxerga bem a demanda, mas
      enxerga FRACO o efeito do preço. Então usamos o modelo para o que ele faz
      bem (prever demanda) e uma regra clara e explicável para o preço.

Este arquivo NÃO acessa o banco: só calcula. Isso facilita testar.
"""

import math

import pandas as pd

from .config import (CONFIANCA_POUCO_HISTORICO, COBERTURA_MAXIMA_DIAS,
                     COBERTURA_MINIMA_DIAS, HORIZONTE_DIAS, LIMITE_VARIACAO_PRECO,
                     MIN_DIAS_COM_VENDA, MIN_DIAS_HISTORICO)
from .modelo import prever_demanda

# Códigos de situação devolvidos (ajudam o Seven a mostrar a mensagem certa)
SUBIR, MANTER, DESCER = "SUBIR", "MANTER", "DESCER"
POUCO_HISTORICO, SEM_ESTOQUE = "POUCO_HISTORICO", "SEM_ESTOQUE"


def calcular_variacao(cobertura_dias: float, limite: float = LIMITE_VARIACAO_PRECO) -> float:
    """
    Devolve a variação de preço (ex.: 0.05 = +5%, -0.10 = -10%) a partir da cobertura.
    Ajuste proporcional: quanto mais longe da faixa equilibrada, maior a mudança.
    """
    if cobertura_dias < COBERTURA_MINIMA_DIAS:
        intensidade = (COBERTURA_MINIMA_DIAS - cobertura_dias) / COBERTURA_MINIMA_DIAS
        return limite * min(intensidade, 1.0)
    if cobertura_dias > COBERTURA_MAXIMA_DIAS:
        intensidade = (cobertura_dias - COBERTURA_MAXIMA_DIAS) / COBERTURA_MAXIMA_DIAS
        return -limite * min(intensidade, 1.0)
    return 0.0


def arredondar_preco_varejo(valor: float, minimo: float, maximo: float) -> float:
    """
    Arredonda para o preço terminado em 9 centavos mais próximo (ex.: 10.52 -> 10.49),
    escolhendo só entre opções dentro do limite [minimo, maximo].
    Se nenhuma opção "...9" couber no limite (preços muito baixos), usa centavos normais.
    """
    acima = round(math.floor(valor * 10) / 10 + 0.09, 2)   # ex.: 10.52 -> 10.59
    abaixo = round(acima - 0.10, 2)                         # ex.: 10.52 -> 10.49
    opcoes = [p for p in (abaixo, acima) if minimo - 1e-9 <= p <= maximo + 1e-9 and p >= 0]
    if opcoes:
        return min(opcoes, key=lambda p: abs(p - valor))
    return round(min(max(valor, minimo), maximo), 2)


def calcular_confianca(pacote: dict, id_produto: int) -> float:
    """
    Confiança = 1 - erro relativo do modelo NESSE produto no teste.
    Ex.: errou 18% da venda média -> confiança 0.82.
    Produto sem medição no teste usa a média dos outros produtos.
    """
    erros = pacote.get("erro_relativo_por_produto", {})
    erro = erros.get(id_produto)
    if erro is None:
        erro = sum(erros.values()) / len(erros) if erros else 1.0
    return round(min(max(1 - erro, 0.0), 1.0), 2)


def calcular_sazonalidade(historico_produto: pd.DataFrame) -> float:
    """
    Fator do mês: quanto o produto costuma vender no mês da previsão, comparado
    à média dele no ano. Ex.: 1.30 = esse mês vende 30% acima do normal.
    Devolve 0 quando não há vendas daquele mês no histórico (não dá para medir).
    """
    if historico_produto.empty:
        return 0.0
    mes_previsao = (historico_produto["data"].max() + pd.Timedelta(days=1)).month
    media_geral = historico_produto["quantidade"].mean()
    do_mes = historico_produto.loc[historico_produto["data"].dt.month == mes_previsao, "quantidade"]
    if do_mes.empty or media_geral == 0:
        return 0.0
    return round(float(do_mes.mean() / media_geral), 3)


def esta_em_promocao(preco_relativo: float) -> int:
    """1 se o preço atual está 10% ou mais ABAIXO do preço médio do produto (já está 'em promoção')."""
    return 1 if preco_relativo <= 0.90 else 0


def recomendar_preco(pacote: dict | None, produto: dict, historico_produto: pd.DataFrame) -> dict:
    """
    Calcula o preço sugerido para UM produto.

    pacote            -> modelo treinado (modelo.carregar_ou_treinar), ou None se
                         o banco ainda não tem dados para treinar (preço é mantido)
    produto           -> dados do produto (conexao.buscar_produto)
    historico_produto -> linhas "produto x dia" desse produto (preparacao.montar_tabela_diaria)
    """
    preco_atual = float(produto["preco_atual"])
    estoque = int(produto["estoque_atual"])
    dias_historico = len(historico_produto)

    resultado = {
        "produto_id": int(produto["id_produto"]),
        "preco_atual": preco_atual,
        "preco_sugerido": preco_atual,
        "variacao_percentual": 0.0,
        "demanda_prevista": 0,
        "cobertura_dias": None,
        "confianca": CONFIANCA_POUCO_HISTORICO,
        "situacao": MANTER,
        "motivo": "",
        "preco_relativo": 1.0,
        "promocao": 0,
        "sazonalidade": calcular_sazonalidade(historico_produto),
        "estoque_atual": estoque,
    }

    dias_com_venda = int((historico_produto["quantidade"] > 0).sum()) if dias_historico else 0

    # ---- Caso 1: pouco histórico (do produto ou do banco todo) -> não arrisca, mantém o preço ----
    if dias_historico < MIN_DIAS_HISTORICO or dias_com_venda < MIN_DIAS_COM_VENDA or pacote is None:
        media = float(historico_produto["quantidade"].mean()) if dias_historico else 0.0
        if dias_historico < MIN_DIAS_HISTORICO:
            motivo = f"Só {dias_historico} dia(s) de histórico (mínimo {MIN_DIAS_HISTORICO})."
        elif dias_com_venda < MIN_DIAS_COM_VENDA:
            motivo = f"Só {dias_com_venda} dia(s) com venda (mínimo {MIN_DIAS_COM_VENDA})."
        else:
            motivo = "O banco ainda não tem vendas suficientes para treinar o modelo."
        resultado.update(
            demanda_prevista=int(round(media * HORIZONTE_DIAS)),
            situacao=POUCO_HISTORICO,
            motivo=motivo + " Preço mantido; previsão baseada na média simples.",
        )
        return resultado

    # ---- Previsão do modelo, no preço atual ----
    # preco_relativo = preço atual comparado ao preço médio histórico do produto
    # (mesma conta feita na preparação dos dados).
    preco_medio = float(historico_produto["preco"].mean())
    preco_relativo = preco_atual / preco_medio if preco_medio > 0 else 1.0
    demanda_7d = prever_demanda(pacote, historico_produto, preco_relativo)
    demanda_diaria = demanda_7d / HORIZONTE_DIAS
    confianca = calcular_confianca(pacote, int(produto["id_produto"]))

    resultado.update(
        demanda_prevista=int(round(demanda_7d)),
        confianca=confianca,
        preco_relativo=round(preco_relativo, 3),
        promocao=esta_em_promocao(preco_relativo),
    )

    # ---- Caso 2: sem estoque -> mantém (não adianta mexer no preço do que não está à venda) ----
    if estoque == 0:
        resultado.update(cobertura_dias=0.0, situacao=SEM_ESTOQUE,
                         motivo="Produto sem estoque. Preço mantido; providenciar reposição.")
        return resultado

    # ---- Caso 3: regra de cobertura ----
    cobertura = estoque / demanda_diaria if demanda_diaria > 0 else math.inf
    variacao = calcular_variacao(cobertura)

    if variacao == 0 or preco_atual == 0:
        preco_sugerido = preco_atual
    else:
        minimo = preco_atual * (1 - LIMITE_VARIACAO_PRECO)
        maximo = preco_atual * (1 + LIMITE_VARIACAO_PRECO)
        preco_sugerido = arredondar_preco_varejo(preco_atual * (1 + variacao), minimo, maximo)
        # Se o arredondamento empurrou para o lado contrário da intenção, mantém o preço.
        if (variacao > 0 and preco_sugerido < preco_atual) or (variacao < 0 and preco_sugerido > preco_atual):
            preco_sugerido = preco_atual

    if preco_sugerido > preco_atual:
        situacao = SUBIR
    elif preco_sugerido < preco_atual:
        situacao = DESCER
    else:
        situacao = MANTER

    texto_cobertura = "sem demanda prevista" if math.isinf(cobertura) else f"{cobertura:.1f} dias"
    motivos = {
        SUBIR: f"Estoque cobre só {texto_cobertura} (mínimo {COBERTURA_MINIMA_DIAS}): demanda alta para o estoque.",
        DESCER: f"Estoque cobre {texto_cobertura} (máximo {COBERTURA_MAXIMA_DIAS}): estoque parado.",
        MANTER: f"Estoque cobre {texto_cobertura}: equilibrado (ou ajuste pequeno demais).",
    }

    resultado.update(
        preco_sugerido=round(preco_sugerido, 2),
        variacao_percentual=round((preco_sugerido / preco_atual - 1) * 100, 2) if preco_atual else 0.0,
        cobertura_dias=None if math.isinf(cobertura) else round(cobertura, 1),
        situacao=situacao,
        motivo=motivos[situacao],
    )
    return resultado
