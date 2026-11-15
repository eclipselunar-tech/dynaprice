"""
modelo.py — ETAPA 3: treinar o modelo que PREVÊ A DEMANDA (unidades vendidas por dia).

Como o modelo aprende (resumo para apresentar):
    1. Recebe milhares de exemplos do passado: "num SÁBADO de JULHO, com preço
       5% acima do normal, vendendo ~12 por dia na última semana, o produto
       vendeu 15 unidades".
    2. Procura a regra que melhor liga as PISTAS (features) à RESPOSTA (quantidade).
    3. Testamos essa regra em dias que ele NUNCA viu (os últimos 60 dias) e
       medimos o quanto errou. Só assim sabemos se ele aprendeu de verdade
       ou só "decorou" o passado.

Algoritmos comparados:
    - Regressão Linear: soma "pesos" para cada pista. Simples e fácil de
      explicar, mas só capta efeitos que se SOMAM (não "sábado E verão juntos").
    - Random Forest (floresta aleatória): centenas de árvores de decisão, cada
      uma treinada com um pedaço sorteado dos dados; a previsão final é a média
      dos "votos". Capta combinações (ex.: sábado no verão vende MUITO mais).
    - Chute simples (linha de base): "amanhã vai vender a média dos últimos 7 dias".
      Se um modelo não ganhar disso, não vale a pena usá-lo.

Ganha o que tiver MENOR erro no teste. Depois ele é re-treinado com TODOS os
dados (inclusive os 60 dias de teste) e salvo em arquivo.
"""

import os
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from .config import (DIAS_TESTE, HORIZONTE_DIAS, JANELA_CURTA, JANELA_LONGA,
                     PASTA_MODELOS, SEMENTE, caminho_do_banco)
from .conexao import buscar_vendas, conectar, listar_produtos
from .erros import DadosInsuficientes
from .preparacao import ALVO, FEATURES, montar_tabela_diaria, tabela_para_treino


def caminho_do_modelo(caminho_banco) -> Path:
    """Cada banco tem o seu arquivo de modelo (um não sobrescreve o do outro)."""
    return PASTA_MODELOS / f"modelo_demanda_{Path(caminho_banco).stem}.joblib"


# ---------------------------------------------------------------------------
# Os candidatos
# ---------------------------------------------------------------------------
class MediaRecente:
    """
    O "chute simples": prevê que amanhã vai vender a média dos últimos 7 dias.
    Tem fit/predict como os modelos do scikit-learn, para poder competir com eles.
    Se nenhum modelo de Machine Learning ganhar dele, é ele que fica.
    """

    def fit(self, X, y):
        return self

    def predict(self, X):
        return X["media_7d"].to_numpy()


def criar_candidatos() -> dict:
    """Cria os dois algoritmos que vamos comparar (ainda sem treinar)."""
    # Na Regressão Linear, "dia da semana" e "mês" não podem ser tratados como
    # números (o modelo acharia que domingo=6 é "6 vezes" segunda=0). Por isso
    # viram colunas de "sim/não" (one-hot): é_sábado? é_julho? ...
    linear = Pipeline([
        ("preparo", ColumnTransformer(
            [("categorias", OneHotEncoder(handle_unknown="ignore"), ["dia_semana", "mes"])],
            remainder="passthrough",
        )),
        ("regressao", LinearRegression()),
    ])
    # A floresta lida bem com números diretamente.
    floresta = RandomForestRegressor(
        n_estimators=200,      # 200 árvores votando
        min_samples_leaf=5,    # cada "folha" precisa de 5+ exemplos (evita decorar casos isolados)
        random_state=SEMENTE,
        n_jobs=-1,             # usa todos os núcleos do processador
    )
    return {"Chute simples (media 7 dias)": MediaRecente(),
            "Regressao Linear": linear, "Random Forest": floresta}


# ---------------------------------------------------------------------------
# Treino + avaliação
# ---------------------------------------------------------------------------
def separar_treino_teste(dados: pd.DataFrame):
    """
    Separa pelo TEMPO, não por sorteio: os últimos DIAS_TESTE dias são o teste.
    Na vida real o modelo sempre prevê o FUTURO, então o teste precisa imitar isso.
    """
    corte = dados["data"].max() - pd.Timedelta(days=DIAS_TESTE)
    return dados[dados["data"] <= corte], dados[dados["data"] > corte]


