import json

from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import path
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from app_estimate_imports.handlers import HandlerFactory
from app_estimate_imports.models import (ImportedEstimateFile, ParseMarkup,
                                         ParseResult)
from app_estimate_imports.services.materialization_service import \
    MaterializationService
from app_estimate_imports.services.parse_service import ParseService
from app_estimate_imports.utils.file_utils import FileUtils


class ParseMarkupInline(admin.TabularInline):
    """Инлайн для просмотра JSON разметки"""

    model = ParseMarkup
    can_delete = False
    extra = 0
    readonly_fields = ("updated_at", "annotation_pretty")
    fields = ("updated_at", "annotation_pretty")

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def annotation_pretty(self, instance: ParseMarkup):
        if not instance or not instance.annotation:
            return "—"

        payload = json.dumps(instance.annotation, ensure_ascii=False, indent=2)
        return format_html(
            "<details><summary>JSON разметки</summary>"
            '<pre style="max-height:480px;overflow:auto;white-space:pre-wrap;">{}</pre>'
            "</details>",
            mark_safe(payload),
        )

    annotation_pretty.short_description = "Просмотр JSON разметки"


class ParseResultInline(admin.TabularInline):
    """Инлайн для просмотра результатов парсинга"""

    model = ParseResult
    can_delete = False
    extra = 0
    readonly_fields = ("created_at", "pretty_json")
    fields = ("created_at", "pretty_json")

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def pretty_json(self, instance: ParseResult) -> str:
        if not instance or not instance.data:
            return "—"

        try:
            payload = json.dumps(instance.data, ensure_ascii=False, indent=2)
        except Exception:
            payload = str(instance.data)

        return format_html(
            "<details><summary>Показать/скрыть JSON</summary>"
            '<pre style="max-height:480px;overflow:auto;white-space:pre-wrap;">{}</pre>'
            "</details>",
            mark_safe(payload),
        )

    pretty_json.short_description = "JSON результат"


