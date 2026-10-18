from flask import Flask, jsonify, request, render_template
from database import conectar
from datetime import datetime

app = Flask(__name__)

@app.route("/", methods=["GET"])
def inicio():
    return render_template("index.html")

@app.route("/api/saude", methods=["GET"])
def verificar_saude():
    return jsonify({
        "status": "ok",
        "servidor": "Flask"
    })

#termos
@app.route("/termos")
def termos():
    return render_template("termos.html")

#rota dos produtos
@app.route("/api/produtos", methods=["GET"])
def listar_produtos():
    conexao = conectar()

    try:
        produtos = conexao.execute("""
            SELECT
                id_produto,
                codigo_barras,
                nome,
                categoria,
                preco_atual,
                estoque_atual,
                ativo
            FROM produtos
            WHERE ativo = 1
            ORDER BY nome
        """).fetchall()

        resultado = [dict(produto) for produto in produtos]

        return jsonify(resultado), 200

    finally:
        conexao.close()

#rota buscar produto
@app.route("/api/produtos/<codigo_barras>", methods=["GET"])
def buscar_produto(codigo_barras):
    conexao = conectar()

    try:
        produto = conexao.execute("""
            SELECT
                id_produto,
                codigo_barras,
                nome,
                categoria,
                preco_atual,
                estoque_atual,
                ativo
            FROM produtos
            WHERE codigo_barras = ? AND ativo = 1
        """, (codigo_barras,)).fetchone()

        if produto is None:
            return jsonify({
                "erro": "Produto nao encontrado."
            }), 404

        return jsonify(dict(produto)), 200

    finally:
        conexao.close()

#rota de cadastro
@app.route("/api/produtos", methods=["POST"])
def cadastrar_produto():
    dados = request.get_json(silent=True)

    if not dados:
        return jsonify({
            "erro": "Envie os dados do produto em formato JSON."
        }), 400

    campos_obrigatorios = [
        "codigo_barras",
        "nome",
        "preco_atual",
        "estoque_atual"
    ]

    for campo in campos_obrigatorios:
        if campo not in dados:
            return jsonify({
                "erro": f"O campo '{campo}' e obrigatorio."
            }), 400

    codigo = str(dados["codigo_barras"]).strip()
    nome = str(dados["nome"]).strip()
    categoria = dados.get("categoria")

    if not codigo or not nome:
        return jsonify({
            "erro": "Codigo de barras e nome nao podem ficar vazios."
        }), 400

    if categoria is not None:
        categoria = str(categoria).strip() or None

    try:
        preco = float(dados["preco_atual"])
        estoque = int(dados["estoque_atual"])

        if preco < 0 or estoque < 0:
            raise ValueError

    except (ValueError, TypeError, OverflowError):
        return jsonify({
            "erro": "Preco e estoque devem ser valores validos e nao negativos."
        }), 400

    if not preco < float("inf"):
        return jsonify({"erro": "Preco invalido."}), 400

    if estoque != dados["estoque_atual"]:
        return jsonify({
            "erro": "O estoque deve ser um numero inteiro."
        }), 400

    conexao = conectar()

    try:
        cursor = conexao.execute("""
            INSERT INTO produtos (
                codigo_barras,
                nome,
                categoria,
                preco_atual,
                estoque_atual
            )
            VALUES (?, ?, ?, ?, ?)
        """, (codigo, nome, categoria, preco, estoque))

        conexao.commit()

        return jsonify({
            "mensagem": "Produto cadastrado com sucesso!",
            "id_produto": cursor.lastrowid
        }), 201

    except Exception as erro:
        conexao.rollback()

        if "UNIQUE constraint failed: produtos.codigo_barras" in str(erro):
            return jsonify({
                "erro": "Ja existe um produto com esse codigo de barras."
            }), 409

        app.logger.exception("Erro ao cadastrar produto")
        return jsonify({
            "erro": "Nao foi possivel cadastrar o produto."
        }), 500

    finally:
        conexao.close()