def avaliar(real, previsto) -> dict:
    """
    MAE = erro médio absoluto: "em média, erra X unidades por dia".
    R²  = quanto da variação das vendas o modelo explica (1 = perfeito, 0 = nada).
    """
    return {"MAE": round(float(mean_absolute_error(real, previsto)), 3),
            "R2": round(float(r2_score(real, previsto)), 3)}


def treinar_modelo(caminho_banco=None, salvar: bool = True, mostrar: bool = True) -> dict:
    """
    Treina, compara, escolhe o melhor e (opcionalmente) salva.
    Devolve um "pacote" (dicionário) com o modelo e as informações do treino.
    """
    caminho_banco = Path(caminho_banco) if caminho_banco else caminho_do_banco()
    con = conectar(caminho_banco)
    try:
        vendas, produtos = buscar_vendas(con), listar_produtos(con)
    finally:
        con.close()

    dados = tabela_para_treino(montar_tabela_diaria(vendas, produtos))
    treino, teste = separar_treino_teste(dados) if len(dados) else (dados, dados)
    # Precisamos de exemplos suficientes para APRENDER (treino) e para CONFERIR (teste).
    if len(treino) < 100 or len(teste) < 10:
        raise DadosInsuficientes(
            f"Poucos dados para treinar: {len(treino)} linhas de treino e {len(teste)} de teste "
            "(mínimo 100 e 10). São necessários uns 3 meses de vendas."
        )

    # ---- Comparação no teste ----
    resultados = {}
    candidatos = criar_candidatos()
    for nome, modelo in candidatos.items():
        modelo.fit(treino[FEATURES], treino[ALVO])
        resultados[nome] = avaliar(teste[ALVO], modelo.predict(teste[FEATURES]))

    melhor = min(candidatos, key=lambda n: resultados[n]["MAE"])

    # Erro do melhor modelo POR PRODUTO no teste (será usado para a "confiança").
    # Erro relativo: 0.20 = erra ~20% da venda média diária do produto.
    # Produto que quase não vendeu no teste fica de fora (dividir por ~0 daria um
    # número sem sentido); ele usa a média dos outros produtos na hora da confiança.
    teste = teste.assign(previsto=candidatos[melhor].predict(teste[FEATURES]))
    erro_por_produto = {}
    for id_produto, g in teste.groupby("id_produto"):
        if g[ALVO].mean() >= 0.5:
            erro_por_produto[id_produto] = round(
                mean_absolute_error(g[ALVO], g["previsto"]) / g[ALVO].mean(), 3)

    # ---- Re-treina o vencedor com TODOS os dados (mais exemplos = modelo melhor) ----
    modelo_final = criar_candidatos()[melhor].fit(dados[FEATURES], dados[ALVO])

    pacote = {
        "modelo": modelo_final,
        "algoritmo": melhor,
        "features": FEATURES,
        "metricas_teste": resultados,
        "erro_relativo_por_produto": {int(k): float(v) for k, v in erro_por_produto.items()},
        "banco": str(caminho_banco.resolve()),
        "banco_nome": caminho_banco.name,  # usado para saber se o modelo serve para o banco
        # Produtos simulados têm código de barras "SIM-..." (ver dados_sinteticos/).
        "dados_simulados": bool(produtos["codigo_barras"].astype(str).str.startswith("SIM-").any()),
        "data_treino": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "periodo_dados": (str(dados["data"].min().date()), str(dados["data"].max().date())),
        "linhas_treino": len(treino), "linhas_teste": len(teste),
    }

    if salvar:
        # Salva primeiro num arquivo temporário e depois troca de uma vez:
        # assim ninguém lê um arquivo pela metade enquanto ele está sendo gravado.
        destino = caminho_do_modelo(caminho_banco)
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporario = destino.with_name(destino.name + f".{os.getpid()}.tmp")
        joblib.dump(pacote, temporario)
        os.replace(temporario, destino)

    if mostrar:
        mostrar_relatorio(pacote)
    return pacote


