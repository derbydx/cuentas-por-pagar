document.addEventListener("DOMContentLoaded", function () {
  const metodoPago = document.getElementById("metodo");
  const camposCheque = document.getElementById("campos-cheque");

  if (!metodoPago || !camposCheque) {
    return;
  }

  function actualizarCamposCheque() {
    const esCheque = metodoPago.value === "Cheque";
    camposCheque.style.display = esCheque ? "" : "none";
    camposCheque.querySelectorAll("input, select").forEach(function (campo) {
      campo.required = esCheque;
    });
  }

  metodoPago.addEventListener("change", actualizarCamposCheque);
  actualizarCamposCheque();
});