# Rota de atualizacao de produto
@app.route("/api/produtos/<codigo_barras>", methods=["PUT"])
def atualizar_produto(codigo_barras):
    dados = request.get_json(silent=True)

    if not isinstance(dados, dict) or not dados:
        return jsonify({
            "erro": "Envie os dados em formato JSON."
        }), 400

    campos_permitidos = [
        "nome",
        "categoria",
        "preco_atual",
        "estoque_atual"
    ]

    if not any(campo in dados for campo in campos_permitidos):
        return jsonify({
            "erro": "Informe pelo menos um campo para atualizar."
        }), 400

    conexao = conectar()

    try:
        produto = conexao.execute("""
            SELECT id_produto, preco_atual
            FROM produtos
            WHERE codigo_barras = ? AND ativo = 1
        """, (codigo_barras,)).fetchone()

        if produto is None:
            return jsonify({
                "erro": "Produto nao encontrado."
            }), 404

        id_produto = produto["id_produto"]
        preco_anterior = float(produto["preco_atual"])
        novo_preco = preco_anterior
        preco_informado = "preco_atual" in dados

        atualizacoes = []
        valores = []

        if "nome" in dados:
            nome = str(dados["nome"]).strip()

            if not nome:
                return jsonify({
                    "erro": "O nome nao pode ficar vazio."
                }), 400

            atualizacoes.append("nome = ?")
            valores.append(nome)

        if "categoria" in dados:
            categoria = dados["categoria"]

            if categoria is not None:
                categoria = str(categoria).strip() or None

            atualizacoes.append("categoria = ?")
            valores.append(categoria)

        if preco_informado:
            try:
                preco_original = dados["preco_atual"]

                if isinstance(preco_original, bool):
                    raise ValueError

                novo_preco = float(preco_original)

                if novo_preco < 0 or not novo_preco < float("inf"):
                    raise ValueError

            except (ValueError, TypeError, OverflowError):
                return jsonify({
                    "erro": "Informe um preco valido e nao negativo."
                }), 400

            atualizacoes.append("preco_atual = ?")
            valores.append(novo_preco)

        if "estoque_atual" in dados:
            try:
                estoque_original = dados["estoque_atual"]
                estoque = int(estoque_original)

                if isinstance(estoque_original, bool):
                    raise ValueError

                if str(estoque_original).strip() != str(estoque):
                    raise ValueError

                if estoque < 0:
                    raise ValueError

            except (ValueError, TypeError, OverflowError):
                return jsonify({
                    "erro": "O estoque deve ser um inteiro nao negativo."
                }), 400

            atualizacoes.append("estoque_atual = ?")
            valores.append(estoque)

        valores.append(codigo_barras)

        conexao.execute(
            "UPDATE produtos SET "
            + ", ".join(atualizacoes)
            + " WHERE codigo_barras = ? AND ativo = 1",
            valores
        )

        etiquetas_pendentes = 0

        # Registrar a mudanca de preco e preparar as etiquetas
        if preco_informado and novo_preco != preco_anterior:
            motivo = dados.get(
                "motivo",
                "Atualizacao manual de preco"
            )

            if motivo is not None:
                motivo = str(motivo).strip() or None

            data_hora = datetime.now().isoformat(
                sep=" ",
                timespec="seconds"
            )

            # Registrar o historico de preco do produto
            conexao.execute("""
                INSERT INTO historico_precos (
                    id_produto,
                    preco_anterior,
                    novo_preco,
                    motivo,
                    origem,
                    data_hora
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                id_produto,
                preco_anterior,
                novo_preco,
                motivo,
                "manual",
                data_hora
            ))

            # Encontrar as etiquetas associadas ao produto
            etiquetas = conexao.execute("""
                SELECT id_etiqueta, preco_exibido
                FROM etiquetas
                WHERE id_produto = ?
            """, (id_produto,)).fetchall()

            for etiqueta in etiquetas:
                # Registrar a atualizacao que precisa ser enviada
                conexao.execute("""
                    INSERT INTO atualizacoes_etiqueta (
                        id_etiqueta,
                        id_produto,
                        preco_anterior,
                        novo_preco,
                        data_hora,
                        origem,
                        status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    etiqueta["id_etiqueta"],
                    id_produto,
                    etiqueta["preco_exibido"],
                    novo_preco,
                    data_hora,
                    "manual",
                    "pendente"
                ))

                # Indicar que a etiqueta precisa ser atualizada
                conexao.execute("""
                    UPDATE etiquetas
                    SET status = ?
                    WHERE id_etiqueta = ?
                """, (
                    "pendente_atualizacao",
                    etiqueta["id_etiqueta"]
                ))

                etiquetas_pendentes += 1

        # Salvar todas as alteracoes juntas
        conexao.commit()

        produto_atualizado = conexao.execute("""
            SELECT
                id_produto,
                codigo_barras,
                nome,
                categoria,
                preco_atual,
                estoque_atual,
                ativo
            FROM produtos
            WHERE codigo_barras = ? AND ativo = 1
        """, (codigo_barras,)).fetchone()

        return jsonify({
            "mensagem": "Produto atualizado com sucesso!",
            "produto": dict(produto_atualizado),
            "etiquetas_pendentes": etiquetas_pendentes
        }), 200

    except Exception:
        conexao.rollback()
        app.logger.exception("Erro ao atualizar produto")

        return jsonify({
            "erro": "Nao foi possivel atualizar o produto."
        }), 500

    finally:
        conexao.close()

