document.addEventListener("DOMContentLoaded", () => {
    configurarNavegacao();
    carregarDashboard();
});

const TITULOS_SECOES = {
    dashboard: "Dashboard",
    produtos: "Produtos",
    estoque: "Estoque",
    vendas: "Vendas",
    etiquetas: "Etiquetas eletrônicas",
    caixa: "Caixa / PDV",
    ia: "Inteligência Artificial"
};

const CONFIGURACOES_SECOES = {
    estoque: {
        url: "/api/estoque",
        destino: "estoque-lista",
        tipo: "estoque"
    },
    vendas: {
        url: "/api/vendas",
        destino: "vendas-lista",
        tipo: "vendas"
    },
    etiquetas: {
        url: "/api/etiquetas/pendentes",
        destino: "etiquetas-lista",
        tipo: "etiquetas",
        campo: "atualizacoes"
    }
};

let pdvProdutos = [];
let pdvCarrinho = [];
let pdvVendaEmAndamento = false;

function configurarNavegacao() {
    const menus = document.querySelectorAll(".menu-item");
    const botaoSidebar = document.getElementById("toggle-sidebar");

    if (botaoSidebar) {
        botaoSidebar.addEventListener("click", () => {
            const escondida = document.body.classList.toggle("sidebar-hidden");

            botaoSidebar.setAttribute("aria-expanded", String(!escondida));
            botaoSidebar.setAttribute(
                "aria-label",
                escondida ? "Abrir menu lateral" : "Fechar menu lateral"
            );
        });
    }

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

            atualizarTexto("page-title", TITULOS_SECOES[secao] || "DynaPrice");

            try {
                if (secao === "ia") {
                    await carregarTelaIA();
                } else if (secao === "caixa") {
                    await pdvInicializar();
                } else if (secao === "dashboard") {
                    await carregarDashboard();
                } else {
                    await carregarSecao(secao);
                }
            } catch (erro) {
                console.error(`Erro ao abrir a seção ${secao}:`, erro);
            }
        });
    });
}

async function buscarDados(url) {
    const resposta = await fetch(url);
    const resultado = await resposta.json().catch(() => null);

    if (!resposta.ok) {
        throw new Error(
            resultado?.erro || `Erro HTTP ${resposta.status}`
        );
    }

    if (resultado === null) {
        throw new Error("O servidor retornou uma resposta inválida.");
    }

    return resultado;
}

async function enviarDados(url, metodo, dados) {
    const resposta = await fetch(url, {
        method: metodo,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(dados)
    });

    const resultado = await resposta.json().catch(() => ({}));

    if (!resposta.ok) {
        throw new Error(
            resultado.erro || "Não foi possível concluir a operação."
        );
    }

    return resultado;
}

function atualizarTexto(id, valor) {
    const elemento = document.getElementById(id);
    if (elemento) elemento.textContent = valor;
}

