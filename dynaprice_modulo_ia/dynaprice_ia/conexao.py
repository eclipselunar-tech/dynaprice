"""
conexao.py — ETAPA 1: conexão com o banco SQLite e leitura dos dados.

Este arquivo só LÊ dados (produtos e vendas). A única gravação do módulo
inteiro acontece mais tarde, em analises_ia (etapa 5).
"""

import sqlite3
from pathlib import Path
from urllib.parse import quote

import pandas as pd

from .config import caminho_do_banco
from .erros import BancoNaoEncontrado


def conectar(caminho: str | Path | None = None) -> sqlite3.Connection:
    """
    Abre a conexão com o banco.

    Cuidado importante: por padrão, se o arquivo não existir, o SQLite CRIA um
    banco novo e vazio sem avisar — e o módulo "funcionaria" sem dados.
    Para evitar isso, abrimos com "mode=rw" (ler e gravar, mas NUNCA criar)
    e checamos antes se o arquivo existe.
    """
    caminho = Path(caminho) if caminho else caminho_do_banco()
    if not caminho.is_file():
        raise BancoNaoEncontrado(f"Banco de dados não encontrado: {caminho}")

    # quote(): protege caminhos com caracteres especiais (#, ?, %, espaço) dentro da URI.
    con = sqlite3.connect(f"file:{quote(caminho.resolve().as_posix(), safe='/:')}?mode=rw", uri=True)
    con.row_factory = sqlite3.Row             # permite acessar colunas pelo nome: linha["preco_atual"]
    con.execute("PRAGMA foreign_keys = ON")   # faz o SQLite respeitar as chaves estrangeiras
    return con


def buscar_produto(con: sqlite3.Connection, produto_id: int) -> dict | None:
    """Devolve os dados de um produto como dicionário, ou None se ele não existir."""
    linha = con.execute(
        """SELECT id_produto, codigo_barras, nome, categoria, preco_atual, estoque_atual, ativo
           FROM produtos WHERE id_produto = ?""",
        (produto_id,),
    ).fetchone()
    return dict(linha) if linha else None


def listar_produtos(con: sqlite3.Connection) -> pd.DataFrame:
    """Devolve todos os produtos numa tabela (DataFrame do pandas)."""
    return pd.read_sql(
        "SELECT id_produto, codigo_barras, nome, categoria, preco_atual, estoque_atual, ativo FROM produtos",
        con,
    )


def tem_view_vendas_ativas(con: sqlite3.Connection) -> bool:
    """Verifica se o banco tem a view "vendas_ativas" (só existe na versão nova do banco)."""
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'view' AND name = 'vendas_ativas'"
    ).fetchone() is not None


def tem_coluna_status(con: sqlite3.Connection) -> bool:
    """Verifica se a tabela vendas tem a coluna status."""
    return any(coluna[1] == "status" for coluna in con.execute("PRAGMA table_info(vendas)"))


def origem_das_vendas(con: sqlite3.Connection) -> str:
    """
    De onde ler as vendas ATIVAS (texto fixo, nunca vindo do usuário):
      - banco novo: a view vendas_ativas;
      - banco com status mas sem a view: filtra status = 'ATIVA' na hora;
      - banco antigo (sem status): todas as vendas valem (não existe cancelamento).
    """
    if tem_view_vendas_ativas(con):
        return "vendas_ativas"
    if tem_coluna_status(con):
        return "(SELECT * FROM vendas WHERE status = 'ATIVA')"
    return "vendas"


def data_ultima_venda(con: sqlite3.Connection) -> pd.Timestamp | None:
    """Data da venda (ativa) mais recente do banco inteiro: é o "hoje" dos dados."""
    valor = con.execute(f"SELECT MAX(data_hora) FROM {origem_das_vendas(con)}").fetchone()[0]
    return pd.Timestamp(valor) if valor else None


def buscar_vendas(con: sqlite3.Connection, produto_id: int | None = None) -> pd.DataFrame:
    """
    Devolve os itens vendidos, SÓ de vendas ATIVAS (canceladas ficam de fora,
    porque não representam demanda real).

    Existem duas versões do banco no grupo (ver origem_das_vendas):
      - NOVA (dynaprice_BD_atualizado.db): tem a coluna vendas.status e a view
        "vendas_ativas", que filtra status = 'ATIVA'. Usamos a view.
      - ANTIGA (dynaprice_BD.db do repositório): não tem status nem a view,
        porque ainda não existe cancelamento. Aí todas as vendas valem.

    Colunas devolvidas: id_produto, data_hora, quantidade, preco_unitario.
    Se produto_id for informado, traz só aquele produto; senão, traz todos
    (o modelo é treinado com as vendas de todos os produtos juntos).
    """
    # O nome da origem é fixo (escolhido aqui, nunca vindo do usuário), então é seguro no texto do SQL.
    origem = origem_das_vendas(con)
    sql = f"""
        SELECT i.id_produto, v.data_hora, i.quantidade, i.preco_unitario
        FROM itens_venda i
        JOIN {origem} v ON v.id_venda = i.id_venda
    """
    parametros: tuple = ()
    if produto_id is not None:
        sql += " WHERE i.id_produto = ?"
        parametros = (produto_id,)

    vendas = pd.read_sql(sql, con, params=parametros)
    vendas["data_hora"] = pd.to_datetime(vendas["data_hora"])  # texto -> data de verdade
    return vendas
