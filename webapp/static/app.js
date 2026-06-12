(function () {
  "use strict";

  // Option metadata is delivered as an inert JSON <script> block (keeps the CSP
  // free of inline-script allowances).
  function readChoices() {
    const el = document.getElementById("ipdf-choices");
    if (!el) return {};
    try {
      return JSON.parse(el.textContent || "{}");
    } catch (_) {
      return {};
    }
  }

  const CHOICES = readChoices();
  const DEFAULTS = CHOICES.defaults || {};

  const $ = (sel) => document.querySelector(sel);

  const dropzone = $("#dropzone");
  const fileInput = $("#file-input");
  const statusEl = $("#status");

  const panel = $("#settings-panel");
  const overlay = $("#overlay");

  const viewUpload = $("#view-upload");
  const viewPaste = $("#view-paste");
  const modeUploadBtn = $("#mode-upload");
  const modePasteBtn = $("#mode-paste");
  const pasteInput = $("#paste-input");
  const pasteConvertBtn = $("#paste-convert");
  const pasteHint = $("#paste-hint");

  const els = {
    preset: $("#opt-preset"),
    theme: $("#opt-theme"),
    font: $("#opt-font"),
    fontSize: $("#opt-font-size"),
    margin: $("#opt-margin"),
    lineHeight: $("#opt-line-height"),
    title: $("#opt-title"),
    hyphenate: $("#opt-hyphenate"),
  };

  // ----------------------------------------------------------------- options
  function fillSelect(select, items, selected) {
    select.innerHTML = "";
    (items || []).forEach((it) => {
      const opt = document.createElement("option");
      opt.value = it.value;
      opt.textContent = it.label;
      if (it.value === selected) opt.selected = true;
      select.appendChild(opt);
    });
  }

  function applyDefaults() {
    fillSelect(els.preset, CHOICES.presets, DEFAULTS.preset);
    fillSelect(els.theme, CHOICES.themes, DEFAULTS.theme);
    fillSelect(els.font, CHOICES.fonts, DEFAULTS.font);
    els.fontSize.value = DEFAULTS.font_size || "";
    els.margin.value = DEFAULTS.margin;
    els.lineHeight.value = DEFAULTS.line_height;
    els.title.value = "";
    els.hyphenate.checked = !!DEFAULTS.hyphenate;
  }

  function currentOptions() {
    return {
      preset: els.preset.value,
      theme: els.theme.value,
      font: els.font.value,
      font_size: els.fontSize.value,
      margin: els.margin.value,
      line_height: els.lineHeight.value,
      title: els.title.value,
      hyphenate: els.hyphenate.checked ? "true" : "false",
    };
  }

  applyDefaults();

  // ----------------------------------------------------------------- panel
  function openPanel() {
    panel.classList.add("open");
    panel.setAttribute("aria-hidden", "false");
    overlay.hidden = false;
  }
  function closePanel() {
    panel.classList.remove("open");
    panel.setAttribute("aria-hidden", "true");
    overlay.hidden = true;
  }
  $("#settings-toggle").addEventListener("click", openPanel);
  $("#settings-close").addEventListener("click", closePanel);
  overlay.addEventListener("click", closePanel);
  $("#reset-defaults").addEventListener("click", applyDefaults);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closePanel();
  });

  // ----------------------------------------------------------------- status
  function setStatus(message, kind) {
    statusEl.hidden = false;
    statusEl.className = "status" + (kind ? " " + kind : "");
    statusEl.textContent = message;
  }
  function setBusy(name) {
    dropzone.classList.add("busy");
    dropzone.querySelector(".dz-inner").innerHTML =
      '<div class="spinner"></div>' +
      '<p class="dz-title">Converting…</p>' +
      '<p class="dz-sub">' + escapeHtml(name) + "</p>";
  }
  function resetDropzone() {
    dropzone.classList.remove("busy");
    dropzone.querySelector(".dz-inner").innerHTML = DROPZONE_HTML;
  }
  const DROPZONE_HTML = dropzone.querySelector(".dz-inner").innerHTML;

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  // ----------------------------------------------------------------- convert
  const ACCEPT = (CHOICES.accept || []).map((s) => s.toLowerCase());

  function hasAllowedExt(name) {
    const lower = name.toLowerCase();
    return ACCEPT.some((ext) => lower.endsWith(ext));
  }

  // Shared submit path for both input modes. `hooks.busy` / `hooks.reset` let
  // each mode show its own progress UI; `fallbackBase` names the download when
  // the server doesn't supply a Content-Disposition filename.
  async function submitConversion(form, fallbackBase, hooks) {
    const opts = currentOptions();
    Object.keys(opts).forEach((k) => form.append(k, opts[k]));

    hooks.busy();
    statusEl.hidden = true;

    try {
      const resp = await fetch("/convert", { method: "POST", body: form });
      if (!resp.ok) {
        let msg = "Conversion failed (HTTP " + resp.status + ").";
        try {
          const data = await resp.json();
          if (data && data.error) msg = data.error;
        } catch (_) { /* non-JSON error */ }
        throw new Error(msg);
      }
      const blob = await resp.blob();
      const dispo = resp.headers.get("Content-Disposition") || "";
      const match = /filename="?([^"]+)"?/.exec(dispo);
      const outName = match ? match[1] : fallbackBase + ".pdf";

      if (isDesktop()) {
        // Native macOS app: hand the bytes to Python for a "Save as…" dialog.
        const res = await saveViaDesktop(blob, outName);
        if (res && res.saved) {
          setStatus("Saved " + (res.path || outName), "ok");
        } else {
          setStatus("Save cancelled.", null);
        }
      } else {
        triggerDownload(blob, outName);
        setStatus("Done — downloaded " + outName, "ok");
      }
    } catch (err) {
      setStatus(err.message || "Something went wrong.", "err");
    } finally {
      hooks.reset();
    }
  }

  async function convertFile(file) {
    if (!file) return;
    if (CHOICES.max_bytes && file.size > CHOICES.max_bytes) {
      setStatus("That file is too large (limit " +
        Math.round(CHOICES.max_bytes / (1024 * 1024)) + " MB).", "err");
      return;
    }
    if (!hasAllowedExt(file.name)) {
      setStatus("Unsupported file. Please choose a Markdown or .docx file.", "err");
      return;
    }

    const form = new FormData();
    form.append("file", file);
    await submitConversion(form, file.name.replace(/\.[^.]+$/, ""), {
      busy: () => setBusy(file.name),
      reset: resetDropzone,
    });
  }

  async function convertText(text) {
    if (!text || !text.trim()) {
      setStatus("Nothing to convert — paste some Markdown first.", "err");
      return;
    }
    if (CHOICES.max_bytes && text.length > CHOICES.max_bytes) {
      setStatus("That's too much text to convert at once.", "err");
      return;
    }

    const form = new FormData();
    form.append("text", text);
    await submitConversion(form, "document", {
      busy: () => setPasteBusy(true),
      reset: () => setPasteBusy(false),
    });
  }

  // True when running inside the pywebview-based macOS desktop app.
  function isDesktop() {
    return !!(window.pywebview && window.pywebview.api && window.pywebview.api.save_pdf);
  }

  function blobToBase64(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        // result is "data:...;base64,XXXX" — keep only the payload.
        const comma = reader.result.indexOf(",");
        resolve(reader.result.slice(comma + 1));
      };
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(blob);
    });
  }

  async function saveViaDesktop(blob, name) {
    const b64 = await blobToBase64(blob);
    return window.pywebview.api.save_pdf(name, b64);
  }

  function triggerDownload(blob, name) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  }

  // -------------------------------------------------------------- paste mode
  function setPasteBusy(busy) {
    pasteConvertBtn.disabled = busy;
    pasteConvertBtn.textContent = busy ? "Converting…" : "Convert to PDF";
  }

  function updatePasteHint() {
    const n = pasteInput.value.length;
    pasteHint.textContent = n ? n.toLocaleString() + " characters" : "";
  }

  function setMode(mode) {
    const paste = mode === "paste";
    viewPaste.hidden = !paste;
    viewUpload.hidden = paste;
    modePasteBtn.classList.toggle("active", paste);
    modeUploadBtn.classList.toggle("active", !paste);
    modePasteBtn.setAttribute("aria-selected", String(paste));
    modeUploadBtn.setAttribute("aria-selected", String(!paste));
    if (paste) pasteInput.focus();
  }

  // ----------------------------------------------------------------- events
  fileInput.addEventListener("change", () => {
    if (fileInput.files && fileInput.files[0]) {
      convertFile(fileInput.files[0]);
      fileInput.value = ""; // allow re-selecting the same file
    }
  });

  dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInput.click();
    }
  });

  ["dragenter", "dragover"].forEach((ev) =>
    dropzone.addEventListener(ev, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.add("dragover");
    })
  );
  ["dragleave", "dragend", "drop"].forEach((ev) =>
    dropzone.addEventListener(ev, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove("dragover");
    })
  );
  dropzone.addEventListener("drop", (e) => {
    const files = e.dataTransfer && e.dataTransfer.files;
    if (files && files[0]) convertFile(files[0]);
  });

  // Avoid the browser opening a file dropped outside the zone.
  ["dragover", "drop"].forEach((ev) =>
    window.addEventListener(ev, (e) => {
      if (!dropzone.contains(e.target)) e.preventDefault();
    })
  );

  // Mode toggle + paste actions.
  modeUploadBtn.addEventListener("click", () => setMode("upload"));
  modePasteBtn.addEventListener("click", () => setMode("paste"));
  pasteInput.addEventListener("input", updatePasteHint);
  pasteConvertBtn.addEventListener("click", () => convertText(pasteInput.value));
  // Cmd/Ctrl+Enter converts from the textarea.
  pasteInput.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      convertText(pasteInput.value);
    }
  });
})();
