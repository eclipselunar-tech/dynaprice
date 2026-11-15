from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import Blueprint, jsonify
from database import conectar

aprovacao_ia = Blueprint("aprovacao_ia", __name__)

def _centavos(valor):
    try:
        numero = Decimal(str(valor))

        if not numero.is_finite() or numero < 0:
            raise ValueError("Preço inválido")

        return int(
            (numero * 100).quantize(
                Decimal("1"),
                rounding=ROUND_HALF_UP
            )
        )

    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Preço inválido") from exc


def preparar_aprovacoes_ia():
    conexao = conectar()

    try:
        conexao.execute("""
            CREATE TABLE IF NOT EXISTS decisoes_precos_ia (
                id_decisao INTEGER PRIMARY KEY AUTOINCREMENT,
                id_analise INTEGER NOT NULL UNIQUE,
                id_produto INTEGER NOT NULL,
                decisao TEXT NOT NULL
                    CHECK (decisao IN ('APROVADA', 'REJEITADA')),
                preco_anterior REAL NOT NULL,
                preco_recomendado REAL NOT NULL,
                data_hora TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (id_analise)
                    REFERENCES analises_ia(id_analise),

                FOREIGN KEY (id_produto)
                    REFERENCES produtos(id_produto)
            )
        """)

        conexao.commit()

    finally:
        conexao.close()


@aprovacao_ia.route(
    "/api/ia/analises/<int:id_analise>/<acao>",
    methods=["POST"]
)
def decidir_analise_ia(id_analise, acao):

    if acao not in ("aprovar", "rejeitar"):
        return jsonify({
            "erro": "Decisão inválida."
        }), 400

    conexao = conectar()

    try:
        conexao.execute("BEGIN IMMEDIATE")

        analise = conexao.execute("""
            SELECT
                a.id_analise,
                a.id_produto,
                a.preco_analisado,
                a.preco_recomendado,
                p.preco_atual,
                p.ativo

            FROM analises_ia a

            JOIN produtos p
                ON p.id_produto = a.id_produto

            WHERE a.id_analise = ?
        """, (id_analise,)).fetchone()

        if analise is None:
            conexao.rollback()

            return jsonify({
                "erro": "Análise não encontrada."
            }), 404

        decisao_existente = conexao.execute("""
            SELECT 1
            FROM decisoes_precos_ia
            WHERE id_analise = ?
        """, (id_analise,)).fetchone()

        if decisao_existente:
            conexao.rollback()

            return jsonify({
                "erro": "Esta análise já recebeu uma decisão."
            }), 409

        if not analise["ativo"]:
            conexao.rollback()

            return jsonify({
                "erro": "Produto inativo."
            }), 409

        anterior = _centavos(
            analise["preco_atual"]
        )

        analisado = _centavos(
            analise["preco_analisado"]
        )

        recomendado = _centavos(
            analise["preco_recomendado"]
        )

        if acao == "aprovar":

            if anterior != analisado:
                conexao.rollback()

                return jsonify({
                    "erro": (
                        "O preço mudou desde a análise. "
                        "Faça uma nova análise."
                    )
                }), 409

            if anterior == recomendado:
                conexao.rollback()

                return jsonify({
                    "erro": (
                        "O preço recomendado é igual "
                        "ao preço atual."
                    )
                }), 409

        decisao = (
            "APROVADA"
            if acao == "aprovar"
            else "REJEITADA"
        )

        conexao.execute("""
            INSERT INTO decisoes_precos_ia (
                id_analise,
                id_produto,
                decisao,
                preco_anterior,
                preco_recomendado
            )

            VALUES (?, ?, ?, ?, ?)
        """, (
            id_analise,
            analise["id_produto"],
            decisao,
            anterior / 100,
            recomendado / 100
        ))

        if acao == "aprovar":

            conexao.execute("""
                UPDATE produtos
                SET preco_atual = ?
                WHERE id_produto = ?
            """, (
                recomendado / 100,
                analise["id_produto"]
            ))

            conexao.execute("""
                INSERT INTO historico_precos (
                    id_produto,
                    preco_anterior,
                    novo_preco,
                    motivo,
                    origem
                )

                VALUES (?, ?, ?, ?, 'IA_APROVADA')
            """, (
                analise["id_produto"],
                anterior / 100,
                recomendado / 100,
                (
                    f"Recomendação da análise IA "
                    f"#{id_analise} aprovada manualmente"
                )
            ))

            etiqueta = conexao.execute("""
                SELECT id_etiqueta
                FROM etiquetas
                WHERE id_produto = ?
            """, (
                analise["id_produto"],
            )).fetchone()

            if etiqueta:

                conexao.execute("""
                    INSERT INTO atualizacoes_etiqueta (
                        id_etiqueta,
                        id_produto,
                        preco_anterior,
                        novo_preco,
                        origem,
                        status
                    )

                    VALUES (
                        ?, ?, ?, ?,
                        'IA_APROVADA',
                        'PENDENTE'
                    )
                """, (
                    etiqueta["id_etiqueta"],
                    analise["id_produto"],
                    anterior / 100,
                    recomendado / 100
                ))

        conexao.commit()

        if acao == "aprovar":
            mensagem = "Preço aprovado e atualizado."
        else:
            mensagem = (
                "Recomendação rejeitada. "
                "Preço mantido."
            )

        return jsonify({
            "mensagem": mensagem,
            "decisao": decisao,
            "id_analise": id_analise
        }), 200

    except Exception:
        conexao.rollback()
        raise

    finally:
        conexao.close()
