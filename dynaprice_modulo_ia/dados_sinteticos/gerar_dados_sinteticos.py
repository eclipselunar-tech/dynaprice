"""
gerar_dados_sinteticos.py
=========================

ATENÇÃO: ESTE SCRIPT GERA DADOS SIMULADOS (INVENTADOS).

Por que ele existe?
    O banco do DynaPrice ainda está vazio (o sistema está saindo do papel).
    Um modelo de Machine Learning aprende com exemplos do passado; sem vendas,
    não há o que aprender. Então criamos vendas "de mentira", mas com padrões
    realistas, só para conseguir treinar e testar o módulo de IA.

O que ele faz?
    1. Copia a ESTRUTURA do banco original (dynaprice_BD_atualizado.db) para um
       arquivo novo: dados_sinteticos/dynaprice_teste_sintetico.db.
       O banco original é aberto SÓ PARA LEITURA e nunca é alterado.
    2. Cadastra produtos simulados e gera 1 ano de vendas para eles.

Como reconhecer o que é simulado?
    - Nome do produto termina com "(SIMULADO)".
    - Código de barras começa com "SIM-".
    - Motivos em historico_precos / historico_vendas começam com "[SIMULADO]".

Quais padrões foram simulados (é ISSO que o modelo vai "descobrir")?
    a) Dia da semana: sábado vende mais, terça vende menos.
    b) Mês (sazonalidade): bebidas e sorvete vendem mais no verão,
       café e chocolate vendem mais no inverno, quase tudo sobe em dezembro.
    c) Preço x demanda (elasticidade): quando o preço sobe, vende menos;
       em promoção, vende mais. Cada produto reage com uma intensidade diferente.
    d) Sorte/acaso: a quantidade do dia é sorteada (distribuição de Poisson),
       então dois sábados iguais não vendem exatamente o mesmo.

Casos especiais criados de propósito (para testar o tratamento de erros):
    - 1 produto LANÇAMENTO, com só 10 dias de vendas (pouco histórico).
    - 1 produto INATIVO (ativo = 0), que parou de vender há 60 dias.
    - 1 produto SEM NENHUMA VENDA.
    - ~3% das vendas são CANCELADAS (o modelo deve ignorá-las).

Quando o grupo tiver dados reais, basta apagar a pasta dados_sinteticos/
e apontar o módulo para o banco real.

Como rodar (no terminal, dentro da pasta do projeto):
    python dados_sinteticos/gerar_dados_sinteticos.py
    python dados_sinteticos/gerar_dados_sinteticos.py --sobrescrever   (recria o arquivo)
"""

import argparse
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import numpy as np

# ---------------------------------------------------------------------------
# CONFIGURAÇÕES
# ---------------------------------------------------------------------------
PASTA = Path(__file__).resolve().parent
BANCO_ORIGINAL = PASTA.parent / "dynaprice_BD_atualizado.db"
BANCO_SINTETICO = PASTA / "dynaprice_teste_sintetico.db"

SEMENTE = 42                   # "semente" do sorteio: mesma semente = mesmos dados sempre (reprodutível)
DIAS_DE_HISTORICO = 365        # 1 ano de vendas
DATA_FINAL = date(2026, 11, 10)  # último dia com vendas (fixo, para os dados serem sempre iguais)
CHANCE_CANCELAMENTO = 0.03     # 3% das vendas serão canceladas

MARCA = "(SIMULADO)"

# Fator do DIA DA SEMANA (0 = segunda ... 6 = domingo). 1.0 = dia "normal".
FATOR_DIA_SEMANA = {0: 0.85, 1: 0.80, 2: 0.90, 3: 0.95, 4: 1.15, 5: 1.45, 6: 1.10}

# Fator do MÊS, por perfil de sazonalidade (1 = janeiro ... 12 = dezembro).
FATOR_MES = {
    "padrao":  {1: 1.05, 2: 0.95, 3: 1.00, 4: 1.00, 5: 1.00, 6: 1.00,
                7: 1.00, 8: 1.00, 9: 1.00, 10: 1.00, 11: 1.05, 12: 1.25},
    "verao":   {1: 1.40, 2: 1.35, 3: 1.15, 4: 1.00, 5: 0.85, 6: 0.75,
                7: 0.70, 8: 0.80, 9: 0.95, 10: 1.10, 11: 1.20, 12: 1.40},
    "inverno": {1: 0.85, 2: 0.85, 3: 0.95, 4: 1.00, 5: 1.10, 6: 1.30,
                7: 1.35, 8: 1.20, 9: 1.00, 10: 0.95, 11: 1.00, 12: 1.10},
}