function obterValor(objeto, campos, padrao = "—") {
    for (const campo of campos) {
        if (objeto?.[campo] !== undefined && objeto[campo] !== null) {
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

function criarElemento(tag, classe = "", texto) {
    const elemento = document.createElement(tag);

    if (classe) elemento.className = classe;
    if (texto !== undefined) elemento.textContent = texto;

    return elemento;
}

function obterLista(resposta, campo = null) {
    if (Array.isArray(resposta)) return resposta;
    if (campo && Array.isArray(resposta?.[campo])) return resposta[campo];
    return [];
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

        const produtos = obterLista(produtosResposta, "produtos");
        const vendas = obterLista(vendasResposta, "vendas");

        atualizarTexto("total-produtos", produtos.length);
        atualizarTexto("total-vendas", vendas.length);
        atualizarTexto(
            "estoque-baixo",
            obterValor(
                estoque,
                ["quantidade_produtos"],
                obterLista(estoque, "produtos").length
            )
        );
        atualizarTexto(
            "etiquetas-pendentes",
            obterValor(
                etiquetas,
                ["quantidade_pendentes"],
                obterLista(etiquetas, "atualizacoes").length
            )
        );

        renderizarGraficoVendas(vendas);
        renderizarAlertasDashboard(estoque, etiquetas);
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
        if (lista) lista.textContent = "Não foi possível carregar os produtos.";
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

        informacoes.append(
            criarElemento(
                "div",
                "product-name",
                produto.nome || "Produto sem nome"
            ),
            criarElemento(
                "div",
                "product-code",
                `Código: ${produto.codigo_barras || "Não informado"}`
            )
        );

        linha.append(
            informacoes,
            criarElemento(
                "div",
                "product-price",
                formatarPreco(produto.preco_atual)
            )
        );

        lista.appendChild(linha);
    });
}

async function carregarSecao(secao) {
    if (secao === "produtos") {
        await carregarProdutosCompletos();
        return;
    }

    const config = CONFIGURACOES_SECOES[secao];
    if (!config) return;

    const destino = document.getElementById(config.destino);
    if (!destino) return;

    destino.textContent = "Carregando dados...";

    try {
        const resposta = await buscarDados(config.url);
        const registros = obterLista(resposta, config.campo);

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
        tentarNovamente.addEventListener(
            "click",
            carregarProdutosCompletos
        );

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

    if (filtroCategoria) {
        const categoriaAnterior = filtroCategoria.value;
        const categorias = [...new Set(
            produtos
                .map((produto) => String(produto.categoria || "").trim())
                .filter(Boolean)
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

        filtroCategoria.value = categorias.includes(categoriaAnterior)
            ? categoriaAnterior
            : "";
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
                !categoriaSelecionada || categoria === categoriaSelecionada;

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
            mostrarFormularioProduto(formularioArea, produto, atualizarDados);
        });
    }

    async function atualizarDados() {
        await carregarProdutosCompletos();
        await carregarDashboard();
    }

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
            mostrarFormularioProduto(formularioArea, null, atualizarDados);
        };
    }

    atualizarTabela();
}

function renderizarTabelaProdutos(destino, produtos, aoEditar) {
    destino.replaceChildren();

    destino.appendChild(
        criarElemento(
            "p",
            "products-count",
            `${produtos.length} produto(s) encontrado(s)`
        )
    );

    if (!produtos.length) {
        destino.appendChild(
            criarElemento("p", "empty-message", "Nenhum produto encontrado.")
        );
        return;
    }

    const tabela = criarElemento("table", "products-table");
    const cabecalho = criarElemento("thead");
    const linhaCabecalho = criarElemento("tr");
    const corpo = criarElemento("tbody");

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

    produtos.forEach((produto) => {
        const linha = criarElemento("tr");
        const estoque = Number(produto.estoque_atual);
        const celulaEstoque = criarElemento(
            "td",
            Number.isFinite(estoque) && estoque <= 5 ? "stock-low" : "",
            Number.isFinite(estoque) ? String(estoque) : "—"
        );

        linha.append(
            criarElemento("td", "", produto.nome || "—"),
            criarElemento("td", "", produto.codigo_barras || "—"),
            criarElemento("td", "", produto.categoria || "Sem categoria"),
            criarElemento("td", "", formatarPreco(produto.preco_atual)),
            celulaEstoque
        );

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
    const campoEstoque = criarCampoFormulario(
        "Estoque atual",
        "estoque_atual",
        produto?.estoque_atual ?? "",
        "number",
        true
    );

    campoPreco.input.min = "0";
    campoPreco.input.step = "0.01";
    campoEstoque.input.min = "0";
    campoEstoque.input.step = "1";

    if (editando) campoCodigo.input.readOnly = true;

    const botoes = criarElemento("div", "form-actions");
    const salvar = criarElemento(
        "button",
        "btn-primary",
        editando ? "Salvar alterações" : "Cadastrar produto"
    );
    const cancelar = criarElemento("button", "btn-secondary", "Cancelar");

    salvar.type = "submit";
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

        if (!codigo || !nome || !precoTexto || !estoqueTexto) {
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
    const input = criarElemento("input", "form-input");

    container.appendChild(criarElemento("span", "", rotulo));

    input.name = nome;
    input.type = tipo;
    input.value = valor;
    input.required = obrigatorio;

    if (tipo === "text") input.autocomplete = "off";

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
        const grupo = criarElemento("div", "data-row-group");
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
            informacoes.append(nome, detalhes);
            linha.append(informacoes, valor);
        } else if (tipo === "vendas") {
            renderizarRegistroVenda(
                grupo,
                linha,
                informacoes,
                nome,
                detalhes,
                valor,
                registro
            );
            destino.appendChild(grupo);
            return;
        } else {
            nome.textContent =
                registro.identificador ||
                `Etiqueta #${registro.id_etiqueta ?? "—"}`;
            detalhes.textContent =
                `Produto: ${registro.nome_produto || registro.codigo_barras || "Não informado"}`;
            valor.textContent =
                `${formatarPreco(registro.novo_preco)} · ${registro.status || "Pendente"}`;
            informacoes.append(nome, detalhes);
            linha.append(informacoes, valor);
        }

        grupo.appendChild(linha);
        destino.appendChild(grupo);
    });
}