# rota de registro de venda
@app.route("/api/vendas", methods=["POST"])
def registrar_venda():
    dados = request.get_json(silent=True)

    if not isinstance(dados, dict):
        return jsonify({
            "erro": "Envie os dados da venda em formato JSON."
        }), 400

    itens_recebidos = dados.get("itens")

    if not isinstance(itens_recebidos, list) or not itens_recebidos:
        return jsonify({
            "erro": "A venda deve conter pelo menos um item."
        }), 400

    # Validar os itens recebidos
    itens_por_codigo = {}

    for item in itens_recebidos:
        if not isinstance(item, dict):
            return jsonify({
                "erro": "Cada item deve ser um objeto JSON."
            }), 400

        codigo = item.get("codigo_barras")
        quantidade_original = item.get("quantidade")

        if not isinstance(codigo, str) or not codigo.strip():
            return jsonify({
                "erro": "Informe um codigo de barras valido."
            }), 400

        if isinstance(quantidade_original, bool):
            return jsonify({
                "erro": "A quantidade deve ser um inteiro positivo."
            }), 400

        try:
            quantidade = int(quantidade_original)

            if str(quantidade_original).strip() != str(quantidade):
                raise ValueError

            if quantidade <= 0:
                raise ValueError

        except (ValueError, TypeError, OverflowError):
            return jsonify({
                "erro": "A quantidade deve ser um inteiro positivo."
            }), 400

        codigo = codigo.strip()

        # Somar quantidades se o mesmo produto aparecer mais de uma vez
        itens_por_codigo[codigo] = (
            itens_por_codigo.get(codigo, 0) + quantidade
        )

    conexao = conectar()

    try:
        # Inicia uma transacao para proteger toda a venda
        conexao.execute("BEGIN IMMEDIATE")

        itens_venda = []
        valor_total = 0.0

        # Consultar produtos e verificar estoque
        for codigo, quantidade in itens_por_codigo.items():
            produto = conexao.execute("""
                SELECT
                    id_produto,
                    codigo_barras,
                    nome,
                    preco_atual,
                    estoque_atual
                FROM produtos
                WHERE codigo_barras = ? AND ativo = 1
            """, (codigo,)).fetchone()

            if produto is None:
                conexao.rollback()
                return jsonify({
                    "erro": "Produto nao encontrado.",
                    "codigo_barras": codigo
                }), 404

            if produto["estoque_atual"] < quantidade:
                conexao.rollback()
                return jsonify({
                    "erro": "Estoque insuficiente.",
                    "produto": produto["nome"],
                    "estoque_disponivel": produto["estoque_atual"],
                    "quantidade_solicitada": quantidade
                }), 409

            preco = float(produto["preco_atual"])
            subtotal = round(preco * quantidade, 2)
            valor_total = round(valor_total + subtotal, 2)

            itens_venda.append({
                "id_produto": produto["id_produto"],
                "codigo_barras": codigo,
                "nome": produto["nome"],
                "quantidade": quantidade,
                "preco_unitario": preco,
                "subtotal": subtotal
            })

        # Registrar a venda
        cursor = conexao.execute("""
            INSERT INTO vendas (data_hora, valor_total)
            VALUES (?, ?)
        """, (
            datetime.now().isoformat(sep=" ", timespec="seconds"),
            valor_total
        ))

        id_venda = cursor.lastrowid

        # Registrar itens e atualizar estoque
        for item in itens_venda:
            conexao.execute("""
                INSERT INTO itens_venda (
                    id_venda,
                    id_produto,
                    quantidade,
                    preco_unitario,
                    subtotal
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                id_venda,
                item["id_produto"],
                item["quantidade"],
                item["preco_unitario"],
                item["subtotal"]
            ))

            resultado = conexao.execute("""
                UPDATE produtos
                SET estoque_atual = estoque_atual - ?
                WHERE id_produto = ?
                  AND ativo = 1
                  AND estoque_atual >= ?
            """, (
                item["quantidade"],
                item["id_produto"],
                item["quantidade"]
            ))

            if resultado.rowcount != 1:
                raise RuntimeError("Nao foi possivel atualizar o estoque.")

        # Confirmar todas as operacoes juntas
        conexao.commit()

        return jsonify({
            "mensagem": "Venda registrada com sucesso!",
            "id_venda": id_venda,
            "valor_total": valor_total,
            "itens": itens_venda
        }), 201

    except Exception:
        conexao.rollback()
        app.logger.exception("Erro ao registrar venda")

        return jsonify({
            "erro": "Nao foi possivel registrar a venda."
        }), 500

    finally:
        conexao.close()

# Rota para listar o historico de vendas
@app.route("/api/vendas", methods=["GET"])
def listar_vendas():
    conexao = conectar()

    try:
        vendas = conexao.execute("""
            SELECT id_venda, data_hora, valor_total
            FROM vendas
            ORDER BY id_venda DESC
        """).fetchall()

        lista_vendas = []

        for venda in vendas:
            lista_vendas.append({
                "id_venda": venda["id_venda"],
                "data_hora": venda["data_hora"],
                "valor_total": venda["valor_total"]
            })

        return jsonify(lista_vendas), 200

    except Exception:
        app.logger.exception("Erro ao consultar vendas")

        return jsonify({
            "erro": "Nao foi possivel consultar as vendas."
        }), 500

    finally:
        conexao.close()


# Rota para consultar os detalhes de uma venda
@app.route("/api/vendas/<int:id_venda>", methods=["GET"])
def detalhar_venda(id_venda):
    conexao = conectar()

    try:
        venda = conexao.execute("""
            SELECT id_venda, data_hora, valor_total
            FROM vendas
            WHERE id_venda = ?
        """, (id_venda,)).fetchone()

        if venda is None:
            return jsonify({
                "erro": "Venda nao encontrada."
            }), 404

        itens = conexao.execute("""
            SELECT
                p.codigo_barras,
                p.nome,
                iv.quantidade,
                iv.preco_unitario,
                iv.subtotal
            FROM itens_venda iv
            JOIN produtos p
                ON iv.id_produto = p.id_produto
            WHERE iv.id_venda = ?
        """, (id_venda,)).fetchall()

        lista_itens = []

        for item in itens:
            lista_itens.append({
                "codigo_barras": item["codigo_barras"],
                "nome": item["nome"],
                "quantidade": item["quantidade"],
                "preco_unitario": item["preco_unitario"],
                "subtotal": item["subtotal"]
            })

        return jsonify({
            "id_venda": venda["id_venda"],
            "data_hora": venda["data_hora"],
            "valor_total": venda["valor_total"],
            "itens": lista_itens
        }), 200

    except Exception:
        app.logger.exception("Erro ao consultar detalhes da venda")

        return jsonify({
            "erro": "Nao foi possivel consultar a venda."
        }), 500

    finally:
        conexao.close()


# Rota para consultar o estoque dos produtos
@app.route("/api/estoque", methods=["GET"])
def consultar_estoque():
    conexao = conectar()

    try:
        produtos = conexao.execute("""
            SELECT
                codigo_barras,
                nome,
                categoria,
                estoque_atual,
                preco_atual
            FROM produtos
            WHERE ativo = 1
            ORDER BY nome
        """).fetchall()

        lista_estoque = []

        for produto in produtos:
            lista_estoque.append({
                "codigo_barras": produto["codigo_barras"],
                "nome": produto["nome"],
                "categoria": produto["categoria"],
                "estoque_atual": produto["estoque_atual"],
                "preco_atual": produto["preco_atual"]
            })

        return jsonify(lista_estoque), 200

    except Exception:
        app.logger.exception("Erro ao consultar estoque")

        return jsonify({
            "erro": "Nao foi possivel consultar o estoque."
        }), 500

    finally:
        conexao.close()

# Rota para consultar produtos com estoque baixo
@app.route("/api/estoque/baixo", methods=["GET"])
def estoque_baixo():
    limite = request.args.get("limite", default=5, type=int)

    if limite < 0:
        return jsonify({
            "erro": "O limite nao pode ser negativo."
        }), 400

    conexao = conectar()

    try:
        produtos = conexao.execute("""
            SELECT
                codigo_barras,
                nome,
                categoria,
                estoque_atual,
                preco_atual
            FROM produtos
            WHERE ativo = 1
              AND estoque_atual <= ?
            ORDER BY estoque_atual ASC, nome ASC
        """, (limite,)).fetchall()

        lista_produtos = []

        for produto in produtos:
            lista_produtos.append({
                "codigo_barras": produto["codigo_barras"],
                "nome": produto["nome"],
                "categoria": produto["categoria"],
                "estoque_atual": produto["estoque_atual"],
                "preco_atual": produto["preco_atual"]
            })

        return jsonify({
            "limite_estoque": limite,
            "quantidade_produtos": len(lista_produtos),
            "produtos": lista_produtos
        }), 200

    except Exception:
        app.logger.exception("Erro ao consultar produtos com estoque baixo")

        return jsonify({
            "erro": "Nao foi possivel consultar o estoque baixo."
        }), 500

    finally:
        conexao.close()


# Rota para consultar o historico de precos de um produto
@app.route("/api/produtos/<codigo_barras>/historico-precos", methods=["GET"])
def historico_precos(codigo_barras):
    conexao = conectar()

    try:
        produto = conexao.execute("""
            SELECT id_produto, codigo_barras, nome, preco_atual
            FROM produtos
            WHERE codigo_barras = ?
        """, (codigo_barras,)).fetchone()

        if produto is None:
            return jsonify({
                "erro": "Produto nao encontrado."
            }), 404

        historico = conexao.execute("""
            SELECT
                preco_anterior,
                novo_preco,
                motivo,
                origem,
                data_hora
            FROM historico_precos
            WHERE id_produto = ?
            ORDER BY data_hora DESC, id_historico DESC
        """, (produto["id_produto"],)).fetchall()

        lista_historico = []

        for registro in historico:
            lista_historico.append({
                "preco_anterior": registro["preco_anterior"],
                "novo_preco": registro["novo_preco"],
                "motivo": registro["motivo"],
                "origem": registro["origem"],
                "data_hora": registro["data_hora"]
            })

        return jsonify({
            "codigo_barras": produto["codigo_barras"],
            "nome": produto["nome"],
            "preco_atual": produto["preco_atual"],
            "quantidade_alteracoes": len(lista_historico),
            "historico": lista_historico
        }), 200

    except Exception:
        app.logger.exception("Erro ao consultar historico de precos")

        return jsonify({
            "erro": "Nao foi possivel consultar o historico de precos."
        }), 500

    finally:
        conexao.close()

# Rota para listar as etiquetas eletronicas
@app.route("/api/etiquetas", methods=["GET"])
def listar_etiquetas():
    conexao = conectar()

    try:
        etiquetas = conexao.execute("""
            SELECT
                e.id_etiqueta,
                e.id_produto,
                p.codigo_barras,
                p.nome AS nome_produto,
                e.identificador,
                e.dispositivo,
                e.tipo_display,
                e.comunicacao_display,
                e.status,
                e.preco_exibido,
                e.ultima_atualizacao
            FROM etiquetas e
            JOIN produtos p
                ON e.id_produto = p.id_produto
            ORDER BY e.id_etiqueta
        """).fetchall()

        lista_etiquetas = []

        for etiqueta in etiquetas:
            lista_etiquetas.append(dict(etiqueta))

        return jsonify({
            "quantidade_etiquetas": len(lista_etiquetas),
            "etiquetas": lista_etiquetas
        }), 200

    except Exception:
        app.logger.exception("Erro ao consultar etiquetas")

        return jsonify({
            "erro": "Nao foi possivel consultar as etiquetas."
        }), 500

    finally:
        conexao.close()

# Rota para cadastrar uma etiqueta eletronica
@app.route("/api/etiquetas", methods=["POST"])
def cadastrar_etiqueta():
    dados = request.get_json(silent=True)

    if not isinstance(dados, dict):
        return jsonify({
            "erro": "Envie os dados em formato JSON."
        }), 400

    campos_obrigatorios = [
        "codigo_barras",
        "identificador",
        "dispositivo",
        "tipo_display",
        "comunicacao_display"
    ]

    for campo in campos_obrigatorios:
        if not isinstance(dados.get(campo), str) or not dados[campo].strip():
            return jsonify({
                "erro": "O campo '" + campo + "' e obrigatorio."
            }), 400

    codigo_barras = dados["codigo_barras"].strip()
    identificador = dados["identificador"].strip()
    dispositivo = dados["dispositivo"].strip()
    tipo_display = dados["tipo_display"].strip()
    comunicacao_display = dados["comunicacao_display"].strip()

    conexao = conectar()

    try:
        produto = conexao.execute("""
            SELECT id_produto, preco_atual
            FROM produtos
            WHERE codigo_barras = ? AND ativo = 1
        """, (codigo_barras,)).fetchone()

        if produto is None:
            return jsonify({
                "erro": "Produto nao encontrado."
            }), 404

        etiqueta_existente = conexao.execute("""
            SELECT id_etiqueta
            FROM etiquetas
            WHERE identificador = ?
        """, (identificador,)).fetchone()

        if etiqueta_existente is not None:
            return jsonify({
                "erro": "Ja existe uma etiqueta com esse identificador."
            }), 409

        cursor = conexao.execute("""
            INSERT INTO etiquetas (
                id_produto,
                identificador,
                dispositivo,
                tipo_display,
                comunicacao_display,
                status,
                preco_exibido,
                ultima_atualizacao
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            produto["id_produto"],
            identificador,
            dispositivo,
            tipo_display,
            comunicacao_display,
            "cadastrada",
            produto["preco_atual"],
            datetime.now().isoformat(sep=" ", timespec="seconds")
        ))

        id_etiqueta = cursor.lastrowid
        conexao.commit()

        etiqueta = conexao.execute("""
            SELECT
                id_etiqueta,
                id_produto,
                identificador,
                dispositivo,
                tipo_display,
                comunicacao_display,
                status,
                preco_exibido,
                ultima_atualizacao
            FROM etiquetas
            WHERE id_etiqueta = ?
        """, (id_etiqueta,)).fetchone()

        return jsonify({
            "mensagem": "Etiqueta cadastrada com sucesso!",
            "etiqueta": dict(etiqueta)
        }), 201

    except Exception:
        conexao.rollback()
        app.logger.exception("Erro ao cadastrar etiqueta")

        return jsonify({
            "erro": "Nao foi possivel cadastrar a etiqueta."
        }), 500

    finally:
        conexao.close()