# Cadastro dos produtos simulados.
#   preco_base   = preço "de referência" do produto
#   demanda_base = unidades vendidas num dia normal, ao preço de referência
#   elasticidade = quanto a demanda reage ao preço. Ex.: -1.5 significa que
#                  um preço 10% mais alto vende ~15% menos. Perto de 0 = item
#                  essencial (arroz, leite), que vende quase igual mesmo mais caro.
#   cobertura    = estoque atual em "dias de venda" (para ter produtos com
#                  estoque baixo e outros com estoque sobrando)
#   situacao     = "normal", "lancamento", "inativo" ou "sem_vendas"
PRODUTOS = [
    # nome,                      categoria,     preco, demanda, elastic., perfil,    cobertura, situacao
    ("Arroz Branco 5kg",          "Mercearia",   27.90,  6,  -0.6, "padrao",   20, "normal"),
    ("Feijao Carioca 1kg",        "Mercearia",    8.49,  9,  -0.7, "padrao",   45, "normal"),
    ("Cafe Torrado 500g",         "Mercearia",   18.90,  7,  -0.9, "inverno",   4, "normal"),
    ("Refrigerante Cola 2L",      "Bebidas",      9.99, 14,  -1.6, "verao",     3, "normal"),
    ("Agua Mineral 1,5L",         "Bebidas",      3.49, 18,  -1.2, "verao",    15, "normal"),
    ("Cerveja Lata 350ml",        "Bebidas",      4.29, 25,  -1.8, "verao",     6, "normal"),
    ("Leite Integral 1L",         "Laticinios",   5.49, 20,  -0.5, "padrao",   10, "normal"),
    ("Iogurte Morango 170g",      "Laticinios",   3.29, 10,  -1.4, "verao",    60, "normal"),
    ("Sabonete 90g",              "Higiene",      2.79,  8,  -1.1, "padrao",   90, "normal"),
    ("Detergente 500ml",          "Limpeza",      2.49,  9,  -1.0, "padrao",   30, "normal"),
    ("Chocolate ao Leite 90g",    "Doces",        6.99,  8,  -1.5, "inverno",  12, "normal"),
    ("Sorvete Pote 1,5L",         "Doces",       21.90,  3,  -1.7, "verao",    50, "normal"),
    ("Biscoito Recheado 130g",    "Doces",        4.59,  7,  -1.3, "padrao",   20, "lancamento"),
    ("Suco de Caixa 1L",          "Bebidas",      7.49,  6,  -1.2, "verao",    25, "inativo"),
    ("Azeite Extra Virgem 500ml", "Mercearia",   39.90,  2,  -1.0, "padrao",   15, "sem_vendas"),
]

DIAS_LANCAMENTO = 10       # o produto "lancamento" só tem vendas nos últimos 10 dias
DIAS_DESDE_INATIVACAO = 60  # o produto "inativo" parou de vender 60 dias antes do fim


# ---------------------------------------------------------------------------
# FUNÇÕES AUXILIARES
# ---------------------------------------------------------------------------
def arredondar_preco(valor: float) -> float:
    """Arredonda para um preço "de mercado", terminando em 9 centavos (ex.: 9.49)."""
    return round(np.floor(valor * 10) / 10 + 0.09, 2)


def gerar_precos_diarios(rng, preco_base, dias):
    """
    Cria a "linha do tempo" de preços de um produto.
    - Em média a cada 30 dias o preço normal é reajustado (entre -10% e +12% do preço base).
    - Em média a cada 60 dias começa uma promoção de 7 dias com 15% de desconto.
    Isso é importante: SEM variação de preço, o modelo nunca conseguiria aprender
    como o preço afeta a demanda.
    Devolve: lista de preços (um por dia) e lista de eventos para o historico_precos.
    """
    preco_normal = preco_base
    dias_promocao_restantes = 0
    precos, eventos = [], []
    preco_ontem = None

    for i, dia in enumerate(dias):
        if dias_promocao_restantes == 0 and rng.random() < 1 / 30:
            preco_normal = arredondar_preco(preco_base * rng.uniform(0.90, 1.12))
        if dias_promocao_restantes == 0 and rng.random() < 1 / 60:
            dias_promocao_restantes = 7

        if dias_promocao_restantes > 0:
            preco_do_dia = arredondar_preco(preco_normal * 0.85)
            dias_promocao_restantes -= 1
            motivo = "[SIMULADO] Promocao"
        else:
            preco_do_dia = preco_normal
            motivo = "[SIMULADO] Reajuste"

        if preco_ontem is not None and preco_do_dia != preco_ontem:
            eventos.append((dia, preco_ontem, preco_do_dia, motivo))
        precos.append(preco_do_dia)
        preco_ontem = preco_do_dia

    return precos, eventos


