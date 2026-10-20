/* ============================================================
   InvoiceLite — app.js
   Pure client-side. No backend, no network calls, no PII
   ever leaves the browser. State is persisted to localStorage.
   ============================================================ */
(function () {
  'use strict';

  /* ---------------- constants ---------------- */
  var STORAGE_KEY = 'invoicelite.state.v1';
  var SEQ_KEY     = 'invoicelite.seq.v1';
  var CURRENCY    = '₦';
  var DEFAULT_INVOICE_NUMBER = 'INV-001';

  /* ---------------- dom refs ---------------- */
  var $ = function (id) { return document.getElementById(id); };

  var els = {
    bizName: $('bizName'),
    bizContact: $('bizContact'),
    bizAddress: $('bizAddress'),
    clientName: $('clientName'),
    clientContact: $('clientContact'),
    clientAddress: $('clientAddress'),
    invoiceNumber: $('invoiceNumber'),
    issueDate: $('issueDate'),
    dueDate: $('dueDate'),
    itemsList: $('itemsList'),
    btnAddItem: $('btnAddItem'),
    itemsEmptyHint: $('itemsEmptyHint'),
    taxRate: $('taxRate'),
    amountPaid: $('amountPaid'),
    notes: $('notes'),
    btnPrint: $('btnPrint'),
    btnPrint2: $('btnPrint2'),
    btnReset: $('btnReset'),
    btnNewInvoice: $('btnNewInvoice'),
    toast: $('toast'),
    // preview
    pvNumber: $('pvNumber'),
    pvBizName: $('pvBizName'),
    pvBizContact: $('pvBizContact'),
    pvBizAddress: $('pvBizAddress'),
    pvClientName: $('pvClientName'),
    pvClientContact: $('pvClientContact'),
    pvClientAddress: $('pvClientAddress'),
    pvIssueDate: $('pvIssueDate'),
    pvDueDate: $('pvDueDate'),
    pvItems: $('pvItems'),
    pvNotes: $('pvNotes'),
    pvSubtotal: $('pvSubtotal'),
    pvTax: $('pvTax'),
    pvTaxRateLabel: $('pvTaxRateLabel'),
    taxRow: $('taxRow'),
    pvTotal: $('pvTotal'),
    pvPaid: $('pvPaid'),
    paidRow: $('paidRow'),
    pvBalance: $('pvBalance'),
    balanceRow: $('balanceRow')
  };

  /* ---------------- formatting helpers ---------------- */
  function toNumber(value) {
    var n = parseFloat(value);
    return isFinite(n) ? n : 0;
  }

  /** Format a number as NGN with thousands separators, e.g. 1250000 -> "₦1,250,000.00" */
  function formatNGN(amount) {
    var n = toNumber(amount);
    var negative = n < 0;
    n = Math.abs(n);
    var fixed = n.toFixed(2);
    var parts = fixed.split('.');
    var whole = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return (negative ? '-' : '') + CURRENCY + whole + '.' + parts[1];
  }

  /** Same but without decimals — used in compact table cells. */
  function formatNGNCompact(amount) {
    return formatNGN(amount);
  }

  function todayISO() {
    var d = new Date();
    var m = String(d.getMonth() + 1).padStart(2, '0');
    var day = String(d.getDate()).padStart(2, '0');
    return d.getFullYear() + '-' + m + '-' + day;
  }

  function addDaysISO(iso, days) {
    var d = iso ? new Date(iso + 'T00:00:00') : new Date();
    if (isNaN(d.getTime())) d = new Date();
    d.setDate(d.getDate() + days);
    var m = String(d.getMonth() + 1).padStart(2, '0');
    var day = String(d.getDate()).padStart(2, '0');
    return d.getFullYear() + '-' + m + '-' + day;
  }

  function formatDateHuman(iso) {
    if (!iso) return '—';
    var d = new Date(iso + 'T00:00:00');
    if (isNaN(d.getTime())) return '—';
    var months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return d.getDate() + ' ' + months[d.getMonth()] + ' ' + d.getFullYear();
  }

  function uid() {
    return 'it_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
  }

  /* ---------------- invoice number sequence ---------------- */
  function readSeq() {
    try {
      var raw = localStorage.getItem(SEQ_KEY);
      var n = parseInt(raw, 10);
      return isFinite(n) && n > 0 ? n : 1;
    } catch (e) {
      return 1;
    }
  }

  function writeSeq(n) {
    try { localStorage.setItem(SEQ_KEY, String(n)); } catch (e) { /* quota / private mode */ }
  }

  function numberForSeq(n) {
    return 'INV-' + String(n).padStart(3, '0');
  }

  /** Bump the persisted sequence and return the new invoice number. */
  function nextInvoiceNumber() {
    var current = readSeq();
    var next = current + 1;
    writeSeq(next);
    return numberForSeq(next);
  }

  /* ---------------- default state ---------------- */
  function makeItem(description, qty, unitPrice) {
    return {
      id: uid(),
      description: description || '',
      qty: (qty === 0 || qty) ? qty : 1,
      unitPrice: unitPrice || 0
    };
  }

  function defaultState() {
    return {
      bizName: '',
      bizContact: '',
      bizAddress: '',
      clientName: '',
      clientContact: '',
      clientAddress: '',
      invoiceNumber: DEFAULT_INVOICE_NUMBER,
      issueDate: todayISO(),
      dueDate: addDaysISO(todayISO(), 14),
      items: [makeItem('', 1, 0)],
      taxRate: 0,
      amountPaid: 0,
      notes: ''
    };
  }

  /* ---------------- state load / save ---------------- */
  function sanitizeItem(raw) {
    var it = raw && typeof raw === 'object' ? raw : {};
    return {
      id: typeof it.id === 'string' && it.id ? it.id : uid(),
      description: typeof it.description === 'string' ? it.description : '',
      qty: isFinite(parseFloat(it.qty)) ? parseFloat(it.qty) : 1,
      unitPrice: isFinite(parseFloat(it.unitPrice)) ? parseFloat(it.unitPrice) : 0
    };
  }

  function loadState() {
    var fresh = defaultState();
    var raw;
    try {
      raw = localStorage.getItem(STORAGE_KEY);
    } catch (e) {
      return fresh; // storage blocked (private mode / disabled cookies)
    }
    if (!raw) return fresh;

    var parsed;
    try {
      parsed = JSON.parse(raw);
    } catch (e) {
      return fresh;
    }
    if (!parsed || typeof parsed !== 'object') return fresh;

    var s = {
      bizName:        typeof parsed.bizName === 'string' ? parsed.bizName : '',
      bizContact:     typeof parsed.bizContact === 'string' ? parsed.bizContact : '',
      bizAddress:     typeof parsed.bizAddress === 'string' ? parsed.bizAddress : '',
      clientName:     typeof parsed.clientName === 'string' ? parsed.clientName : '',
      clientContact:  typeof parsed.clientContact === 'string' ? parsed.clientContact : '',
      clientAddress:  typeof parsed.clientAddress === 'string' ? parsed.clientAddress : '',
      invoiceNumber:  typeof parsed.invoiceNumber === 'string' && /^INV-\d{3,}$/.test(parsed.invoiceNumber)
                        ? parsed.invoiceNumber : DEFAULT_INVOICE_NUMBER,
      issueDate:      typeof parsed.issueDate === 'string' ? parsed.issueDate : fresh.issueDate,
      dueDate:        typeof parsed.dueDate === 'string' ? parsed.dueDate : fresh.dueDate,
      items:          Array.isArray(parsed.items) ? parsed.items.map(sanitizeItem) : fresh.items,
      taxRate:        isFinite(parseFloat(parsed.taxRate)) ? Math.min(100, Math.max(0, parseFloat(parsed.taxRate))) : 0,
      amountPaid:     isFinite(parseFloat(parsed.amountPaid)) ? Math.max(0, parseFloat(parsed.amountPaid)) : 0,
      notes:          typeof parsed.notes === 'string' ? parsed.notes : ''
    };
    if (!s.items.length) s.items = [makeItem('', 1, 0)];
    return s;
  }

  function saveState() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (e) {
      toast('Could not save — browser storage is unavailable.');
    }
  }

  /* ---------------- state ---------------- */
  var state = loadState();

  // Ensure a real sequence exists that is >= the persisted invoice number.
  (function bootstrapSeq() {
    var seq = readSeq();
    var match = /^INV-(\d+)$/.exec(state.invoiceNumber);
    var fromNumber = match ? parseInt(match[1], 10) : 1;
    if (!isFinite(seq) || seq < fromNumber) writeSeq(fromNumber);
  })();

  /* ---------------- calculations ---------------- */
  function lineTotal(item) {
    var qty = toNumber(item.qty);
    var price = toNumber(item.unitPrice);
    var total = qty * price;
    return isFinite(total) ? Math.round(total * 100) / 100 : 0;
  }

  function computeTotals() {
    var subtotal = state.items.reduce(function (sum, item) {
      return sum + lineTotal(item);
    }, 0);
    subtotal = Math.round(subtotal * 100) / 100;

    var taxRate = Math.min(100, Math.max(0, toNumber(state.taxRate)));
    var tax = Math.round(subtotal * (taxRate / 100) * 100) / 100;
    var total = Math.round((subtotal + tax) * 100) / 100;
    var paid = Math.max(0, toNumber(state.amountPaid));
    var balance = Math.round((total - paid) * 100) / 100;

    return {
      subtotal: subtotal,
      taxRate: taxRate,
      tax: tax,
      total: total,
      paid: paid,
      balance: balance
    };
  }

  /* ---------------- toast ---------------- */
  var toastTimer = null;
  function toast(message) {
    els.toast.textContent = message;
    els.toast.classList.add('show');
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      els.toast.classList.remove('show');
    }, 2600);
  }

  /* ---------------- item rendering (form) ---------------- */
  function buildItemCard(item, index) {
    var card = document.createElement('div');
    card.className = 'item-card';
    card.dataset.id = item.id;

    // description
    var fDesc = document.createElement('div');
    fDesc.className = 'f-desc';
    var descLabel = document.createElement('label');
    descLabel.className = 'lbl';
    descLabel.textContent = 'Description';
    var descId = 'item-desc-' + item.id;
    descLabel.setAttribute('for', descId);
    var descInput = document.createElement('input');
    descInput.type = 'text';
    descInput.id = descId;
    descInput.value = item.description;
    descInput.placeholder = 'e.g. Brand identity design';
    descInput.setAttribute('aria-label', 'Line item ' + (index + 1) + ' description');
    descInput.addEventListener('input', function () {
      state.items[index].description = descInput.value;
      saveState();
      renderPreview();
    });
    fDesc.appendChild(descLabel);
    fDesc.appendChild(descInput);

    // qty
    var fQty = document.createElement('div');
    fQty.className = 'f-qty';
    var qtyLabel = document.createElement('label');
    qtyLabel.className = 'lbl';
    qtyLabel.textContent = 'Qty';
    var qtyId = 'item-qty-' + item.id;
    qtyLabel.setAttribute('for', qtyId);
    var qtyInput = document.createElement('input');
    qtyInput.type = 'number';
    qtyInput.id = qtyId;
    qtyInput.min = '0';
    qtyInput.step = '1';
    qtyInput.inputMode = 'decimal';
    qtyInput.value = item.qty;
    qtyInput.setAttribute('aria-label', 'Line item ' + (index + 1) + ' quantity');
    qtyInput.addEventListener('input', function () {
      state.items[index].qty = qtyInput.value === '' ? 0 : toNumber(qtyInput.value);
      saveState();
      updateLineTotal(card, state.items[index]);
      renderPreview();
    });
    fQty.appendChild(qtyLabel);
    fQty.appendChild(qtyInput);

    // unit price
    var fPrice = document.createElement('div');
    fPrice.className = 'f-price';
    var priceLabel = document.createElement('label');
    priceLabel.className = 'lbl';
    priceLabel.textContent = 'Unit price (₦)';
    var priceId = 'item-price-' + item.id;
    priceLabel.setAttribute('for', priceId);
    var priceInput = document.createElement('input');
    priceInput.type = 'number';
    priceInput.id = priceId;
    priceInput.min = '0';
    priceInput.step = '0.01';
    priceInput.inputMode = 'decimal';
    priceInput.value = item.unitPrice;
    priceInput.setAttribute('aria-label', 'Line item ' + (index + 1) + ' unit price in Naira');
    priceInput.addEventListener('input', function () {
      state.items[index].unitPrice = priceInput.value === '' ? 0 : toNumber(priceInput.value);
      saveState();
      updateLineTotal(card, state.items[index]);
      renderPreview();
    });
    fPrice.appendChild(priceLabel);
    fPrice.appendChild(priceInput);

    // amount
    var fAmt = document.createElement('div');
    fAmt.className = 'f-amt';
    var amtSpan = document.createElement('span');
    amtSpan.className = 'item-line-total';
    amtSpan.textContent = formatNGN(lineTotal(item));
    fAmt.appendChild(amtSpan);

    // delete
    var fDel = document.createElement('div');
    fDel.className = 'f-del';
    var delBtn = document.createElement('button');
    delBtn.type = 'button';
    delBtn.className = 'btn-icon';
    delBtn.innerHTML = '&times;';
    delBtn.title = 'Remove line item';
    delBtn.setAttribute('aria-label', 'Remove line item ' + (index + 1));
    delBtn.addEventListener('click', function () {
      removeItem(item.id);
    });
    fDel.appendChild(delBtn);

    card.appendChild(fDesc);
    card.appendChild(fQty);
    card.appendChild(fPrice);
    card.appendChild(fAmt);
    card.appendChild(fDel);

    return card;
  }

  function updateLineTotal(card, item) {
    var span = card.querySelector('.item-line-total');
    if (span) span.textContent = formatNGN(lineTotal(item));
  }

  function renderItems() {
    els.itemsList.innerHTML = '';
    state.items.forEach(function (item, index) {
      els.itemsList.appendChild(buildItemCard(item, index));
    });
    els.itemsEmptyHint.textContent = state.items.length
      ? 'Line amounts update as you type.'
      : 'Add at least one line item to issue an invoice.';
    if (!state.items.length) els.itemsEmptyHint.textContent = 'Add at least one line item to issue an invoice.';
  }

  function addItem() {
    state.items.push(makeItem('', 1, 0));
    saveState();
    renderItems();
    renderPreview();
    // focus the newest description input
    var cards = els.itemsList.querySelectorAll('.item-card');
    var last = cards[cards.length - 1];
    if (last) {
      var input = last.querySelector('.f-desc input');
      if (input) input.focus();
    }
  }

  function removeItem(id) {
    if (state.items.length <= 1) {
      // keep a single empty row rather than an unsaveable blank invoice
      state.items = [makeItem('', 1, 0)];
      saveState();
      renderItems();
      renderPreview();
      toast('Invoice needs at least one line item.');
      return;
    }
    state.items = state.items.filter(function (item) { return item.id !== id; });
    saveState();
    renderItems();
    renderPreview();
    toast('Line item removed.');
  }

  /* ---------------- preview rendering ---------------- */
  function setText(el, text, fallback) {
    var value = (text === undefined || text === null) ? '' : String(text).trim();
    if (value) {
      el.textContent = value;
      el.classList.remove('is-placeholder');
    } else {
      el.textContent = fallback || '—';
      el.classList.add('is-placeholder');
    }
  }

  function renderPreviewItems() {
    els.pvItems.innerHTML = '';
    var visible = state.items.filter(function (item) {
      return String(item.description).trim() !== '' || lineTotal(item) !== 0;
    });

    if (!visible.length) {
      var emptyRow = document.createElement('tr');
      emptyRow.className = 'is-empty';
      var emptyCell = document.createElement('td');
      emptyCell.colSpan = 4;
      emptyCell.textContent = 'No line items yet';
      emptyRow.appendChild(emptyCell);
      els.pvItems.appendChild(emptyRow);
      return;
    }

    visible.forEach(function (item) {
      var tr = document.createElement('tr');
      tr.className = 'item-row';

      var tdDesc = document.createElement('td');
      tdDesc.className = 'desc-cell';
      tdDesc.textContent = item.description || 'Untitled item';

      var tdQty = document.createElement('td');
      tdQty.className = 'num';
      tdQty.textContent = String(toNumber(item.qty));

      var tdPrice = document.createElement('td');
      tdPrice.className = 'num';
      tdPrice.textContent = formatNGNCompact(toNumber(item.unitPrice));

      var tdAmount = document.createElement('td');
      tdAmount.className = 'num';
      tdAmount.textContent = formatNGNCompact(lineTotal(item));

      tr.appendChild(tdDesc);
      tr.appendChild(tdQty);
      tr.appendChild(tdPrice);
      tr.appendChild(tdAmount);
      els.pvItems.appendChild(tr);
    });
  }

  function renderPreview() {
    var totals = computeTotals();

    els.pvNumber.textContent = state.invoiceNumber || DEFAULT_INVOICE_NUMBER;
    setText(els.pvBizName, state.bizName, 'Your business name');
    setText(els.pvBizContact, state.bizContact, '');
    setText(els.pvBizAddress, state.bizAddress, '');
    setText(els.pvClientName, state.clientName, 'Client name');
    setText(els.pvClientContact, state.clientContact, '');
    setText(els.pvClientAddress, state.clientAddress, '');

    els.pvBizContact.style.display = String(state.bizContact || '').trim() ? '' : 'none';
    els.pvBizAddress.style.display = String(state.bizAddress || '').trim() ? '' : 'none';
    els.pvClientContact.style.display = String(state.clientContact || '').trim() ? '' : 'none';
    els.pvClientAddress.style.display = String(state.clientAddress || '').trim() ? '' : 'none';

    els.pvIssueDate.textContent = formatDateHuman(state.issueDate);
    els.pvDueDate.textContent = formatDateHuman(state.dueDate);

    renderPreviewItems();

    setText(els.pvNotes, state.notes, '—');

    els.pvSubtotal.textContent = formatNGN(totals.subtotal);

    if (totals.taxRate > 0) {
      els.taxRow.hidden = false;
      els.pvTaxRateLabel.textContent = '(' + totals.taxRate + '%)';
      els.pvTax.textContent = formatNGN(totals.tax);
    } else {
      els.taxRow.hidden = true;
    }

    els.pvTotal.textContent = formatNGN(totals.total);

    if (totals.paid > 0) {
      els.paidRow.hidden = false;
      els.pvPaid.textContent = formatNGN(totals.paid);
      els.balanceRow.hidden = false;
      els.pvBalance.textContent = formatNGN(totals.balance);
    } else {
      els.paidRow.hidden = true;
      els.balanceRow.hidden = true;
    }
  }

  /* ---------------- form binding ---------------- */
  function bindTextInput(el, key) {
    el.value = state[key] === undefined || state[key] === null ? '' : state[key];
    el.addEventListener('input', function () {
      state[key] = el.value;
      saveState();
      renderPreview();
    });
  }

  function bindNumberInput(el, key, opts) {
    el.value = state[key];
    el.addEventListener('input', function () {
      var raw = el.value;
      var n = raw === '' ? 0 : toNumber(raw);
      if (opts && opts.min !== undefined) n = Math.max(opts.min, n);
      if (opts && opts.max !== undefined) n = Math.min(opts.max, n);
      state[key] = n;
      saveState();
      renderPreview();
    });
    el.addEventListener('blur', function () {
      if (el.value === '' || !isFinite(parseFloat(el.value))) {
        state[key] = opts && opts.min !== undefined ? opts.min : 0;
        el.value = state[key];
        saveState();
        renderPreview();
      }
    });
  }

  function bindAll() {
    bindTextInput(els.bizName, 'bizName');
    bindTextInput(els.bizContact, 'bizContact');
    bindTextInput(els.bizAddress, 'bizAddress');
    bindTextInput(els.clientName, 'clientName');
    bindTextInput(els.clientContact, 'clientContact');
    bindTextInput(els.clientAddress, 'clientAddress');
    bindTextInput(els.notes, 'notes');

    // invoice number (read-only display, auto-generated)
    els.invoiceNumber.value = state.invoiceNumber;

    // dates
    els.issueDate.value = state.issueDate;
    els.issueDate.addEventListener('change', function () {
      state.issueDate = els.issueDate.value;
      saveState();
      renderPreview();
    });

    els.dueDate.value = state.dueDate;
    els.dueDate.addEventListener('change', function () {
      state.dueDate = els.dueDate.value;
      saveState();
      renderPreview();
    });

    bindNumberInput(els.taxRate, 'taxRate', { min: 0, max: 100 });
    bindNumberInput(els.amountPaid, 'amountPaid', { min: 0 });
  }

  /* ---------------- actions ---------------- */
  function printInvoice() {
    // Give the browser a tick so any pending input state is reflected.
    window.requestAnimationFrame(function () {
      window.print();
    });
  }

  function startNewInvoice() {
    var ok = window.confirm(
      'Start a new invoice?\n\n' +
      'The current invoice fields will be cleared. Your next invoice number will be ' +
      'reserved automatically. This cannot be undone.'
    );
    if (!ok) return;

    var preserved = {
      bizName: state.bizName,
      bizContact: state.bizContact,
      bizAddress: state.bizAddress
    };

    var newNumber = nextInvoiceNumber();

    state = defaultState();
    state.bizName = preserved.bizName;
    state.bizContact = preserved.bizContact;
    state.bizAddress = preserved.bizAddress;
    state.invoiceNumber = newNumber;

    saveState();

    // re-sync the whole form
    els.bizName.value = state.bizName;
    els.bizContact.value = state.bizContact;
    els.bizAddress.value = state.bizAddress;
    els.clientName.value = '';
    els.clientContact.value = '';
    els.clientAddress.value = '';
    els.invoiceNumber.value = state.invoiceNumber;
    els.issueDate.value = state.issueDate;
    els.dueDate.value = state.dueDate;
    els.taxRate.value = state.taxRate;
    els.amountPaid.value = state.amountPaid;
    els.notes.value = state.notes;

    renderItems();
    renderPreview();
    toast('New invoice started — ' + state.invoiceNumber);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function resetEverything() {
    var ok = window.confirm(
      'Reset InvoiceLite?\n\n' +
      'This clears all saved invoice data from this browser and restarts numbering at INV-001. ' +
      'There is no server copy to restore from.'
    );
    if (!ok) return;

    try {
      localStorage.removeItem(STORAGE_KEY);
      localStorage.removeItem(SEQ_KEY);
    } catch (e) { /* ignore */ }

    state = defaultState();

    els.bizName.value = '';
    els.bizContact.value = '';
    els.bizAddress.value = '';
    els.clientName.value = '';
    els.clientContact.value = '';
    els.clientAddress.value = '';
    els.invoiceNumber.value = state.invoiceNumber;
    els.issueDate.value = state.issueDate;
    els.dueDate.value = state.dueDate;
    els.taxRate.value = state.taxRate;
    els.amountPaid.value = state.amountPaid;
    els.notes.value = state.notes;

    renderItems();
    renderPreview();
    saveState();
    toast('All local data cleared.');
  }

  /* ---------------- init ---------------- */
  function init() {
    bindAll();
    renderItems();
    renderPreview();

    els.btnAddItem.addEventListener('click', addItem);
    els.btnPrint.addEventListener('click', printInvoice);
    els.btnPrint2.addEventListener('click', printInvoice);
    els.btnNewInvoice.addEventListener('click', startNewInvoice);
    els.btnReset.addEventListener('click', resetEverything);

    // Keyboard: Ctrl/Cmd+Enter adds an item; Ctrl/Cmd+P is left to the browser.
    document.addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        addItem();
      }
    });

    // Warn once if storage is unavailable (private mode, blocked cookies).
    try {
      localStorage.setItem('invoicelite.probe', '1');
      localStorage.removeItem('invoicelite.probe');
    } catch (err) {
      toast('Storage is blocked — data will not survive a refresh.');
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();