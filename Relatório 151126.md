# DynaPrice — Frontend e Backend Flask (`app.py`)

Resumo rápido da implementação do painel web e das rotas Flask. Este documento descreve a versão do frontend com **Caixa Rápido, atalhos e gráficos** e o `app.py` enviado ao projeto.

> ⚠️ **O DynaPrice é um sistema em desenvolvimento.** As vendas e o estoque são gravados no SQLite real configurado em `database.py`. As etiquetas eletrônicas são **simuladas** no backend: processar uma atualização não significa que um dispositivo físico recebeu o novo preço. O módulo de IA é separado e pode utilizar um modelo treinado com dados simulados.

---

## 1. O que foi desenvolvido

Foi criado um **painel de gestão e ponto de venda (PDV)** acessado pelo navegador, usando **HTML, CSS e JavaScript** no frontend e **Python + Flask + SQLite** no backend.

O sistema reúne as seguintes telas:

| Tela | O que faz |
| --- | --- |
| **Dashboard** | Mostra indicadores de vendas, alertas de estoque e etiquetas, gráfico de faturamento e produtos mais vendidos. |
| **Produtos** | Lista e permite cadastrar/editar produtos e seus preços. |
| **Estoque** | Consulta as quantidades disponíveis e os produtos com estoque baixo. |
| **Vendas** | Consulta vendas registradas, detalhes e cancelamento. |
| **Etiquetas** | Consulta etiquetas e atualizações de preço pendentes. |
| **Caixa / PDV** | Busca produtos, monta carrinho, valida quantidades e registra vendas. |
| **Inteligência Artificial** | Solicita sugestões de preço, consulta histórico e interage com o fluxo de aprovação. |

### Como o frontend funciona

1. O Flask entrega a página `templates/index.html` pela rota `GET /`.
2. O navegador carrega os estilos de `static/css/style.css` e os scripts de `static/js/`.
3. O JavaScript identifica a tela selecionada no menu lateral e consulta as APIs do Flask com `fetch`.
4. O Flask consulta ou altera o banco SQLite por meio da função `conectar()` de `database.py`.
5. O backend devolve dados em **JSON** e o JavaScript atualiza a tela sem precisar recarregar a página inteira.

### Caixa / PDV

1. O operador pesquisa um produto por nome ou código de barras.
2. Adiciona produtos ao carrinho e ajusta as quantidades.
3. O frontend mostra subtotais e total da compra.
4. Ao finalizar, o frontend envia os itens para `POST /api/vendas`.
5. **O backend consulta novamente os preços e estoques no banco**, valida os itens, grava a venda e seus itens e desconta as quantidades do estoque em uma única transação.
6. O frontend apresenta a confirmação e permite imprimir um **comprovante não fiscal**.

O frontend apresenta opções de pagamento, como dinheiro, PIX, débito e crédito, e calcula troco para pagamento em dinheiro. **A forma de pagamento não é persistida na tabela de vendas pelo `app.py` atual.** Não há integração bancária ou emissão de documento fiscal.

### Modo Caixa Rápido

É uma apresentação ampliada do mesmo PDV, para agilizar a operação. O botão **Ativar Caixa Rápido** altera a aparência da tela, oculta o menu lateral, destaca a área de venda e o total. Ao sair, **o carrinho permanece**.

| Atalho | Ação |
| --- | --- |
| `F2` ou `Alt + Q` | Foca a pesquisa de produtos. |
| `F4` ou `Alt + Enter` | Abre a finalização, se houver condições para finalizar. |
| `Enter` na busca | Aciona a busca/seleção conforme o campo do PDV. |
| `Esc` | Sai do Caixa Rápido quando não existe modal aberto. |

> Em alguns notebooks, `F2` e `F4` exigem a tecla `Fn`. Atalhos com `Alt` podem depender do navegador ou do sistema operacional.

### Gráficos do Dashboard

