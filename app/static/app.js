// Lógica del frontend: carga de factura, edición de datos extraídos y guardado en Excel.
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const dropZone = $("drop-zone");
  const fileInput = $("file-input");
  const btnBrowse = $("btn-browse");
  const processing = $("processing");
  const resultPanel = $("result");
  const form = $("invoice-form");
  const formErrors = $("form-errors");
  const saveSuccess = $("save-success");

  let currentFile = null;

  // --- Carga de archivo (drag & drop + botón) ---
  btnBrowse.addEventListener("click", (e) => {
    e.stopPropagation();
    fileInput.click();
  });

  dropZone.addEventListener("click", () => fileInput.click());
  dropZone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInput.click();
    }
  });

  ["dragover", "dragenter"].forEach((evt) =>
    dropZone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropZone.classList.add("dragover");
    })
  );
  ["dragleave", "drop"].forEach((evt) =>
    dropZone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropZone.classList.remove("dragover");
    })
  );
  dropZone.addEventListener("drop", (e) => {
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  });
  fileInput.addEventListener("change", () => {
    if (fileInput.files[0]) handleFile(fileInput.files[0]);
  });

  // --- Flujo principal ---
  async function handleFile(file) {
    currentFile = file;
    hide(formErrors);
    hide(saveSuccess);
    dropZone.classList.add("hidden");
    show(processing);

    const data = new FormData();
    data.append("file", file);

    try {
      const res = await fetch("/api/extract", { method: "POST", body: data });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.detail || "Error al procesar el archivo.");
      fillForm(payload.datos);
      hide(processing);
      show(resultPanel);
      resultPanel.scrollIntoView({ behavior: "smooth" });
    } catch (err) {
      hide(processing);
      show(dropZone);
      alert(err.message);
    }
  }

  function fillForm(datos) {
    form.fecha.value = datos.fecha || "";
    form.nit.value = datos.nit || "";
    form.razon_social.value = datos.razon_social || "";
    form.numero_factura.value = datos.numero_factura || "";
    form.subtotal.value = datos.subtotal ?? "";
    form.iva.value = datos.iva ?? "";
    form.total.value = datos.total ?? "";
    form.moneda.value = datos.moneda || "COP";
    renderItems(datos.line_items || []);
  }

  function formToPayload() {
    return {
      fecha: form.fecha.value,
      nit: form.nit.value,
      razon_social: form.razon_social.value,
      numero_factura: form.numero_factura.value,
      subtotal: form.subtotal.value === "" ? null : Number(form.subtotal.value),
      iva: form.iva.value === "" ? null : Number(form.iva.value),
      total: form.total.value === "" ? null : Number(form.total.value),
      moneda: form.moneda.value,
      line_items: readItems(),
    };
  }

  // --- Tabla de productos ---
  const itemsBody = $("items-body");

  function renderItems(items) {
    itemsBody.innerHTML = "";
    items.forEach((item) => addItemRow(item));
    if (items.length === 0) addItemRow(null);
  }

  function addItemRow(item) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><input class="input-producto" data-field="producto" placeholder="Nombre del producto" /></td>
      <td class="num"><input type="number" step="0.01" min="0" data-field="cantidad" /></td>
      <td class="num"><input type="number" step="0.01" min="0" data-field="precio_unitario" /></td>
      <td class="num"><input type="number" step="0.01" min="0" data-field="subtotal" /></td>
      <td class="num"><input type="number" step="0.01" min="0" data-field="iva" /></td>
      <td class="num"><input type="number" step="0.01" min="0" data-field="total" /></td>
      <td><button type="button" class="btn-remove" title="Eliminar">×</button></td>
    `;
    if (item) {
      tr.querySelector('[data-field="producto"]').value = item.producto || "";
      tr.querySelector('[data-field="cantidad"]').value = item.cantidad ?? "";
      tr.querySelector('[data-field="precio_unitario"]').value = item.precio_unitario ?? "";
      tr.querySelector('[data-field="subtotal"]').value = item.subtotal ?? "";
      tr.querySelector('[data-field="iva"]').value = item.iva ?? "";
      tr.querySelector('[data-field="total"]').value = item.total ?? "";
    }
    tr.querySelector(".btn-remove").addEventListener("click", () => {
      tr.remove();
      if (itemsBody.children.length === 0) addItemRow(null);
    });
    itemsBody.appendChild(tr);
  }

  function readItems() {
    const rows = [...itemsBody.querySelectorAll("tr")];
    return rows
      .map((tr) => {
        const val = (field) => {
          const el = tr.querySelector(`[data-field="${field}"]`);
          return el ? el.value.trim() : "";
        };
        return {
          producto: val("producto"),
          cantidad: val("cantidad") === "" ? null : Number(val("cantidad")),
          precio_unitario: val("precio_unitario") === "" ? null : Number(val("precio_unitario")),
          subtotal: val("subtotal") === "" ? null : Number(val("subtotal")),
          iva: val("iva") === "" ? null : Number(val("iva")),
          total: val("total") === "" ? null : Number(val("total")),
        };
      })
      .filter((i) => i.producto !== "" || i.subtotal !== null);
  }

  $("btn-add-item").addEventListener("click", () => {
    const last = itemsBody.querySelector("tr:last-child");
    if (last) {
      const producto = last.querySelector('[data-field="producto"]').value.trim();
      if (producto === "") return; // no agregar si la última fila está vacía
    }
    addItemRow(null);
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    hide(formErrors);
    hide(saveSuccess);

    try {
      const res = await fetch("/api/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ datos: formToPayload() }),
      });
      const payload = await res.json();

      if (!res.ok) {
        if (payload.errores) showErrors(payload.errores);
        else alert(payload.detail || "Error al guardar.");
        return;
      }

      show(saveSuccess);
      saveSuccess.innerHTML =
        "Factura guardada en <strong>" + payload.archivo + "</strong> (fila " + payload.fila + ").";
    } catch (err) {
      alert("No se pudo conectar con el servidor: " + err.message);
    }
  });

  function showErrors(lista) {
    const ul = document.createElement("ul");
    lista.forEach((msg) => {
      const li = document.createElement("li");
      li.textContent = msg;
      ul.appendChild(li);
    });
    formErrors.innerHTML = "";
    formErrors.appendChild(ul);
    show(formErrors);
  }

  $("btn-reset").addEventListener("click", reset);

  function reset() {
    currentFile = null;
    fileInput.value = "";
    form.reset();
    itemsBody.innerHTML = "";
    hide(resultPanel);
    hide(formErrors);
    hide(saveSuccess);
    show(dropZone);
  }

  function show(el) { el.classList.remove("hidden"); }
  function hide(el) { el.classList.add("hidden"); }
})();
