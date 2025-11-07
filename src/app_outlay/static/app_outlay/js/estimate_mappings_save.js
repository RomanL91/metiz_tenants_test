// path: src/app_outlay/static/app_outlay/js/estimate_mappings_save.js
/**
 * Модуль сохранения сопоставлений
 */
(function (window) {
    'use strict';

    const EstimateMappingsSave = {
        SAVE_MAPPINGS_URL: '',
        EXISTING_MAPPINGS: {},

        init(saveMappingsUrl, existingMappings) {
            this.SAVE_MAPPINGS_URL = saveMappingsUrl;
            this.EXISTING_MAPPINGS = existingMappings;
            this._bindSaveButton();
        },

        _getCsrfToken() {
            const input = document.querySelector('[name=csrfmiddlewaretoken]');
            if (input && input.value) return input.value;

            const m = document.cookie.match(/(?:^|;)\s*csrftoken=([^;]+)/);
            return m ? decodeURIComponent(m[1]) : '';
        },

        _bindSaveButton() {
            const btnSaveMappings = document.getElementById('btn-save-mappings');
            const statusSpan = document.getElementById('auto-match-status');

            if (!btnSaveMappings) return;

            btnSaveMappings.addEventListener('click', async () => {
                btnSaveMappings.disabled = true;
                statusSpan.textContent = 'Сохранение...';
                statusSpan.style.color = '#666';

                const { mappings, deletions } = this._collectMappings();

                if (mappings.length > 0 || deletions.length > 0) {
                    try {
                        const resp = await fetch(this.SAVE_MAPPINGS_URL, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-CSRFToken': this._getCsrfToken()
                            },
                            body: JSON.stringify({ mappings, deletions })
                        });

                        const data = await resp.json();

                        if (!data.ok) {
                            statusSpan.textContent = '❌ Ошибка сопоставлений: ' + (data.error || 'unknown');
                            statusSpan.style.color = '#721c24';
                            btnSaveMappings.disabled = false;
                            return;
                        }
                    } catch (e) {
                        console.error('Ошибка сохранения сопоставлений:', e);
                        statusSpan.textContent = '❌ Ошибка сети (сопоставления)';
                        statusSpan.style.color = '#721c24';
                        btnSaveMappings.disabled = false;
                        return;
                    }
                }

                statusSpan.textContent = 'Сохранение формы...';
                this._submitAdminForm(statusSpan);
            });
        },

        _collectMappings() {
            const mappings = [];
            const deletions = [];
            let currentSection = 'Без группы';

            document.querySelectorAll('#tc-map tbody tr').forEach(tr => {
                if (tr.classList.contains('sec-hdr')) {
                    const badge = tr.querySelector('.badge');
                    if (badge) currentSection = badge.textContent.trim();
                    return;
                }

                const tcInput = tr.querySelector('.js-tc-autocomplete');
                const qtyInput = tr.querySelector('.qty-input');
                const rowIndex = parseInt(tr.dataset.row || '0', 10);

                if (!tcInput || !qtyInput || !rowIndex) return;

                const verId = parseInt(tcInput.dataset.id || '0', 10) || 0;  // dataset.id = ID ВЕРСИИ
                const quantity = parseFloat((qtyInput.value || '0').replace(',', '.')) || 0;
                const hadMapping = (this.EXISTING_MAPPINGS[String(rowIndex)] != null);

                if (verId > 0 && quantity > 0) {
                    mappings.push({
                        section: currentSection,
                        tc_version_id: verId,
                        quantity,
                        row_index: rowIndex,
                        tc_name: tcInput.value
                    });
                } else if (hadMapping) {
                    deletions.push(rowIndex);
                }
            });

            return { mappings, deletions };
        },

        _submitAdminForm(statusSpan) {
            const adminForm = document.querySelector('form#estimate_form') ||
                Array.from(document.querySelectorAll('form')).find(f =>
                    f.querySelector('[name=csrfmiddlewaretoken]')
                );

            if (adminForm) {
                let cont = adminForm.querySelector('input[name="_continue"]');
                if (!cont) {
                    cont = document.createElement('input');
                    cont.type = 'hidden';
                    cont.name = '_continue';
                    cont.value = 'Save and continue editing';
                    adminForm.appendChild(cont);
                }
                adminForm.submit();
            } else {
                statusSpan.textContent = '✅ Сопоставления сохранены';
                statusSpan.style.color = '#155724';
                setTimeout(() => {
                    window.location.reload();
                }, 800);
            }
        }
    };

    window.EstimateMappingsSave = EstimateMappingsSave;
})(window);