function renderizarRegistroVenda(
    grupo,
    linha,
    informacoes,
    nome,
    detalhes,
    valor,
    registro
) {
    const status = String(registro.status || "ATIVA").toUpperCase();

    nome.textContent = `Venda #${registro.id_venda ?? "—"}`;
    detalhes.textContent =
        `Data: ${registro.data_hora || "Não informada"} · Status: ${status}`;
    valor.textContent = formatarPreco(registro.valor_total);
    informacoes.append(nome, detalhes);

    const acoes = criarElemento("div", "data-actions");
    const botaoDetalhes = criarElemento(
        "button",
        "btn-secondary",
        "Ver detalhes"
    );
    const painelDetalhes = criarElemento("div", "sale-details");

    botaoDetalhes.type = "button";
    painelDetalhes.hidden = true;

    botaoDetalhes.addEventListener("click", async () => {
        if (!painelDetalhes.hidden) {
            painelDetalhes.hidden = true;
            botaoDetalhes.textContent = "Ver detalhes";
            return;
        }

        painelDetalhes.hidden = false;
        botaoDetalhes.textContent = "Ocultar detalhes";

        if (!painelDetalhes.dataset.carregado) {
            await carregarDetalhesVenda(registro.id_venda, painelDetalhes);
        }
    });

    acoes.appendChild(botaoDetalhes);

    if (status === "ATIVA" && registro.id_venda != null) {
        const botaoCancelar = criarElemento(
            "button",
            "btn-secondary",
            "Cancelar venda"
        );

        botaoCancelar.type = "button";
        botaoCancelar.addEventListener("click", async () => {
            const confirmar = window.confirm(
                `Deseja realmente cancelar a venda #${registro.id_venda}? O estoque será restaurado.`
            );

            if (!confirmar) return;

            botaoCancelar.disabled = true;
            botaoCancelar.textContent = "Cancelando...";

            try {
                await enviarDados(
                    `/api/vendas/${encodeURIComponent(registro.id_venda)}/cancelar`,
                    "POST",
                    {}
                );

                alert("Venda cancelada com sucesso!");
                await carregarSecao("vendas");
                await carregarDashboard();
            } catch (erro) {
                console.error("Erro ao cancelar venda:", erro);
                alert(`Não foi possível cancelar a venda: ${erro.message}`);
                botaoCancelar.disabled = false;
                botaoCancelar.textContent = "Cancelar venda";
            }
        });

        acoes.appendChild(botaoCancelar);
    }

    linha.append(informacoes, valor, acoes);
    grupo.append(linha, painelDetalhes);
}

