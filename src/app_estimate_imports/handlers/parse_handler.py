"""
Модуль обработчика операций парсинга и материализации.

Назначение
----------
- Запуск парсинга загруженного файла и сохранение результата в JSON (ParseResult).
- Пакетный парсинг выбранных файлов из списка в админке.
- Выдача JSON пользователю для скачивания.
- Материализация (создание сущностей сметы) на основе сохранённой разметки.

Особенности
-----------
- Вся доменная логика инкапсулирована в сервисах:
  * ParseService — парсинг одиночного/нескольких файлов.
  * MaterializationService — материализация сметы из разметки.
- Handler отвечает за получение объекта, сообщения пользователю и HTTP-ответы.
"""

import json

from django.urls import reverse
from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect

from app_estimate_imports.handlers.base_handler import BaseHandler
from app_estimate_imports.services.parse_service import ParseService
from app_estimate_imports.services.materialization_service import MaterializationService


class ParseHandler(BaseHandler):
    """Обработчик операций парсинга и материализации"""

    def __init__(self, admin_instance):
        """
        Конструктор обработчика.

        :param admin_instance: Экземпляр ModelAdmin, через который выполняются действия в админке.
        """
        super().__init__(admin_instance)
        self.parse_service = ParseService()
        self.materialization_service = MaterializationService()

    def parse_file(self, request: HttpRequest, pk: int) -> HttpResponse:
        """
        Парсит файл по первичному ключу и создаёт/обновляет JSON (ParseResult).

        При успешном парсинге показывает сообщение об успехе, иначе — ошибки сервиса.

        :param request: Текущий HTTP-запрос.
        :param pk: Первичный ключ импортированного файла.
        :returns: Redirect на страницу изменения объекта (../<pk>/change/).
        """
        obj = self.get_object_or_error(request, pk)
        if not obj:
            return self.redirect_back_or_change(request)

        success = self.parse_service.parse_file(obj)

        if success:
            messages.success(request, "Готово: JSON создан/обновлён")
        else:
            self.parse_service.add_messages_to_request(request)

        return HttpResponseRedirect(f"../{obj.pk}/change/")

    def parse_multiple_files(self, request: HttpRequest, queryset) -> tuple[int, int]:
        """
        Пакетно парсит выбранные файлы из списка в админке.

        :param request: Текущий HTTP-запрос.
        :param queryset: QuerySet выбранных ImportedEstimateFile.
        :returns: Кортеж (успешно, с ошибками), где:
                  - успешно: количество успешно распарсенных файлов,
                  - с ошибками: количество файлов, завершившихся с ошибкой.
        """
        return self.parse_service.parse_multiple_files(queryset)

    def download_json(self, request: HttpRequest, pk: int) -> HttpResponse:
        """
        Отдаёт на скачивание JSON-результат парсинга.

        Если ParseResult отсутствует — выводит предупреждение и перенаправляет назад.

        :param request: Текущий HTTP-запрос.
        :param pk: Первичный ключ импортированного файла.
        :returns: HttpResponse с application/json (attachment) или redirect обратно.
        """
        obj = self.get_object_or_error(request, pk)
        if not obj or not hasattr(obj, "parse_result"):
            messages.warning(request, "JSON ещё не создан")
            return self.redirect_back_or_change(request, obj)

        payload = json.dumps(obj.parse_result.data, ensure_ascii=False, indent=2)
        response = HttpResponse(payload, content_type="application/json; charset=utf-8")

        safe_name = (obj.original_name or f"file_{obj.pk}").rsplit(".", 1)[0]
        response["Content-Disposition"] = f'attachment; filename="{safe_name}.json"'

        return response

    def materialize(self, request: HttpRequest, pk: int) -> HttpResponse:
        """
        Материализует смету из сохранённой разметки.

        Требует, чтобы у файла уже существовал объект разметки (markup).
        В случае успеха показывает сообщение «Смета создана», иначе — сообщения сервиса.

        :param request: Текущий HTTP-запрос.
        :param pk: Первичный ключ импортированного файла.
        :returns: Redirect на страницу изменения объекта (../<pk>/change/).
        """
        obj = self.get_object_or_error(request, pk)
        if not obj or not hasattr(obj, "markup"):
            messages.error(request, "Нет разметки для материализации")
            return self.redirect_back_or_change(request)

        result = self.materialization_service.materialize_estimate(obj)

        # Успех: пришёл объект Estimate → редиректим на его change
        if result is not None and hasattr(result, "pk"):
            estimate = result
            urlname = (
                f"admin:{estimate._meta.app_label}_{estimate._meta.model_name}_change"
            )
            messages.success(request, "Смета создана")
            return HttpResponseRedirect(reverse(urlname, args=[estimate.pk]))

        # Ошибка
        self.materialization_service.add_messages_to_request(request)
        return self.redirect_back_or_change(request)
