
document.addEventListener("DOMContentLoaded", () => {
    carregarDashboard();

    const menus = document.querySelectorAll(".menu-item");

    menus.forEach((menu) => {
        menu.addEventListener("click", async (evento) => {
            evento.preventDefault();

            const secao = menu.dataset.view;

            if (!secao) return;

            menus.forEach((item) => {
                item.classList.toggle("active", item === menu);
            });

            document.querySelectorAll(".page-view").forEach((view) => {
                view.hidden = view.id !== `${secao}-view`;
            });

const titulos = {
    dashboard: "Dashboard",
    produtos: "Produtos",
    estoque: "Estoque",
    vendas: "Vendas",
    etiquetas: "Etiquetas eletrônicas",
    caixa: "Caixa / PDV"
};

            atualizarTexto("page-title", titulos[secao] || "DynaPrice");

if (secao === "caixa") {
    await pdvInicializar();
}
        });
    });
});

async function buscarDados(url) {
    const resposta = await fetch(url);

    if (!resposta.ok) {
        throw new Error(`Erro HTTP ${resposta.status}`);
    }

    return await resposta.json();
}

async function enviarDados(url, metodo, dados) {
    const resposta = await fetch(url, {
        method: metodo,
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(dados)
    });

    const resultado = await resposta.json();

    if (!resposta.ok) {
        throw new Error(resultado.erro || "Não foi possível concluir a operação.");
    }

    return resultado;
}

function atualizarTexto(id, valor) {
    const elemento = document.getElementById(id);

    if (elemento) {
        elemento.textContent = valor;
    }
}

function obterValor(objeto, campos, padrao = "—") {
    for (const campo of campos) {
        if (
            objeto &&
            objeto[campo] !== undefined &&
            objeto[campo] !== null
        ) {
            return objeto[campo];
        }
    }

    return padrao;
}

function formatarPreco(valor) {
    const preco = Number(valor);

    if (!Number.isFinite(preco)) {
        return "Preço indisponível";
    }

    return preco.toLocaleString("pt-BR", {
        style: "currency",
        currency: "BRL"
    });
}

function criarElemento(tag, classe, texto) {
    const elemento = document.createElement(tag);

    if (classe) elemento.className = classe;
    if (texto !== undefined) elemento.textContent = texto;

    return elemento;
}

async function carregarDashboard() {
    try {
        const [produtosResposta, vendasResposta, estoque, etiquetas] =
            await Promise.all([
                buscarDados("/api/produtos"),
                buscarDados("/api/vendas"),
                buscarDados("/api/estoque/baixo?limite=5"),
                buscarDados("/api/etiquetas/pendentes")
            ]);

        const produtos = Array.isArray(produtosResposta)
            ? produtosResposta
            : produtosResposta.produtos || [];

        const vendas = Array.isArray(vendasResposta)
            ? vendasResposta
            : vendasResposta.vendas || [];

        atualizarTexto("total-produtos", produtos.length);
        atualizarTexto("total-vendas", vendas.length);
        renderizarGraficoVendas(vendas);
        renderizarAlertasDashboard(estoque, etiquetas);

        atualizarTexto(
            "estoque-baixo",
            obterValor(
                estoque,
                ["quantidade_produtos"],
                estoque.produtos?.length ?? 0
            )
        );

        atualizarTexto(
            "etiquetas-pendentes",
            obterValor(
                etiquetas,
                ["quantidade_pendentes"],
                etiquetas.atualizacoes?.length ?? 0
            )
        );

        mostrarProdutos(produtos);

        atualizarTexto("api-status", "Conectado");
        atualizarTexto("status-titulo", "Sistema conectado");
        atualizarTexto(
            "status-descricao",
            "O servidor Flask respondeu corretamente."
        );
    } catch (erro) {
        console.error("Erro ao carregar dashboard:", erro);

        atualizarTexto("api-status", "Sem conexão");
        atualizarTexto("status-titulo", "Falha na conexão");
        atualizarTexto(
            "status-descricao",
            "Não foi possível consultar todos os dados da API."
        );

        const lista = document.getElementById("lista-produtos");

        if (lista) {
            lista.textContent = "Não foi possível carregar os produtos.";
        }
    }
}