async function carregarDetalhesVenda(idVenda, painel) {
    painel.replaceChildren();
    painel.appendChild(
        criarElemento("p", "", "Carregando detalhes da venda...")
    );

    try {
        const venda = await buscarDados(
            `/api/vendas/${encodeURIComponent(idVenda)}`
        );

        painel.replaceChildren();

        const titulo = criarElemento("h3", "", "Detalhes da venda");
        const informacoes = criarElemento("div", "sale-info");

        informacoes.append(
            criarElemento("p", "", `Venda: #${venda.id_venda}`),
            criarElemento(
                "p",
                "",
                `Data: ${venda.data_hora || "Não informada"}`
            ),
            criarElemento("p", "", `Status: ${venda.status || "—"}`)
        );

        if (venda.data_hora_cancelamento) {
            informacoes.appendChild(
                criarElemento(
                    "p",
                    "",
                    `Cancelamento: ${venda.data_hora_cancelamento}`
                )
            );
        }

        if (venda.motivo_cancelamento) {
            informacoes.appendChild(
                criarElemento(
                    "p",
                    "",
                    `Motivo: ${venda.motivo_cancelamento}`
                )
            );
        }

        const tituloItens = criarElemento("h4", "", "Produtos vendidos");
        const listaItens = criarElemento("div", "sale-items");

        if (Array.isArray(venda.itens) && venda.itens.length) {
            venda.itens.forEach((item) => {
                const linhaItem = criarElemento("div", "sale-item");

                linhaItem.append(
                    criarElemento(
                        "strong",
                        "",
                        item.nome || "Produto sem nome"
                    ),
                    criarElemento(
                        "p",
                        "",
                        `Código: ${item.codigo_barras || "—"}`
                    ),
                    criarElemento("p", "", `Quantidade: ${item.quantidade}`),
                    criarElemento(
                        "p",
                        "",
                        `Preço unitário: ${formatarPreco(item.preco_unitario)}`
                    ),
                    criarElemento(
                        "p",
                        "",
                        `Subtotal: ${formatarPreco(item.subtotal)}`
                    )
                );

                listaItens.appendChild(linhaItem);
            });
        } else {
            listaItens.textContent = "Nenhum item encontrado nesta venda.";
        }

        painel.append(
            titulo,
            informacoes,
            tituloItens,
            listaItens,
            criarElemento(
                "h3",
                "sale-total",
                `Total da venda: ${formatarPreco(venda.valor_total)}`
            )
        );

        painel.dataset.carregado = "1";
    } catch (erro) {
        console.error("Erro ao carregar detalhes da venda:", erro);
        painel.replaceChildren();
        painel.appendChild(
            criarElemento(
                "p",
                "error-message",
                `Não foi possível carregar os detalhes: ${erro.message}`
            )
        );
    }
}

function renderizarGraficoVendas(vendas) {
    const vendasAtivas = vendas.filter((venda) => {
        return String(venda.status || "ATIVA").toUpperCase() === "ATIVA";
    });

    const total = vendasAtivas.reduce(
        (soma, venda) => soma + (Number(venda.valor_total) || 0),
        0
    );

    atualizarTexto("faturamento-total", formatarPreco(total));
    atualizarTexto(
        "ticket-medio",
        formatarPreco(vendasAtivas.length ? total / vendasAtivas.length : 0)
    );

    const canvas = document.getElementById("grafico-vendas");
    const mensagem = document.getElementById("grafico-vendas-mensagem");

    if (!canvas) return;

    const contexto = canvas.getContext("2d");
    if (!contexto) {
        if (mensagem) mensagem.textContent = "Não foi possível desenhar o gráfico.";
        return;
    }

    const porDia = {};

    vendasAtivas.forEach((venda) => {
        if (!venda.data_hora) return;

        const data = new Date(venda.data_hora);
        if (Number.isNaN(data.getTime())) return;

        const chave = [
            data.getFullYear(),
            String(data.getMonth() + 1).padStart(2, "0"),
            String(data.getDate()).padStart(2, "0")
        ].join("-");

        porDia[chave] =
            (porDia[chave] || 0) + (Number(venda.valor_total) || 0);
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
        contexto.fillText("Sem dados disponíveis", largura / 2, altura / 2);
        return;
    }

    const valores = dias.map((dia) => porDia[dia]);
    const maiorValor = Math.max(...valores, 1);

    contexto.font = "10px Segoe UI, Arial";
    contexto.textAlign = "right";

    for (let indice = 0; indice <= 4; indice++) {
        const y = margem.topo + areaAltura * indice / 4;
        const valor = maiorValor * (4 - indice) / 4;

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
        const y = margem.topo + areaAltura * (1 - valor / maiorValor);

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

        const [ano, mes, dia] = dias[indice].split("-");
        contexto.fillText(`${dia}/${mes}`, ponto.x, altura - 10);
    });
}

