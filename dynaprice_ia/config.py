"""
config.py — Configurações do módulo de IA do DynaPrice, todas num lugar só.

Para usar outro banco (por exemplo, o banco REAL do grupo), há duas formas:
  1. Mudar CAMINHO_BANCO_PADRAO abaixo; ou
  2. Definir a variável de ambiente DYNAPRICE_BANCO com o caminho do arquivo .db
     (útil para o Seven, sem precisar mexer no código).
"""

import os
from pathlib import Path

PASTA_PROJETO = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# BANCO DE DADOS
# ---------------------------------------------------------------------------
# ATENÇÃO: por enquanto o padrão é o banco com DADOS SIMULADOS, porque o banco
# real do grupo ainda está vazio. Quando houver dados reais, troque para:
#   PASTA_PROJETO / "dynaprice_BD_atualizado.db"
CAMINHO_BANCO_PADRAO = PASTA_PROJETO / "dados_sinteticos" / "dynaprice_teste_sintetico.db"


def caminho_do_banco() -> Path:
    """Devolve o caminho do banco: a variável de ambiente tem prioridade sobre o padrão."""
    return Path(os.environ.get("DYNAPRICE_BANCO", CAMINHO_BANCO_PADRAO))


# ---------------------------------------------------------------------------
# PREPARAÇÃO DOS DADOS
# ---------------------------------------------------------------------------
# Produto com MENOS dias de histórico do que isso é considerado "pouco histórico":
# o módulo devolve o preço atual sem mudança e confiança baixa.
MIN_DIAS_HISTORICO = 30
# E também precisa ter vendido em pelo menos este número de dias (um produto que
# vendeu 1 vez há 40 dias tem "40 dias de histórico", mas quase nenhuma informação).
MIN_DIAS_COM_VENDA = 10

# Tamanho das "janelas" das médias móveis usadas como pistas (features).
JANELA_CURTA = 7    # ritmo recente (última semana)
JANELA_LONGA = 28   # tamanho "normal" do produto (último mês)

# ---------------------------------------------------------------------------
# MODELO (TREINO E PREVISÃO)
# ---------------------------------------------------------------------------
# Pasta onde os modelos treinados ficam salvos (para não treinar a cada chamada).
# Cada banco tem o seu arquivo: modelo_demanda_<nome do banco>.joblib
PASTA_MODELOS = PASTA_PROJETO / "dynaprice_ia" / "modelos"

HORIZONTE_DIAS = 7   # a previsão de demanda é para os próximos 7 dias
DIAS_TESTE = 60      # os últimos 60 dias ficam guardados para TESTAR o modelo
SEMENTE = 42         # deixa o treino reprodutível (mesmo resultado toda vez)

# ---------------------------------------------------------------------------
# REGRAS DE PREÇO
# ---------------------------------------------------------------------------
# Quanto o preço pode subir ou descer em UM recálculo (0.10 = 10%).
# Valor a confirmar com o líder do grupo.
LIMITE_VARIACAO_PRECO = 0.10

# Cobertura do estoque = para quantos dias o estoque atual dá, na demanda prevista.
COBERTURA_MINIMA_DIAS = 7    # abaixo disso: vai faltar produto -> preço SOBE
COBERTURA_MAXIMA_DIAS = 30   # acima disso: estoque parado    -> preço DESCE
# Entre os dois: equilibrado -> preço se MANTÉM.

# Confiança usada quando o produto tem pouco histórico (preço não muda).
CONFIANCA_POUCO_HISTORICO = 0.1