function mostrarProdutos(produtos) {
    const lista = document.getElementById("lista-produtos");

    if (!lista) return;

    lista.replaceChildren();

    if (!produtos.length) {
        lista.textContent = "Nenhum produto cadastrado.";
        return;
    }

    produtos.slice(0, 5).forEach((produto) => {
        const linha = criarElemento("div", "product-row");
        const informacoes = criarElemento("div");

        const nome = criarElemento(
            "div",
            "product-name",
            produto.nome || "Produto sem nome"
        );

        const codigo = criarElemento(
            "div",
            "product-code",
            `Código: ${produto.codigo_barras || "Não informado"}`
        );

        const preco = criarElemento(
            "div",
            "product-price",
            formatarPreco(produto.preco_atual)
        );

        informacoes.append(nome, codigo);
        linha.append(informacoes, preco);
        lista.appendChild(linha);
    });
}

async function carregarSecao(secao) {
    if (secao === "produtos") {
        await carregarProdutosCompletos();
        return;
    }

    const configuracoes = {
        estoque: {
            url: "/api/estoque/baixo?limite=5",
            destino: "estoque-lista",
            campos: ["produtos"],
            tipo: "estoque"
        },
        vendas: {
            url: "/api/vendas",
            destino: "vendas-lista",
            campos: ["vendas"],
            tipo: "vendas"
        },
        etiquetas: {
            url: "/api/etiquetas/pendentes",
            destino: "etiquetas-lista",
            campos: ["atualizacoes"],
            tipo: "etiquetas"
        }
    };

    const config = configuracoes[secao];

    if (!config) return;

    const destino = document.getElementById(config.destino);

    if (!destino) return;

    destino.textContent = "Carregando dados...";

    try {
        const resposta = await buscarDados(config.url);
        let registros = Array.isArray(resposta) ? resposta : [];

        if (!Array.isArray(resposta)) {
            for (const campo of config.campos) {
                if (Array.isArray(resposta[campo])) {
                    registros = resposta[campo];
                    break;
                }
            }
        }

        mostrarRegistros(destino, registros, config.tipo);
    } catch (erro) {
        console.error(`Erro ao carregar ${secao}:`, erro);
        destino.textContent =
            "Não foi possível carregar os dados. Verifique a API.";
    }
}

async function carregarProdutosCompletos() {
    const destino = document.getElementById("produtos-lista-completa");

    if (!destino) return;

    destino.textContent = "Carregando produtos...";

    try {
        const produtos = await buscarDados("/api/produtos");

        if (!Array.isArray(produtos)) {
            throw new Error("Formato inesperado na resposta de produtos.");
        }

        renderizarTelaProdutos(destino, produtos);
    } catch (erro) {
        console.error("Erro ao carregar produtos:", erro);
        destino.replaceChildren();

        const mensagem = criarElemento(
            "p",
            "error-message",
            "Não foi possível carregar os produtos."
        );

        const tentarNovamente = criarElemento(
            "button",
            "btn-secondary",
            "Tentar novamente"
        );

        tentarNovamente.type = "button";
        tentarNovamente.addEventListener("click", carregarProdutosCompletos);

        destino.append(mensagem, tentarNovamente);
    }
}


