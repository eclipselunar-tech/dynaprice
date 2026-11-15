# DynaPrice — Módulo de Inteligência Artificial (`dynaprice_ia`)

Módulo Python que **prevê a demanda** dos produtos com Machine Learning (scikit-learn) e **sugere um preço**
com base na demanda prevista, no estoque e no preço atual, respeitando um limite de variação.

> ⚠️ **O modelo atual foi treinado com DADOS SIMULADOS.** O banco do grupo ainda não tem vendas.
> Os dados simulados ficam separados em `dados_sinteticos/` e são marcados com "(SIMULADO)" no nome
> do produto e "SIM-" no código de barras. Quando houver dados reais, basta apontar para o banco real
> (veja [Trocar para o banco real](#trocar-para-o-banco-real)).

O módulo **só sugere e registra** a análise (tabela `analises_ia`). Ele **não** altera `produtos.preco_atual`,
não grava em `historico_precos` e não mexe em `etiquetas` / `atualizacoes_etiqueta`. Isso é feito pela
aplicação principal, depois que o usuário aprovar a sugestão.

---

## Sumário
1. [Estrutura dos arquivos](#estrutura-dos-arquivos)
2. [Instalação](#instalação)
3. [Como usar (integração)](#como-usar-integração)
4. [Como funciona, etapa por etapa](#como-funciona-etapa-por-etapa)
5. [Os dados simulados](#os-dados-simulados)
6. [O modelo: como aprende e como foi avaliado](#o-modelo-como-aprende-e-como-foi-avaliado)
7. [A regra de preço](#a-regra-de-preço)
8. [O que é gravado no banco](#o-que-é-gravado-no-banco)
9. [Trocar para o banco real e re-treinar](#trocar-para-o-banco-real)
10. [Testes](#testes)
11. [Limitações](#limitações)
12. [Observações para o grupo](#observações-para-o-grupo)

---

## Estrutura dos arquivos

```
dynaprice_ia/                 <- o módulo (é isto que a aplicação importa)
  __init__.py                 exporta recalcular_preco, retreinar_modelo e os erros
  config.py                   TODAS as configurações (caminho do banco, limite de 10%, faixas...)
  erros.py                    erros com nome (ProdutoNaoEncontrado, ProdutoInativo, ...)
  conexao.py                  Etapa 1 - conexão com o SQLite e leitura dos dados
  preparacao.py               Etapa 2 - tabela "produto x dia" e as features
  modelo.py                   Etapa 3 - treino, avaliação e previsão da demanda
  recomendacao.py             Etapa 4 - regra demanda x estoque -> preço sugerido
  registro.py                 Etapa 5 - gravação em analises_ia
  integracao.py               Etapa 6 - função recalcular_preco
  modelos/modelo_demanda_<banco>.joblib   modelo treinado, um por banco (gerado automaticamente)
dados_sinteticos/             <- DADOS SIMULADOS (pode apagar quando houver dados reais)
  gerar_dados_sinteticos.py   gerador
  dynaprice_teste_sintetico.db    cópia do banco com dados simulados
tests/                        testes automáticos (pytest)
exemplo_uso.py                exemplo simples de chamada
treinar_modelo.py             re-treina o modelo e mostra o relatório
requirements.txt              bibliotecas necessárias
```

## Instalação

Requer **Python 3.10+** (testado com Python 3.13, numpy 2.5, pandas 3.1, scikit-learn 1.9).

```bash
python -m pip install -r requirements.txt
```

Para gerar (ou recriar) o banco simulado:

```bash
python dados_sinteticos/gerar_dados_sinteticos.py --sobrescrever
```

## Como usar (integração)

```python
from dynaprice_ia import recalcular_preco

resultado = recalcular_preco(4)                                    # usa o banco configurado
resultado = recalcular_preco(4, caminho_banco="dynaprice_BD.db")   # ou informa o banco
```

### Retorno

Um dicionário com tipos comuns do Python (pode ir direto para `jsonify`):

| Chave | Exemplo | Significado |
|---|---|---|
| `produto_id` | `4` | produto analisado |
| `preco_atual` | `10.49` | preço atual (não é alterado) |
| `preco_sugerido` | `11.09` | preço recomendado |
| `demanda_prevista` | `98` | unidades previstas para os **próximos 7 dias** |
| `confianca` | `0.70` | de 0 a 1 (quanto confiar na previsão) |
| `id_analise` | `15` | id da linha gravada em `analises_ia` |
| `situacao` | `"SUBIR"` | `SUBIR`, `DESCER`, `MANTER`, `POUCO_HISTORICO` ou `SEM_ESTOQUE` |
| `motivo` | `"Estoque cobre só 3.0 dias..."` | explicação em texto, para mostrar ao usuário |
| `variacao_percentual` | `5.72` | variação do preço em % |
| `cobertura_dias` | `3.0` | para quantos dias o estoque dura (`None` se não há demanda prevista) |

### Erros

Todos herdam de `ErroDynaPriceIA` (dá para capturar todos de uma vez):

| Erro | Quando |
|---|---|
| `ProdutoNaoEncontrado` | não existe produto com esse id |
| `ProdutoInativo` | produto com `ativo = 0` |
| `BancoNaoEncontrado` | o arquivo `.db` não existe (o módulo **não** cria um banco vazio) |
| `ValueError` | `produto_id` não é um número inteiro |

Produto **sem histórico** ou com **pouco histórico** (< 30 dias desde a 1ª venda, ou < 10 dias com venda)
**não** gera erro: devolve o preço atual,
`situacao = "POUCO_HISTORICO"` e `confianca = 0.1`. O mesmo acontece se o banco inteiro ainda tiver vendas de
menos para treinar o modelo (sistema recém-começado).

### Sugestão de rota Flask (para a aplicação principal)

Apenas uma sugestão; o formato final é decisão de quem integra.

```python
from database import CAMINHO_BANCO
from dynaprice_ia import recalcular_preco, ErroDynaPriceIA, ProdutoNaoEncontrado, ProdutoInativo

@app.route("/api/produtos/<int:id_produto>/recalcular", methods=["POST"])
def recalcular(id_produto):
    try:
        return jsonify(recalcular_preco(id_produto, caminho_banco=CAMINHO_BANCO)), 200
    except ProdutoNaoEncontrado as erro:
        return jsonify({"erro": str(erro)}), 404
    except ProdutoInativo as erro:
        return jsonify({"erro": str(erro)}), 409
    except ErroDynaPriceIA as erro:
        return jsonify({"erro": str(erro)}), 500
```

Depois que o usuário **aprovar**, a aplicação aplica o preço pela rota que já existe
(`PUT /api/produtos/<codigo_barras>`), que grava `historico_precos` e prepara as etiquetas.

---

## Como funciona, etapa por etapa

```
recalcular_preco(id)
   │
   ├─ 1. conexao      lê o produto e as vendas ATIVAS (canceladas ficam de fora)
   ├─ 2. preparacao   monta a tabela "produto x dia" + features
   ├─ 3. modelo       prevê a demanda dos próximos 7 dias (Random Forest)
   ├─ 4. recomendacao demanda x estoque -> preço sugerido (máx. ±10%)
   ├─ 5. registro     grava em analises_ia
   └─ 6. devolve o dicionário
```

## Os dados simulados

Como o banco do grupo está vazio, o script `dados_sinteticos/gerar_dados_sinteticos.py` cria uma **cópia** do
banco (o original não é alterado) com **15 produtos** e **1 ano de vendas** (11/11/2025 a 10/11/2026):
14.132 vendas, das quais 423 canceladas (3%).

A demanda de cada dia foi gerada pela fórmula:

```
demanda média = demanda normal do produto
                × fator do dia da semana   (sábado 1,45 ... terça 0,80)
                × fator do mês             (bebidas/sorvete sobem no verão; café/chocolate no inverno; dezembro sobe)
                × (preço do dia / preço normal) ^ elasticidade   (preço maior -> vende menos)
quantidade real = sorteio de Poisson em torno da média   (o "acaso" do dia a dia)
```

O preço de cada produto muda ao longo do ano (reajustes ~1x/mês e promoções de 7 dias com 15% de desconto),
para que exista variação de preço nos dados.

Casos especiais criados de propósito: 1 produto **lançado há 10 dias**, 1 **inativo** e 1 **sem nenhuma venda**.

**O modelo não conhece essa fórmula.** Ele precisa descobrir os padrões só olhando as vendas — é isso que a
avaliação mede.

## O modelo: como aprende e como foi avaliado

### O que ele prevê
A **quantidade vendida por dia** de cada produto. A previsão dos próximos 7 dias é a soma de 7 previsões diárias.

### As pistas (features)

| Feature | O que ensina |
|---|---|
| `dia_semana` | sábado vende mais que terça |
| `mes` | sazonalidade (verão/inverno) |
| `preco_relativo` | preço do dia ÷ preço médio do produto (1,10 = 10% mais caro que o normal) |
| `media_7d` | média de vendas dos **7 dias anteriores** (ritmo recente) |
| `media_28d` | média de vendas dos **28 dias anteriores** (tamanho normal do produto) |

Usamos o preço **relativo** (e não em reais) para comparar produtos diferentes: R$ 4 é caro para água e barato
para azeite. As médias usam **só dias anteriores** — se usassem o próprio dia, o modelo "colaria" a resposta.

### Como aprende
O modelo recebe ~4.300 exemplos ("num sábado de julho, com preço 5% acima do normal, vendendo ~12/dia na última
semana, vendeu 15") e procura a regra que melhor liga as pistas à resposta.

Foram comparados:
- **Regressão Linear** — soma um "peso" para cada pista. Simples, mas só capta efeitos que se somam.
- **Random Forest** — 200 árvores de decisão, cada uma treinada com uma parte sorteada dos dados; a previsão
  é a média dos "votos". Capta combinações (ex.: sábado **e** verão).
- **Chute simples** (linha de base) — "vai vender a média dos últimos 7 dias".

### Como foi avaliado
Divisão **pelo tempo**: treino com os primeiros ~10 meses, teste com os **últimos 60 dias**, que o modelo nunca
viu (na vida real, sempre prevemos o futuro).

| Método | MAE (erro médio) | R² |
|---|---|---|
| Chute simples (média 7 dias) | 3,65 un/dia | 0,645 |
| Regressão Linear | 3,12 un/dia | 0,747 |
| **Random Forest (escolhido)** | **2,96 un/dia** | **0,768** |

- **MAE**: em média, o modelo erra ~3 unidades por dia.
- **R²**: explica ~77% da variação das vendas. O restante é, em boa parte, o "acaso" do sorteio, que nenhum
  modelo consegue prever.
- O modelo **ganhou do chute simples**, logo aprendeu algo útil.

Importância das features na Random Forest: `media_7d` 54%, `media_28d` 29%, `dia_semana` 12,5%,
`preco_relativo` 2,6%, `mes` 1,6% (o mês pesa pouco porque a média de 28 dias já "carrega" a estação).

O chute simples também concorre: se nenhum modelo de Machine Learning ganhar dele (o que pode acontecer com
dados reais), é ele que fica — e o relatório mostra isso.

Depois de escolhido, o vencedor é **re-treinado com todos os dados** e salvo em
`modelos/modelo_demanda_<nome do banco>.joblib`. Se o arquivo for re-treinado por outro programa, a aplicação
percebe a mudança e recarrega o modelo sozinha.
Para ver o relatório de novo: `python treinar_modelo.py`.

### Confiança
`confianca = 1 − erro relativo do modelo naquele produto no teste`. Ex.: errou 18% da venda média da cerveja →
confiança 0,82. Produtos com pouco histórico recebem 0,1.

## A regra de preço

O modelo prevê a demanda; uma **regra clara** decide o preço:

```
cobertura = estoque_atual ÷ demanda diária prevista     (para quantos dias o estoque dá)

cobertura < 7 dias   -> vai faltar   -> SOBE    (proporcional: 7 dias = 0% ... 0 dia = +10%)
7 a 30 dias          -> equilibrado  -> MANTÉM
cobertura > 30 dias  -> parado       -> DESCE   (proporcional: 30 dias = 0% ... 60+ dias = −10%)
```

- Limite de **±10% por recálculo** (`LIMITE_VARIACAO_PRECO` no `config.py`, a confirmar com o líder).
- O preço é arredondado para terminar em **9 centavos** (R$ 11,09), sem passar do limite.
- **Estoque zero** → preço mantido (`SEM_ESTOQUE`).
- **Pouco histórico** (< 30 dias desde a 1ª venda ou < 10 dias com venda) → preço mantido
  (`POUCO_HISTORICO`, confiança 0,1).

**Por que uma regra e não "o modelo escolhe o preço de maior lucro"?** Não temos o custo dos produtos (não dá
para calcular lucro) e o teste mostrou que o modelo enxerga **fraco** o efeito do preço (ver Limitações).
Então o modelo é usado para o que faz bem — prever demanda — e a decisão de preço fica explicável.

Todas as faixas são constantes no `config.py`.

## O que é gravado no banco

Uma linha em `analises_ia` por chamada (inclusive quando o preço é mantido):

| Coluna | Valor |
|---|---|
| `data_hora` | hora **local** (o `CURRENT_TIMESTAMP` do SQLite usa UTC; o `app.py` usa hora local) |
| `demanda` | unidades previstas para 7 dias |
| `estoque_informado` | estoque no momento da análise |
| `promocao` | 1 se o preço atual está 10%+ abaixo da média do produto |
| `sazonalidade` | fator do mês: 1,30 = esse mês vende 30% acima da média do produto (0 = sem dado) |
| `preco_analisado` / `preco_recomendado` | preço atual / sugerido |
| `confianca` | 0 a 1 |
| `modelo` | ex.: `Random Forest \| treino 2026-11-11 \| DADOS SIMULADOS` |

Os valores são validados (mesmas regras CHECK do banco) antes de gravar. `situacao` e `motivo` não têm coluna
na tabela; vão só no retorno da função.

## Trocar para o banco real

Qualquer uma das opções:
1. Passar o caminho na chamada: `recalcular_preco(4, caminho_banco="dynaprice_BD.db")`;
2. Definir a variável de ambiente `DYNAPRICE_BANCO` com o caminho do `.db`;
3. Mudar `CAMINHO_BANCO_PADRAO` em `dynaprice_ia/config.py`.

O modelo salvo guarda **qual banco** usou no treino. Se o banco for outro, ele é **re-treinado
automaticamente** na primeira chamada (um modelo de dados simulados nunca é usado no banco real).

O módulo funciona com as **duas versões** do banco do grupo: a nova (com `vendas.status` e a view
`vendas_ativas`) e a antiga do repositório (sem elas — nesse caso todas as vendas são consideradas).
Se o banco tiver `vendas.status` mas não a view, as vendas canceladas são filtradas do mesmo jeito.

### Re-treinar
Quando entrarem muitas vendas novas (ex.: uma vez por semana):

```python
from dynaprice_ia import retreinar_modelo
retreinar_modelo()            # ou retreinar_modelo(caminho_banco="...")
```

São necessários uns **3 meses de vendas** para o primeiro treino (antes disso, o preço é mantido).

## Testes

```bash
python -m pytest -v
```

29 testes cobrindo: erros (produto inexistente, inativo, banco inexistente, id inválido), pouco histórico,
banco recém-começado, formato do retorno (inclusive conversão para JSON), limite de ±10%, arredondamento,
estoque zero, gravação em `analises_ia`, garantia de que `preco_atual`/`historico_precos`/etiquetas **não**
mudam, chaves estrangeiras e compatibilidade com o banco antigo. Os testes usam **cópias temporárias** do banco
e do modelo; não alteram nenhum arquivo do projeto.

Para ver um exemplo de uso: `python exemplo_uso.py` (grava análises no banco simulado).

## Limitações

- **Dados simulados**: as métricas acima medem o quanto o modelo recupera padrões que **nós** criamos. Com dados
  reais os números serão diferentes e precisam ser medidos de novo (`python treinar_modelo.py`).
- **Efeito do preço fraco**: o modelo percebe a direção certa (preço maior → vende menos), mas subestima a força
  (ex.: na cerveja, +10% no preço deveria reduzir ~16% das vendas; o modelo prevê ~0,4%). Motivo: o preço variou
  pouco no histórico e seu efeito se mistura com a sazonalidade. Por isso o preço é decidido pela regra de
  cobertura de estoque, e não por otimização de lucro.
- **Sem custo do produto**: não há preço mínimo de lucro. A única proteção contra preço baixo demais é o limite
  de ±10% por recálculo (vários recálculos seguidos podem acumular quedas).
- **Previsão de 7 dias simplificada**: as médias de 7 e 28 dias ficam fixas nos últimos valores conhecidos
  durante os 7 dias previstos.
- **Sazonalidade** só tem sentido com pelo menos 1 ano de vendas do produto.
- **Promoção** é inferida pelo preço (o banco não registra promoções).
- **Concorrência / clima / feriados** não são considerados.

## Observações para o grupo

Encontradas ao comparar o repositório com o banco (não são parte do módulo de IA; apenas para conhecimento):

1. O `dynaprice_BD.db` do repositório é uma **versão anterior** do `dynaprice_BD_atualizado.db`: não tem
   `vendas.status`, `data_hora_cancelamento`, `motivo_cancelamento`, a view `vendas_ativas`, a tabela
   `historico_vendas` nem os triggers de venda cancelada. Os dois estão vazios.
2. O `app.py` grava status em minúsculo (`'pendente'`, `'cadastrada'`, `'pendente_atualizacao'`, origem
   `'manual'`), enquanto os padrões do banco são em maiúsculo (`'PENDENTE'`, `'OFFLINE'`, `'API REST'`, `'IA'`).
   Vale padronizar para os filtros funcionarem.
3. O padrão `CURRENT_TIMESTAMP` do SQLite grava em UTC (3h à frente de Brasília); o `app.py` grava hora local.