- **Faturamento ao longo do tempo**, com filtros de **7, 30 ou 90 dias**.
- **Produtos mais vendidos**, calculados a partir dos itens das vendas ativas.
- Desenho dos gráficos em **Canvas** no próprio JavaScript, com interação no gráfico de faturamento.
- Atualização dos dados quando o Dashboard é carregado e após operações relevantes de venda.

**Limitação:** o gráfico de produtos mais vendidos consulta detalhes individuais das vendas por `GET /api/vendas/<id>`. Funciona para um projeto de menor porte, mas pode ficar lento com muitas vendas. Uma futura API SQL agregada seria mais eficiente.

---

## 2. Para o grupo: como o `app.py` funciona

O arquivo `app.py` cria a aplicação Flask, registra o módulo de aprovação de IA e disponibiliza as rotas HTTP que o frontend utiliza.

### Organização das rotas

| Método e rota | Função |
| --- | --- |
| `GET /` | Entrega `index.html`. |
| `GET /termos` | Entrega `termos.html`. |
| `GET /api/saude` | Informa se o servidor está respondendo. |
| `GET /api/produtos` | Lista produtos ativos. |
| `GET /api/produtos/<codigo_barras>` | Busca produto ativo pelo código de barras. |
| `POST /api/produtos` | Cadastra produto. |
| `PUT /api/produtos/<codigo_barras>` | Atualiza nome, categoria, preço ou estoque. |
| `GET /api/produtos/<codigo_barras>/historico-precos` | Consulta histórico de preços. |
| `GET /api/estoque` | Lista estoque dos produtos ativos. |
| `GET /api/estoque/baixo?limite=5` | Lista produtos com estoque igual ou inferior ao limite. |
| `GET /api/vendas` | Lista histórico de vendas. |
| `GET /api/vendas/<id_venda>` | Retorna dados e itens de uma venda. |
| `POST /api/vendas` | Registra uma venda e desconta estoque. |
| `POST /api/vendas/<id_venda>/cancelar` | Cancela venda e devolve estoque. |
| `GET /api/etiquetas` | Lista etiquetas cadastradas. |
| `POST /api/etiquetas` | Cadastra uma etiqueta vinculada a um produto. |
| `GET /api/etiquetas/pendentes` | Lista atualizações de etiqueta pendentes. |
| `POST /api/etiquetas/atualizacoes/<id_atualizacao>/processar` | Simula o processamento de uma atualização. |
| `POST /api/ia/produtos/<id_produto>/analisar` | Solicita análise e recomendação de preço ao módulo de IA. |
| `GET /api/ia/historico` | Consulta histórico de análises da IA. |

As rotas de **aprovação/rejeição de recomendações** são adicionadas pelo `Blueprint` importado de `aprovacao_ia.py`; portanto, **não são definidas diretamente no `app.py`**.

### Registro de venda: proteção dos dados

A rota `POST /api/vendas`:

1. Exige uma lista de itens com código de barras e quantidade inteira positiva.
2. Agrupa produtos repetidos, somando quantidades.
3. Inicia uma transação SQLite com `BEGIN IMMEDIATE`.
4. Confere se os produtos existem, estão ativos e possuem estoque suficiente.
5. Obtém o preço diretamente do banco, não do valor exibido no navegador.
6. Grava a venda em `vendas` e cada item em `itens_venda`.
7. Desconta o estoque em `produtos`.
8. Executa `commit()` se tudo der certo ou `rollback()` se ocorrer um erro.

Isso reduz o risco de vendas incompletas e impede que o navegador determine sozinho o preço cobrado.

### Cancelamento de venda

A rota `POST /api/vendas/<id>/cancelar`:

- Confere se a venda existe e não está cancelada.
- Atualiza seu status para `CANCELADA` e registra data e motivo.
- Devolve ao estoque as quantidades dos itens vendidos.
- Registra o evento na tabela `historico_vendas`.
- Faz tudo na mesma transação SQLite.

**Importante:** cancelar uma venda altera seu status; o histórico continua existindo para consulta e auditoria.

### Alteração de preços e etiquetas