# Rota para consultar atualizacoes pendentes das etiquetas
@app.route("/api/etiquetas/pendentes", methods=["GET"])
def listar_atualizacoes_pendentes():
    conexao = conectar()

    try:
        atualizacoes = conexao.execute("""
            SELECT
                ae.id_atualizacao,
                ae.id_etiqueta,
                ae.id_produto,
                p.codigo_barras,
                p.nome AS nome_produto,
                e.identificador,
                e.dispositivo,
                e.tipo_display,
                e.comunicacao_display,
                ae.preco_anterior,
                ae.novo_preco,
                ae.data_hora,
                ae.origem,
                ae.status
            FROM atualizacoes_etiqueta ae
            JOIN etiquetas e
                ON ae.id_etiqueta = e.id_etiqueta
            JOIN produtos p
                ON ae.id_produto = p.id_produto
            WHERE ae.status = 'pendente'
            ORDER BY ae.data_hora ASC, ae.id_atualizacao ASC
        """).fetchall()

        lista_atualizacoes = [
            dict(atualizacao)
            for atualizacao in atualizacoes
        ]

        return jsonify({
            "quantidade_pendentes": len(lista_atualizacoes),
            "atualizacoes": lista_atualizacoes
        }), 200

    except Exception:
        app.logger.exception(
            "Erro ao consultar atualizacoes pendentes"
        )

        return jsonify({
            "erro": "Nao foi possivel consultar as atualizacoes pendentes."
        }), 500

    finally:
        conexao.close()