function renderizarTelaProdutos(destino, produtos) {
    destino.replaceChildren();

    const busca = document.getElementById("pesquisa-produtos");
    const filtroCategoria = document.getElementById("filtro-categoria");
    const filtroEstoque = document.getElementById("filtro-estoque");
    const limparFiltros = document.getElementById("limpar-filtros");
    const resultado = document.getElementById("produtos-resultado");
    const formularioArea = criarElemento("div", "product-form-area");
    const tabelaArea = criarElemento("div", "products-table-area");

    destino.append(formularioArea, tabelaArea);

    // Atualiza os indicadores usando todos os produtos carregados.
    atualizarTexto("produtos-total", produtos.length);

    atualizarTexto(
        "produtos-baixo",
        produtos.filter((produto) => {
            const estoque = Number(produto.estoque_atual);
            return Number.isFinite(estoque) && estoque > 0 && estoque <= 5;
        }).length
    );

    atualizarTexto(
        "produtos-zerados",
        produtos.filter((produto) => Number(produto.estoque_atual) === 0).length
    );

    // Preenche as categorias disponíveis sem duplicá-las.
    if (filtroCategoria) {
        const categoriaAnterior = filtroCategoria.value;

        const categorias = [...new Set(
            produtos
                .map((produto) => String(produto.categoria || "").trim())
                .filter((categoria) => categoria !== "")
        )].sort((a, b) => a.localeCompare(b, "pt-BR"));

        filtroCategoria.replaceChildren(
            criarElemento("option", "", "Todas as categorias")
        );
        filtroCategoria.options[0].value = "";

        categorias.forEach((categoria) => {
            const opcao = criarElemento("option", "", categoria);
            opcao.value = categoria;
            filtroCategoria.appendChild(opcao);
        });

        if (categorias.includes(categoriaAnterior)) {
            filtroCategoria.value = categoriaAnterior;
        }
    }

    function atualizarTabela() {
        const termo = (busca?.value || "")
            .trim()
            .toLocaleLowerCase("pt-BR");

        const categoriaSelecionada = filtroCategoria?.value || "";
        const situacaoSelecionada = filtroEstoque?.value || "";

        const filtrados = produtos.filter((produto) => {
            const nome = String(produto.nome || "")
                .toLocaleLowerCase("pt-BR");

            const codigo = String(produto.codigo_barras || "")
                .toLocaleLowerCase("pt-BR");

            const categoria = String(produto.categoria || "").trim();
            const estoque = Number(produto.estoque_atual);

            const correspondePesquisa =
                nome.includes(termo) || codigo.includes(termo);

            const correspondeCategoria =
                !categoriaSelecionada ||
                categoria === categoriaSelecionada;

            let correspondeEstoque = true;

            if (situacaoSelecionada === "zerado") {
                correspondeEstoque = estoque === 0;
            } else if (situacaoSelecionada === "baixo") {
                correspondeEstoque =
                    Number.isFinite(estoque) && estoque > 0 && estoque <= 5;
            } else if (situacaoSelecionada === "normal") {
                correspondeEstoque =
                    Number.isFinite(estoque) && estoque > 5;
            }

            return (
                correspondePesquisa &&
                correspondeCategoria &&
                correspondeEstoque
            );
        });

        if (resultado) {
            resultado.textContent =
                `${filtrados.length} de ${produtos.length} produto(s) exibido(s)`;
        }

        renderizarTabelaProdutos(tabelaArea, filtrados, (produto) => {
            mostrarFormularioProduto(formularioArea, produto, async () => {
                await carregarProdutosCompletos();
                await carregarDashboard();
            });
        });
    }

    // Conecta os controles existentes no HTML.
    if (busca) busca.oninput = atualizarTabela;
    if (filtroCategoria) filtroCategoria.onchange = atualizarTabela;
    if (filtroEstoque) filtroEstoque.onchange = atualizarTabela;

    if (limparFiltros) {
        limparFiltros.onclick = () => {
            if (busca) busca.value = "";
            if (filtroCategoria) filtroCategoria.value = "";
            if (filtroEstoque) filtroEstoque.value = "";

            atualizarTabela();
        };
    }

    const novoProduto = document.getElementById("novo-produto");

    if (novoProduto) {
        novoProduto.onclick = () => {
            mostrarFormularioProduto(formularioArea, null, async () => {
                await carregarProdutosCompletos();
                await carregarDashboard();
            });
        };
    }

    atualizarTabela();
}


