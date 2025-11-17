// path: src/app_outlay/static/app_outlay/js/estimate_sections.js
/**
 * Модуль управления секциями (аккордеон, древовидная структура)
 */
(function (window) {
    'use strict';

    const EstimateSections = {
        CALC_ORDER: [],
        tree: null,
        nodeIdCounter: 0,
        initialized: false,

        init(calcOrder) {
            console.log('🔧 EstimateSections.init() начало');

            this.CALC_ORDER = calcOrder;
            this.nodeIdCounter = 0;
            this.initialized = false;

            this.buildTree();

            if (!this.tree) {
                console.warn('⚠️ Tree не построено, создаём пустой ROOT');
                this.tree = {
                    name: 'ROOT',
                    level: -1,
                    children: [],
                    items: [],
                    path: '',
                    color: null,
                    nodeId: 'root'
                };
            }

            this.renderTree();
            this._bindCollapseButtons();

            this.initialized = true;

            console.log('✅ EstimateSections инициализирован, initialized =', this.initialized);
        },

        _generateNodeId() {
            return `node-${++this.nodeIdCounter}`;
        },

        buildTree() {
            const dataEl = document.getElementById('table-sections-data');
            if (!dataEl) {
                console.warn('⚠️ table-sections-data не найден в DOM');
                return;
            }

            let sections = [];
            try {
                const content = dataEl.textContent || '[]';
                sections = JSON.parse(content);
                console.log(`📊 Парсинг успешен: ${sections.length} секций`);
            } catch (e) {
                console.error('❌ Ошибка парсинга table-sections-data:', e);
                return;
            }

            if (!sections || sections.length === 0) {
                console.warn('⚠️ table-sections пустой');
                return;
            }

            console.log(`📊 Построение дерева из ${sections.length} секций`);

            const root = {
                name: 'ROOT',
                level: -1,
                children: [],
                items: [],
                path: '',
                color: null,
                nodeId: 'root'
            };

            sections.forEach(sec => {
                const pathParts = (sec.path || '').split('/').map(s => s.trim()).filter(Boolean);

                if (pathParts.length === 0) {
                    (sec.items || []).forEach(item => {
                        root.items.push({
                            ...item,
                            level: 0,
                            color: sec.color,
                            parentNodeId: 'root'
                        });
                    });
                    return;
                }

                let currentNode = root;
                let currentPath = '';

                pathParts.forEach((part, idx) => {
                    currentPath = currentPath ? `${currentPath} / ${part}` : part;

                    let childNode = currentNode.children.find(c => c.name === part);

                    if (!childNode) {
                        childNode = {
                            name: part,
                            level: idx,
                            children: [],
                            items: [],
                            path: currentPath,
                            color: idx === pathParts.length - 1 ? sec.color : null,
                            nodeId: this._generateNodeId(),
                            parentNode: currentNode
                        };
                        currentNode.children.push(childNode);
                    }

                    currentNode = childNode;
                });

                (sec.items || []).forEach(item => {
                    currentNode.items.push({
                        ...item,
                        level: pathParts.length,
                        color: sec.color,
                        parentNodeId: currentNode.nodeId
                    });
                });
            });

            this.tree = root;
            console.log(`✅ Дерево построено: ${this.nodeIdCounter} узлов, ${root.items.length} корневых items`);
        },

        renderTree() {
            const tbody = document.getElementById('tc-map-body');
            if (!tbody) {
                console.error('❌ tc-map-body не найден');
                return;
            }

            tbody.innerHTML = '';

            if (!this.tree) {
                console.warn('⚠️ Tree не инициализирован, пропускаем рендеринг');
                return;
            }

            this._renderNode(this.tree, tbody);
            console.log('✅ Дерево отрендерено');
        },

        _renderNode(node, container) {
            if (node.level >= 0) {
                const nodeRow = this._createNodeRow(node);
                container.appendChild(nodeRow);
            }

            (node.items || []).forEach((item, idx) => {
                const itemRow = this._createItemRow(item, `item-${node.nodeId}-${idx}`);
                container.appendChild(itemRow);
            });

            (node.children || []).forEach(child => {
                this._renderNode(child, container);
            });
        },

        _createNodeRow(node) {
            const tr = document.createElement('tr');
            tr.className = 'tree-node-row';
            tr.dataset.nodeId = node.nodeId;
            tr.dataset.level = node.level;

            const td = document.createElement('td');
            td.colSpan = this._getColSpan();
            td.className = 'tree-node-cell';
            td.dataset.level = node.level;

            // Применяем цвет к border
            if (node.color) {
                td.style.borderLeftColor = node.color;
            }

            const hasChildren = (node.children || []).length > 0 || (node.items || []).length > 0;

            // Создаём внутренний контейнер
            const inner = document.createElement('div');
            inner.className = 'tree-node-cell-inner';

            inner.innerHTML = `
                <span class="tree-indent"></span>
                <span class="tree-toggle ${!hasChildren ? 'is-leaf' : ''}">▼</span>
                <div class="tree-node-content">
                    <span class="tree-node-name" title="${this._escapeHtml(node.name)}">${this._escapeHtml(node.name)}</span>
                </div>
                <div class="tree-node-totals" style="display: none;"></div>
            `;

            td.appendChild(inner);
            tr.appendChild(td);

            if (hasChildren) {
                tr.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this._toggleNode(node.nodeId);
                });
            }

            return tr;
        },

        _createItemRow(item, itemId) {
            const tr = document.createElement('tr');
            tr.className = 'tree-data-row';
            tr.dataset.row = item.row_index;
            tr.dataset.itemId = itemId;
            tr.dataset.level = item.level;
            tr.dataset.parentNodeId = item.parentNodeId || '';

            const optCols = window.OPTIONAL_COLS || [];

            let optCells = '';
            (item.opt_values || []).forEach(col_data => {
                optCells += `
                    <td class="cell-2lines opt-cell" data-rid="${col_data.rid}">
                        <div class="sys">—</div>
                        <div class="muted">xls: ${this._escapeHtml(col_data.value || '—')}</div>
                    </td>
                `;
            });

            tr.innerHTML = `
                <td>${this._escapeHtml(item.name || '')}</td>
                <td>${this._escapeHtml(item.unit || '')}</td>
                <td>
                    <input type="number" step="0.01" class="qty-input" value="${item.qty || ''}" placeholder="0">
                </td>
                <td>
                    <input type="text" class="tc-input js-tc-autocomplete" placeholder="Найти ТК…" data-id="" data-text="">
                    <div class="muted">строка Excel: ${item.row_index}</div>
                </td>
                ${optCells}
            `;

            return tr;
        },

        _escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        },

        _toggleNode(nodeId) {
            const nodeRow = document.querySelector(`[data-node-id="${nodeId}"]`);
            if (!nodeRow) return;

            const isCollapsed = nodeRow.classList.toggle('is-collapsed');
            this._setChildrenVisibility(nodeId, !isCollapsed);
        },

        _setChildrenVisibility(nodeId, visible) {
            if (!this.tree) return;

            const node = this._findNodeById(this.tree, nodeId);
            if (!node) {
                console.warn('Node not found:', nodeId);
                return;
            }

            (node.items || []).forEach((item, idx) => {
                const itemId = `item-${nodeId}-${idx}`;
                const itemRow = document.querySelector(`[data-item-id="${itemId}"]`);
                if (itemRow) {
                    itemRow.style.display = visible ? '' : 'none';
                }
            });

            (node.children || []).forEach(child => {
                const childRow = document.querySelector(`[data-node-id="${child.nodeId}"]`);
                if (childRow) {
                    childRow.style.display = visible ? '' : 'none';
                    if (!visible || !childRow.classList.contains('is-collapsed')) {
                        this._setChildrenVisibility(child.nodeId, visible);
                    }
                }
            });
        },

        _findNodeById(node, nodeId) {
            if (!node) return null;
            if (node.nodeId === nodeId) return node;

            for (const child of (node.children || [])) {
                const found = this._findNodeById(child, nodeId);
                if (found) return found;
            }

            return null;
        },

        updateSectionTotals() {
            if (!this.initialized) {
                console.warn('⚠️ EstimateSections.initialized =', this.initialized, '- пропускаем updateSectionTotals');
                return;
            }

            if (!this.tree) {
                console.warn('⚠️ Tree не инициализирован, пропускаем updateSectionTotals');
                return;
            }

            const nodeTotals = {};

            document.querySelectorAll('.tree-data-row').forEach(tr => {
                if (tr.style.display === 'none') return;

                const calcDataStr = tr.dataset.calcData;
                if (!calcDataStr) return;

                try {
                    const calc = JSON.parse(calcDataStr);
                    const mat = Number(calc.PRICE_FOR_ALL_MATERIAL || 0);
                    const work = Number(calc.PRICE_FOR_ALL_WORK || 0);
                    const total = Number(calc.TOTAL_PRICE || 0);

                    const parentNodeId = tr.dataset.parentNodeId;
                    if (!parentNodeId) return;

                    if (!nodeTotals[parentNodeId]) {
                        nodeTotals[parentNodeId] = { mat: 0, work: 0, total: 0 };
                    }

                    nodeTotals[parentNodeId].mat += mat;
                    nodeTotals[parentNodeId].work += work;
                    nodeTotals[parentNodeId].total += total;
                } catch (e) {
                    console.warn('Parse calcData error:', e);
                }
            });

            this._aggregateTotalsUp(this.tree, nodeTotals);

            Object.keys(nodeTotals).forEach(nodeId => {
                if (nodeId === 'root') return;

                const data = nodeTotals[nodeId];
                const nodeRow = document.querySelector(`[data-node-id="${nodeId}"]`);
                if (!nodeRow) return;

                const totalsDiv = nodeRow.querySelector('.tree-node-totals');
                if (!totalsDiv) return;

                if (data.total > 0) {
                    const fmt = n => n.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

                    totalsDiv.innerHTML = `
                        <div class="total-item">
                            <span class="total-label">МАТ:</span>
                            <span class="total-value">${fmt(data.mat)}</span>
                        </div>
                        <span class="divider"></span>
                        <div class="total-item">
                            <span class="total-label">РАБ:</span>
                            <span class="total-value">${fmt(data.work)}</span>
                        </div>
                        <span class="divider"></span>
                        <div class="total-item">
                            <span class="total-label">Итого:</span>
                            <span class="total-value">${fmt(data.total)}</span>
                        </div>
                    `;
                    totalsDiv.style.display = 'flex';
                } else {
                    totalsDiv.style.display = 'none';
                }
            });
        },

        _aggregateTotalsUp(node, nodeTotals) {
            if (!node || !node.children) return;

            (node.children || []).forEach(child => {
                this._aggregateTotalsUp(child, nodeTotals);

                if (nodeTotals[child.nodeId] && node.nodeId !== 'root') {
                    if (!nodeTotals[node.nodeId]) {
                        nodeTotals[node.nodeId] = { mat: 0, work: 0, total: 0 };
                    }
                    nodeTotals[node.nodeId].mat += nodeTotals[child.nodeId].mat;
                    nodeTotals[node.nodeId].work += nodeTotals[child.nodeId].work;
                    nodeTotals[node.nodeId].total += nodeTotals[child.nodeId].total;
                }
            });
        },

        _getColSpan() {
            const optCols = window.OPTIONAL_COLS || [];
            return 4 + optCols.length;
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
            document.querySelectorAll('.tree-node-row').forEach(nodeRow => {
                const nodeId = nodeRow.dataset.nodeId;
                if (!nodeRow.classList.contains('is-collapsed')) {
                    nodeRow.classList.add('is-collapsed');
                    this._setChildrenVisibility(nodeId, false);
                }
            });
        },

        expandAll() {
            document.querySelectorAll('.tree-node-row').forEach(nodeRow => {
                const nodeId = nodeRow.dataset.nodeId;
                if (nodeRow.classList.contains('is-collapsed')) {
                    nodeRow.classList.remove('is-collapsed');
                    this._setChildrenVisibility(nodeId, true);
                }
            });
        }
    };

    window.EstimateSections = EstimateSections;
})(window);