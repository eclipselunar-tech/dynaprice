
# DynaPrice — Módulo de IA (entrega do João)

Resumo rápido da entrega. Os detalhes completos (como o modelo aprende, métricas, testes) estão no `README.md`.

> ⚠️ **O modelo foi treinado com DADOS SIMULADOS**, porque o banco do grupo ainda está vazio.
> Os produtos simulados têm "(SIMULADO)" no nome e "SIM-" no código de barras.
> Quando houver vendas reais, o módulo re-treina sozinho no banco real.

---

## 1. Para o líder: o que o módulo faz

Recebe o ID de um produto, **prevê quanto ele vai vender nos próximos 7 dias** e **sugere um preço**.

Ele **só sugere e registra** a análise na tabela `analises_ia`. **Não** altera `produtos.preco_atual`,
**não** grava em `historico_precos` e **não** mexe em `etiquetas` / `atualizacoes_etiqueta`.

### Como funciona
1. Lê do banco as vendas **ativas** (canceladas ficam de fora).
2. Monta uma tabela "produto × dia" com 5 pistas: **dia da semana**, **mês**, **preço comparado ao normal**,
   **média de vendas dos últimos 7 dias** e **dos últimos 28 dias**.
3. Um modelo **Random Forest** (scikit-learn) prevê a demanda. Foi comparado com Regressão Linear e com um
   "chute simples" (média dos últimos 7 dias) e ganhou dos dois: **erra em média ~3 unidades por dia** e
   **explica 77% da variação das vendas** (testado em 60 dias que o modelo nunca viu).
4. **Regra do preço** (demanda prevista × estoque):
   - estoque para **menos de 7 dias** → preço **sobe**;
   - estoque para **mais de 30 dias** → preço **desce**;
   - entre 7 e 30 dias → **mantém**;
   - mudança máxima de **±10%** por recálculo; preço termina em 9 centavos (ex.: R$ 11,09).
5. Grava a análise em `analises_ia` e devolve o resultado.

### Pontos importantes
- Produto **com pouco histórico** (menos de 30 dias, ou menos de 10 dias com venda), **sem estoque**, ou banco
  com vendas de menos para treinar (menos de ~3 meses): o preço é **mantido**, com confiança baixa (0,1).
- Funciona com as **duas versões** do banco do grupo (a nova, com cancelamento de vendas, e a antiga do GitHub).
- Todas as regras (limite de 10%, faixas de 7 e 30 dias etc.) ficam em `dynaprice_ia/config.py`.
- 60 testes automáticos (`python -m pytest -v`).

### Limitação principal
O modelo prevê bem a **demanda**, mas percebe **pouco o efeito do preço** (no histórico o preço variou pouco e o
efeito se mistura com a estação do ano). Por isso o preço é decidido por uma **regra simples e explicável**
(cobertura de estoque), e não pelo modelo. Também não temos o **custo** dos produtos, então não há preço
mínimo de lucro: a única proteção é o limite de ±10% por recálculo.

---

## 2. Para o Seven: como integrar

### Instalação
```bash
python -m pip install -r requirements.txt
```
Coloque a pasta `dynaprice_ia/` ao lado do `app.py`.

### Chamada
```python
from database import CAMINHO_BANCO
from dynaprice_ia import recalcular_preco

resultado = recalcular_preco(id_produto, caminho_banco=CAMINHO_BANCO)
```
Se `caminho_banco` não for informado, usa a variável de ambiente `DYNAPRICE_BANCO` ou o padrão do `config.py`
(hoje, o banco simulado).

### O que retorna
Um dicionário (já pronto para o `jsonify`):

```python
{
    "produto_id": 4,
    "preco_atual": 10.49,
    "preco_sugerido": 11.09,
    "demanda_prevista": 98,          # unidades nos próximos 7 dias
    "confianca": 0.7,                # 0 a 1
    "id_analise": 15,                # linha gravada em analises_ia
    "situacao": "SUBIR",             # SUBIR, DESCER, MANTER, POUCO_HISTORICO ou SEM_ESTOQUE
    "motivo": "Estoque cobre só 3.0 dias (mínimo 7): demanda alta para o estoque.",
    "variacao_percentual": 5.72,
    "cobertura_dias": 3.0            # para quantos dias o estoque dura (None se não há demanda)
}
```

### Erros possíveis
Todos herdam de `ErroDynaPriceIA`:

| Erro | Quando |
|---|---|
| `ProdutoNaoEncontrado` | não existe produto com esse ID |
| `ProdutoInativo` | produto com `ativo = 0` |
| `BancoNaoEncontrado` | o arquivo `.db` não existe (o módulo não cria banco vazio) |
| `ValueError` | ID não é número inteiro |

Produto sem histórico **não** gera erro: devolve o preço atual com `situacao = "POUCO_HISTORICO"`.

### Exemplo de rota Flask (sugestão)
```python
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

Depois que o usuário **aprovar** a sugestão, aplique o preço pela rota que já existe
(`PUT /api/produtos/<codigo_barras>`), que grava `historico_precos` e prepara as etiquetas.

### Re-treinar o modelo
Quando entrarem muitas vendas novas (ex.: uma vez por semana):
```bash
python treinar_modelo.py caminho/do/dynaprice_BD.db
```
ou, no código: `from dynaprice_ia import retreinar_modelo; retreinar_modelo(CAMINHO_BANCO)`.
O app percebe o modelo novo sozinho, sem reiniciar.

---

## 2b. Promoções (novo): `avaliar_promocao`

Avalia se uma promoção **vale a pena**. **Somente leitura**: não grava nada e não muda preços.

```python
from dynaprice_ia import avaliar_promocao
avaliacao = avaliar_promocao(id_produto, desconto_percentual=15, dias=7, caminho_banco=CAMINHO_BANCO)
```

- Compara a demanda e a **receita** sem e com o desconto, e verifica se o **estoque** aguenta.
- Veredito: **"vale a pena"**, **"não vale a pena"** ou **"arriscado"**, com o `motivo` em texto.
- O efeito do desconto vem da **elasticidade** de cada produto (Regressão de Poisson). Nos dados simulados ela
  acertou **8 de 12** produtos; o modelo de demanda sozinho subestimava muito (cerveja −20%: real +49%, ele +7%).
- Limites: desconto de 1% a 50%, duração de 1 a 30 dias. Erros iguais aos do `recalcular_preco` + `ValueError`.
- ⚠️ É análise de **receita, não de lucro** (o banco não tem custo dos produtos), e foi validada com **dados simulados**.
- Retorno, exemplos e a rota Flask sugerida (`POST /api/produtos/<id>/avaliar-promocao`) estão no `README.md`,
  seção "Promoções".

---

## 3. Para o grupo decidir

1. **Limite de variação de preço**: está em **±10% por recálculo**. Está bom? (muda em `dynaprice_ia/config.py`,
   constante `LIMITE_VARIACAO_PRECO`).
2. **Banco antigo no GitHub**: o `dynaprice_BD.db` do repositório é uma versão **anterior** do banco — não tem
   `vendas.status`, `data_hora_cancelamento`, `motivo_cancelamento`, a view `vendas_ativas`, a tabela
   `historico_vendas` nem os triggers de venda cancelada. Qual versão será a oficial? (o módulo funciona com as duas)
3. **Status em minúsculo × maiúsculo**: o `app.py` grava `'pendente'`, `'cadastrada'`, `'pendente_atualizacao'` e
   origem `'manual'`, mas os padrões do banco são em maiúsculo (`'PENDENTE'`, `'OFFLINE'`, `'API REST'`, `'IA'`).
   Vale padronizar para os filtros não falharem.
4. (Detalhe) O padrão `CURRENT_TIMESTAMP` do SQLite grava em **UTC** (3h à frente de Brasília), enquanto o `app.py`
   grava hora local. O módulo de IA grava hora local, igual ao `app.py`.

---

## Conteúdo do .zip

| Item | O que é |
|---|---|
| `LEIA-ME-PRIMEIRO.md` | este arquivo |
| `README.md` | documentação completa (modelo, métricas, regras, limitações) |
| `dynaprice_ia/` | o módulo (com o modelo já treinado em `modelos/`) |
| `dados_sinteticos/` | gerador e banco com dados **simulados** (pode apagar quando houver dados reais) |
| `tests/` | testes automáticos (`python -m pytest -v`) |
| `dados_sinteticos/validar_elasticidade.py` | confere se o efeito do desconto foi aprendido |
| `exemplo_uso.py` | exemplo de chamada (`python exemplo_uso.py`) |
| `treinar_modelo.py` | re-treina e mostra o relatório do modelo |
| `requirements.txt` | bibliotecas necessárias |