function renderizarTabelaProdutos(destino, produtos, aoEditar) {
    destino.replaceChildren();

    const resumo = criarElemento(
        "p",
        "products-count",
        `${produtos.length} produto(s) encontrado(s)`
    );

    destino.appendChild(resumo);

    if (!produtos.length) {
        destino.appendChild(
            criarElemento("p", "empty-message", "Nenhum produto encontrado.")
        );
        return;
    }

    const tabela = criarElemento("table", "products-table");
    const cabecalho = criarElemento("thead");
    const linhaCabecalho = criarElemento("tr");

    [
        "Produto",
        "Código de barras",
        "Categoria",
        "Preço",
        "Estoque",
        "Ações"
    ].forEach((texto) => {
        linhaCabecalho.appendChild(criarElemento("th", "", texto));
    });

    cabecalho.appendChild(linhaCabecalho);

    const corpo = criarElemento("tbody");

    produtos.forEach((produto) => {
        const linha = criarElemento("tr");

        linha.appendChild(criarElemento("td", "", produto.nome || "—"));
        linha.appendChild(
            criarElemento("td", "", produto.codigo_barras || "—")
        );
        linha.appendChild(
            criarElemento("td", "", produto.categoria || "Sem categoria")
        );
        linha.appendChild(
            criarElemento("td", "", formatarPreco(produto.preco_atual))
        );

        const estoque = Number(produto.estoque_atual);
        const celulaEstoque = criarElemento(
            "td",
            estoque <= 5 ? "stock-low" : "",
            Number.isFinite(estoque) ? String(estoque) : "—"
        );

        linha.appendChild(celulaEstoque);

        const celulaAcoes = criarElemento("td");
        const editar = criarElemento("button", "btn-secondary", "Editar");
        editar.type = "button";
        editar.addEventListener("click", () => aoEditar(produto));

        celulaAcoes.appendChild(editar);
        linha.appendChild(celulaAcoes);
        corpo.appendChild(linha);
    });

    tabela.append(cabecalho, corpo);

    const tabelaScroll = criarElemento("div", "table-scroll");
    tabelaScroll.appendChild(tabela);
    destino.appendChild(tabelaScroll);
}

function mostrarFormularioProduto(area, produto, aoSalvar) {
    area.replaceChildren();

    const editando = Boolean(produto);
    const formulario = criarElemento("form", "product-form");
    formulario.noValidate = true;

    const titulo = criarElemento(
        "h3",
        "",
        editando ? "Editar produto" : "Cadastrar produto"
    );

    const aviso = criarElemento("p", "form-message");
    aviso.setAttribute("role", "status");

    const campoCodigo = criarCampoFormulario(
        "Código de barras",
        "codigo_barras",
        produto?.codigo_barras || "",
        "text",
        true
    );

    const campoNome = criarCampoFormulario(
        "Nome do produto",
        "nome",
        produto?.nome || "",
        "text",
        true
    );

    const campoCategoria = criarCampoFormulario(
        "Categoria",
        "categoria",
        produto?.categoria || "",
        "text",
        false
    );

    const campoPreco = criarCampoFormulario(
        "Preço atual (R$)",
        "preco_atual",
        produto?.preco_atual ?? "",
        "number",
        true
    );

    campoPreco.input.min = "0";
    campoPreco.input.step = "0.01";

    const campoEstoque = criarCampoFormulario(
        "Estoque atual",
        "estoque_atual",
        produto?.estoque_atual ?? "",
        "number",
        true
    );

    campoEstoque.input.min = "0";
    campoEstoque.input.step = "1";

    if (editando) {
        campoCodigo.input.readOnly = true;
    }

    const botoes = criarElemento("div", "form-actions");

    const salvar = criarElemento(
        "button",
        "btn-primary",
        editando ? "Salvar alterações" : "Cadastrar produto"
    );
    salvar.type = "submit";

    const cancelar = criarElemento("button", "btn-secondary", "Cancelar");
    cancelar.type = "button";
    cancelar.addEventListener("click", () => area.replaceChildren());

    botoes.append(salvar, cancelar);

    formulario.append(
        titulo,
        aviso,
        campoCodigo.container,
        campoNome.container,
        campoCategoria.container,
        campoPreco.container,
        campoEstoque.container,
        botoes
    );

    formulario.addEventListener("submit", async (evento) => {
        evento.preventDefault();
        aviso.textContent = "";

        const codigo = campoCodigo.input.value.trim();
        const nome = campoNome.input.value.trim();
        const categoria = campoCategoria.input.value.trim();
        const precoTexto = campoPreco.input.value.trim();
        const estoqueTexto = campoEstoque.input.value.trim();

        if (!codigo || !nome || precoTexto === "" || estoqueTexto === "") {
            aviso.textContent = "Preencha todos os campos obrigatórios.";
            return;
        }

        const preco = Number(precoTexto);
        const estoque = Number(estoqueTexto);

        if (!Number.isFinite(preco) || preco < 0) {
            aviso.textContent = "Informe um preço válido e não negativo.";
            return;
        }

        if (!Number.isInteger(estoque) || estoque < 0) {
            aviso.textContent = "O estoque deve ser um inteiro não negativo.";
            return;
        }

        const dados = {
            codigo_barras: codigo,
            nome,
            categoria: categoria || null,
            preco_atual: preco,
            estoque_atual: estoque
        };

        salvar.disabled = true;
        salvar.textContent = "Salvando...";

        try {
            if (editando) {
                delete dados.codigo_barras;

                await enviarDados(
                    `/api/produtos/${encodeURIComponent(produto.codigo_barras)}`,
                    "PUT",
                    dados
                );
            } else {
                await enviarDados("/api/produtos", "POST", dados);
            }

            alert(
                editando
                    ? "Produto atualizado com sucesso!"
                    : "Produto cadastrado com sucesso!"
            );

            area.replaceChildren();
            await aoSalvar();
        } catch (erro) {
            aviso.textContent = erro.message;
        } finally {
            salvar.disabled = false;
            salvar.textContent = editando
                ? "Salvar alterações"
                : "Cadastrar produto";
        }
    });

    area.appendChild(formulario);
    formulario.scrollIntoView({ behavior: "smooth", block: "start" });
}