Quando `PUT /api/produtos/<codigo_barras>` recebe um preço diferente do anterior, o backend:

1. Atualiza `produtos.preco_atual`.
2. Grava o preço anterior, o novo e o motivo em `historico_precos`.
3. Localiza as etiquetas vinculadas ao produto.
4. Cria registros em `atualizacoes_etiqueta` com status `pendente`.
5. Marca as etiquetas como `pendente_atualizacao`.

O processamento de etiquetas é **simulado**: o banco passa a registrar o novo preço exibido, mas a resposta inclui `confirmacao_dispositivo: false`. Não há comunicação física com etiquetas implementada nessa rota.

### Integração com a IA

O `app.py` importa `recalcular_preco` de `dynaprice_ia` e passa explicitamente o caminho do banco (`CAMINHO_BANCO`). A rota de análise **solicita uma sugestão**, sem aplicar automaticamente o preço. O fluxo de aprovação é tratado por um módulo separado (`aprovacao_ia`).

---

## 3. Para quem vai integrar ou executar

### Estrutura básica esperada

```text
DynaPrice/
├── app.py
├── database.py
├── dynaprice_BD.db
├── aprovacao_ia.py           # ou módulo equivalente importável
├── dynaprice_ia/             # pacote da IA
├── templates/
│   ├── index.html
│   └── termos.html
└── static/
    ├── css/
    │   └── style.css
    ├── js/
    │   ├── script.js
    │   └── tema.js           # se referenciado pelo HTML
    └── img/
        └── logo.png         # além de outros recursos usados
```

> A estrutura acima mostra os arquivos principais, não necessariamente todos os arquivos do projeto. Os caminhos de scripts, imagens e estilos precisam corresponder aos declarados no HTML.

### Instalação e inicialização

Instale as dependências Python do projeto, incluindo **Flask** e as dependências dos módulos de IA/aprovação. Se existir um `requirements.txt` consolidado:

```bash
python -m pip install -r requirements.txt
```

Inicie o servidor na pasta do projeto:

```bash
python app.py
```

Na configuração padrão de desenvolvimento do Flask, acesse:

```text
http://127.0.0.1:5000/
```

O arquivo `database.py` deve apontar para o banco correto e disponibilizar `conectar` e `CAMINHO_BANCO`. O `app.py` também precisa conseguir importar `aprovacao_ia` e `dynaprice_ia`.

**Atenção:** o `app.py` enviado usa `app.run(debug=True)`, apropriado para desenvolvimento local, **não para exposição pública/produção**.

### Exemplo de comunicação frontend → backend

O JavaScript pode consultar os produtos assim:

```javascript
const resposta = await fetch('/api/produtos');
if (!resposta.ok) throw new Error('Falha ao carregar produtos');
const produtos = await resposta.json();
```

Exemplo do corpo JSON enviado ao registrar uma venda:

```json
{
  "itens": [
    { "codigo_barras": "7890000000001", "quantidade": 2 },
    { "codigo_barras": "7890000000002", "quantidade": 1 }
  ]
}
```

Os códigos são **exemplos ilustrativos**, não produtos confirmados no banco. O backend consulta o preço real de cada produto.

### Testes manuais recomendados

- Abrir cada tela e conferir se os dados aparecem.
- Cadastrar produto, editar preço e verificar histórico/etiqueta pendente.
- Tentar vender quantidade maior que o estoque e conferir o bloqueio.
- Registrar venda e verificar baixa no estoque.
- Cancelar venda e verificar devolução ao estoque e status `CANCELADA`.
- Ativar Caixa Rápido, usar `F2`/`Alt + Q`, `F4`/`Alt + Enter` e sair com `Esc`.
- Confirmar que o carrinho não desaparece ao alternar entre modo normal e rápido.
- Conferir gráficos de 7, 30 e 90 dias e exclusão de vendas canceladas.
- Solicitar análise de IA e conferir que a sugestão não altera o preço antes da aprovação.

---

