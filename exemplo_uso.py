"""
exemplo_uso.py — Exemplo simples de como a aplicação principal usa o módulo de IA.

Como rodar (na pasta do projeto):
    python exemplo_uso.py

ATENÇÃO: cada chamada GRAVA uma linha em analises_ia do banco configurado
(hoje: o banco SIMULADO em dados_sinteticos/). Para "zerar" o banco simulado:
    python dados_sinteticos/gerar_dados_sinteticos.py --sobrescrever
"""

from dynaprice_ia import ErroDynaPriceIA, recalcular_preco

# 3 = café (estoque baixo), 9 = sabonete (estoque parado), 13 = lançamento (pouco histórico),
# 14 = produto inativo (erro), 999 = não existe (erro)
for produto_id in [3, 9, 13, 14, 999]:
    print(f"\n--- recalcular_preco({produto_id}) ---")
    try:
        r = recalcular_preco(produto_id)
        print(f"Situação: {r['situacao']}  |  R$ {r['preco_atual']:.2f} -> R$ {r['preco_sugerido']:.2f}"
              f" ({r['variacao_percentual']:+.2f}%)")
        print(f"Demanda prevista (7 dias): {r['demanda_prevista']} un  |  Confiança: {r['confianca']:.2f}"
              f"  |  id_analise: {r['id_analise']}")
        print(f"Motivo: {r['motivo']}")
    except ErroDynaPriceIA as erro:
        # Erros "conhecidos" do módulo: produto inexistente, inativo, banco não encontrado
        print(f"Erro tratado ({type(erro).__name__}): {erro}")