function criarCampoFormulario(rotulo, nome, valor, tipo, obrigatorio) {
    const container = criarElemento("label", "form-field");
    container.appendChild(criarElemento("span", "", rotulo));

    const input = criarElemento("input", "form-input");
    input.name = nome;
    input.type = tipo;
    input.value = valor;
    input.required = obrigatorio;

    if (tipo === "text") {
        input.autocomplete = "off";
    }

    container.appendChild(input);

    return { container, input };
}

function mostrarRegistros(destino, registros, tipo) {
    destino.replaceChildren();

    if (!registros.length) {
        destino.textContent = "Nenhum registro encontrado.";
        return;
    }

    registros.forEach((registro) => {
        const linha = criarElemento("div", "data-row");
        const informacoes = criarElemento("div");
        const nome = criarElemento("strong");
        const detalhes = criarElemento("div", "data-details");
        const valor = criarElemento("div", "data-value");

        if (tipo === "estoque") {
            nome.textContent = registro.nome || "Produto sem nome";
            detalhes.textContent =
                `Código: ${registro.codigo_barras || "—"} · Categoria: ${registro.categoria || "Sem categoria"}`;
            valor.textContent = `Estoque: ${registro.estoque_atual ?? "—"}`;
        } else if (tipo === "vendas") {
            nome.textContent = `Venda #${registro.id_venda ?? "—"}`;
            detalhes.textContent = `Data: ${registro.data_hora || "Não informada"}`;
            valor.textContent = formatarPreco(registro.valor_total);
        } else {
            nome.textContent = registro.identificador || `Etiqueta #${registro.id_etiqueta ?? "—"}`;
            detalhes.textContent =
                `Produto: ${registro.nome_produto || registro.codigo_barras || "Não informado"}`;
            valor.textContent = `${formatarPreco(registro.novo_preco)} · ${registro.status || "Pendente"}`;
        }

        informacoes.append(nome, detalhes);
        linha.append(informacoes, valor);
        destino.appendChild(linha);
    });
}


