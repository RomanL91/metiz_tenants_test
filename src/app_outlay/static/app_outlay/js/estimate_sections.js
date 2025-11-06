// path: src/app_outlay/static/app_outlay/js/estimate_sections.js
/**
 * Модуль управления секциями (коллапс, итоги)
 */
(function (window) {
    'use strict';

    const EstimateSections = {
        CALC_ORDER: [],

        init(calcOrder) {
            this.CALC_ORDER = calcOrder;
            this.initSectionCollapse();
            this.updateSectionTotals();
            this._bindCollapseButtons();
        },

        initSectionCollapse() {
            document.querySelectorAll('.sec-hdr').forEach(hdr => {
                hdr.addEventListener('click', function () {
                    const sectionId = this.dataset.sectionId;
                    const isCollapsed = this.classList.toggle('collapsed');

                    document.querySelectorAll(`tr[data-section-id="${sectionId}"]:not(.sec-hdr)`).forEach(row => {
                        row.style.display = isCollapsed ? 'none' : '';
                    });
                });
            });
        },

        updateSectionTotals() {
            const sections = {};

            document.querySelectorAll('#tc-map tbody tr[data-row]').forEach(tr => {
                const sectionId = tr.dataset.sectionId;
                if (!sectionId) return;

                if (!sections[sectionId]) {
                    sections[sectionId] = {
                        mat: 0,
                        work: 0,
                        total: 0,
                        count: 0
                    };
                }

                if (tr.style.display === 'none') return;

                // Читаем из data-атрибута (как в computeBaseTotals)
                const calcDataStr = tr.dataset.calcData;
                if (!calcDataStr) return;

                try {
                    const calc = JSON.parse(calcDataStr);

                    const mat = Number(calc.PRICE_FOR_ALL_MATERIAL || 0);
                    const work = Number(calc.PRICE_FOR_ALL_WORK || 0);
                    const total = Number(calc.TOTAL_PRICE || 0);

                    if (mat > 0 || work > 0 || total > 0) {
                        sections[sectionId].mat += mat;
                        sections[sectionId].work += work;
                        sections[sectionId].total += total;
                        sections[sectionId].count++;
                    }
                } catch (e) {
                    console.warn('Parse calcData error in section:', e);
                }
            });

            Object.keys(sections).forEach(sectionId => {
                const data = sections[sectionId];
                const hdr = document.querySelector(`.sec-hdr[data-section-id="${sectionId}"]`);
                if (!hdr) return;

                const totalsSpan = hdr.querySelector('.sec-totals');
                if (!totalsSpan) return;

                if (data.count > 0) {
                    const mat = data.mat;
                    const works = data.work;
                    const total = data.total;

                    const fmt = n => n.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                    totalsSpan.textContent = `(МАТ: ${fmt(mat)} | РАБ: ${fmt(works)} | Итого: ${fmt(total)})`;
                } else {
                    totalsSpan.textContent = '';
                }
            });
        },

        _bindCollapseButtons() {
            const btnCollapseAll = document.getElementById('btn-collapse-all');
            const btnExpandAll = document.getElementById('btn-expand-all');

            if (btnCollapseAll) {
                btnCollapseAll.addEventListener('click', () => this.collapseAll());
            }

            if (btnExpandAll) {
                btnExpandAll.addEventListener('click', () => this.expandAll());
            }
        },

        collapseAll() {
            document.querySelectorAll('.sec-hdr').forEach(hdr => {
                const sectionId = hdr.dataset.sectionId;
                if (!hdr.classList.contains('collapsed')) {
                    hdr.classList.add('collapsed');
                    document.querySelectorAll(`tr[data-section-id="${sectionId}"]:not(.sec-hdr)`).forEach(row => {
                        row.style.display = 'none';
                    });
                }
            });
        },

        expandAll() {
            document.querySelectorAll('.sec-hdr').forEach(hdr => {
                const sectionId = hdr.dataset.sectionId;
                if (hdr.classList.contains('collapsed')) {
                    hdr.classList.remove('collapsed');
                    document.querySelectorAll(`tr[data-section-id="${sectionId}"]:not(.sec-hdr)`).forEach(row => {
                        row.style.display = '';
                    });
                }
            });
        }
    };

    window.EstimateSections = EstimateSections;
})(window);