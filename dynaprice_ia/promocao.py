"""
promocao.py — Avalia se uma PROMOÇÃO vale a pena (pedido do líder / professor).

    from dynaprice_ia import avaliar_promocao
    resultado = avaliar_promocao(6, desconto_percentual=15, dias=7)

SOMENTE LEITURA: esta função não grava nada no banco, não altera preços e não
mexe em etiquetas. Ela só calcula e devolve a avaliação.

Como funciona:
    1. Demanda SEM promoção: prevista pelo modelo de demanda que já existe
       (o mesmo do recalcular_preco), no preço atual, para os `dias` da promoção.
    2. Demanda COM promoção: demanda sem promoção x (1 - desconto) ^ elasticidade
       (a elasticidade vem de elasticidade.py). Ex.: elasticidade -1.8 e 15% de
       desconto -> 0.85 ^ -1.8 = 1.34 -> vende ~34% a mais.
    3. Receita = unidades vendidas x preço. As unidades nunca passam do estoque
       (não dá para vender o que não existe).
    4. Veredito:
         "não vale a pena" -> a receita com promoção é MENOR ou igual (ou não há estoque)
         "arriscado"       -> a receita sobe, mas o estoque acaba antes do fim da promoção,
                              ou o desconto leva o preço abaixo de qualquer preço já visto
                              no histórico, ou não há dados para medir o efeito do preço
         "vale a pena"     -> a receita sobe e nenhum dos riscos acima acontece

IMPORTANTE: a análise é de RECEITA, não de LUCRO. O banco não tem o custo dos
produtos; uma promoção pode aumentar a receita e mesmo assim dar prejuízo.
"""

import math
from pathlib import Path

import pandas as pd

from .config import MIN_DIAS_COM_VENDA, MIN_DIAS_HISTORICO, caminho_do_banco
from .conexao import buscar_produto, buscar_vendas, conectar, data_ultima_venda
from .elasticidade import estimar_elasticidade
from .erros import ProdutoInativo, ProdutoNaoEncontrado
from .integracao import _obter_modelo
from .modelo import prever_demanda
from .preparacao import montar_tabela_diaria

# Limites aceitos (decididos com o grupo)
DESCONTO_MINIMO, DESCONTO_MAXIMO = 1, 50   # em %
DIAS_MINIMO, DIAS_MAXIMO = 1, 30

VALE, NAO_VALE, ARRISCADO = "vale a pena", "não vale a pena", "arriscado"
AVISO_RECEITA = "Atenção: análise de RECEITA, não de lucro (o custo do produto não está no banco)."
AVISO_SIMULADO = "Modelo treinado com DADOS SIMULADOS."


# ---------------------------------------------------------------------------
# Validação das entradas
# ---------------------------------------------------------------------------
def _validar_inteiro(valor, nome: str) -> int:
    """Aceita 7 ou 7.0; recusa True/False, 2.5, texto e vazio."""
    if isinstance(valor, bool) or (isinstance(valor, float) and not valor.is_integer()):
        raise ValueError(f"{nome} deve ser um número inteiro (recebido: {valor!r}).")
    try:
        return int(valor)
    except (TypeError, ValueError):
        raise ValueError(f"{nome} deve ser um número inteiro (recebido: {valor!r}).") from None


def _validar_desconto(desconto) -> float:
    if isinstance(desconto, bool) or not isinstance(desconto, (int, float)) or math.isnan(desconto):
        raise ValueError(f"desconto_percentual deve ser um número (recebido: {desconto!r}).")
    if not DESCONTO_MINIMO <= desconto <= DESCONTO_MAXIMO:
        raise ValueError(f"desconto_percentual deve estar entre {DESCONTO_MINIMO} e {DESCONTO_MAXIMO} "
                         f"(recebido: {desconto}).")
    return float(desconto)


