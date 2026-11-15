"""
treinar_modelo.py — Re-treina o modelo de demanda e mostra o relatório (métricas e importância).

Como rodar (na pasta do projeto):
    python treinar_modelo.py                      (usa o banco configurado em dynaprice_ia/config.py)
    python treinar_modelo.py caminho/do/banco.db  (usa outro banco)
"""

import sys

from dynaprice_ia import retreinar_modelo

retreinar_modelo(sys.argv[1] if len(sys.argv) > 1 else None)