@admin.register(ImportedEstimateFile)
class ImportedEstimateFileAdmin(admin.ModelAdmin):
    """Упрощенная админка с делегированием всей логики в обработчики"""

    # Конфигурация отображения
    list_display = (
        # "id",
        "original_name",
        "actions_col",
        "sheet_count",
        "size_kb",
        "uploaded_at",
        "sha256_short",
    )
    list_display_links = ("original_name",)
    search_fields = ("original_name", "sha256")
    readonly_fields = ("uploaded_at", "size_bytes", "sha256", "sheet_count")
    inlines = (ParseResultInline, ParseMarkupInline)
    actions = ("parse_now", "create_estimate_from_markup")
    date_hierarchy = "uploaded_at"

    # --- Методы отображения ---

    def size_kb(self, obj: ImportedEstimateFile) -> str:
        return FileUtils.format_file_size(obj.size_bytes or 0)

    size_kb.short_description = "Размер"

    def sha256_short(self, obj: ImportedEstimateFile) -> str:
        return (obj.sha256 or "")[:12] + "…" if obj.sha256 else "—"

    sha256_short.short_description = "SHA256"

    def actions_col(self, obj):
        """Генерирует кнопки действий"""
        buttons = []

        if hasattr(obj, "parse_result"):
            buttons.extend(
                [
                    format_html(
                        '<a class="button" href="{}">График</a>', f"./{obj.pk}/graph/"
                    ),
                    format_html(
                        '<a class="button" href="{}">Таблица</a>', f"./{obj.pk}/grid/"
                    ),
                ]
            )

        if hasattr(obj, "markup"):
            buttons.append(
                format_html(
                    '<a class="button" href="{}">Создать смету</a>',
                    f"./{obj.pk}/materialize/",
                )
            )

        return mark_safe("&nbsp;".join(buttons))

    actions_col.short_description = "Действия"

    # --- URL маршрутизация ---

    def get_urls(self):
        """Регистрация URL через обработчики"""
        urls = super().get_urls()

        custom_urls = [
            # Основные операции
            path(
                "<int:pk>/parse/",
                self.admin_site.admin_view(self._delegate("parse", "parse_file")),
                name="imports_parse",
            ),
            path(
                "<int:pk>/compose/",
                self.admin_site.admin_view(self._delegate("compose", "show_compose")),
                name="imports_compose",
            ),
            path(
                "<int:pk>/grid/",
                self.admin_site.admin_view(self._delegate("grid", "show_grid")),
                name="imports_grid",
            ),
            path(
                "<int:pk>/graph/",
                self.admin_site.admin_view(self._delegate("graph", "show_graph")),
                name="imports_graph",
            ),
            path(
                "<int:pk>/materialize/",
                self.admin_site.admin_view(self._delegate("parse", "materialize")),
                name="imports_materialize",
            ),
            # API endpoints
            path(
                "<int:pk>/api/save-schema/",
                self.admin_site.admin_view(self._delegate("api", "save_schema_api")),
                name="imports_api_save_schema",
            ),
            # path(
            #     "<int:pk>/api/extract-from-grid/",
            #     self.admin_site.admin_view(
            #         self._delegate("api", "extract_from_grid_api")
            #     ),
            #     name="imports_api_extract_from_grid",
            # ),
            path(
                "<int:pk>/api/groups/list/",
                self.admin_site.admin_view(self._delegate("api", "groups_list_api")),
                name="imports_groups_list",
            ),
            path(
                "<int:pk>/api/groups/create/",
                self.admin_site.admin_view(self._delegate("api", "groups_create_api")),
                name="imports_groups_create",
            ),
            path(
                "<int:pk>/api/groups/delete/",
                self.admin_site.admin_view(self._delegate("api", "groups_delete_api")),
                name="imports_groups_delete",
            ),
            path(
                "<int:pk>/api/graph-data/",
                self.admin_site.admin_view(self._delegate("graph", "graph_data_api")),
                name="imports_graph_data",
            ),
            path(
                "<int:pk>/api/auto-groups-from-colors/",
                self.admin_site.admin_view(
                    self._delegate("api", "auto_groups_from_colors_api")
                ),
                name="imports_api_auto_groups_colors",
            ),
        ]

        return custom_urls + urls

    def _delegate(self, handler_type: str, method_name: str):
        """Создает функцию-делегат для обработчика"""

        def wrapper(request, pk: int):
            try:
                handler = HandlerFactory.create(handler_type, self)
                method = getattr(handler, method_name)
                return method(request, pk)
            except Exception as e:
                messages.error(request, f"Ошибка обработки: {e!r}")
                return HttpResponseRedirect(request.META.get("HTTP_REFERER", ".."))

        return wrapper

    # --- Массовые действия ---

    def parse_now(self, request, queryset):
        """Парсит выбранные файлы"""
        handler = HandlerFactory.create("parse", self)
        ok, fail = handler.parse_multiple_files(request, queryset)

        if ok:
            messages.success(request, f"Распарсено успешно: {ok}")
        if fail and not ok:
            messages.error(request, "Ошибки при парсинге. См. сообщения выше.")

    parse_now.short_description = "Распарсить (синхронно)"

    def create_estimate_from_markup(self, request, queryset):
        """Создает сметы из разметки"""
        ok = 0
        for file_obj in queryset:
            try:
                if not hasattr(file_obj, "markup"):
                    messages.warning(request, f"[{file_obj}] нет разметки")
                    continue

                handler = HandlerFactory.create("parse", self)

                service = MaterializationService()
                if service.materialize_estimate(file_obj):
                    ok += 1
                else:
                    service.add_messages_to_request(request)

            except Exception as e:
                messages.error(request, f"[{file_obj}] ошибка материализации: {e!r}")

        if ok:
            messages.success(request, f"Создано смет: {ok}")

    create_estimate_from_markup.short_description = "Создать смету из разметки"

    # --- Редиректы после сохранения ---

    def response_add(self, request, obj, post_url_continue=None):
        """
        Переопределяет редирект после создания нового объекта.

        После загрузки файла всегда перенаправляет на таблицу для работы с данными.
        """
        if obj.file:
            # Файл загружен - идём на таблицу (парсинг уже выполнен в save_model)
            # Из /add/ нужно подняться на уровень вверх: ../{pk}/grid/
            return HttpResponseRedirect(f"../{obj.pk}/grid/")

        # Стандартное поведение для случаев без файла (не должно происходить в норме)
        return super().response_add(request, obj, post_url_continue)

    def response_change(self, request, obj):
        """
        Переопределяет редирект после изменения существующего объекта.

        После сохранения всегда перенаправляет на таблицу для работы с данными.
        """
        if obj.file:
            # Файл есть - идём на таблицу (парсинг выполнен в save_model при необходимости)
            # Из /{pk}/change/ переходим в /{pk}/grid/
            return HttpResponseRedirect(f"../grid/")

        # Стандартное поведение для случаев без файла
        return super().response_change(request, obj)

    # --- Сохранение модели ---

    def save_model(self, request, obj: ImportedEstimateFile, form, change):
        """Обновляет метаданные и автоматически запускает парсинг при сохранении"""
        # Проверяем, изменился ли файл
        file_changed = False
        old_sha256 = None

        if change:  # Это обновление существующего объекта
            try:
                old_obj = ImportedEstimateFile.objects.get(pk=obj.pk)
                old_sha256 = old_obj.sha256
            except ImportedEstimateFile.DoesNotExist:
                pass

        # Сохраняем объект
        super().save_model(request, obj, form, change)

        # Обновляем метаданные при загрузке/замене файла
        if obj.file and (not obj.sha256 or not obj.size_bytes):
            try:
                with obj.file.open("rb") as f:
                    obj.size_bytes = obj.file.size or 0
                    new_sha256 = FileUtils.compute_sha256(f)

                    # Проверяем, изменился ли файл
                    if old_sha256 and new_sha256 != old_sha256:
                        file_changed = True
                    elif not old_sha256:
                        file_changed = True

                    obj.sha256 = new_sha256

                obj.save(update_fields=["size_bytes", "sha256"])
            except Exception as e:
                messages.warning(request, f"Не удалось обновить метаданные: {e}")
                return

        # ОБЯЗАТЕЛЬНЫЙ автоматический парсинг
        # Парсим в случаях: новый файл, изменён файл, или нет результата
        should_parse = obj.file and (
            not change or file_changed or not hasattr(obj, "parse_result")
        )

        if should_parse:
            parse_service = ParseService()

            try:
                success = parse_service.parse_file(obj)

                if success:
                    # Обновляем sheet_count из результата парсинга
                    if hasattr(obj, "parse_result") and obj.parse_result.data:
                        sheet_count = obj.parse_result.data.get("file", {}).get(
                            "sheets", 0
                        )
                        if sheet_count:
                            obj.sheet_count = sheet_count
                            obj.save(update_fields=["sheet_count"])

                    messages.success(request, "✅ Файл успешно загружен и распарсен")
                else:
                    # Показываем ошибки из сервиса
                    parse_service.add_messages_to_request(request)
                    messages.warning(
                        request,
                        "⚠️ Файл сохранен, но парсинг завершился с ошибками. "
                        "Попробуйте перепарсить позже.",
                    )
            except Exception as e:
                messages.error(
                    request,
                    f"⚠️ Файл сохранен, но произошла ошибка при автопарсинге: {e!r}",
                )

        # Гарантируем наличие ParseResult для редиректа на /grid/
        # Если по какой-то причине ParseResult нет - создаём принудительно
        if obj.file and not hasattr(obj, "parse_result"):
            messages.info(
                request, "Запуск принудительного парсинга для создания данных..."
            )
            parse_service = ParseService()
            try:
                parse_service.parse_file(obj)
            except Exception as e:
                messages.error(
                    request,
                    f"⚠️ Не удалось создать ParseResult: {e!r}. "
                    "Таблица может быть недоступна.",
                )