function renderizarGraficoVendas(vendas) {
    const canvas = document.getElementById("grafico-vendas");

    if (!canvas) return;

    const contexto = canvas.getContext("2d");
    const mensagem = document.getElementById("grafico-vendas-mensagem");

    const total = vendas.reduce(
        (soma, venda) => soma + (Number(venda.valor_total) || 0),
        0
    );

    atualizarTexto("faturamento-total", formatarPreco(total));
    atualizarTexto(
        "ticket-medio",
        formatarPreco(vendas.length ? total / vendas.length : 0)
    );

    const porDia = {};

    vendas.forEach((venda) => {
        if (!venda.data_hora) return;

        const data = new Date(venda.data_hora);

        if (Number.isNaN(data.getTime())) return;

        const chave = [
            data.getFullYear(),
            String(data.getMonth() + 1).padStart(2, "0"),
            String(data.getDate()).padStart(2, "0")
        ].join("-");

        porDia[chave] = (porDia[chave] || 0) +
            (Number(venda.valor_total) || 0);
    });

    const dias = Object.keys(porDia).sort().slice(-7);

    if (mensagem) {
        mensagem.textContent = dias.length
            ? "Valores agrupados pelas datas das vendas registradas."
            : "Ainda não há vendas com datas válidas para exibir no gráfico.";
    }

    const largura = canvas.clientWidth;
    const altura = canvas.clientHeight;

    if (!largura || !altura) return;

    const escala = window.devicePixelRatio || 1;

    canvas.width = largura * escala;
    canvas.height = altura * escala;

    contexto.setTransform(escala, 0, 0, escala, 0, 0);
    contexto.clearRect(0, 0, largura, altura);

    const margem = { esquerda: 48, direita: 12, topo: 18, baixo: 34 };
    const areaLargura = largura - margem.esquerda - margem.direita;
    const areaAltura = altura - margem.topo - margem.baixo;

    if (!dias.length) {
        contexto.fillStyle = "#8790a3";
        contexto.font = "13px Segoe UI, Arial";
        contexto.textAlign = "center";
        contexto.fillText(
            "Sem dados disponíveis",
            largura / 2,
            altura / 2
        );
        return;
    }

    const valores = dias.map((dia) => porDia[dia]);
    const maiorValor = Math.max(...valores, 1);

    contexto.font = "10px Segoe UI, Arial";
    contexto.textAlign = "right";

    for (let i = 0; i <= 4; i++) {
        const y = margem.topo + areaAltura * i / 4;
        const valor = maiorValor * (4 - i) / 4;

        contexto.strokeStyle = "#e9edf4";
        contexto.lineWidth = 1;
        contexto.beginPath();
        contexto.moveTo(margem.esquerda, y);
        contexto.lineTo(largura - margem.direita, y);
        contexto.stroke();

        contexto.fillStyle = "#8790a3";
        contexto.fillText(
            valor.toLocaleString("pt-BR", {
                notation: "compact",
                maximumFractionDigits: 1
            }),
            margem.esquerda - 8,
            y + 4
        );
    }

    const pontos = valores.map((valor, indice) => {
        const x = dias.length === 1
            ? margem.esquerda + areaLargura / 2
            : margem.esquerda +
              areaLargura * indice / (dias.length - 1);

        const y = margem.topo +
            areaAltura * (1 - valor / maiorValor);

        return { x, y };
    });

    if (pontos.length > 1) {
        contexto.beginPath();
        contexto.moveTo(pontos[0].x, pontos[0].y);

        pontos.slice(1).forEach((ponto) => {
            contexto.lineTo(ponto.x, ponto.y);
        });

        contexto.strokeStyle = "#6558e8";
        contexto.lineWidth = 3;
        contexto.lineJoin = "round";
        contexto.stroke();
    }

    pontos.forEach((ponto, indice) => {
        contexto.beginPath();
        contexto.arc(ponto.x, ponto.y, 4, 0, Math.PI * 2);
        contexto.fillStyle = "#6558e8";
        contexto.fill();

        contexto.fillStyle = "#8790a3";
        contexto.textAlign = "center";

        const partes = dias[indice].split("-");
        contexto.fillText(
            `${partes[2]}/${partes[1]}`,
            ponto.x,
            altura - 10
        );
    });
}

function renderizarAlertasDashboard(estoque, etiquetas) {
    const destino = document.getElementById("alertas-dashboard");

    if (!destino) return;

    destino.replaceChildren();

    const produtosBaixos = Array.isArray(estoque)
        ? estoque
        : estoque.produtos || [];

    const pendentes = Array.isArray(etiquetas)
        ? etiquetas
        : etiquetas.atualizacoes || [];

    const alertas = [];

    if (produtosBaixos.length) {
        alertas.push({
            titulo: `${produtosBaixos.length} produto(s) com estoque baixo`,
            descricao: "Confira a tela Estoque para identificar os produtos.",
            simbolo: "!",
            classe: ""
        });
    }

    if (pendentes.length) {
        alertas.push({
            titulo: `${pendentes.length} atualização(ões) pendente(s)`,
            descricao: "Existem etiquetas aguardando processamento.",
            simbolo: "↻",
            classe: "info"
        });
    }

    if (!alertas.length) {
        const linha = criarElemento("div", "alert-item");
        const icone = criarElemento("div", "alert-icon info", "✓");
        const informacoes = criarElemento("div");
        const titulo = criarElemento("strong", "", "Nenhum alerta encontrado");
        const descricao = criarElemento(
            "p",
            "",
            "Não foram encontrados alertas nas consultas realizadas."
        );

        informacoes.append(titulo, descricao);
        linha.append(icone, informacoes);
        destino.appendChild(linha);
        return;
    }

    alertas.forEach((alerta) => {
        const linha = criarElemento("div", "alert-item");
        const icone = criarElemento(
            "div",
            `alert-icon ${alerta.classe}`,
            alerta.simbolo
        );

        const informacoes = criarElemento("div");
        const titulo = criarElemento("strong", "", alerta.titulo);
        const descricao = criarElemento("p", "", alerta.descricao);

        informacoes.append(titulo, descricao);
        linha.append(icone, informacoes);
        destino.appendChild(linha);
    });
}