def carregar_ou_treinar(caminho_banco=None) -> dict:
    """
    Usa o modelo salvo, se existir E tiver sido treinado com um banco de MESMO NOME.
    Isso evita usar um modelo treinado com dados simulados (dynaprice_teste_sintetico.db)
    num banco real (ou vice-versa). Comparamos só o nome do arquivo, e não o caminho
    completo, para o modelo continuar valendo quando a pasta do projeto for copiada
    para outro computador. Caso contrário, treina de novo e salva.
    """
    caminho_banco = Path(caminho_banco) if caminho_banco else caminho_do_banco()
    arquivo = caminho_do_modelo(caminho_banco)
    if arquivo.is_file():
        pacote = joblib.load(arquivo)
        if pacote.get("banco_nome") == caminho_banco.name and "dados_simulados" in pacote:
            return pacote
    return treinar_modelo(caminho_banco, salvar=True, mostrar=False)


# ---------------------------------------------------------------------------
# Previsão dos próximos dias
# ---------------------------------------------------------------------------
def prever_demanda(pacote: dict, historico_produto: pd.DataFrame,
                   preco_relativo: float, dias: int = HORIZONTE_DIAS) -> float:
    """
    Prevê quantas unidades o produto vai vender nos próximos `dias` dias,
    SE o preço relativo for `preco_relativo` (1.0 = preço normal do produto).

    historico_produto = linhas desse produto vindas de preparacao.montar_tabela_diaria.

    Simplificação (dizer ao professor): para os dias futuros, as médias de
    7 e 28 dias ficam fixas no último valor conhecido, porque ainda não
    sabemos as vendas futuras. O que muda dia a dia é o dia da semana e o mês.
    """
    ultimos = historico_produto.sort_values("data")["quantidade"]
    media_7d = ultimos.tail(JANELA_CURTA).mean()
    media_28d = ultimos.tail(JANELA_LONGA).mean()
    ultimo_dia = historico_produto["data"].max()

    futuro = pd.DataFrame({"data": pd.date_range(ultimo_dia + pd.Timedelta(days=1), periods=dias)})
    futuro["dia_semana"] = futuro["data"].dt.day_of_week
    futuro["mes"] = futuro["data"].dt.month
    futuro["preco_relativo"] = preco_relativo
    futuro["media_7d"] = media_7d
    futuro["media_28d"] = media_28d

    previsao_diaria = np.clip(pacote["modelo"].predict(futuro[FEATURES]), 0, None)  # venda não pode ser negativa
    return float(previsao_diaria.sum())


# ---------------------------------------------------------------------------
# Relatório (para ler no terminal / mostrar ao professor)
# ---------------------------------------------------------------------------
def descricao_do_modelo(pacote: dict | None) -> str:
    """Texto gravado na coluna analises_ia.modelo. Ex.: 'Random Forest | treino 2026-11-11 | DADOS SIMULADOS'."""
    if pacote is None:
        return "Sem modelo (dados insuficientes para treinar)"
    texto = f"{pacote['algoritmo']} | treino {pacote['data_treino'][:10]}"
    return texto + (" | DADOS SIMULADOS" if pacote.get("dados_simulados") else "")


def importancia_das_features(pacote: dict) -> pd.Series | None:
    """Quanto cada pista ajudou a floresta a decidir (soma 1.0). Só existe na Random Forest."""
    modelo = pacote["modelo"]
    if hasattr(modelo, "feature_importances_"):
        return pd.Series(modelo.feature_importances_, index=pacote["features"]).sort_values(ascending=False)
    return None


def mostrar_relatorio(pacote: dict) -> None:
    print("=" * 60)
    print("RELATÓRIO DO TREINO DO MODELO DE DEMANDA")
    print("=" * 60)
    print(f"Banco usado: {pacote['banco']}")
    if pacote.get("dados_simulados"):
        print(">>> ATENÇÃO: treinado com DADOS SIMULADOS <<<")
    print(f"Período: {pacote['periodo_dados'][0]} a {pacote['periodo_dados'][1]}")
    print(f"Linhas de treino: {pacote['linhas_treino']} | de teste: {pacote['linhas_teste']} "
          f"(últimos {DIAS_TESTE} dias)\n")
    print("Resultado no TESTE (dias que o modelo nunca viu):")
    for nome, m in pacote["metricas_teste"].items():
        marca = "  <== escolhido" if nome == pacote["algoritmo"] else ""
        print(f"  {nome:30s} MAE = {m['MAE']:6.2f} un/dia | R² = {m['R2']:.3f}{marca}")
    imp = importancia_das_features(pacote)
    if imp is not None:
        print("\nO que o modelo mais usou para decidir (importância):")
        for f, v in imp.items():
            print(f"  {f:15s} {'#' * int(v * 50)} {v:.1%}")
    print("=" * 60)