def sortear_horario(rng, dia):
    """Sorteia a hora da venda, com picos no almoço (11-12h) e fim de tarde (17-19h)."""
    horas = np.arange(8, 22)  # loja aberta das 8h às 21h59
    pesos = np.array([2, 3, 4, 6, 6, 4, 3, 3, 4, 6, 7, 6, 4, 2], dtype=float)
    hora = int(rng.choice(horas, p=pesos / pesos.sum()))
    return datetime(dia.year, dia.month, dia.day, hora,
                    int(rng.integers(0, 60)), int(rng.integers(0, 60)))


# ---------------------------------------------------------------------------
# PASSO 1: copiar a estrutura do banco original
# ---------------------------------------------------------------------------
def criar_copia_do_banco(sobrescrever: bool) -> sqlite3.Connection:
    if not BANCO_ORIGINAL.exists():
        sys.exit(f"ERRO: banco original não encontrado em {BANCO_ORIGINAL}")

    if BANCO_SINTETICO.exists() and not sobrescrever:
        sys.exit(f"O arquivo {BANCO_SINTETICO.name} já existe. "
                 "Use --sobrescrever para recriá-lo.")

    # Abre o original em modo SOMENTE LEITURA ("mode=ro"): é impossível alterá-lo.
    caminho_uri = quote(BANCO_ORIGINAL.as_posix(), safe="/:")
    original = sqlite3.connect(f"file:{caminho_uri}?mode=ro", uri=True)

    # Proteção: se um dia o banco original tiver dados REAIS, não misturamos.
    # (Checado ANTES de apagar qualquer coisa.)
    qtd_produtos = original.execute("SELECT COUNT(*) FROM produtos").fetchone()[0]
    if qtd_produtos > 0:
        original.close()
        sys.exit("ERRO: o banco original já tem produtos cadastrados. "
                 "Este gerador só deve ser usado enquanto não há dados reais.")

    if BANCO_SINTETICO.exists():
        BANCO_SINTETICO.unlink()  # só chega aqui com --sobrescrever e após as checagens

    # Copia o arquivo inteiro (estrutura, índices, triggers) para o novo banco.
    copia = sqlite3.connect(BANCO_SINTETICO)
    original.backup(copia)
    original.close()

    copia.execute("PRAGMA foreign_keys = ON")  # liga a checagem de chaves estrangeiras
    return copia


