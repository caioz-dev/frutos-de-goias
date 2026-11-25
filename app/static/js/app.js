// JavaScript mínimo, só para conforto. O site funciona sem ele: busca,
// pedido e impressão também funcionam pelo servidor.
// Fica em arquivo separado porque o Content-Security-Policy proíbe
// scripts embutidos no HTML.
(function () {
  "use strict";

  // Remove acentos e deixa minúsculo: "Açaí" -> "acai".
  function normalizar(texto) {
    return texto.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }

  // Filtro instantâneo de sabores: <input data-filtro="#id-da-lista">
  document.querySelectorAll("[data-filtro]").forEach(function (campo) {
    var alvo = document.querySelector(campo.dataset.filtro);
    if (!alvo) return;
    var semResultado = alvo.querySelector("[data-sem-resultado]");

    function aplicar() {
      var termo = normalizar(campo.value.trim());
      var algumVisivel = false;
      alvo.querySelectorAll("[data-categoria]").forEach(function (cat) {
        var visiveis = 0;
        // A categoria inteira aparece se o termo for o começo de uma palavra
        // dela (ex.: "kids", "premium"); senão, compara com o nome do sabor.
        var categoriaBate = !!termo && normalizar(cat.dataset.categoria).split(/\s+/).some(function (p) {
          return p.indexOf(termo) === 0;
        });
        cat.querySelectorAll("[data-nome]").forEach(function (item) {
          var mostra = !termo || categoriaBate || normalizar(item.dataset.nome).indexOf(termo) !== -1;
          item.hidden = !mostra;
          if (mostra) visiveis++;
        });
        cat.hidden = visiveis === 0;
        if (visiveis) algumVisivel = true;
      });
      if (semResultado) semResultado.hidden = algumVisivel;
    }
    campo.addEventListener("input", aplicar);
  });

  // Total de unidades escolhidas no formulário de pedido.
  var form = document.querySelector("[data-form-pedido]");
  if (form) {
    var total = form.querySelector("[data-total]");
    var atualizar = function () {
      var soma = 0;
      form.querySelectorAll("[data-qtd]").forEach(function (c) {
        var n = parseInt(c.value, 10);
        if (n > 0 && n <= 99) soma += n;
      });
      total.textContent = soma;
    };
    form.addEventListener("input", atualizar);
    atualizar();
  }

  // Contador de caracteres das observações.
  document.querySelectorAll("[data-contador]").forEach(function (area) {
    var saida = document.querySelector(area.dataset.contador);
    var max = parseInt(area.getAttribute("maxlength"), 10);
    var atualizar = function () { saida.textContent = area.value.length + " de " + max + " caracteres"; };
    area.addEventListener("input", atualizar);
    atualizar();
  });

  // Botão de imprimir.
  document.querySelectorAll("[data-imprimir]").forEach(function (botao) {
    botao.addEventListener("click", function () { window.print(); });
  });
})();
