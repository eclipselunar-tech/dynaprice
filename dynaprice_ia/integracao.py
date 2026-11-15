"""
integracao.py — ETAPA 6: a função que a aplicação principal (Seven) chama.

    from dynaprice_ia import recalcular_preco
    resultado = recalcular_preco(4)

Fluxo de uma chamada:
    1. Abre o banco e confere o produto (existe? está ativo?).
    2. Monta o histórico diário do produto (etapa 2).
    3. Carrega o modelo treinado (etapa 3) — fica guardado na memória após a 1ª vez.
    4. Calcula o preço sugerido (etapa 4).
    5. Grava a análise em analises_ia (etapa 5).
    6. Devolve um dicionário pronto para virar JSON (jsonify do Flask).

O que esta função NÃO faz (é papel da aplicação principal, após aprovação do usuário):
    alterar produtos.preco_atual, gravar historico_precos, atualizar etiquetas.
"""

import threading
from pathlib import Path

import pandas as pd

from .config import caminho_do_banco
from .conexao import buscar_produto, buscar_vendas, conectar, data_ultima_venda
from .erros import DadosInsuficientes, ProdutoInativo, ProdutoNaoEncontrado
from .modelo import (caminho_do_modelo, carregar_ou_treinar, descricao_do_modelo,
                     treinar_modelo)
from .preparacao import montar_tabela_diaria
from .recomendacao import recomendar_preco
from .registro import registrar_analise

# Modelos já carregados, um por banco: evita ler o arquivo do disco a cada chamada.
# Guarda (data de modificação do arquivo, modelo): se o arquivo mudar (re-treino
# feito em outro programa), o modelo é recarregado.
_modelos_em_memoria: dict[str, tuple[float, dict]] = {}
# Trava: se duas chamadas chegarem juntas, só uma treina/carrega o modelo por vez.
_trava = threading.Lock()


def _data_do_arquivo(arquivo: Path) -> float | None:
    return arquivo.stat().st_mtime if arquivo.is_file() else None


def _obter_modelo(caminho_banco: Path) -> dict | None:
    """Devolve o modelo do banco (da memória, do arquivo ou treinando). None = dados insuficientes."""
    chave = str(caminho_banco.resolve())
    arquivo = caminho_do_modelo(caminho_banco)
    with _trava:
        em_memoria = _modelos_em_memoria.get(chave)
        if em_memoria and em_memoria[0] == _data_do_arquivo(arquivo):
            return em_memoria[1]
        try:
            pacote = carregar_ou_treinar(caminho_banco)
        except DadosInsuficientes:
            # Não guarda nada de propósito: na próxima chamada tenta de novo,
            # porque podem ter entrado vendas novas.
            return None
        _modelos_em_memoria[chave] = (_data_do_arquivo(arquivo), pacote)
        return pacote


def retreinar_modelo(caminho_banco=None, mostrar: bool = True) -> dict:
    """
    Re-treina o modelo com os dados atuais do banco (usar quando entrarem muitas vendas novas,
    por exemplo, uma vez por semana). Também atualiza o modelo guardado na memória.
    """
    caminho_banco = Path(caminho_banco) if caminho_banco else caminho_do_banco()
    with _trava:
        pacote = treinar_modelo(caminho_banco, salvar=True, mostrar=mostrar)
        _modelos_em_memoria[str(caminho_banco.resolve())] = (
            _data_do_arquivo(caminho_do_modelo(caminho_banco)), pacote)
    return pacote


def recalcular_preco(produto_id: int, caminho_banco=None) -> dict:
    """
    Analisa um produto, sugere um preço e registra a análise em analises_ia.

    Parâmetros:
        produto_id    -> id_produto da tabela produtos
        caminho_banco -> (opcional) caminho do arquivo .db. Se não for informado,
                         usa a variável de ambiente DYNAPRICE_BANCO ou o padrão do config.py.

    Devolve um dicionário, por exemplo:
        {"produto_id": 4, "preco_atual": 10.49, "preco_sugerido": 11.09,
         "demanda_prevista": 98, "confianca": 0.7, "id_analise": 15,
         "situacao": "SUBIR", "motivo": "Estoque cobre só 3.0 dias ...",
         "variacao_percentual": 5.72, "cobertura_dias": 3.0}

    Erros possíveis (todos herdam de erros.ErroDynaPriceIA):
        ProdutoNaoEncontrado, ProdutoInativo, BancoNaoEncontrado
        ValueError -> produto_id não é um número inteiro
    """
    # bool é recusado (True viraria 1) e número quebrado também (3.7 viraria 3, outro produto).
    if isinstance(produto_id, bool) or (isinstance(produto_id, float) and not produto_id.is_integer()):
        raise ValueError(f"produto_id deve ser um número inteiro (recebido: {produto_id!r}).")
    try:
        produto_id = int(produto_id)
    except (TypeError, ValueError):
        raise ValueError(f"produto_id deve ser um número inteiro (recebido: {produto_id!r}).") from None

    caminho_banco = Path(caminho_banco) if caminho_banco else caminho_do_banco()
    con = conectar(caminho_banco)  # dá BancoNaoEncontrado se o arquivo não existir
    try:
        # ---- 1. Conferir o produto ----
        produto = buscar_produto(con, produto_id)
        if produto is None:
            raise ProdutoNaoEncontrado(f"Não existe produto com id {produto_id}.")
        if produto["ativo"] != 1:
            raise ProdutoInativo(f"O produto {produto_id} ({produto['nome']}) está inativo.")

        # ---- 2. Histórico diário do produto ----
        # A data de referência é a última venda do BANCO INTEIRO (não só deste produto),
        # para que dias recentes sem venda deste produto contem como zero.
        historico = montar_tabela_diaria(
            buscar_vendas(con, produto_id),
            pd.DataFrame([produto]),
            data_referencia=data_ultima_venda(con),
        )

        # ---- 3 e 4. Modelo + recomendação ----
        pacote = _obter_modelo(caminho_banco)
        resultado = recomendar_preco(pacote, produto, historico)

        # ---- 5. Registrar ----
        id_analise = registrar_analise(con, resultado, descricao_do_modelo(pacote))
    finally:
        con.close()

    # ---- 6. Devolver só tipos "comuns" do Python (o jsonify do Flask não aceita tipos do numpy) ----
    return {
        "produto_id": int(resultado["produto_id"]),
        "preco_atual": float(resultado["preco_atual"]),
        "preco_sugerido": float(resultado["preco_sugerido"]),
        "demanda_prevista": int(resultado["demanda_prevista"]),
        "confianca": float(resultado["confianca"]),
        "id_analise": int(id_analise),
        "situacao": str(resultado["situacao"]),
        "motivo": str(resultado["motivo"]),
        "variacao_percentual": float(resultado["variacao_percentual"]),
        "cobertura_dias": None if resultado["cobertura_dias"] is None else float(resultado["cobertura_dias"]),
    }