function renderizarAlertasDashboard(estoque, etiquetas) {
    const destino = document.getElementById("alertas-dashboard");
    if (!destino) return;

    destino.replaceChildren();

    const produtosBaixos = obterLista(estoque, "produtos");
    const pendentes = obterLista(etiquetas, "atualizacoes");
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

        informacoes.append(
            criarElemento("strong", "", "Nenhum alerta encontrado"),
            criarElemento(
                "p",
                "",
                "Não foram encontrados alertas nas consultas realizadas."
            )
        );

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

        informacoes.append(
            criarElemento("strong", "", alerta.titulo),
            criarElemento("p", "", alerta.descricao)
        );

        linha.append(icone, informacoes);
        destino.appendChild(linha);
    });
}

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
                (item) => String(item.codigo_barras) === codigo
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
        pdvProdutos = obterLista(resposta, "produtos");
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
            `Código: ${produto.codigo_barras || "—"} · ${pdvMoeda(produto.preco_atual)} · Estoque: ${produto.estoque_atual ?? "—"}`
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
        (item) => item.codigo_barras === codigo
    );
    const quantidadeAtual = existente ? existente.quantidade : 0;

    if (!Number.isInteger(estoque) || estoque <= quantidadeAtual) {
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
        const mais = criarElemento("button", "secondary-button", "+");
        const remover = criarElemento("button", "secondary-button", "Remover");

        menos.type = "button";
        menos.setAttribute("aria-label", `Diminuir ${item.nome}`);
        menos.addEventListener("click", () => {
            if (item.quantidade > 1) {
                item.quantidade--;
            } else {
                pdvCarrinho = pdvCarrinho.filter((outro) => outro !== item);
            }

            pdvMostrarCarrinho();
        });

        mais.type = "button";
        mais.disabled = item.quantidade >= item.estoque;
        mais.setAttribute("aria-label", `Aumentar ${item.nome}`);
        mais.addEventListener("click", () => {
            if (item.quantidade < item.estoque) {
                item.quantidade++;
                pdvMostrarCarrinho();
            }
        });

        remover.type = "button";
        remover.addEventListener("click", () => {
            pdvCarrinho = pdvCarrinho.filter((outro) => outro !== item);
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
            itens: pdvCarrinho.map((item) => ({
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
        pdvMensagem(`Não foi possível concluir a venda: ${erro.message}`);
    } finally {
        pdvVendaEmAndamento = false;
        pdvMostrarCarrinho();
    }
}


// Inteligência Artificial: análise sob demanda, sem atualização automática de preços.
async function carregarTelaIA() {
    const seletor = document.getElementById("ia-produto");
    const botao = document.getElementById("ia-analisar");
    const mensagem = document.getElementById("ia-mensagem");
    if (!seletor || !botao || !mensagem) return;

    mensagem.textContent = "Carregando produtos...";
    botao.disabled = true;
    try {
        const resposta = await buscarDados("/api/produtos");
        const produtos = obterLista(resposta, "produtos");
        const selecaoAnterior = seletor.value;
        seletor.replaceChildren();
        const inicial = document.createElement("option");
        inicial.value = "";
        inicial.textContent = "Selecione um produto";
        seletor.appendChild(inicial);
        for (const produto of produtos) {
            const opcao = document.createElement("option");
            opcao.value = String(produto.id_produto);
            opcao.textContent = `${produto.nome} — ${formatarPreco(produto.preco_atual)}`;
            seletor.appendChild(opcao);
        }
        if (produtos.some(p => String(p.id_produto) === selecaoAnterior)) {
            seletor.value = selecaoAnterior;
        }
        mensagem.textContent = produtos.length
            ? "Escolha um produto e clique em Analisar com IA."
            : "Nenhum produto ativo encontrado.";
        botao.disabled = !produtos.length;
    } catch (erro) {
        mensagem.textContent = `Erro ao carregar produtos: ${erro.message}`;
    }

    if (!botao.dataset.iaConfigurada) {
        botao.addEventListener("click", analisarProdutoIA);
        botao.dataset.iaConfigurada = "1";
    }
    await inicializarHistoricoIA();
}

async function analisarProdutoIA() {
    const seletor = document.getElementById("ia-produto");
    const botao = document.getElementById("ia-analisar");
    const mensagem = document.getElementById("ia-mensagem");
    const resultado = document.getElementById("ia-resultado");
    const id = Number(seletor?.value);
    if (!Number.isInteger(id) || id <= 0) {
        mensagem.textContent = "Selecione um produto válido.";
        return;
    }

    botao.disabled = true;
    resultado.hidden = true;
    document.getElementById("ia-decisao").hidden = true;
    mensagem.textContent = "Analisando produto...";
    try {
        const dados = await enviarDados(`/api/ia/produtos/${id}/analisar`, "POST", {});
        atualizarTexto("ia-preco-atual", formatarPreco(dados.preco_atual));
        atualizarTexto("ia-preco-sugerido", formatarPreco(dados.preco_sugerido));
        atualizarTexto("ia-demanda", `${dados.demanda_prevista} unidade(s)`);
        atualizarTexto("ia-confianca", `${(Number(dados.confianca) * 100).toFixed(0)}%`);
        atualizarTexto("ia-variacao", `${Number(dados.variacao_percentual).toFixed(2)}%`);
        atualizarTexto("ia-situacao", String(dados.situacao ?? "—").replaceAll("_", " "));
        atualizarTexto("ia-motivo", dados.motivo ?? "Sem justificativa disponível.");
        atualizarTexto("ia-id-analise", dados.id_analise ?? "—");
        resultado.hidden = false;
        configurarDecisaoIA(dados);
        mensagem.textContent = "Análise concluída. Nenhum preço foi alterado.";
        await carregarHistoricoIA();
    } catch (erro) {
        mensagem.textContent = `Não foi possível analisar: ${erro.message}`;
    } finally {
        botao.disabled = false;
    }
}


let historicoIAInicializado = false;

async function inicializarHistoricoIA() {
    const filtro = document.getElementById("ia-filtro-historico");
    const atualizar = document.getElementById("ia-atualizar-historico");
    if (!filtro || !atualizar) return;

    if (!historicoIAInicializado) {
        filtro.addEventListener("change", carregarHistoricoIA);
        atualizar.addEventListener("click", carregarHistoricoIA);
        historicoIAInicializado = true;
    }

    try {
        const resposta = await buscarDados("/api/produtos");
        const produtos = obterLista(resposta, "produtos");
        const selecionado = filtro.value;
        filtro.replaceChildren();
        const todos = document.createElement("option");
        todos.value = "";
        todos.textContent = "Todos os produtos";
        filtro.appendChild(todos);

        for (const produto of produtos) {
            const opcao = document.createElement("option");
            opcao.value = String(produto.id_produto);
            opcao.textContent = produto.nome;
            filtro.appendChild(opcao);
        }
        if (produtos.some(produto => String(produto.id_produto) === selecionado)) {
            filtro.value = selecionado;
        }
    } catch (erro) {
        console.error("Erro ao carregar filtro do histórico:", erro);
    }
    await carregarHistoricoIA();
}

async function carregarHistoricoIA() {
    const filtro = document.getElementById("ia-filtro-historico");
    const corpo = document.getElementById("ia-historico-corpo");
    const mensagem = document.getElementById("ia-historico-mensagem");
    if (!corpo || !mensagem) return;

    mensagem.textContent = "Carregando histórico...";
    corpo.replaceChildren();

    try {
        const parametros = new URLSearchParams();
        if (filtro?.value) parametros.set("id_produto", filtro.value);
        const url = "/api/ia/historico" + (parametros.size ? `?${parametros}` : "");
        const registros = await buscarDados(url);
        if (!Array.isArray(registros)) throw new Error("Formato de resposta inválido.");

        if (registros.length === 0) {
            const celula = corpo.insertRow().insertCell();
            celula.colSpan = 7;
            celula.textContent = "Nenhuma análise encontrada.";
        }

        for (const registro of registros) {
            const linha = corpo.insertRow();
            let data = "—";
            if (registro.data_hora) {
                const instante = new Date(String(registro.data_hora).replace(" ", "T") + "Z");
                data = Number.isNaN(instante.getTime())
                    ? String(registro.data_hora)
                    : instante.toLocaleString("pt-BR");
            }
            const confianca = registro.confianca == null
                ? "—"
                : `${(Number(registro.confianca) * 100).toFixed(0)}%`;
            const preco = valor => valor == null ? "—" : formatarPreco(valor);
            const valores = [
                data,
                registro.produto,
                registro.demanda,
                preco(registro.preco_analisado),
                preco(registro.preco_recomendado),
                confianca,
                registro.decisao === "APROVADA" ? "Aprovada" : registro.decisao === "REJEITADA" ? "Rejeitada" : "Pendente"
            ];
            for (const valor of valores) {
                linha.insertCell().textContent = String(valor ?? "—");
            }
        }
        mensagem.textContent = `${registros.length} análise(s) encontrada(s).`;
    } catch (erro) {
        mensagem.textContent = `Erro ao carregar histórico: ${erro.message}`;
    }
}


let analiseAtualIA = null;

function configurarDecisaoIA(dados) {
    const painel = document.getElementById("ia-decisao");
    const aprovar = document.getElementById("ia-aprovar");
    const rejeitar = document.getElementById("ia-rejeitar");
    const status = document.getElementById("ia-decisao-status");
    if (!painel || !aprovar || !rejeitar || !status) return;

    analiseAtualIA = dados;
    painel.hidden = false;
    status.textContent = "A aprovação altera o preço cadastrado e pode gerar uma atualização de etiqueta.";
    const valido = Number.isInteger(Number(dados.id_analise)) && Number(dados.id_analise) > 0;
    const diferente = Math.round(Number(dados.preco_atual) * 100) !== Math.round(Number(dados.preco_sugerido) * 100);
    aprovar.disabled = !valido || !diferente;
    rejeitar.disabled = !valido;
    if (!diferente) status.textContent = "Preço sugerido igual ao atual. Não há alteração para aprovar.";

    aprovar.onclick = () => decidirPrecoIA("aprovar");
    rejeitar.onclick = () => decidirPrecoIA("rejeitar");
}

async function decidirPrecoIA(acao) {
    if (!analiseAtualIA) return;
    const id = Number(analiseAtualIA.id_analise);
    const aprovar = document.getElementById("ia-aprovar");
    const rejeitar = document.getElementById("ia-rejeitar");
    const status = document.getElementById("ia-decisao-status");
    const descricao = acao === "aprovar"
        ? `Confirmar a alteração do preço de ${formatarPreco(analiseAtualIA.preco_atual)} para ${formatarPreco(analiseAtualIA.preco_sugerido)}?`
        : "Confirmar a rejeição desta recomendação?";
    if (!window.confirm(descricao)) return;
    aprovar.disabled = true;
    rejeitar.disabled = true;
    status.textContent = "Registrando decisão...";
    try {
        const resposta = await enviarDados(`/api/ia/analises/${id}/${acao}`, "POST", {});
        status.textContent =
            resposta.mensagem || "Decisão registrada.";

        const painelDecisao = document.getElementById("ia-decisao");

        if (painelDecisao) {
            painelDecisao.hidden = true;
        }

        analiseAtualIA = null;

        await carregarHistoricoIA();
        if (acao === "aprovar") {
            await carregarTelaIA();
        }
    } catch (erro) {
        status.textContent = `Não foi possível registrar a decisão: ${erro.message}`;
        aprovar.disabled = acao === "aprovar" && Math.round(Number(analiseAtualIA.preco_atual) * 100) === Math.round(Number(analiseAtualIA.preco_sugerido) * 100);
        rejeitar.disabled = false;
    }
}