let pdvProdutos = [];
let pdvCarrinho = [];
let pdvVendaEmAndamento = false;

function pdvMoeda(valor) {
    return formatarPreco(valor);
}

async function pdvInicializar() {
    const busca = document.getElementById("pdv-busca");
    const limpar = document.getElementById("pdv-limpar");
    const finalizar = document.getElementById("pdv-finalizar");

    if (!busca || !limpar || !finalizar) return;

    if (!busca.dataset.pdvAtivo) {
        busca.dataset.pdvAtivo = "1";

        busca.addEventListener("input", pdvMostrarProdutos);

        busca.addEventListener("keydown", (evento) => {
            if (evento.key !== "Enter") return;

            evento.preventDefault();

            const codigo = busca.value.trim();

            if (!codigo) return;

            const produto = pdvProdutos.find(
                item => String(item.codigo_barras) === codigo
            );

            if (produto) {
                pdvAdicionar(produto);
                busca.value = "";
                pdvMostrarProdutos();
            }
        });

        limpar.addEventListener("click", () => {
            pdvCarrinho = [];
            pdvMensagem("");
            pdvMostrarCarrinho();
        });

        finalizar.addEventListener("click", pdvFinalizarVenda);
    }

    await pdvCarregarProdutos();
    pdvMostrarCarrinho();
    busca.focus();
}

async function pdvCarregarProdutos() {
    const resultados = document.getElementById("pdv-resultados");

    if (!resultados) return;

    resultados.textContent = "Carregando produtos...";

    try {
        const resposta = await buscarDados("/api/produtos");

        pdvProdutos = Array.isArray(resposta)
            ? resposta
            : resposta.produtos || [];

        pdvMostrarProdutos();
    } catch (erro) {
        console.error("Erro ao carregar produtos do PDV:", erro);
        resultados.textContent = "Não foi possível carregar os produtos.";
    }
}

function pdvMostrarProdutos() {
    const resultados = document.getElementById("pdv-resultados");
    const busca = document.getElementById("pdv-busca");

    if (!resultados || !busca) return;

    resultados.replaceChildren();

    const termo = busca.value.trim().toLocaleLowerCase("pt-BR");

    const encontrados = pdvProdutos.filter((produto) => {
        const nome = String(produto.nome || "").toLocaleLowerCase("pt-BR");
        const codigo = String(produto.codigo_barras || "").toLowerCase();

        return nome.includes(termo) || codigo.includes(termo);
    }).slice(0, 30);

    if (!encontrados.length) {
        resultados.textContent = "Nenhum produto encontrado.";
        return;
    }

    encontrados.forEach((produto) => {
        const linha = criarElemento("div", "pdv-product");
        const info = criarElemento("div", "pdv-product-info");
        const nome = criarElemento("strong", "", produto.nome || "Sem nome");

        const detalhe = criarElemento(
            "span",
            "",
            `Código: ${produto.codigo_barras || "—"} · ${pdvMoeda(produto.preco_atual)} · Estoque: ${produto.estoque_atual}`
        );

        const botao = criarElemento("button", "secondary-button", "Adicionar");
        botao.type = "button";
        botao.disabled = Number(produto.estoque_atual) <= 0;

        botao.addEventListener("click", () => pdvAdicionar(produto));

        info.append(nome, detalhe);
        linha.append(info, botao);
        resultados.appendChild(linha);
    });
}

function pdvMensagem(texto) {
    atualizarTexto("pdv-mensagem", texto);
}

