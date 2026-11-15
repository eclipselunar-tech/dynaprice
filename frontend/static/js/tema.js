
(() => {
    const chave = "dynaprice-tema";
    const raiz = document.documentElement;
    let tema = "dark";
    try {
        const salvo = localStorage.getItem(chave);
        if (salvo === "light" || salvo === "dark") tema = salvo;
    } catch (_) { }
    raiz.dataset.theme = tema;

    function atualizarBotao() {
        const botao = document.getElementById("theme-toggle");
        if (!botao) return;
        const escuro = raiz.dataset.theme === "dark";
        botao.setAttribute("aria-pressed", String(escuro));
        botao.setAttribute("aria-label", escuro ? "Ativar modo claro" : "Ativar modo escuro");
        botao.title = escuro ? "Ativar modo claro" : "Ativar modo escuro";
        botao.querySelector(".theme-toggle-icon").textContent = escuro ? "☀️" : "🌙";
        botao.querySelector(".theme-toggle-label").textContent = escuro ? "Modo claro" : "Modo escuro";
    }

    document.addEventListener("DOMContentLoaded", () => {
        atualizarBotao();
        const botao = document.getElementById("theme-toggle");
        if (!botao) return;
        botao.addEventListener("click", () => {
            const proximo = raiz.dataset.theme === "dark" ? "light" : "dark";
            raiz.dataset.theme = proximo;
            try { localStorage.setItem(chave, proximo); } catch (_) {}
            atualizarBotao();
        });
    });
})();
