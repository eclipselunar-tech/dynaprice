"""
validar_elasticidade.py — O modelo APRENDEU o efeito do desconto que colocamos nos dados simulados?

Nos dados simulados nós sabemos a "resposta certa": cada produto foi criado com uma
elasticidade (ex.: cerveja -1.8). Este script compara essa verdade com:
    - a elasticidade estimada pela Regressão de Poisson (dynaprice_ia/elasticidade.py),
      usada pelo avaliar_promocao;
    - o efeito que o modelo de demanda original (Random Forest) prevê para um desconto de 20%.

Só funciona com o banco SIMULADO (é o único em que sabemos a verdade). Não grava nada.

Como rodar (na pasta do projeto):
    python dados_sinteticos/validar_elasticidade.py
"""

import math
import sys
from pathlib import Path

PASTA = Path(__file__).resolve().parent
sys.path.insert(0, str(PASTA.parent))  # para conseguir importar o dynaprice_ia

import pandas as pd  # noqa: E402

from dynaprice_ia.conexao import buscar_vendas, conectar, listar_produtos  # noqa: E402
from dynaprice_ia.elasticidade import estimar_elasticidade  # noqa: E402
from dynaprice_ia.modelo import carregar_ou_treinar, prever_demanda  # noqa: E402
from dynaprice_ia.preparacao import montar_tabela_diaria  # noqa: E402
from gerar_dados_sinteticos import BANCO_SINTETICO, PRODUTOS  # noqa: E402

TOLERANCIA = 0.3  # diferença aceitável entre a elasticidade real e a estimada
DESCONTO = 0.20

con = conectar(BANCO_SINTETICO)
try:
    produtos = listar_produtos(con)
    tabela = montar_tabela_diaria(buscar_vendas(con), produtos)
finally:
    con.close()
pacote = carregar_ou_treinar(BANCO_SINTETICO)

linhas, acertos, avaliados = [], 0, 0
for id_produto, (nome, _, _, _, elasticidade_real, _, _, situacao) in enumerate(PRODUTOS, start=1):
    if situacao != "normal":
        continue  # lançamento, inativo e sem vendas não têm histórico para comparar
    historico = tabela[tabela["id_produto"] == id_produto]
    estimada = estimar_elasticidade(historico)["elasticidade"]

    preco_relativo = float(historico["preco"].iloc[-1] / historico["preco"].mean())
    base = prever_demanda(pacote, historico, preco_relativo)
    com_desconto = prever_demanda(pacote, historico, preco_relativo * (1 - DESCONTO))
    # elasticidade "implícita" da Random Forest: quanto ela reage a 20% de desconto
    elasticidade_rf = math.log(com_desconto / base) / math.log(1 - DESCONTO) if base > 0 else 0.0

    acertou = estimada is not None and abs(estimada - elasticidade_real) <= TOLERANCIA
    acertos += acertou
    avaliados += 1
    linhas.append({
        "produto": nome[:22],
        "real": elasticidade_real,
        "Poisson": estimada,
        "Random Forest": round(elasticidade_rf, 2),
        "efeito real -20%": f"{(1 - DESCONTO) ** elasticidade_real - 1:+.0%}",
        "Poisson -20%": f"{(1 - DESCONTO) ** estimada - 1:+.0%}" if estimada is not None else "-",
        "RF -20%": f"{com_desconto / base - 1:+.0%}" if base > 0 else "-",
        "Poisson ok?": "sim" if acertou else "NÃO",
    })

print("VALIDAÇÃO DO EFEITO DO DESCONTO (dados SIMULADOS)")
print("Elasticidade: -1.8 = cada 1% de desconto aumenta as vendas em ~1.8%\n")
print(pd.DataFrame(linhas).to_string(index=False))
print(f"\nPoisson acertou (erro <= {TOLERANCIA}) em {acertos} de {avaliados} produtos.")
print("A Random Forest (modelo de demanda) subestima o efeito em quase todos: por isso o")
print("avaliar_promocao usa a elasticidade do Poisson, e não a Random Forest, para o desconto.")