function pdvAdicionar(produto) {
    const estoque = Number(produto.estoque_atual);
    const codigo = String(produto.codigo_barras);

    const existente = pdvCarrinho.find(
        item => item.codigo_barras === codigo
    );

    const quantidadeAtual = existente ? existente.quantidade : 0;

    if (quantidadeAtual >= estoque) {
        pdvMensagem("Quantidade maior que o estoque disponível.");
        return;
    }

    if (existente) {
        existente.quantidade++;
    } else {
        pdvCarrinho.push({
            codigo_barras: codigo,
            nome: produto.nome,
            preco: Number(produto.preco_atual),
            estoque,
            quantidade: 1
        });
    }

    pdvMensagem("");
    pdvMostrarCarrinho();
}

function pdvMostrarCarrinho() {
    const area = document.getElementById("pdv-carrinho");

    if (!area) return;

    area.replaceChildren();

    if (!pdvCarrinho.length) {
        area.textContent = "Nenhum produto adicionado.";
    }

    pdvCarrinho.forEach((item) => {
        const linha = criarElemento("div", "pdv-cart-item");
        const info = criarElemento("div", "pdv-product-info");
        const nome = criarElemento("strong", "", item.nome);

        const detalhe = criarElemento(
            "span",
            "",
            `${item.quantidade} × ${pdvMoeda(item.preco)} = ${pdvMoeda(item.quantidade * item.preco)}`
        );

        const acoes = criarElemento("div", "pdv-cart-actions");

        const menos = criarElemento("button", "secondary-button", "−");
        menos.type = "button";
        menos.setAttribute("aria-label", `Diminuir ${item.nome}`);

        menos.addEventListener("click", () => {
            if (item.quantidade > 1) {
                item.quantidade--;
            } else {
                pdvCarrinho = pdvCarrinho.filter(
                    outro => outro !== item
                );
            }

            pdvMostrarCarrinho();
        });

        const mais = criarElemento("button", "secondary-button", "+");
        mais.type = "button";
        mais.disabled = item.quantidade >= item.estoque;
        mais.setAttribute("aria-label", `Aumentar ${item.nome}`);

        mais.addEventListener("click", () => {
            if (item.quantidade < item.estoque) {
                item.quantidade++;
                pdvMostrarCarrinho();
            }
        });

        const remover = criarElemento("button", "secondary-button", "Remover");
        remover.type = "button";

        remover.addEventListener("click", () => {
            pdvCarrinho = pdvCarrinho.filter(
                outro => outro !== item
            );

            pdvMostrarCarrinho();
        });

        info.append(nome, detalhe);
        acoes.append(menos, mais, remover);
        linha.append(info, acoes);
        area.appendChild(linha);
    });

    const total = pdvCarrinho.reduce(
        (soma, item) => soma + item.preco * item.quantidade,
        0
    );

    atualizarTexto("pdv-total", pdvMoeda(total));

    const finalizar = document.getElementById("pdv-finalizar");

    if (finalizar) {
        finalizar.disabled =
            pdvCarrinho.length === 0 || pdvVendaEmAndamento;
    }
}

async function pdvFinalizarVenda() {
    const finalizar = document.getElementById("pdv-finalizar");

    if (pdvVendaEmAndamento || !pdvCarrinho.length) {
        pdvMensagem("Adicione produtos antes de finalizar a venda.");
        return;
    }

    pdvVendaEmAndamento = true;

    if (finalizar) finalizar.disabled = true;

    pdvMensagem("Registrando venda...");

    try {
        const resposta = await enviarDados("/api/vendas", "POST", {
            itens: pdvCarrinho.map(item => ({
                codigo_barras: item.codigo_barras,
                quantidade: item.quantidade
            }))
        });

        pdvCarrinho = [];
        pdvMostrarCarrinho();

        pdvMensagem(
            `Venda #${resposta.id_venda} registrada com sucesso! Total: ${pdvMoeda(resposta.valor_total)}`
        );

        await pdvCarregarProdutos();
        await carregarDashboard();

    } catch (erro) {
        console.error("Erro ao finalizar venda:", erro);

        pdvMensagem(
            `Não foi possível concluir a venda: ${erro.message}`
        );

    } finally {
        pdvVendaEmAndamento = false;
        pdvMostrarCarrinho();
    }
}