# ---------------------------------------------------------------------------
# PASSO 2: gerar produtos, preços e vendas
# ---------------------------------------------------------------------------
def gerar_dados(con: sqlite3.Connection):
    rng = np.random.default_rng(SEMENTE)
    dias = [DATA_FINAL - timedelta(days=d) for d in range(DIAS_DE_HISTORICO - 1, -1, -1)]

    # compras_por_dia[dia] = lista de (id_produto, quantidade, preco_unitario)
    compras_por_dia = {d: [] for d in dias}

    for n, (nome, categoria, preco_base, demanda_base, elasticidade,
            perfil, cobertura, situacao) in enumerate(PRODUTOS, start=1):

        precos, eventos = gerar_precos_diarios(rng, preco_base, dias)

        # Em que período este produto vende?
        if situacao == "lancamento":
            dias_com_venda = set(dias[-DIAS_LANCAMENTO:])
        elif situacao == "inativo":
            dias_com_venda = set(dias[:-DIAS_DESDE_INATIVACAO])
        elif situacao == "sem_vendas":
            dias_com_venda = set()
        else:
            dias_com_venda = set(dias)

        # O lançamento não tem histórico de preço antigo; o sem_vendas também não.
        if situacao in ("lancamento", "sem_vendas"):
            eventos = [e for e in eventos if e[0] in dias_com_venda]

        cur = con.execute(
            """INSERT INTO produtos (codigo_barras, nome, categoria, preco_atual, estoque_atual, ativo)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (f"SIM-{n:04d}", f"{nome} {MARCA}", categoria, precos[-1],
             int(demanda_base * cobertura), 0 if situacao == "inativo" else 1),
        )
        id_produto = cur.lastrowid

        for dia, preco_antes, preco_depois, motivo in eventos:
            con.execute(
                """INSERT INTO historico_precos (id_produto, preco_anterior, novo_preco, motivo, origem, data_hora)
                   VALUES (?, ?, ?, ?, 'SIMULADO', ?)""",
                (id_produto, preco_antes, preco_depois, motivo, f"{dia} 07:00:00"),
            )

        # ---- A "FÓRMULA" DA DEMANDA (o padrão escondido que o modelo vai aprender) ----
        # demanda média do dia = demanda_base
        #                        x fator do dia da semana
        #                        x fator do mês
        #                        x (preço do dia / preço base) ^ elasticidade
        # Depois sorteamos a quantidade real com Poisson (acaso do dia a dia).
        for dia, preco in zip(dias, precos):
            if dia not in dias_com_venda:
                continue
            media = (demanda_base
                     * FATOR_DIA_SEMANA[dia.weekday()]
                     * FATOR_MES[perfil][dia.month]
                     * (preco / preco_base) ** elasticidade)
            quantidade_do_dia = int(rng.poisson(media))

            # Divide a quantidade do dia em compras de 1 a 3 unidades
            while quantidade_do_dia > 0:
                q = min(quantidade_do_dia, int(rng.choice([1, 1, 1, 2, 2, 3])))
                compras_por_dia[dia].append((id_produto, q, preco))
                quantidade_do_dia -= q

    # ---- Agrupa as compras em "cupons" (vendas) com 1 a 4 produtos ----
    total_vendas = total_canceladas = 0
    for dia in dias:
        compras = compras_por_dia[dia]
        rng.shuffle(compras)
        cupons, i = [], 0
        while i < len(compras):
            tamanho = int(rng.integers(1, 5))
            cupons.append(compras[i:i + tamanho])
            i += tamanho

        cupons_com_hora = sorted(((sortear_horario(rng, dia), c) for c in cupons),
                                 key=lambda x: x[0])
        for horario, cupom in cupons_com_hora:
            # Junta o mesmo produto repetido no mesmo cupom
            itens = {}
            for id_produto, q, preco in cupom:
                itens.setdefault(id_produto, [0, preco])[0] += q
            valor_total = round(sum(q * p for q, p in itens.values()), 2)

            cur = con.execute(
                "INSERT INTO vendas (data_hora, valor_total, status) VALUES (?, ?, 'ATIVA')",
                (horario.strftime("%Y-%m-%d %H:%M:%S"), valor_total),
            )
            id_venda = cur.lastrowid
            con.executemany(
                """INSERT INTO itens_venda (id_venda, id_produto, quantidade, preco_unitario, subtotal)
                   VALUES (?, ?, ?, ?, ?)""",
                [(id_venda, pid, q, p, round(q * p, 2)) for pid, (q, p) in itens.items()],
            )
            total_vendas += 1

            # Alguns cupons são cancelados DEPOIS de registrados (como na vida real).
            # Os itens ficam no banco, mas a venda fica com status CANCELADA.
            if rng.random() < CHANCE_CANCELAMENTO:
                hora_cancel = (horario + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
                con.execute(
                    """UPDATE vendas SET status = 'CANCELADA', data_hora_cancelamento = ?,
                       motivo_cancelamento = '[SIMULADO] Cliente desistiu' WHERE id_venda = ?""",
                    (hora_cancel, id_venda),
                )
                con.execute(
                    """INSERT INTO historico_vendas (id_venda, acao, data_hora, valor_total_anterior,
                       valor_total_novo, motivo) VALUES (?, 'CANCELAMENTO', ?, ?, ?, '[SIMULADO] Cliente desistiu')""",
                    (id_venda, hora_cancel, valor_total, valor_total),
                )
                total_canceladas += 1

    return total_vendas, total_canceladas


# ---------------------------------------------------------------------------
# PROGRAMA PRINCIPAL
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Gera um banco com dados SIMULADOS do DynaPrice.")
    parser.add_argument("--sobrescrever", action="store_true",
                        help="apaga e recria o banco sintético, se já existir")
    args = parser.parse_args()

    con = criar_copia_do_banco(args.sobrescrever)
    try:
        with con:  # tudo numa transação: ou grava tudo, ou nada
            vendas, canceladas = gerar_dados(con)
        problemas_fk = con.execute("PRAGMA foreign_key_check").fetchall()
        integridade = con.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        con.close()

    print(f"Banco SIMULADO criado em: {BANCO_SINTETICO}")
    print(f"  Produtos: {len(PRODUTOS)} | Vendas: {vendas} ({canceladas} canceladas)")
    print(f"  Chaves estrangeiras com problema: {len(problemas_fk)} | Integridade: {integridade}")


if __name__ == "__main__":
    main()