def _validar_dias(dias) -> int:
    dias = _validar_inteiro(dias, "dias")
    if not DIAS_MINIMO <= dias <= DIAS_MAXIMO:
        raise ValueError(f"dias deve estar entre {DIAS_MINIMO} e {DIAS_MAXIMO} (recebido: {dias}).")
    return dias


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------
def avaliar_promocao(produto_id: int, desconto_percentual: float, dias: int, caminho_banco=None) -> dict:
    """
    Avalia uma promoção de `desconto_percentual`% durante `dias` dias para um produto.

    Devolve um dicionário pronto para jsonify, por exemplo:
        {"produto_id": 8, "nome": "Iogurte Morango 170g (SIMULADO)",
         "preco_atual": 3.39, "preco_promocional": 2.88,
         "demanda_sem_promocao": 80, "demanda_com_promocao": 101,
         "receita_sem": 271.2, "receita_com": 290.88, "variacao_receita_percentual": 7.26,
         "cobertura_estoque_dias": 41.6, "veredito": "vale a pena", "motivo": "...",
         "desconto_percentual": 15.0, "dias": 7, "elasticidade_estimada": -1.45}

    Erros: ProdutoNaoEncontrado, ProdutoInativo, BancoNaoEncontrado e ValueError
    (produto_id, desconto ou dias inválidos).
    """
    produto_id = _validar_inteiro(produto_id, "produto_id")
    desconto = _validar_desconto(desconto_percentual)
    dias = _validar_dias(dias)

    caminho_banco = Path(caminho_banco) if caminho_banco else caminho_do_banco()
    con = conectar(caminho_banco)  # só leitura daqui em diante: nenhum INSERT/UPDATE neste arquivo
    try:
        produto = buscar_produto(con, produto_id)
        if produto is None:
            raise ProdutoNaoEncontrado(f"Não existe produto com id {produto_id}.")
        if produto["ativo"] != 1:
            raise ProdutoInativo(f"O produto {produto_id} ({produto['nome']}) está inativo.")
        historico = montar_tabela_diaria(
            buscar_vendas(con, produto_id),
            pd.DataFrame([produto]),
            data_referencia=data_ultima_venda(con),
        )
    finally:
        con.close()

    pacote = _obter_modelo(caminho_banco)  # o mesmo modelo de demanda do recalcular_preco
    preco_atual = float(produto["preco_atual"])
    estoque = int(produto["estoque_atual"])
    fator_preco = 1 - desconto / 100
    preco_promocional = round(preco_atual * fator_preco, 2)

    resultado = {
        "produto_id": produto_id,
        "nome": str(produto["nome"]),
        "preco_atual": preco_atual,
        "preco_promocional": preco_promocional,
        "demanda_sem_promocao": 0,
        "demanda_com_promocao": None,
        "receita_sem": 0.0,
        "receita_com": None,
        "variacao_receita_percentual": None,
        "cobertura_estoque_dias": None,
        "veredito": ARRISCADO,
        "motivo": "",
        "desconto_percentual": desconto,
        "dias": dias,
        "elasticidade_estimada": None,
    }
    avisos = AVISO_RECEITA + (f" {AVISO_SIMULADO}" if pacote and pacote.get("dados_simulados") else "")

    # ---- Caso 1: poucos dados (mesma regra do recalcular_preco) -> "arriscado" ----
    dias_historico = len(historico)
    dias_com_venda = int((historico["quantidade"] > 0).sum()) if dias_historico else 0
    if dias_historico < MIN_DIAS_HISTORICO or dias_com_venda < MIN_DIAS_COM_VENDA or pacote is None:
        media = float(historico["quantidade"].mean()) if dias_historico else 0.0
        demanda_sem = media * dias
        if pacote is None:
            causa = "O banco ainda não tem vendas suficientes para treinar o modelo."
        else:
            causa = (f"Pouco histórico ({dias_historico} dia(s), {dias_com_venda} com venda; mínimo "
                     f"{MIN_DIAS_HISTORICO} dias e {MIN_DIAS_COM_VENDA} com venda).")
        resultado.update(
            demanda_sem_promocao=int(round(demanda_sem)),
            receita_sem=round(min(demanda_sem, estoque) * preco_atual, 2),
            motivo=f"{causa} Não dá para prever o efeito da promoção com segurança. {avisos}",
        )
        return _tipos_python(resultado)

    # ---- Demanda sem promoção (modelo existente) ----
    preco_medio = float(historico["preco"].mean())
    preco_relativo = preco_atual / preco_medio if preco_medio > 0 else 1.0
    demanda_sem = prever_demanda(pacote, historico, preco_relativo, dias=dias)

    # ---- Efeito do desconto (elasticidade) ----
    estimativa = estimar_elasticidade(historico)
    resultado["elasticidade_estimada"] = estimativa["elasticidade"]
    unidades_sem = min(demanda_sem, estoque)
    receita_sem = unidades_sem * preco_atual
    resultado.update(demanda_sem_promocao=int(round(demanda_sem)), receita_sem=round(receita_sem, 2))

    if not estimativa["confiavel"]:
        resultado["motivo"] = f"{estimativa['motivo']} {avisos}"
        return _tipos_python(resultado)

    demanda_com = demanda_sem * fator_preco ** estimativa["elasticidade"]
    unidades_com = min(demanda_com, estoque)
    receita_com = unidades_com * preco_promocional
    variacao = (receita_com / receita_sem - 1) * 100 if receita_sem > 0 else None
    cobertura = estoque / (demanda_com / dias) if demanda_com > 0 else None

    resultado.update(
        demanda_com_promocao=int(round(demanda_com)),
        receita_com=round(receita_com, 2),
        variacao_receita_percentual=None if variacao is None else round(variacao, 2),
        cobertura_estoque_dias=None if cobertura is None else round(cobertura, 1),
    )

    # ---- Veredito ----
    vendas_a_mais = (demanda_com / demanda_sem - 1) * 100 if demanda_sem > 0 else 0.0
    resumo = (f"Com {desconto:g}% de desconto por {dias} dia(s), a previsão passa de "
              f"{demanda_sem:.0f} para {demanda_com:.0f} unidades ({vendas_a_mais:+.0f}%) e a receita "
              f"de R$ {receita_sem:.2f} para R$ {receita_com:.2f}"
              + (f" ({variacao:+.1f}%)." if variacao is not None else "."))
    fora_do_historico = preco_relativo * fator_preco < estimativa["preco_relativo_minimo"] - 1e-9
    falta_estoque = estoque < demanda_com

    if estoque == 0:
        veredito, explicacao = NAO_VALE, "Produto sem estoque: não há o que vender na promoção."
    elif receita_com <= receita_sem and estoque <= demanda_sem:
        veredito, explicacao = NAO_VALE, (f"O estoque ({estoque} un) já acaba mesmo SEM promoção: "
                                          "o desconto só venderia as mesmas unidades mais barato.")
    elif receita_com <= receita_sem:
        veredito, explicacao = NAO_VALE, ("O aumento das vendas não compensa o preço menor "
                                          "(produto pouco sensível a desconto).")
    elif falta_estoque or fora_do_historico:
        riscos = []
        if falta_estoque:
            riscos.append(f"o estoque ({estoque} un) acaba em ~{cobertura:.1f} dia(s), antes do fim da promoção")
        if fora_do_historico:
            riscos.append("o desconto leva o preço abaixo de qualquer preço já praticado, "
                          "então a previsão é menos segura")
        veredito, explicacao = ARRISCADO, "A receita sobe, mas " + " e ".join(riscos) + "."
    else:
        veredito, explicacao = VALE, "A receita sobe e o estoque aguenta a promoção inteira."

    resultado.update(veredito=veredito, motivo=f"{resumo} {explicacao} {avisos}")
    return _tipos_python(resultado)


def _tipos_python(resultado: dict) -> dict:
    """Garante tipos comuns do Python (o jsonify do Flask não aceita tipos do numpy)."""
    convertido = {}
    for chave, valor in resultado.items():
        if valor is None or isinstance(valor, (str, bool)):
            convertido[chave] = valor
        elif chave in ("produto_id", "dias", "demanda_sem_promocao", "demanda_com_promocao"):
            convertido[chave] = int(valor)
        else:
            convertido[chave] = float(valor)
    return convertido
