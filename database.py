
import sqlite3
from pathlib import Path

# Caminho do banco de dados na mesma pasta deste arquivo
BASE_DIR = Path(__file__).resolve().parent
CAMINHO_BANCO = BASE_DIR / "dynaprice_BD.db"


def conectar():
    """Abre uma conexão com o banco de dados."""
    conexao = sqlite3.connect(CAMINHO_BANCO)
    conexao.row_factory = sqlite3.Row
    return conexao

