// path: src/app_outlay/static/app_outlay/js/estimate_calc.js
/**
 * Модуль расчётов технических карт
 */
(function (window) {
    'use strict';

    const EstimateCalc = {
        CALC_ORDER: [],
        CALC_URL: '',

        init(calcOrder, calcUrl) {
            this.CALC_ORDER = calcOrder;
            this.CALC_URL = calcUrl;
            this._bindQtyInputs();
        },

        _bindQtyInputs() {
            document.querySelectorAll('#tc-map .qty-input').forEach(inp => {
                inp.addEventListener('change', () => this.triggerRowCalc(inp.closest('tr')));
                inp.addEventListener('blur', () => this.triggerRowCalc(inp.closest('tr')));
            });
        },

        async triggerRowCalc(tr) {
            if (!tr) return;

            const inpTC = tr.querySelector('.js-tc-autocomplete');
            const inpQty = tr.querySelector('.qty-input');
            const tcId = parseInt(inpTC?.dataset.id || '0', 10) || 0;
            const qty = parseFloat((inpQty?.value || '').replace(',', '.')) || 0;

            tr.querySelectorAll('.opt-cell .sys').forEach(el => el.textContent = '—');

            if (!tcId || !isFinite(qty) || qty === 0) return;

            try {
                const resp = await fetch(this.CALC_URL + '?tc=' + tcId + '&qty=' + encodeURIComponent(qty));
                const data = await resp.json();

                if (!data.ok) return;

                const calc = data.calc || {};
                const cells = tr.querySelectorAll('.opt-cell');

                this.CALC_ORDER.forEach((rid, idx) => {
                    const td = cells[idx];
                    if (!td) return;

                    const val = (calc[rid] != null)
                        ? Number(calc[rid]).toLocaleString(undefined, { maximumFractionDigits: 4 })
                        : '—';

                    td.querySelector('.sys').textContent = val;
                });

                setTimeout(() => this.updateSummary(), 100);
            } catch (e) {
                console.error('Calc error:', e);
            }
        },

        computeBaseTotals() {
            const rows = document.querySelectorAll('#tc-map tbody tr:not(.sec-hdr)');
            const totals = {};

            this.CALC_ORDER.forEach(rid => totals[rid] = 0);

            let calculatedRows = 0;

            rows.forEach(tr => {
                const cells = tr.querySelectorAll('.opt-cell');
                let hasValues = false;

                this.CALC_ORDER.forEach((rid, idx) => {
                    const cell = cells[idx];
                    if (!cell) return;

                    const text = (cell.querySelector('.sys')?.textContent || '').trim();
                    if (!text || text === '—') return;

                    const val = parseFloat(text.replace(/\s/g, '').replace(',', '.'));
                    if (!isNaN(val)) {
                        totals[rid] += val;
                        hasValues = true;
                    }
                });

                if (hasValues) calculatedRows++;
            });

            return {
                rows: rows.length,
                calculatedRows,
                baseMat: Number(totals['PRICE_FOR_ALL_MATERIAL'] || 0),
                baseWorks: Number(totals['PRICE_FOR_ALL_WORK'] || 0),
                baseTotal: Number(totals['TOTAL_PRICE'] || 0)
            };
        },

        renderMetricCards(container, { titleMat, titleWorks, titleTotal, mainMat, mainWorks, mainTotal }) {
            const fmt = n => n.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            const card = (title, main) => `
          <div class="metric-card">
            <div class="metric-title">${title}</div>
            <div class="metric-value">${fmt(main)}</div>
          </div>`;

            container.innerHTML = [
                card(titleMat, mainMat),
                card(titleWorks, mainWorks),
                card(titleTotal, mainTotal)
            ].join('');
        },

        updateSummary() {
            const base = this.computeBaseTotals();
            const noteBase = document.getElementById('summary-note-base');
            const boxBase = document.getElementById('metrics-base');

            if (noteBase) {
                noteBase.textContent = `Рассчитано строк: ${base.calculatedRows} из ${base.rows}`;
            }

            if (boxBase) {
                this.renderMetricCards(boxBase, {
                    titleMat: 'Материалы',
                    titleWorks: 'Работы',
                    titleTotal: 'Итого',
                    mainMat: base.baseMat,
                    mainWorks: base.baseWorks,
                    mainTotal: base.baseTotal
                });
            }

            // Триггер для других модулей
            if (window.EstimateSections) {
                window.EstimateSections.updateSectionTotals();
            }
        },

        async prefillExistingMappings(existingMappings) {
            const mappingEntries = Object.entries(existingMappings);

            if (mappingEntries.length === 0) {
                this.updateSummary();
                return;
            }

            const calcPromises = [];

            mappingEntries.forEach(([rowIndex, mapping]) => {
                const tr = document.querySelector(`tr[data-row="${rowIndex}"]`);
                if (!tr) return;

                const tcInput = tr.querySelector('.js-tc-autocomplete');
                const qtyInput = tr.querySelector('.qty-input');

                if (tcInput && mapping.tc_id && mapping.tc_name) {
                    tcInput.value = mapping.tc_name;
                    tcInput.dataset.id = mapping.tc_id;
                    tcInput.dataset.text = mapping.tc_name;
                    tcInput.style.background = '#e7f3ff';

                    const openLink = tcInput.parentElement?.querySelector('.tc-open-link');
                    if (openLink) {
                        const id = parseInt(mapping.tc_id || '0', 10) || 0;
                        if (id > 0) {
                            openLink.href = window.tcChangeUrl ? window.tcChangeUrl(id) : '#';
                            openLink.style.display = 'block';
                        } else {
                            openLink.removeAttribute('href');
                            openLink.style.display = 'none';
                        }
                    }

                    const clearBtn = tcInput.parentElement?.querySelector('.tc-clear-btn');
                    if (clearBtn) clearBtn.style.display = 'block';
                }

                if (qtyInput && mapping.quantity) {
                    qtyInput.value = mapping.quantity;
                }

                if (mapping.tc_id && mapping.quantity > 0) {
                    calcPromises.push(this.triggerRowCalc(tr));
                }
            });

            if (calcPromises.length > 0) {
                await Promise.all(calcPromises);
            }

            this.updateSummary();
        },

        async recalcAllRows() {
            const rows = document.querySelectorAll('#tc-map tbody tr:not(.sec-hdr)');
            const promises = [];

            rows.forEach(tr => {
                const qtyInput = tr.querySelector('.qty-input');
                const tcInput = tr.querySelector('.js-tc-autocomplete');
                const tcId = parseInt(tcInput?.dataset.id || '0', 10) || 0;
                const qty = parseFloat((qtyInput?.value || '').replace(',', '.')) || 0;

                if (tcId > 0 && qty > 0) {
                    promises.push(this.triggerRowCalc(tr));
                }
            });

            await Promise.all(promises);
            this.updateSummary();
        }
    };

    window.EstimateCalc = EstimateCalc;
})(window);