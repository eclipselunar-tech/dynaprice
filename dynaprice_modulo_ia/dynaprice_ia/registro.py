"""
registro.py — ETAPA 5: gravar o resultado da análise na tabela analises_ia.

Esta é a ÚNICA gravação que o módulo de IA faz no banco.
O módulo NÃO altera produtos.preco_atual, NÃO grava em historico_precos e
NÃO mexe em etiquetas/atualizacoes_etiqueta: isso é feito pela aplicação
principal (Seven), depois que o usuário aprovar a sugestão.

Como cada coluna é preenchida:
    id_produto         -> o produto analisado
    data_hora          -> hora LOCAL do computador (o padrão CURRENT_TIMESTAMP
                          do SQLite grava em UTC, 3h à frente de Brasília;
                          o app.py do grupo usa hora local, então seguimos ele)
    demanda            -> unidades previstas para os próximos 7 dias
    estoque_informado  -> estoque no momento da análise
    promocao           -> 1 se o preço atual está 10%+ abaixo da média do produto
    sazonalidade       -> fator do mês (1.30 = mês vende 30% acima do normal; 0 = sem dado)
    preco_analisado    -> preço atual
    preco_recomendado  -> preço sugerido
    confianca          -> 0 a 1
    modelo             -> ex.: "Random Forest | treino 2026-11-11 | DADOS SIMULADOS"
"""

import sqlite3
from datetime import datetime


def validar_antes_de_gravar(dados: dict) -> None:
    """
    Confere as mesmas regras (CHECK / NOT NULL) da tabela analises_ia ANTES de
    gravar. O banco recusaria de qualquer forma, mas aqui a mensagem de erro
    fica clara, dizendo qual campo está errado.
    """
    problemas = []
    if dados["demanda"] is None or dados["demanda"] < 0:
        problemas.append("demanda deve ser >= 0")
    if dados["estoque_informado"] is None or dados["estoque_informado"] < 0:
        problemas.append("estoque_informado deve ser >= 0")
    if dados["promocao"] not in (0, 1):
        problemas.append("promocao deve ser 0 ou 1")
    if dados["sazonalidade"] is None:
        problemas.append("sazonalidade não pode ser vazia")
    if dados["preco_analisado"] is None or dados["preco_analisado"] < 0:
        problemas.append("preco_analisado deve ser >= 0")
    if dados["preco_recomendado"] is None or dados["preco_recomendado"] < 0:
        problemas.append("preco_recomendado deve ser >= 0")
    if dados["confianca"] is not None and not (0 <= dados["confianca"] <= 1):
        problemas.append("confianca deve estar entre 0 e 1")
    if problemas:
        raise ValueError("Análise inválida, não gravada: " + "; ".join(problemas))


def registrar_analise(con: sqlite3.Connection, resultado: dict, descricao_modelo: str) -> int:
    """
    Grava uma linha em analises_ia e devolve o id_analise criado.

    resultado        -> saída de recomendacao.recomendar_preco
    descricao_modelo -> saída de modelo.descricao_do_modelo
    """
    dados = {
        "id_produto": int(resultado["produto_id"]),
        "data_hora": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "demanda": int(resultado["demanda_prevista"]),
        "estoque_informado": int(resultado["estoque_atual"]),
        "promocao": int(resultado["promocao"]),
        "sazonalidade": float(resultado["sazonalidade"]),
        "preco_analisado": float(resultado["preco_atual"]),
        "preco_recomendado": float(resultado["preco_sugerido"]),
        "confianca": float(resultado["confianca"]),
        "modelo": descricao_modelo,
    }
    validar_antes_de_gravar(dados)

    with con:  # transação: grava tudo ou nada
        cursor = con.execute(
            """INSERT INTO analises_ia (id_produto, data_hora, demanda, estoque_informado, promocao,
                                        sazonalidade, preco_analisado, preco_recomendado, confianca, modelo)
               VALUES (:id_produto, :data_hora, :demanda, :estoque_informado, :promocao,
                       :sazonalidade, :preco_analisado, :preco_recomendado, :confianca, :modelo)""",
            dados,
        )
    return int(cursor.lastrowid)
