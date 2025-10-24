// path: src/app_outlay/static/app_outlay/js/estimate_filters.js
/**
 * Модуль фильтрации и сортировки таблицы
 */
(function (window) {
    'use strict';

    const EstimateFilters = {
        flt: {},
        sortState: { key: null, dir: 'asc' },

        init() {
            this.flt = {
                text: document.getElementById('flt-text'),
                unit: document.getElementById('flt-unit'),
                qmin: document.getElementById('flt-qty-min'),
                qmax: document.getElementById('flt-qty-max'),
                stateAll: document.getElementById('flt-state-all'),
                stateMapped: document.getElementById('flt-state-mapped'),
                stateUnmapped: document.getElementById('flt-state-unmapped'),
                applyBtn: document.getElementById('flt-apply'),
                resetBtn: document.getElementById('flt-reset'),
            };

            this.buildUnitOptions();
            this.hookFilters();
            this.hookSortHeaders();
            this.applyFilters();
            this.refreshSortIndicators();
        },

        normalizeStr(s) {
            return (s || '').toString().toLowerCase().trim();
        },

        parseQty(v) {
            const n = parseFloat((v || '').toString().replace(',', '.'));
            return isNaN(n) ? null : n;
        },

        getRowData(tr) {
            const tds = tr.querySelectorAll('td');
            const name = (tds[0]?.textContent || '').trim();
            const unit = (tds[1]?.textContent || '').trim();
            const qtyInput = tr.querySelector('.qty-input');
            const qty = this.parseQty(qtyInput?.value);
            const tcInput = tr.querySelector('.js-tc-autocomplete');
            const tcText = (tcInput?.dataset.text || tcInput?.value || '').trim();
            const mapped = !!(tcInput && (tcInput.dataset.id || '').length > 0);

            return { name, unit, qty, tcText, mapped };
        },

        buildUnitOptions() {
            const set = new Set();

            document.querySelectorAll('#tc-map tbody tr:not(.sec-hdr)').forEach(tr => {
                const unit = (tr.querySelector('td:nth-child(2)')?.textContent || '').trim();
                if (unit) set.add(unit);
            });

            const cur = this.flt.unit.value;
            this.flt.unit.innerHTML = '<option value="">Все</option>' +
                Array.from(set).sort().map(u => `<option value="${u}">${u}</option>`).join('');

            if (Array.from(set).includes(cur)) {
                this.flt.unit.value = cur;
            }
        },

        rowPassesFilters(tr) {
            const d = this.getRowData(tr);

            const text = this.normalizeStr(this.flt.text.value);
            if (text) {
                const hay = this.normalizeStr(d.name + ' ' + d.tcText);
                if (!hay.includes(text)) return false;
            }

            if (this.flt.unit.value && d.unit !== this.flt.unit.value) return false;

            const qmin = this.parseQty(this.flt.qmin.value);
            const qmax = this.parseQty(this.flt.qmax.value);

            if (qmin != null && (d.qty == null || d.qty < qmin)) return false;
            if (qmax != null && (d.qty == null || d.qty > qmax)) return false;

            if (this.flt.stateMapped.checked && !d.mapped) return false;
            if (this.flt.stateUnmapped.checked && d.mapped) return false;

            return true;
        },

        applyFilters() {
            const sections = [];
            let curSec = null;

            document.querySelectorAll('#tc-map tbody tr').forEach(tr => {
                if (tr.classList.contains('sec-hdr')) {
                    curSec = { hdr: tr, rows: [] };
                    sections.push(curSec);
                    return;
                }

                if (!curSec) {
                    curSec = { hdr: null, rows: [] };
                    sections.push(curSec);
                }

                const pass = this.rowPassesFilters(tr);
                tr.style.display = pass ? '' : 'none';
                curSec.rows.push(tr);
            });

            sections.forEach(sec => {
                if (!sec.hdr) return;
                const anyVisible = sec.rows.some(r => r.style.display !== 'none');
                sec.hdr.style.display = anyVisible ? '' : 'none';
            });
        },

        applySort() {
            if (!this.sortState.key) return;

            const key = this.sortState.key;
            const dir = this.sortState.dir === 'asc' ? 1 : -1;

            let curSec = null;
            const tbody = document.querySelector('#tc-map tbody');
            const sections = [];

            Array.from(tbody.querySelectorAll('tr')).forEach(tr => {
                if (tr.classList.contains('sec-hdr')) {
                    curSec = { hdr: tr, rows: [] };
                    sections.push(curSec);
                    return;
                }

                if (!curSec) {
                    curSec = { hdr: null, rows: [] };
                    sections.push(curSec);
                }

                if (tr.style.display === 'none') return;
                curSec.rows.push(tr);
            });

            sections.forEach(sec => {
                const rows = sec.rows;

                rows.sort((a, b) => {
                    const A = this.getRowData(a);
                    const B = this.getRowData(b);
                    let va, vb;

                    if (key === 'name') {
                        va = this.normalizeStr(A.name);
                        vb = this.normalizeStr(B.name);
                    } else if (key === 'unit') {
                        va = this.normalizeStr(A.unit);
                        vb = this.normalizeStr(B.unit);
                    } else if (key === 'qty') {
                        va = A.qty ?? -Infinity;
                        vb = B.qty ?? -Infinity;
                    } else if (key === 'tc') {
                        va = this.normalizeStr(A.tcText);
                        vb = this.normalizeStr(B.tcText);
                    } else {
                        va = 0;
                        vb = 0;
                    }

                    if (va < vb) return -1 * dir;
                    if (va > vb) return 1 * dir;
                    return 0;
                });

                let anchor = sec.hdr ? sec.hdr.nextSibling : tbody.firstChild;
                rows.forEach(r => tbody.insertBefore(r, anchor));
            });
        },

        refreshSortIndicators() {
            document.querySelectorAll('#tc-map thead .sortable').forEach(el => {
                el.classList.toggle('active', el.dataset.key === this.sortState.key);
                el.setAttribute('data-dir', this.sortState.dir);
            });
        },

        setSort(key) {
            if (this.sortState.key !== key) {
                this.sortState.key = key;
                this.sortState.dir = 'asc';
            } else {
                this.sortState.dir = (this.sortState.dir === 'asc') ? 'desc' : 'asc';
            }

            this.refreshSortIndicators();
            this.applyFilters();
            this.applySort();
        },

        hookSortHeaders() {
            document.querySelectorAll('#tc-map thead .sortable').forEach(el => {
                el.addEventListener('click', () => this.setSort(el.dataset.key));
            });
        },

        hookFilters() {
            ['input', 'change'].forEach(evt => {
                this.flt.text.addEventListener(evt, () => this.applyFilters());
                this.flt.unit.addEventListener(evt, () => this.applyFilters());
                this.flt.qmin.addEventListener(evt, () => this.applyFilters());
                this.flt.qmax.addEventListener(evt, () => this.applyFilters());
                this.flt.stateAll.addEventListener(evt, () => this.applyFilters());
                this.flt.stateMapped.addEventListener(evt, () => this.applyFilters());
                this.flt.stateUnmapped.addEventListener(evt, () => this.applyFilters());
            });

            if (this.flt.applyBtn) {
                this.flt.applyBtn.addEventListener('click', () => {
                    this.applyFilters();
                    this.applySort();
                });
            }

            if (this.flt.resetBtn) {
                this.flt.resetBtn.addEventListener('click', () => {
                    this.flt.text.value = '';
                    this.flt.unit.value = '';
                    this.flt.qmin.value = '';
                    this.flt.qmax.value = '';
                    this.flt.stateAll.checked = true;
                    this.applyFilters();
                    this.applySort();
                });
            }
        }
    };

    window.EstimateFilters = EstimateFilters;
})(window);