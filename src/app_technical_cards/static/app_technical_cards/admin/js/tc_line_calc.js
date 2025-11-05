/**
 * Автоматический пересчёт стоимости строк материалов/работ
 * при изменении количества или цены
 */

(function ($) {
    'use strict';

    // Ждём полной загрузки DOM
    $(document).ready(function () {

        // Функция пересчёта одной строки
        function recalculateLine(row) {
            // Находим поля qty и price в текущей строке
            var qtyInput = row.find('input[name*="qty_per_unit"]');
            var priceInput = row.find('input[name*="price_per_unit"]');
            var costCell = row.find('td:last'); // Последняя ячейка с readonly полем

            if (qtyInput.length && priceInput.length) {
                var qty = parseFloat(qtyInput.val()) || 0;
                var price = parseFloat(priceInput.val()) || 0;
                var total = qty * price;

                // Определяем цвет в зависимости от суммы
                var color = total > 1000 ? '#e53935' : '#43a047';

                // Обновляем отображение
                costCell.html(
                    '<strong style="color: ' + color + ';">' +
                    total.toFixed(2) +
                    '</strong>'
                );

                // Добавляем анимацию
                costCell.addClass('cost-updated');
                setTimeout(function () {
                    costCell.removeClass('cost-updated');
                }, 300);
            }
        }

        // Функция пересчёта итогов версии (опционально)
        function recalculateVersionTotals(versionBlock) {
            var materialTotal = 0;
            var workTotal = 0;

            // Считаем материалы
            versionBlock.find('.tcvmaterialnestedinline-group tr').each(function () {
                var row = $(this);
                var qty = parseFloat(row.find('input[name*="qty_per_unit"]').val()) || 0;
                var price = parseFloat(row.find('input[name*="price_per_unit"]').val()) || 0;
                materialTotal += qty * price;
            });

            // Считаем работы
            versionBlock.find('.tcvworknestedinline-group tr').each(function () {
                var row = $(this);
                var qty = parseFloat(row.find('input[name*="qty_per_unit"]').val()) || 0;
                var price = parseFloat(row.find('input[name*="price_per_unit"]').val()) || 0;
                workTotal += qty * price;
            });

            var grandTotal = materialTotal + workTotal;

            // Обновляем блок с итогами (если есть)
            var costBlock = versionBlock.find('.cost_breakdown_display');
            if (costBlock.length) {
                costBlock.html(
                    '<div style="font-family: monospace; line-height: 1.8; padding: 10px; background: #f5f5f5; border-radius: 8px;">' +
                    '<div>Материалы: <strong style="color: #7b1fa2;">' + materialTotal.toFixed(2) + ' ₽</strong></div>' +
                    '<div>Работы: <strong style="color: #388e3c;">' + workTotal.toFixed(2) + ' ₽</strong></div>' +
                    '<hr style="margin: 8px 0; border: none; border-top: 2px solid #333;">' +
                    '<div>ИТОГО: <strong style="font-size: 1.2em; color: #d32f2f;">' + grandTotal.toFixed(2) + ' ₽</strong></div>' +
                    '</div>'
                );
            }
        }

        // Обработчик изменений для qty и price
        $(document).on('input change', 'input[name*="qty_per_unit"], input[name*="price_per_unit"]', function () {
            var input = $(this);
            var row = input.closest('tr');

            // Пересчитываем текущую строку
            recalculateLine(row);

            // Пересчитываем итоги версии
            var versionBlock = input.closest('.djn-inline-form');
            if (versionBlock.length) {
                recalculateVersionTotals(versionBlock);
            }
        });

        // Обработчик для добавления новых строк (через django-nested-admin)
        $(document).on('formset:added', function (event, $row, formsetName) {
            // Инициализируем пересчёт для новой строки
            setTimeout(function () {
                recalculateLine($row);
            }, 100);
        });

        // Обработчик для удаления строк
        $(document).on('formset:removed', function (event, $row, formsetName) {
            // Пересчитываем итоги после удаления
            var versionBlock = $row.closest('.djn-inline-form');
            if (versionBlock.length) {
                setTimeout(function () {
                    recalculateVersionTotals(versionBlock);
                }, 100);
            }
        });

        // Инициализация при загрузке страницы
        $('tr.djn-item').each(function () {
            recalculateLine($(this));
        });

        console.log('✅ TC Line Calculator initialized');
    });

    // Добавляем CSS для анимации
    $('<style>')
        .text('.cost-updated { animation: pulse 0.3s ease-in-out; } ' +
            '@keyframes pulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.1); } }')
        .appendTo('head');

})(django.jQuery || jQuery);