## 4. Pontos importantes e limitações

1. **Sem login ou permissões no `app.py` mostrado:** não há proteção de rotas por usuário. Isso precisa ser implementado antes de disponibilizar o sistema para múltiplos operadores ou na internet.
2. **Sem abertura/fechamento de caixa:** não há controle de turno, operador ou conferência de caixa implementado nas rotas apresentadas.
3. **Pagamento não registrado no banco:** o frontend oferece opções de pagamento, mas `POST /api/vendas` não recebe nem persiste a forma de pagamento.
4. **Comprovante não fiscal:** imprimir um comprovante pelo navegador não substitui NFC-e, SAT ou outro documento fiscal exigível.
5. **Etiquetas em modo simulado:** não há confirmação de hardware; o processamento altera registros no SQLite.
6. **Desempenho dos gráficos:** o cálculo dos produtos mais vendidos faz várias consultas HTTP a detalhes de vendas. Uma rota agregada no Flask seria melhor em bases grandes.
7. **Dinheiro e precisão:** os valores monetários são tratados como `float` em partes do `app.py`; uma evolução para centavos inteiros ou `Decimal` reduz riscos de arredondamento.
8. **Fuso horário:** o `app.py` registra várias datas com `datetime.now()` (hora local), enquanto `CURRENT_TIMESTAMP` do SQLite usa UTC por padrão. Convém padronizar as datas.
9. **Validação e segurança:** as rotas validam diversos campos e usam parâmetros SQL, mas ainda são necessários testes integrados, autenticação e configuração segura de produção.
10. **Dependência do esquema:** as rotas de cancelamento pressupõem campos como `vendas.status` e a tabela `historico_vendas`. Um banco antigo pode não funcionar com todas as rotas.

---

## 5. Para o grupo decidir

1. **Autenticação:** haverá login de administrador e operador de caixa? Quais telas cada perfil poderá acessar?
2. **Pagamentos:** será necessário registrar forma de pagamento, valor recebido, troco e relatórios por meio de pagamento?
3. **Operação do caixa:** implementar abertura, fechamento, sangria e suprimento?
4. **Etiquetas físicas:** qual hardware e protocolo serão usados para substituir a simulação?
5. **Relatórios:** criar endpoints SQL específicos para gráficos, exportação e histórico de vendas?
6. **Implantação:** o sistema será usado apenas no computador local, na rede da loja ou hospedado na internet?
7. **Banco oficial:** confirmar que todos os integrantes estão usando a mesma versão do `dynaprice_BD.db`.

---

## 6. Arquivos principais da entrega

| Arquivo/pasta | O que é |
| --- | --- |
| `templates/index.html` | Estrutura das telas, menu, formulários, gráficos e PDV. |
| `static/css/style.css` | Layout responsivo, estilos das telas e apresentação do Caixa Rápido. |
| `static/js/script.js` | Navegação, consumo das APIs, gráficos, PDV, carrinho, atalhos e interações com IA. |
| `static/js/tema.js` | Alternância de tema, quando incluída na versão do projeto. |
| `app.py` | Servidor Flask e rotas de produtos, vendas, estoque, etiquetas e IA. |
| `database.py` | Conexão SQLite e localização do arquivo `.db`. |
| `dynaprice_BD.db` | Banco de dados do sistema. |
| `aprovacao_ia.py` | Blueprint separado de aprovação/rejeição de sugestões de IA. |
| `dynaprice_ia/` | Módulo que calcula recomendações de preço; entrega separada. |

### Resumo final

**Frontend:** apresenta as telas e facilita o trabalho do operador. **Backend (`app.py`):** valida as operações, registra vendas, controla estoque e expõe as APIs. **SQLite:** armazena os dados. **Módulo de IA:** calcula sugestões de preço; sua aplicação depende do fluxo de aprovação.

> Este documento é um resumo técnico da implementação analisada, não um certificado de testes de produção. Os recursos devem ser testados em conjunto com o banco e os módulos efetivamente instalados.
