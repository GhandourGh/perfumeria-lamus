/* Perfumería Lamus — shared interactions.
   Server-rendered app: this file only handles navigation, dialogs,
   previews, and guards. No data lives here. */

(function () {
  "use strict";

  /* ---------- Currency ---------- */

  function formatCOP(value) {
    var n = Math.round(Number(value) || 0);
    var sign = n < 0 ? "-" : "";
    return sign + "$" + Math.abs(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  }

  /* ---------- Icons ---------- */

  if (window.lucide) lucide.createIcons();

  var csrfMeta = document.querySelector('meta[name="csrf-token"]');
  if (csrfMeta) {
    document.querySelectorAll('form[method="post"], form[method="POST"]').forEach(function (form) {
      if (!form.querySelector('input[name="_csrf_token"]')) {
        var token = document.createElement("input");
        token.type = "hidden";
        token.name = "_csrf_token";
        token.value = csrfMeta.content;
        form.appendChild(token);
      }
    });
  }

  var backLink = document.querySelector("[data-back-link]");
  if (backLink) {
    backLink.addEventListener("click", function (event) {
      if (window.history.length > 1 && document.referrer) {
        try {
          var previous = new URL(document.referrer);
          if (previous.origin === window.location.origin && previous.pathname !== "/login") {
            event.preventDefault();
            window.history.back();
          }
        } catch (error) {
          /* Keep the link's safe overview fallback. */
        }
      }
    });
  }

  /* ---------- Mobile drawer ---------- */

  var toggle = document.querySelector("[data-nav-toggle]");
  var scrim = document.querySelector("[data-nav-scrim]");

  function closeNav() {
    document.body.classList.remove("nav-open");
    if (toggle) toggle.setAttribute("aria-expanded", "false");
  }

  var navMenus = Array.prototype.slice.call(document.querySelectorAll("[data-nav-menu]"));
  function closeNavMenus(except) {
    navMenus.forEach(function (menu) {
      if (menu !== except) menu.removeAttribute("open");
    });
  }
  navMenus.forEach(function (menu) {
    menu.addEventListener("toggle", function () {
      if (menu.open) closeNavMenus(menu);
    });
  });
  document.addEventListener("click", function (event) {
    if (!event.target.closest("[data-nav-menu]")) closeNavMenus();
  });

  if (toggle) {
    toggle.addEventListener("click", function () {
      var open = document.body.classList.toggle("nav-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }
  if (scrim) scrim.addEventListener("click", closeNav);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      closeNavMenus();
      closeNav();
      if (toggle) toggle.focus();
    }
  });

  /* ---------- Toasts ---------- */

  document.querySelectorAll(".toast").forEach(function (toast) {
    var close = toast.querySelector(".toast-close");
    function dismiss() {
      toast.classList.add("is-leaving");
      setTimeout(function () { toast.remove(); }, 260);
    }
    if (close) close.addEventListener("click", dismiss);
    if (!toast.closest(".auth-flash")) setTimeout(dismiss, 6000);
  });

  /* ---------- Dialog sheets ---------- */

  document.querySelectorAll("[data-open-sheet]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var sheet = document.getElementById(btn.getAttribute("data-open-sheet"));
      if (!sheet) return;
      sheet.showModal();
      var first = sheet.querySelector("input, select, textarea");
      if (first) first.focus();
    });
  });

  document.querySelectorAll("dialog.sheet").forEach(function (sheet) {
    sheet.querySelectorAll("[data-close-sheet]").forEach(function (btn) {
      btn.addEventListener("click", function () { sheet.close(); });
    });
    sheet.addEventListener("click", function (e) {
      if (e.target === sheet) sheet.close(); // backdrop click
    });
  });

  /* ---------- Submit guard: no duplicate financial entries ---------- */

  document.querySelectorAll("form[data-guard]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (form.dataset.submitted === "true") {
        e.preventDefault();
        return;
      }
      form.dataset.submitted = "true";
      var button = form.querySelector('button[type="submit"]');
      if (button) button.classList.add("is-loading");
    });
  });

  /* ---------- Unsaved-changes warning ---------- */

  document.querySelectorAll("form[data-warn-unsaved]").forEach(function (form) {
    var dirty = false;
    form.addEventListener("input", function () { dirty = true; });
    form.addEventListener("submit", function () { dirty = false; });
    window.addEventListener("beforeunload", function (e) {
      if (dirty) { e.preventDefault(); e.returnValue = ""; }
    });
  });

  /* ---------- Live balance preview on money forms ----------
     A form declares: data-preview data-balance="130000" data-kind="payment|charge"
     and contains .preview-strip with [data-preview-current], [data-preview-entry],
     [data-preview-result]. Payments over the balance are flagged. */

  document.querySelectorAll("form[data-preview]").forEach(function (form) {
    var amountInput = form.querySelector('input[name="amount"]');
    var strip = form.querySelector(".preview-strip");
    if (!amountInput || !strip) return;

    var balance = Number(form.dataset.balance) || 0;
    var kind = form.dataset.kind || "charge";
    var currentEl = strip.querySelector("[data-preview-current]");
    var entryEl = strip.querySelector("[data-preview-entry]");
    var resultEl = strip.querySelector("[data-preview-result]");
    var warnEl = form.querySelector("[data-preview-warning]");
    var submit = form.querySelector('button[type="submit"]');

    function update() {
      var amount = Number(amountInput.value) || 0;
      var next = kind === "payment" ? balance - amount : balance + amount;
      if (currentEl) currentEl.textContent = formatCOP(balance);
      if (entryEl) {
        var sign = amount === 0 ? "" : (kind === "payment" ? "− " : "+ ");
        entryEl.textContent = sign + formatCOP(amount);
      }
      if (resultEl) resultEl.textContent = formatCOP(next);
      var invalid = kind === "payment" && amount > balance;
      if (warnEl) warnEl.hidden = !invalid;
      if (submit) submit.disabled = invalid || amount <= 0;
    }

    amountInput.addEventListener("input", update);
    update();
  });

  /* ---------- Registry filtering, searching, sorting ----------
     Container: [data-registry]. Rows carry data-search, data-balance,
     data-lastpay, data-created, data-name.
     Controls: [data-registry-search], .chip[data-filter], [data-registry-sort]. */

  document.querySelectorAll("[data-registry]").forEach(function (registry) {
    var scope = document;
    var search = scope.querySelector("[data-registry-search]");
    var chips = scope.querySelectorAll(".chip[data-filter]");
    var sortSel = scope.querySelector("[data-registry-sort]");
    var emptyMsg = scope.querySelector("[data-registry-empty]");
    var activeFilter = "all";

    function rows() {
      return Array.prototype.slice.call(registry.querySelectorAll("[data-row]"));
    }

    var predicates = {
      all: function () { return true; },
      debt: function (r) { return Number(r.dataset.balance) > 0; },
      clear: function (r) { return Number(r.dataset.balance) <= 0; },
      "paid-recently": function (r) {
        if (!r.dataset.lastpay) return false;
        return (Date.now() - Date.parse(r.dataset.lastpay)) < 30 * 864e5;
      }
    };

    function apply() {
      var q = (search && search.value || "").trim().toLowerCase();
      var pred = predicates[activeFilter] || predicates.all;
      var visible = 0;
      registry.classList.toggle("is-searching", Boolean(q) || activeFilter !== "all");
      rows().forEach(function (row) {
        var hit = (!q || (row.dataset.search || "").indexOf(q) !== -1) && pred(row);
        row.hidden = !hit;
        if (hit) visible++;
      });
      if (emptyMsg) emptyMsg.hidden = visible !== 0;
    }

    function sortRows() {
      if (!sortSel) return;
      var mode = sortSel.value;
      var parent = registry.querySelector("tbody") || registry;
      var sorted = rows().sort(function (a, b) {
        switch (mode) {
          case "balance-desc": return Number(b.dataset.balance) - Number(a.dataset.balance);
          case "recent": return (b.dataset.lastactivity || "").localeCompare(a.dataset.lastactivity || "");
          case "newest": return (b.dataset.created || "").localeCompare(a.dataset.created || "");
          default: return (a.dataset.name || "").localeCompare(b.dataset.name || "");
        }
      });
      sorted.forEach(function (row) { parent.appendChild(row); });
    }

    if (search) search.addEventListener("input", apply);
    chips.forEach(function (chip) {
      chip.addEventListener("click", function () {
        chips.forEach(function (c) { c.setAttribute("aria-pressed", "false"); });
        chip.setAttribute("aria-pressed", "true");
        activeFilter = chip.dataset.filter;
        apply();
      });
    });
    if (sortSel) sortSel.addEventListener("change", sortRows);
    apply();
  });

  /* ---------- Dashboard card limits ---------- */

  document.querySelectorAll("[data-expand-cards]").forEach(function (button) {
    button.addEventListener("click", function () {
      var grid = document.getElementById(button.getAttribute("data-expand-cards"));
      if (!grid) return;
      var expanded = button.getAttribute("aria-expanded") === "true";
      button.setAttribute("aria-expanded", expanded ? "false" : "true");
      grid.classList.toggle("is-expanded", !expanded);
      var label = button.querySelector("[data-expand-label]");
      if (label) label.textContent = expanded ? "Show all" : "Show less";
      if (expanded) button.scrollIntoView({ block: "nearest" });
    });
  });

  /* ---------- Compact dashboard lists ---------- */

  document.querySelectorAll("[data-expand-panel]").forEach(function (button) {
    button.addEventListener("click", function () {
      var panel = document.getElementById(button.getAttribute("data-expand-panel"));
      if (!panel) return;
      var expanded = button.getAttribute("aria-expanded") === "true";
      button.setAttribute("aria-expanded", expanded ? "false" : "true");
      panel.classList.toggle("is-expanded", !expanded);
      var label = button.querySelector("[data-expand-label]");
      if (label) label.textContent = expanded ? "Expand" : "Collapse";
      if (expanded) panel.scrollTop = 0;
    });
  });

  /* ---------- Confirmed ledger editing ---------- */

  (function () {
    var editDialog = document.getElementById("sheet-edit-ledger");
    var confirmDialog = document.getElementById("sheet-confirm-ledger-edit");
    var form = document.getElementById("ledger-edit-form");
    if (!editDialog || !confirmDialog || !form) return;

    var amount = form.querySelector('[name="amount"]');
    var description = form.querySelector('[name="description"]');
    var notes = form.querySelector('[name="notes"]');
    var method = form.querySelector('[name="payment_method"]');
    var dueDate = form.querySelector('[name="due_date"]');
    var descriptionField = form.querySelector("[data-edit-description-field]");
    var methodField = form.querySelector("[data-edit-method-field]");
    var dueDateField = form.querySelector("[data-edit-due-date-field]");

    document.querySelectorAll("[data-edit-ledger]").forEach(function (button) {
      button.addEventListener("click", function () {
        var isPayment = button.dataset.entryKind === "payment";
        form.reset();
        form.action = button.dataset.action;
        form.dataset.confirmed = "false";
        form.dataset.entryLabel = button.dataset.entryLabel || "Ledger entry";
        amount.value = button.dataset.amount || "";
        description.value = button.dataset.description || "";
        notes.value = button.dataset.notes || "";
        method.value = button.dataset.paymentMethod || "CASH";
        dueDate.value = button.dataset.dueDate || "";
        descriptionField.hidden = isPayment;
        methodField.hidden = !isPayment;
        dueDateField.hidden = button.dataset.supportsDueDate !== "true";
        editDialog.showModal();
        amount.focus();
      });
    });

    form.addEventListener("submit", function (event) {
      if (form.dataset.confirmed === "true") return;
      event.preventDefault();
      var label = confirmDialog.querySelector("[data-confirm-entry-label]");
      var value = confirmDialog.querySelector("[data-confirm-entry-amount]");
      if (label) label.textContent = form.dataset.entryLabel || "Ledger entry";
      if (value) value.textContent = formatCOP(amount.value);
      confirmDialog.showModal();
      var confirmButton = confirmDialog.querySelector("[data-confirm-ledger-edit]");
      if (confirmButton) confirmButton.focus();
    });

    confirmDialog.querySelectorAll("[data-close-confirm-edit]").forEach(function (button) {
      button.addEventListener("click", function () { confirmDialog.close(); });
    });

    var confirmButton = confirmDialog.querySelector("[data-confirm-ledger-edit]");
    if (confirmButton) {
      confirmButton.addEventListener("click", function () {
        form.dataset.confirmed = "true";
        confirmDialog.close();
        form.requestSubmit();
      });
    }
  })();

  /* ---------- Print buttons ---------- */

  document.querySelectorAll("[data-print]").forEach(function (btn) {
    btn.addEventListener("click", function () { window.print(); });
  });

  /* ---------- Pay full balance ---------- */

  document.querySelectorAll("[data-fill-balance]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var form = btn.closest("form");
      if (!form) return;
      var input = form.querySelector('input[name="amount"]');
      if (!input) return;
      input.value = Math.round(Number(form.dataset.balance) || 0);
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.focus();
    });
  });

  /* ---------- Deep-link: open a sheet from ?action= on load ---------- */

  (function () {
    var action = new URLSearchParams(window.location.search).get("action");
    var map = { pay: "sheet-payment", sale: "sheet-debt", purchase: "sheet-purchase", vpay: "sheet-vendor-payment" };
    var id = action && map[action];
    var sheet = id && document.getElementById(id);
    if (sheet && sheet.showModal) {
      sheet.showModal();
      var first = sheet.querySelector("input, select, textarea");
      if (first) first.focus();
    }
  })();

  /* ---------- Bank: warn (don't block) before overdrawing ---------- */

  document.querySelectorAll("[data-bank-form]").forEach(function (form) {
    var balance = Number(form.dataset.bankBalance) || 0;
    var type = form.querySelector('[name="change_type"]');
    var amount = form.querySelector('[name="amount"]');
    var warn = form.querySelector("[data-overdraw-warning]");

    function overdraw() {
      return type && type.value === "REMOVE" && (Number(amount.value) || 0) > balance;
    }
    function update() { if (warn) warn.hidden = !overdraw(); }

    if (type) type.addEventListener("change", update);
    if (amount) amount.addEventListener("input", update);
    form.addEventListener("submit", function (e) {
      if (overdraw()) {
        var next = balance - (Number(amount.value) || 0);
        if (!window.confirm("This will take the bank balance to " + formatCOP(next) + ". Record it anyway?")) {
          e.preventDefault();
          e.stopImmediatePropagation();
          form.dataset.submitted = "";
          var submit = form.querySelector('button[type="submit"]');
          if (submit) submit.classList.remove("is-loading");
        }
      }
    });
    update();
  });
})();