# Rota para processar uma atualizacao pendente
@app.route(
    "/api/etiquetas/atualizacoes/<int:id_atualizacao>/processar",
    methods=["POST"]
)
def processar_atualizacao_etiqueta(id_atualizacao):
    conexao = conectar()

    try:
        conexao.execute("BEGIN IMMEDIATE")

        atualizacao = conexao.execute("""
            SELECT
                ae.id_atualizacao,
                ae.id_etiqueta,
                ae.id_produto,
                ae.novo_preco,
                ae.status
            FROM atualizacoes_etiqueta ae
            WHERE ae.id_atualizacao = ?
        """, (id_atualizacao,)).fetchone()

        if atualizacao is None:
            conexao.rollback()
            return jsonify({
                "erro": "Atualizacao nao encontrada."
            }), 404

        if atualizacao["status"] != "pendente":
            conexao.rollback()
            return jsonify({
                "erro": "A atualizacao nao esta pendente.",
                "status_atual": atualizacao["status"]
            }), 409

        # Esta etapa simula o processamento.
        # Ainda nao existe confirmacao de envio ao ESP32.

        data_hora = datetime.now().isoformat(
            sep=" ",
            timespec="seconds"
        )

        conexao.execute("""
            UPDATE atualizacoes_etiqueta
            SET status = ?
            WHERE id_atualizacao = ?
              AND status = 'pendente'
        """, (
            "processada_simulada",
            id_atualizacao
        ))

        conexao.commit()

        return jsonify({
            "mensagem": "Atualizacao processada em modo simulado.",
            "id_atualizacao": id_atualizacao,
            "id_etiqueta": atualizacao["id_etiqueta"],
            "novo_preco": atualizacao["novo_preco"],
            "status": "processada_simulada",
            "confirmacao_dispositivo": False,
            "data_processamento": data_hora
        }), 200

    except Exception:
        conexao.rollback()
        app.logger.exception(
            "Erro ao processar atualizacao da etiqueta"
        )

        return jsonify({
            "erro": "Nao foi possivel processar a atualizacao."
        }), 500

    finally:
        conexao.close()

if __name__ == "__main__":
    app.run(debug=True)
