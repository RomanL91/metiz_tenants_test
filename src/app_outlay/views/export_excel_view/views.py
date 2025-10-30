# path: src/app_outlay/views/export_excel_view/views.py
"""
Views (контроллеры) для экспорта сметы в Excel.

Архитектура:
- Thin Controllers: минимум логики, делегирование в сервис
- Django Messages: стандартные сообщения для пользователя
- Clear Flow: валидация → сервис → ответ
"""

import os
from django.views import View
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib import messages
from django.urls import reverse

from .services import ExcelExportService
from .exceptions import ExcelExportError


class EstimateExportExcelView(View):
    """
    Экспорт сметы в Excel с расчётами.

    **Endpoint:** GET /api/outlay/estimates/{estimate_id}/export-excel/

    **Response:**
    - Success: Binary Excel file для скачивания
    - Error: Redirect на страницу сметы с Django message

    **Use Case:**
    Экспорт рассчитанной сметы обратно в исходный Excel файл
    с заполненными значениями на основе техкарт, НР и НДС.

    **Features:**
    - Запись количества (QTY)
    - Запись цен материалов/работ
    - Учёт накладных расходов (НР)
    - Учёт НДС
    - Сохранение форматирования исходного файла

    **Permissions:**
    Доступ через Django Admin (проверяется в urls.py)
    """

    def get(self, request, estimate_id: int):
        """
        Обработка GET запроса экспорта.

        Алгоритм:
        1. Создание сервиса экспорта
        2. Выполнение экспорта (валидация, расчёты, запись)
        3. Чтение временного файла
        4. Формирование HTTP-ответа с файлом
        5. Удаление временного файла

        При ошибках:
        - Добавляет сообщение через Django messages
        - Редиректит обратно на страницу редактирования сметы

        Args:
            request: Django Request
            estimate_id: ID сметы из URL

        Returns:
            HttpResponse: Excel файл (binary) или редирект при ошибке

        Example:
            GET /api/outlay/estimates/123/export-excel/

            Success: <binary Excel file>
            Error: Redirect to /admin/app_outlay/estimate/123/change/
        """
        # URL для редиректа при ошибках
        redirect_url = self._get_redirect_url(request, estimate_id)

        try:
            # Шаг 1: Создание сервиса
            service = ExcelExportService(estimate_id=estimate_id)

            # Шаг 2: Экспорт
            temp_path, output_filename, updated_count = service.export_to_excel()

            # Шаг 3: Чтение файла
            with open(temp_path, "rb") as f:
                file_content = f.read()

            # Шаг 4: Формирование ответа
            response = HttpResponse(
                file_content,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            response["Content-Disposition"] = (
                f'attachment; filename="{output_filename}"'
            )

            # Шаг 5: Удаление временного файла
            try:
                os.unlink(temp_path)
            except Exception:
                pass  # Не критично

            # Success message
            messages.success(
                request,
                f"✅ Экспорт выполнен успешно! Обновлено строк: {updated_count}",
            )

            return response

        except ExcelExportError as e:
            # Доменные ошибки → сообщение пользователю
            if "не найдена" in e.message.lower():
                messages.error(request, f"❌ {e.message}")
            elif "не найден" in e.message.lower():
                messages.error(request, f"⚠️ {e.message}")
            else:
                messages.warning(request, f"⚠️ {e.message}")

            return HttpResponseRedirect(redirect_url)

        except Exception as e:
            # Неожиданные ошибки → сообщение разработчикам
            messages.error(
                request, f"❌ Ошибка экспорта: {str(e)}. Обратитесь к администратору."
            )
            return HttpResponseRedirect(redirect_url)

    def _get_redirect_url(self, request, estimate_id: int) -> str:
        """
        Получение URL для редиректа при ошибках.

        Пытается вернуть на страницу редактирования сметы.
        Если не получается - возвращает на HTTP_REFERER или корень админки.

        Args:
            request: Django Request
            estimate_id: ID сметы

        Returns:
            str: URL для редиректа
        """
        try:
            # Попытка построить URL админки
            from app_outlay.models import Estimate

            return reverse(
                f"admin:{Estimate._meta.app_label}_{Estimate._meta.model_name}_change",
                args=[estimate_id],
            )
        except Exception:
            # Fallback: HTTP_REFERER или корень
            return request.META.get("HTTP_REFERER", "/admin/")
