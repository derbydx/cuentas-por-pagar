document.addEventListener("DOMContentLoaded", function () {
  const metodoPago = document.getElementById("metodo");
  const camposCheque = document.getElementById("campos-cheque");

  if (metodoPago && camposCheque) {
    function actualizarCamposCheque() {
      const esCheque = metodoPago.value === "Cheque";
      camposCheque.style.display = esCheque ? "" : "none";
      camposCheque.querySelectorAll("input, select").forEach(function (campo) {
        campo.required = esCheque;
      });
    }

    metodoPago.addEventListener("change", actualizarCamposCheque);
    actualizarCamposCheque();
  }

  document.querySelectorAll("[data-fecha-destino]").forEach(function (selector) {
    selector.addEventListener("change", function () {
      const destino = document.querySelector(
        '[name="' + selector.dataset.fechaDestino + '"]'
      );
      if (destino && selector.value) {
        destino.value = selector.value;
      }
    });
  });
});
