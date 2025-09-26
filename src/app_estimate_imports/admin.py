from __future__ import annotations

import json, secrets
from django.contrib import admin, messages
from django.http import HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import ImportedEstimateFile, ParseResult, ParseMarkup
from .services import parse_and_store, save_imported_file
from .services_markup import build_markup_skeleton
from app_estimate_imports.utils_markup import ensure_uids_in_tree

from app_outlay.services_materialize import materialize_estimate_from_markup
from app_estimate_imports.utils_excel import load_sheet_rows_full


# --- Роли колонок (код, заголовок, цвет, обязательность) ---
ROLE_DEFS = [
    ("NONE", "—", None, False),
    # обязательные для «захвата» ТК/работ
    ("NAME_OF_WORK", "НАИМЕНОВАНИЕ РАБОТ/ТК", "#E3F2FD", True),
    ("UNIT", "ЕД. ИЗМ.", "#FFF8E1", True),
    ("QTY", "КОЛ-ВО", "#E8F5E9", True),
    # опциональные стоимости
    ("UNIT_PRICE_OF_MATERIAL", "ЦЕНА МАТ/ЕД", "#F3E5F5", False),
    ("UNIT_PRICE_OF_WORK", "ЦЕНА РАБОТЫ/ЕД", "#EDE7F6", False),
    ("UNIT_PRICE_OF_MATERIALS_AND_WORKS", "ЦЕНА МАТ+РАБ/ЕД", "#E1F5FE", False),
    ("PRICE_FOR_ALL_MATERIAL", "ИТОГО МАТЕРИАЛ", "#FBE9E7", False),
    ("PRICE_FOR_ALL_WORK", "ИТОГО РАБОТА", "#FFF3E0", False),
    ("TOTAL_PRICE", "ОБЩАЯ ЦЕНА", "#FFEBEE", False),
]
# удобные представления
ROLE_DEFS = [
    {"id": rid, "title": title, "color": color or "#ffffff", "required": required}
    for (rid, title, color, required) in ROLE_DEFS
]
ROLE_IDS = [r["id"] for r in ROLE_DEFS]
REQUIRED_ROLE_IDS = [r["id"] for r in ROLE_DEFS if r["required"]]

# ----- Инлайн для просмотра JSON прямо на карточке файла -----


class ParseMarkupInline(admin.StackedInline):
    model = ParseMarkup
    can_delete = False
    extra = 0
    readonly_fields = ("updated_at", "annotation_pretty")
    fields = ("annotation", "updated_at", "annotation_pretty")

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


class ParseResultInline(admin.StackedInline):
    model = ParseResult
    can_delete = False
    extra = 0
    readonly_fields = ("estimate_name", "created_at", "pretty_json")
    fields = ("estimate_name", "created_at", "pretty_json")

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


# ----- Админ импортированного файла -----


@admin.register(ImportedEstimateFile)
class ImportedEstimateFileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "original_name",
        "size_kb",
        "sheet_count",
        "uploaded_at",
        "sha256_short",
        "has_result",
        "actions_col",
    )
    list_display_links = ("id", "original_name")
    search_fields = ("original_name", "sha256")
    readonly_fields = ("uploaded_at", "size_bytes", "sha256", "sheet_count")
    inlines = (ParseResultInline, ParseMarkupInline)
    actions = ("parse_now",)

    # — колонки —

    def size_kb(self, obj: ImportedEstimateFile) -> str:
        return f"{(obj.size_bytes or 0)/1024:.1f} KB"

    size_kb.short_description = "Размер"

    def sha256_short(self, obj: ImportedEstimateFile) -> str:
        return (obj.sha256 or "")[:12] + "…" if obj.sha256 else "—"

    sha256_short.short_description = "SHA256"

    def has_result(self, obj: ImportedEstimateFile) -> str:
        return "✅" if hasattr(obj, "parse_result") else "—"

    has_result.short_description = "JSON"

    def actions_col(self, obj):
        buttons = [
            format_html(
                '<a class="button" href="{}">Распарсить</a>', self._parse_url(obj.pk)
            )
        ]
        if hasattr(obj, "parse_result"):
            buttons.append(
                format_html(
                    '<a class="button" href="{}">Сгенерировать разметку</a>',
                    f"./{obj.pk}/generate-markup/",
                )
            )
            buttons.append(
                format_html(
                    '<a class="button" href="{}">Разметить</a>', f"./{obj.pk}/labeler/"
                )
            )
            buttons.append(
                format_html(
                    '<a class="button" href="{}">Граф</a>', f"./{obj.pk}/graph/"
                )
            )
            buttons.append(
                format_html(
                    '<a class="button" href="{}">Таблица</a>', f"./{obj.pk}/grid/"
                )
            )  # ← НОВОЕ
        if hasattr(obj, "markup"):
            buttons.append(
                format_html(
                    '<a class="button" href="{}">Создать смету</a>',
                    f"./{obj.pk}/materialize/",
                )
            )
        return mark_safe("&nbsp;".join(buttons))

    actions_col.short_description = "Действия"

    # — object-tools urls —

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<int:pk>/parse/",
                self.admin_site.admin_view(self.parse_view),
                name="imports_parse",
            ),
            path(
                "<int:pk>/download-json/",
                self.admin_site.admin_view(self.download_json_view),
                name="imports_download_json",
            ),
            path(
                "<int:pk>/generate-markup/",
                self.admin_site.admin_view(self.generate_markup_view),
                name="imports_generate_markup",
            ),
            path(
                "<int:pk>/materialize/",
                self.admin_site.admin_view(self.materialize_view),
                name="imports_materialize",
            ),
            path(
                "<int:pk>/uids/",
                self.admin_site.admin_view(self.uids_view),
                name="imports_uids",
            ),
            path(
                "<int:pk>/labeler/",
                self.admin_site.admin_view(self.labeler_view),
                name="imports_labeler",
            ),
            path(
                "<int:pk>/set-label/",
                self.admin_site.admin_view(self.set_label_view),
                name="imports_set_label",
            ),
            path(
                "<int:pk>/compose/",
                self.admin_site.admin_view(self.compose_view),
                name="imports_compose",
            ),
            # path(
            #     "<int:pk>/graph/",
            #     self.admin_site.admin_view(self.graph_view),
            #     name="imports_graph",
            # ),
            path(
                "<int:pk>/api/set-label/",
                self.admin_site.admin_view(self.api_set_label),
                name="imports_api_set_label",
            ),
            path(
                "<int:pk>/api/attach-members/",
                self.admin_site.admin_view(self.api_attach_members),
                name="imports_api_attach_members",
            ),
            path(
                "<int:pk>/grid/",
                self.admin_site.admin_view(self.grid_view),
                name="imports_grid",
            ),
            path(
                "<int:pk>/api/save-schema/",
                self.admin_site.admin_view(self.api_save_schema),
                name="imports_api_save_schema",
            ),
            path(
                "<int:pk>/api/extract-from-grid/",
                self.admin_site.admin_view(self.api_extract_from_grid),
                name="imports_api_extract_from_grid",
            ),
            path(
                "<int:pk>/api/groups/list/",
                self.admin_site.admin_view(self.api_groups_list),
                name="imports_groups_list",
            ),
            path(
                "<int:pk>/api/groups/create/",
                self.admin_site.admin_view(self.api_groups_create),
                name="imports_groups_create",
            ),
            path(
                "<int:pk>/api/groups/delete/",
                self.admin_site.admin_view(self.api_groups_delete),
                name="imports_groups_delete",
            ),
            path(
                "<int:pk>/graph/",
                self.admin_site.admin_view(self.graph_view),
                name="imports_graph",
            ),
            path(
                "<int:pk>/api/graph-data/",
                self.admin_site.admin_view(self.api_graph_data),
                name="imports_graph_data",
            ),
        ]
        return custom + urls

    def _parse_url(self, pk: int) -> str:
        return f"./{pk}/parse/"

    def _download_url(self, pk: int) -> str:
        return f"./{pk}/download-json/"

    # — действия / вьюхи —

    def parse_now(self, request, queryset):
        ok, fail = 0, 0
        for f in queryset:
            try:
                parse_and_store(f)
                ok += 1
            except Exception as e:
                fail += 1
                self.message_user(
                    request, f"[{f.original_name}] ошибка: {e!r}", level=messages.ERROR
                )
        if ok:
            self.message_user(
                request, f"Распарсено успешно: {ok}", level=messages.SUCCESS
            )
        if fail and not ok:
            self.message_user(
                request,
                "Ошибки при парсинге. См. сообщения выше.",
                level=messages.ERROR,
            )

    parse_now.short_description = "Распарсить (синхронно)"

    def parse_view(self, request, pk: int):
        obj = self.get_object(request, pk)
        if not obj:
            self.message_user(request, "Файл не найден", level=messages.ERROR)
            return self.response_post_save_change(request, None)
        try:
            parse_and_store(obj)
            self.message_user(
                request, "Готово: JSON создан/обновлён", level=messages.SUCCESS
            )
        except Exception as e:
            self.message_user(request, f"Ошибка парсинга: {e!r}", level=messages.ERROR)
        return self.response_change(request, obj)

    def download_json_view(self, request, pk: int):
        obj = self.get_object(request, pk)
        if not obj or not hasattr(obj, "parse_result"):
            self.message_user(request, "JSON ещё не создан", level=messages.WARNING)
            return (
                self.response_change(request, obj)
                if obj
                else self.response_post_save_change(request, None)
            )
        payload = json.dumps(obj.parse_result.data, ensure_ascii=False, indent=2)
        resp = HttpResponse(payload, content_type="application/json; charset=utf-8")
        safe_name = (obj.original_name or f"file_{obj.pk}").rsplit(".", 1)[0]
        resp["Content-Disposition"] = f'attachment; filename="{safe_name}.json"'
        return resp

    def generate_markup_skeleton(self, request, queryset):
        ok = 0
        for f in queryset:
            pr = getattr(f, "parse_result", None)
            if not pr:
                self.message_user(
                    request, f"[{f}] нет ParseResult", level=messages.WARNING
                )
                continue
            if not hasattr(f, "markup"):
                f.markup = ParseMarkup.objects.create(
                    file=f, parse_result=pr, annotation={}
                )
            # гарантируем uid'ы
            pr.data = ensure_uids_in_tree(pr.data)
            pr.save(update_fields=["data"])
            f.markup.annotation = build_markup_skeleton(pr)
            f.markup.save(update_fields=["annotation"])
            ok += 1
        if ok:
            self.message_user(
                request, f"Скелет разметки создан: {ok}", level=messages.SUCCESS
            )

    generate_markup_skeleton.short_description = "Сгенерировать черновик разметки"

    def generate_markup_view(self, request, pk: int):
        obj = self.get_object(request, pk)
        if not obj or not hasattr(obj, "parse_result"):
            self.message_user(
                request, "Нет ParseResult для генерации", level=messages.ERROR
            )
            return HttpResponseRedirect(request.META.get("HTTP_REFERER", ".."))
        if not hasattr(obj, "markup"):
            obj.markup = ParseMarkup.objects.create(
                file=obj, parse_result=obj.parse_result, annotation={}
            )
        obj.parse_result.data = ensure_uids_in_tree(obj.parse_result.data)
        obj.parse_result.save(update_fields=["data"])
        obj.markup.annotation = build_markup_skeleton(obj.parse_result)
        obj.markup.save(update_fields=["annotation"])
        self.message_user(request, "Черновик разметки создан", level=messages.SUCCESS)
        return HttpResponseRedirect(f"../{pk}/change/")

    def create_estimate_from_markup(self, request, queryset):
        ok = 0
        for f in queryset:
            if not hasattr(f, "markup"):
                self.message_user(
                    request, f"[{f}] нет разметки", level=messages.WARNING
                )
                continue
            try:
                materialize_estimate_from_markup(f.markup)
                ok += 1
            except Exception as e:
                self.message_user(
                    request, f"[{f}] ошибка материализации: {e!r}", level=messages.ERROR
                )
        if ok:
            self.message_user(request, f"Создано смет: {ok}", level=messages.SUCCESS)

    create_estimate_from_markup.short_description = "Создать смету из разметки"

    def materialize_view(self, request, pk: int):
        obj = self.get_object(request, pk)
        if not obj or not hasattr(obj, "markup"):
            self.message_user(
                request, "Нет разметки для материализации", level=messages.ERROR
            )
            return HttpResponseRedirect(request.META.get("HTTP_REFERER", ".."))
        materialize_estimate_from_markup(obj.markup)
        self.message_user(request, "Смета создана", level=messages.SUCCESS)
        return HttpResponseRedirect(f"../{pk}/change/")

    def uids_view(self, request, pk: int):
        obj = self.get_object(request, pk)
        if not obj or not hasattr(obj, "parse_result"):
            self.message_user(request, "Нет ParseResult", level=messages.ERROR)
            return HttpResponseRedirect(request.META.get("HTTP_REFERER", ".."))

        from app_outlay.services_materialize import (
            _index_titles_by_uid,
        )  # или вынеси в utils

        mapping = _index_titles_by_uid(obj.parse_result.data)

        rows = "".join(
            f"<tr><td><code>{uid}</code></td><td>{title}</td></tr>"
            for uid, title in mapping.items()
        )
        html = f"""
        <h2>UID → Название ({obj.original_name})</h2>
        <table class="adminlist">
        <thead><tr><th>UID</th><th>Название</th></tr></thead>
        <tbody>{rows}</tbody>
        </table>
        <p><a class="button" href="../change/">Назад</a></p>
        """
        return HttpResponse(mark_safe(html))

    def labeler_view(self, request, pk: int):
        """
        Таблица узлов с кнопками: сделать TECH_CARD/WORK/MATERIAL/GROUP.
        Для узлов, помеченных как TECH_CARD, показываем кнопку «Состав ТК».
        """
        obj = self.get_object(request, pk)
        if not obj or not hasattr(obj, "parse_result"):
            self.message_user(request, "Нет ParseResult", level=messages.ERROR)
            return HttpResponseRedirect(request.META.get("HTTP_REFERER", ".."))

        # гарантируем uid'ы и наличие markup
        from app_estimate_imports.services_markup import (
            ensure_markup_exists,
            list_nodes,
        )

        markup = ensure_markup_exists(obj)
        nodes = list_nodes(obj.parse_result)
        labels = (markup.annotation or {}).get("labels", {})

        def btn(uid, label):
            return format_html(
                '<a class="button" href="../set-label/?uid={}&label={}">{}</a>',
                uid,
                label,
                label,
            )

        rows = []
        for n in nodes:
            uid = n["uid"]
            title = n["title"] or "—"
            path = n["path"]
            cur = labels.get(uid, "—")
            buttons = "&nbsp;".join(
                [
                    btn(uid, "TECH_CARD"),
                    btn(uid, "WORK"),
                    btn(uid, "MATERIAL"),
                    btn(uid, "GROUP"),
                ]
            )
            extra = ""
            if cur == "TECH_CARD":
                extra = format_html(
                    '&nbsp;&nbsp;<a class="button" href="../compose/?tc_uid={}">Состав ТК</a>',
                    uid,
                )
            rows.append(
                f"<tr><td><code>{uid}</code></td><td>{title}</td><td>{path}</td><td>{cur}</td><td>{buttons}{extra}</td></tr>"
            )

        html = f"""
        <h2>Разметка узлов ({obj.original_name})</h2>
        <p>Кликните метку для нужного UID. Для ТЕХКАРТ нажмите «Состав ТК», чтобы выбрать её работы и материалы.</p>
        <table class="adminlist">
        <thead><tr><th>UID</th><th>Название</th><th>Путь</th><th>Метка</th><th>Действия</th></tr></thead>
        <tbody>{"".join(rows)}</tbody>
        </table>
        <p><a class="button" href="../change/">Назад</a></p>
        """
        return HttpResponse(mark_safe(html))

    def set_label_view(self, request, pk: int):
        """
        Присваивает метку узлу и возвращает в labeler.
        """
        obj = self.get_object(request, pk)
        if not obj:
            self.message_user(request, "Файл не найден", level=messages.ERROR)
            return HttpResponseRedirect(request.META.get("HTTP_REFERER", ".."))

        uid = request.GET.get("uid")
        label = request.GET.get("label")
        if not uid or not label:
            self.message_user(request, "uid/label не переданы", level=messages.ERROR)
            return HttpResponseRedirect(f"../labeler/")

        try:
            from app_estimate_imports.services_markup import set_label

            set_label(obj, uid, label)
            self.message_user(request, f"{uid} → {label}", level=messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"Ошибка: {e!r}", level=messages.ERROR)

        return HttpResponseRedirect(f"../labeler/")

    def compose_view(self, request, pk: int):
        """
        Настройка состава выбранной TECH_CARD: мультиселект WORK и MATERIAL.
        GET: форма, POST: сохранение.
        """
        obj = self.get_object(request, pk)
        if not obj or not hasattr(obj, "parse_result"):
            self.message_user(request, "Нет ParseResult", level=messages.ERROR)
            return HttpResponseRedirect(request.META.get("HTTP_REFERER", ".."))

        from app_estimate_imports.services_markup import (
            ensure_markup_exists,
            list_nodes,
            set_tc_members,
        )

        markup = ensure_markup_exists(obj)
        labels = (markup.annotation or {}).get("labels", {})
        nodes = list_nodes(obj.parse_result)

        tc_uid = request.GET.get("tc_uid") or request.POST.get("tc_uid")
        if not tc_uid:
            self.message_user(request, "Не указан tc_uid", level=messages.ERROR)
            return HttpResponseRedirect(f"../labeler/")

        if request.method == "POST":
            works = request.POST.getlist("works")
            materials = request.POST.getlist("materials")
            try:
                set_tc_members(obj, tc_uid, works, materials)
                self.message_user(
                    request, "Состав техкарты обновлён", level=messages.SUCCESS
                )
                return HttpResponseRedirect(f"../labeler/")
            except Exception as e:
                self.message_user(request, f"Ошибка: {e!r}", level=messages.ERROR)

        # подготовим списки выбора
        work_opts = []
        material_opts = []
        cur_works, cur_materials = [], []
        # найдём текущую запись ТК
        for entry in (markup.annotation or {}).get("tech_cards", []):
            if entry.get("uid") == tc_uid:
                cur_works = entry.get("works") or []
                cur_materials = entry.get("materials") or []
                break

        for n in nodes:
            uid = n["uid"]
            title = n["title"] or uid
            if labels.get(uid) == "WORK":
                sel = "selected" if uid in cur_works else ""
                work_opts.append(
                    f'<option value="{uid}" {sel}>{title} ({uid})</option>'
                )
            elif labels.get(uid) == "MATERIAL":
                sel = "selected" if uid in cur_materials else ""
                material_opts.append(
                    f'<option value="{uid}" {sel}>{title} ({uid})</option>'
                )

        html = f"""
        <h2>Состав техкарты: {tc_uid}</h2>
        <form method="post">
        {request.csrf_processing_done or ""}
        <input type="hidden" name="tc_uid" value="{tc_uid}">
        <div style="display:flex; gap:24px;">
            <div>
            <label><strong>WORKS</strong></label><br>
            <select name="works" multiple size="15" style="min-width:360px;">{"".join(work_opts)}</select>
            </div>
            <div>
            <label><strong>MATERIALS</strong></label><br>
            <select name="materials" multiple size="15" style="min-width:360px;">{"".join(material_opts)}</select>
            </div>
        </div>
        <p style="margin-top:16px;">
            <button class="button" type="submit">Сохранить</button>
            <a class="button" href="../labeler/">Отмена</a>
        </p>
        </form>
        """
        return HttpResponse(mark_safe(html))

    def graph_view(self, request, pk: int):
        obj = self.get_object(request, pk)
        if not obj or not hasattr(obj, "parse_result"):
            self.message_user(request, "Нет ParseResult", level=messages.ERROR)
            return HttpResponseRedirect(request.META.get("HTTP_REFERER", ".."))

        pr = obj.parse_result
        sheets = pr.data.get("sheets") or []
        sheet_i = int(request.GET.get("sheet") or 0)
        if sheet_i < 0 or sheet_i >= len(sheets):
            sheet_i = 0
        sheet_names = [s.get("name") or f"Лист {i+1}" for i, s in enumerate(sheets)]

        ctx = dict(
            self.admin_site.each_context(request),
            title=f"Граф: {obj.original_name}",
            file=obj,
            sheet_index=sheet_i,
            sheet_names=sheet_names,
        )
        return TemplateResponse(request, "admin/app_estimate_imports/graph.html", ctx)

    def api_set_label(self, request, pk: int):
        obj = self.get_object(request, pk)
        if not obj:
            return HttpResponse(
                json.dumps({"ok": False, "error": "file_not_found"}),
                content_type="application/json",
                status=404,
            )
        try:
            payload = json.loads(request.body.decode("utf-8"))
            uid = payload["uid"]
            label = payload["label"]
            title = payload.get("title", "")
            from app_estimate_imports.services_markup import set_label

            set_label(obj, uid, label, title=title)  # ← передаём title
            return HttpResponse(
                json.dumps({"ok": True}), content_type="application/json"
            )
        except Exception as e:
            return HttpResponse(
                json.dumps({"ok": False, "error": str(e)}),
                content_type="application/json",
                status=400,
            )

    def api_attach_members(self, request, pk: int):
        obj = self.get_object(request, pk)
        if not obj:
            return HttpResponse(
                json.dumps({"ok": False, "error": "file_not_found"}),
                content_type="application/json",
                status=404,
            )

        try:
            payload = json.loads(request.body.decode("utf-8"))
            tc_uid = payload["tc_uid"]
            works = payload.get("works", [])
            materials = payload.get("materials", [])
            from app_estimate_imports.services_markup import set_tc_members

            set_tc_members(obj, tc_uid, works, materials)
            return HttpResponse(
                json.dumps({"ok": True}), content_type="application/json"
            )
        except Exception as e:
            return HttpResponse(
                json.dumps({"ok": False, "error": str(e)}),
                content_type="application/json",
                status=400,
            )

    def _ensure_markup(self, file_obj):
        from app_estimate_imports.services_markup import ensure_markup_exists

        return ensure_markup_exists(file_obj)

    def _guess_schema(self, rows):
        # как раньше, только возвращает list[str]
        max_cols = max((len(r.get("cells") or []) for r in rows), default=0)
        roles = ["NONE"] * max_cols
        header_zone = rows[:8]
        for r in header_zone:
            cells = [((c or "").strip()) for c in r.get("cells", [])]
            for ci, val in enumerate(cells):
                low = val.lower()
                if "шифр" in low:
                    roles[ci] = "TECH_CARD"
                if ("наименован" in low and "работ" in low) or low == "наименование":
                    roles[ci] = "WORK"
                if "ед.изм" in low or "ед. изм" in low:
                    roles[ci] = "UNIT"
                if "кол-во" in low or "количество" in low or low in {"колво", "кол-во"}:
                    roles[ci] = "QTY"
                if re.fullmatch(r"ур\d+", low):
                    idx = int(re.findall(r"\d+", low)[0])
                    if 1 <= idx <= 6:
                        roles[ci] = f"GROUP-{idx}"
        if not any(r.startswith("GROUP-") for r in roles) and max_cols >= 9:
            for i, tag in enumerate(
                ["GROUP-1", "GROUP-2", "GROUP-3", "GROUP-4"], start=5
            ):
                if i < max_cols and roles[i] == "NONE":
                    roles[i] = tag
        return roles

    def grid_view(self, request, pk: int):
        obj = self.get_object(request, pk)
        if not obj or not hasattr(obj, "parse_result"):
            self.message_user(request, "Нет ParseResult", level=messages.ERROR)
            return HttpResponseRedirect(request.META.get("HTTP_REFERER", ".."))

        pr = obj.parse_result
        sheets = pr.data.get("sheets") or []
        sheet_i = int(request.GET.get("sheet") or 0)
        if sheet_i < 0 or sheet_i >= len(sheets):
            sheet_i = 0
        sheet = sheets[sheet_i] if sheets else {"name": "Лист1", "rows": []}
        rows = sheet.get("rows") or []

        # показать все строки?
        show_all = request.GET.get("all") == "1"
        if show_all:
            # если используете загрузку полного листа из файла — оставьте этот блок;
            # иначе просто rows остаются как есть

            xlsx_path = getattr(obj.file, "path", None) or (
                pr.data.get("file") or {}
            ).get("path")
            if xlsx_path:
                try:
                    rows = load_sheet_rows_full(xlsx_path, sheet_index=sheet_i)
                except Exception as e:
                    self.message_user(
                        request,
                        f"Не удалось загрузить полный лист: {e!r}",
                        level=messages.WARNING,
                    )

        preview_rows = rows
        max_cols = max((len(r.get("cells") or []) for r in preview_rows), default=0)
        cols = list(range(max_cols))
        sheet_names = [s.get("name") or f"Лист {i+1}" for i, s in enumerate(sheets)]

        # загружаем сохранённую схему (если была); иначе — ВСЕ NONE
        markup = self._ensure_markup(obj)
        schema = (markup.annotation or {}).get("schema") or {}
        sheets_schema = schema.get("sheets") or {}
        sheet_cfg = sheets_schema.get(str(sheet_i)) or {}

        col_roles = (sheets_schema.get(str(sheet_i)) or {}).get("col_roles") or []
        if len(col_roles) < max_cols:
            col_roles = (col_roles + ["NONE"] * (max_cols - len(col_roles)))[:max_cols]

        # 🔹 новые поля с дефолтами
        unit_allow_raw = sheet_cfg.get("unit_allow_raw") or "м2, м3, шт, пм"
        require_qty = sheet_cfg.get("require_qty")
        require_qty = True if require_qty is None else bool(require_qty)

        # авто-шапки колонок из первых строк отображаемой выборки
        col_headers = []
        for ci in range(max_cols):
            header = ""
            for r in preview_rows[:8]:
                cells = r.get("cells") or []
                if ci < len(cells):
                    val = (cells[ci] or "").strip()
                    if val:
                        header = val
                        break
            col_headers.append(header)

        ctx = dict(
            self.admin_site.each_context(request),
            title=f"Таблица: {obj.original_name}",
            file=obj,
            sheet_index=sheet_i,
            sheet_names=sheet_names,
            rows=preview_rows,
            cols=cols,
            role_defs=ROLE_DEFS,
            col_roles=col_roles,
            col_headers=col_headers,
            show_all=show_all,
            total_rows=len(rows),
            # 🔹 отдаём в шаблон
            unit_allow_raw=unit_allow_raw,
            require_qty=require_qty,
        )
        return TemplateResponse(request, "admin/app_estimate_imports/grid.html", ctx)

    def api_save_schema(self, request, pk: int):
        obj = self.get_object(request, pk)
        if not obj:
            return HttpResponse(
                json.dumps({"ok": False, "error": "file_not_found"}),
                content_type="application/json",
                status=404,
            )
        try:
            payload = json.loads(request.body.decode("utf-8"))
            col_roles = payload.get("col_roles") or []
            sheet_i = str(payload.get("sheet_index") or "0")

            # 🔹 новые поля из payload
            unit_allow_raw = (
                payload.get("unit_allow_raw") or payload.get("unit_allow") or ""
            )
            require_qty = bool(payload.get("require_qty"))

            markup = self._ensure_markup(obj)
            ann = markup.annotation or {}
            schema = ann.get("schema") or {}
            sheets_schema = schema.get("sheets") or {}

            sheet_cfg = sheets_schema.get(sheet_i) or {}
            sheet_cfg["col_roles"] = col_roles
            sheet_cfg["unit_allow_raw"] = unit_allow_raw
            sheet_cfg["require_qty"] = require_qty

            sheets_schema[sheet_i] = sheet_cfg
            schema["sheets"] = sheets_schema
            ann["schema"] = schema
            markup.annotation = ann
            markup.save(update_fields=["annotation"])
            return HttpResponse(
                json.dumps({"ok": True}), content_type="application/json"
            )
        except Exception as e:
            return HttpResponse(
                json.dumps({"ok": False, "error": str(e)}),
                content_type="application/json",
                status=400,
            )

    def api_extract_from_grid(self, request, pk: int):
        obj = self.get_object(request, pk)
        if not obj:
            return HttpResponse(
                json.dumps({"ok": False, "error": "file_not_found"}),
                content_type="application/json",
                status=404,
            )
        try:
            payload = json.loads(request.body.decode("utf-8"))
            col_roles = payload.get("col_roles") or []
            sheet_i = int(payload.get("sheet_index") or 0)

            unit_allow_raw = (
                payload.get("unit_allow_raw") or payload.get("unit_allow") or ""
            )
            require_qty = bool(payload.get("require_qty"))

            from app_estimate_imports.services_markup import build_annotation_from_grid

            markup = self._ensure_markup(obj)
            annotation = build_annotation_from_grid(
                obj.parse_result,
                col_roles,
                sheet_index=sheet_i,
                existing=markup.annotation,
            )

            # параллельно обновим схему листа
            ann = annotation
            schema = ann.get("schema") or {}
            sheets_schema = schema.get("sheets") or {}
            sheet_cfg = sheets_schema.get(str(sheet_i)) or {}
            sheet_cfg["col_roles"] = col_roles
            sheet_cfg["unit_allow_raw"] = unit_allow_raw
            sheet_cfg["require_qty"] = require_qty
            sheets_schema[str(sheet_i)] = sheet_cfg
            schema["sheets"] = sheets_schema
            ann["schema"] = schema

            markup.annotation = ann
            markup.save(update_fields=["annotation"])
            return HttpResponse(
                json.dumps({"ok": True}), content_type="application/json"
            )
        except Exception as e:
            return HttpResponse(
                json.dumps({"ok": False, "error": str(e)}),
                content_type="application/json",
                status=400,
            )

    def _sheet_cfg(self, markup, sheet_i: int):
        ann = markup.annotation or {}
        schema = ann.get("schema") or {}
        sheets = schema.get("sheets") or {}
        cfg = sheets.get(str(sheet_i)) or {}
        cfg.setdefault("groups", [])
        sheets[str(sheet_i)] = cfg
        schema["sheets"] = sheets
        ann["schema"] = schema
        markup.annotation = ann
        return cfg, ann

    def api_groups_list(self, request, pk: int):
        obj = self.get_object(request, pk)
        if not obj:
            return HttpResponse(
                json.dumps({"ok": False, "error": "file_not_found"}),
                content_type="application/json",
                status=404,
            )
        sheet_i = int(request.GET.get("sheet_index") or 0)
        markup = self._ensure_markup(obj)
        cfg, _ = self._sheet_cfg(markup, sheet_i)
        return HttpResponse(
            json.dumps({"ok": True, "groups": cfg.get("groups")}),
            content_type="application/json",
        )

    def api_groups_create(self, request, pk: int):
        obj = self.get_object(request, pk)
        if not obj:
            return HttpResponse(
                json.dumps({"ok": False, "error": "file_not_found"}),
                content_type="application/json",
                status=404,
            )
        try:
            p = json.loads(request.body.decode("utf-8"))
            sheet_i = int(p.get("sheet_index") or 0)
            name = (p.get("name") or "").strip()
            rows = p.get("rows") or []  # [[s,e], ...] 1-based
            parent_uid = p.get("parent_uid")
            color = p.get("color") or "#E0F7FA"

            if not name or not rows:
                return HttpResponse(
                    json.dumps({"ok": False, "error": "empty_name_or_rows"}),
                    content_type="application/json",
                    status=400,
                )

            markup = self._ensure_markup(obj)
            cfg, ann = self._sheet_cfg(markup, sheet_i)
            groups = cfg.get("groups") or []

            # если есть родитель — проверим покрытие
            if parent_uid:
                parent = next((g for g in groups if g.get("uid") == parent_uid), None)
                if not parent:
                    return HttpResponse(
                        json.dumps({"ok": False, "error": "parent_not_found"}),
                        content_type="application/json",
                        status=400,
                    )
                if not _ranges_cover(parent.get("rows") or [], rows):
                    return HttpResponse(
                        json.dumps({"ok": False, "error": "parent_not_cover"}),
                        content_type="application/json",
                        status=400,
                    )

            uid = "grp_" + secrets.token_hex(8)
            item = {
                "uid": uid,
                "name": name,
                "color": color,
                "parent_uid": parent_uid,
                "rows": rows,
            }
            groups.append(item)
            cfg["groups"] = groups
            markup.annotation = ann
            markup.save(update_fields=["annotation"])
            return HttpResponse(
                json.dumps({"ok": True, "group": item}), content_type="application/json"
            )
        except Exception as e:
            return HttpResponse(
                json.dumps({"ok": False, "error": str(e)}),
                content_type="application/json",
                status=400,
            )

    def api_groups_delete(self, request, pk: int):
        obj = self.get_object(request, pk)
        if not obj:
            return HttpResponse(
                json.dumps({"ok": False, "error": "file_not_found"}),
                content_type="application/json",
                status=404,
            )
        try:
            p = json.loads(request.body.decode("utf-8"))
            sheet_i = int(p.get("sheet_index") or 0)
            uid = p.get("uid")
            if not uid:
                return HttpResponse(
                    json.dumps({"ok": False, "error": "no_uid"}),
                    content_type="application/json",
                    status=400,
                )

            markup = self._ensure_markup(obj)
            cfg, ann = self._sheet_cfg(markup, sheet_i)
            groups = cfg.get("groups") or []
            # удаляем группу и всех её потомков (простая рекурсия)
            to_delete = set()

            def collect(u):
                to_delete.add(u)
                for g in groups:
                    if g.get("parent_uid") == u:
                        collect(g.get("uid"))

            collect(uid)
            cfg["groups"] = [g for g in groups if g.get("uid") not in to_delete]
            markup.annotation = ann
            markup.save(update_fields=["annotation"])
            return HttpResponse(
                json.dumps({"ok": True}), content_type="application/json"
            )
        except Exception as e:
            return HttpResponse(
                json.dumps({"ok": False, "error": str(e)}),
                content_type="application/json",
                status=400,
            )

    # — пересчёт метаданных при сохранении (удобно в админке) —

    def save_model(self, request, obj: ImportedEstimateFile, form, change):
        super().save_model(request, obj, form, change)
        # При первичном аплоаде обновим size/sha/sheet_count
        from .utils import compute_sha256, count_sheets_safely

        if obj.file and (not obj.sha256 or not obj.size_bytes or not obj.sheet_count):
            f = obj.file.open("rb")
            obj.size_bytes = obj.file.size or 0
            obj.sha256 = compute_sha256(f)
            obj.sheet_count = count_sheets_safely(obj.file.path)
            obj.save(update_fields=["size_bytes", "sha256", "sheet_count"])

    # ---- вспомогательные: нормализация юнитов и чтение схемы ----

    def _load_groups(self, markup, sheet_i: int):
        """
        Возвращает список групп для листа sheet_i в нормализованном виде:
        [{uid, name, parent_uid, color, rows:[[start,end], ...]}, ...]
        Ищет в нескольких местах annotation: schema.sheets, groups, sheets.
        """
        ann = markup.annotation or {}
        sheet_key = str(sheet_i)

        groups_all = []

        # Вариант 0 (ВАЖНО): annotation["schema"]["sheets"][sheet]["groups"]
        schema = ann.get("schema") or {}
        sheets_schema = schema.get("sheets") or {}
        raw = sheets_schema.get(sheet_key)
        if isinstance(raw, dict) and isinstance(raw.get("groups"), list):
            groups_all = raw["groups"]

        # Вариант A: annotation["groups"][sheet] => list | dict(items/groups)
        if not groups_all:
            root = ann.get("groups")
            if isinstance(root, dict):
                raw = root.get(sheet_key)
                if isinstance(raw, list):
                    groups_all = raw
                elif isinstance(raw, dict):
                    if isinstance(raw.get("items"), list):
                        groups_all = raw["items"]
                    elif isinstance(raw.get("groups"), list):
                        groups_all = raw["groups"]

        # Вариант B: annotation["sheets"][sheet]["groups" | "items"]
        if not groups_all:
            sheets = ann.get("sheets") or {}
            raw = sheets.get(sheet_key) or {}
            if isinstance(raw, dict):
                for k in ("groups", "items"):
                    if isinstance(raw.get(k), list):
                        groups_all = raw[k]
                        break

        # Нормализация
        norm = []
        for g in groups_all or []:
            uid = g.get("uid") or g.get("id") or g.get("gid")
            if not uid:
                continue
            name = g.get("name") or g.get("title") or "Группа"
            parent = g.get("parent_uid") or g.get("parent") or g.get("parentId") or None
            color = g.get("color") or "#90caf9"
            rows = g.get("rows") or g.get("ranges") or []
            rr = []
            for r in rows:
                if isinstance(r, (list, tuple)) and len(r) >= 2:
                    try:
                        rr.append([int(r[0]), int(r[1])])
                    except Exception:
                        pass
            norm.append(
                {
                    "uid": uid,
                    "name": name,
                    "parent_uid": parent,
                    "color": color,
                    "rows": rr,
                }
            )
        return norm

    @staticmethod
    def _normalize_unit_py(u: str) -> str:
        if not u:
            return ""
        s = (u or "").lower().strip()
        s = s.replace("\u00b2", "2").replace("\u00b3", "3")
        compact = "".join(ch for ch in s if ch not in " .,")
        # те же эвристики, что и в grid.js
        import re

        if re.fullmatch(r"(м\^?2|м2|квм|мкв|квадратн\w*метр\w*)", compact or ""):
            return "м2"
        if re.fullmatch(r"(м\^?3|м3|кубм|мкуб|кубическ\w*метр\w*)", compact or ""):
            return "м3"
        if re.fullmatch(r"(шт|штука|штуки|штук)", compact or ""):
            return "шт"
        if re.fullmatch(r"(пм|погм|погонныйметр|погонныхметров)", compact or ""):
            return "пм"
        if re.fullmatch(r"(компл|комплект|комплекта|комплектов)", compact or ""):
            return "компл"
        return compact

    def _read_schema_for_sheet(self, markup, sheet_i: int):
        """Возвращает (col_roles, unit_allow_set, require_qty) с fallback'ами."""
        ann = markup.annotation or {}
        schema = ann.get("schema") or {}
        sheets = schema.get("sheets") or {}
        s = sheets.get(str(sheet_i)) or {}
        col_roles = s.get("col_roles") or []
        # unit_allow/require_qty допускаем как на уровне листа, так и глобально
        unit_allow_raw = s.get("unit_allow_raw") or schema.get("unit_allow_raw") or ""
        require_qty = bool(
            s.get("require_qty")
            if s.get("require_qty") is not None
            else schema.get("require_qty") or False
        )
        unit_allow_set = set()
        for x in unit_allow_raw.split(",") if unit_allow_raw else []:
            nx = self._normalize_unit_py(x)
            if nx:
                unit_allow_set.add(nx)
        return col_roles, unit_allow_set, require_qty

    def _detect_techcards(
        self, pr_data: dict, sheet_i: int, col_roles, unit_allow_set, require_qty: bool
    ):
        """Сканирует строки листа и возвращает список ТК: dict(id,row_index,name)."""
        sheets = pr_data.get("sheets") or []
        sheet = sheets[sheet_i] if sheet_i < len(sheets) else {}
        rows = sheet.get("rows") or []

        # индексы колонок по ролям
        def idxs(role):
            return [i for i, r in enumerate(col_roles or []) if r == role]

        name_cols = idxs("NAME_OF_WORK")
        unit_cols = idxs("UNIT")
        qty_cols = idxs("QTY")

        def val(row, idx):
            cells = row.get("cells") or []
            return (cells[idx] if idx < len(cells) else "") or ""

        def any_nonempty(row, idxs_):
            for i in idxs_:
                if (val(row, i) or "").strip():
                    return True
            return False

        def first_text(row, idxs_):
            for i in idxs_:
                t = (val(row, i) or "").strip()
                if t:
                    return t
            return ""

        def qty_ok(row):
            if not require_qty:
                return True
            import re

            for i in qty_cols:
                raw = (val(row, i) or "").replace(" ", "").replace(",", ".")
                try:
                    num = float(raw)
                except Exception:
                    continue
                if num > 0:
                    return True
            return False

        tcs = []
        for row in rows:
            has_name = any_nonempty(row, name_cols)
            unit_raw = first_text(row, unit_cols)
            unit_norm = self._normalize_unit_py(unit_raw)
            has_unit = bool(unit_norm) and (
                not unit_allow_set or unit_norm in unit_allow_set
            )
            if has_name and has_unit and qty_ok(row):
                tcs.append(
                    {
                        "id": f"t:{row.get('row_index')}",
                        "row_index": row.get("row_index"),
                        "name": first_text(row, name_cols)
                        or f"ТК {row.get('row_index')}",
                    }
                )
        return tcs

    def api_graph_data(self, request, pk: int):
        obj = self.get_object(request, pk)
        if not obj or not hasattr(obj, "parse_result"):
            return HttpResponse(
                json.dumps({"ok": False, "error": "no_parse_result"}),
                content_type="application/json",
                status=400,
            )

        sheet_i = int(request.GET.get("sheet_index") or 0)

        # читаем группы (толерантно к схеме хранения)
        markup = self._ensure_markup(obj)
        groups_all = self._load_groups(markup, sheet_i)

        # глубина по parent_uid
        by_id = {g["uid"]: g for g in groups_all}

        def depth(uid):
            d = 0
            cur = by_id.get(uid)
            while cur and cur.get("parent_uid"):
                d += 1
                cur = by_id.get(cur.get("parent_uid"))
            return d

        for g in groups_all:
            g["_depth"] = depth(g["uid"])

        # схема/юниты/qty → находим ТК
        col_roles, unit_allow_set, require_qty = self._read_schema_for_sheet(
            markup, sheet_i
        )
        tcs = self._detect_techcards(
            obj.parse_result.data, sheet_i, col_roles, unit_allow_set, require_qty
        )

        # сопоставляем ТК самой глубокой группе, накрывающей строку
        def row_covered_by_group(g, row_index: int) -> bool:
            for s, e in g.get("rows") or []:
                if s <= row_index <= e:
                    return True
            return False

        # узлы/рёбра
        sheets = obj.parse_result.data.get("sheets") or []
        sheet_name = (
            sheets[sheet_i].get("name") if sheet_i < len(sheets) else None
        ) or f"Лист {sheet_i+1}"
        root_id = f"root:{sheet_i}"
        nodes = [
            {
                "data": {
                    "id": root_id,
                    "label": f"Лист: {sheet_name}",
                    "type": "root",
                    "color": "#bdbdbd",
                }
            }
        ]
        edges = []

        # группы → узлы
        for g in groups_all:
            gid = f"g:{g['uid']}"
            nodes.append(
                {
                    "data": {
                        "id": gid,
                        "label": g.get("name") or "Группа",
                        "type": "group",
                        "color": g.get("color") or "#90caf9",
                    }
                }
            )

        # связи групп (parent→child), иначе корень
        for g in groups_all:
            gid = f"g:{g['uid']}"
            parent_uid = g.get("parent_uid")
            if parent_uid and parent_uid in by_id:
                pid = f"g:{parent_uid}"
            else:
                pid = root_id
            edges.append(
                {"data": {"id": f"e:{pid}->{gid}", "source": pid, "target": gid}}
            )

        # ТК → узлы + связь с самой глубокой покрывающей группой (или корнем)
        for t in tcs:
            row_index = t.get("row_index")
            owner_gid = None
            if row_index is not None:
                covering = [g for g in groups_all if row_covered_by_group(g, row_index)]
                covering.sort(key=lambda x: x["_depth"])
                if covering:
                    owner_gid = f"g:{covering[-1]['uid']}"
            if not owner_gid:
                owner_gid = root_id

            nodes.append(
                {
                    "data": {
                        "id": t["id"],
                        "label": t["name"],
                        "type": "tc",
                        "color": "#a5d6a7",
                    }
                }
            )
            edges.append(
                {
                    "data": {
                        "id": f"e:{owner_gid}->{t['id']}",
                        "source": owner_gid,
                        "target": t["id"],
                    }
                }
            )

        payload = {"ok": True, "nodes": nodes, "edges": edges}
        return HttpResponse(
            json.dumps(payload, ensure_ascii=False), content_type="application/json"
        )


# Вне класса (ниже файла admin.py) — утилита сборки графа:
import hashlib
import re


def _ranges_cover(a, b):
    """Проверяет, что объединение диапазонов a полностью покрывает b."""
    # простая проверка: каждый [s2,e2] из b попадает в любой [s1,e1] из a
    for s2, e2 in b:
        if not any(s1 <= s2 and e2 <= e1 for s1, e1 in a):
            return False
    return True


def _norm(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _guess_schema(rows: list[dict]) -> list[str]:
    max_cols = max((len(r.get("cells") or []) for r in rows), default=0)
    roles = ["NONE"] * max_cols
    header_zone = rows[:8]
    for r in header_zone:
        cells = [(_norm(c) if c is not None else "") for c in r.get("cells", [])]
        for ci, val in enumerate(cells):
            low = val.lower()
            if "шифр" in low:
                roles[ci] = "TECH_CARD"  # практично: «ШИФР» = ТК
            if ("наименован" in low and "работ" in low) or low == "наименование":
                roles[ci] = "WORK"  # чаще всего это работа/описание
            if "ед.изм" in low or "ед. изм" in low:
                roles[ci] = "UNIT"
            if "кол-во" in low or "количество" in low or low in {"колво", "кол-во"}:
                roles[ci] = "QTY"
            if re.fullmatch(r"ур\d+", low):  # ур1..ур6
                idx = int(re.findall(r"\d+", low)[0])
                if 1 <= idx <= 6:
                    roles[ci] = f"GROUP-{idx}"
    # если явно не нашли уровни — попробуем 5..8, как в твоём примере
    if not any(r.startswith("GROUP-") for r in roles) and max_cols >= 9:
        for i, tag in enumerate(["GROUP-1", "GROUP-2", "GROUP-3", "GROUP-4"], start=5):
            if i < max_cols and roles[i] == "NONE":
                roles[i] = tag
    return roles


def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def _detect_schema(rows: list[dict]) -> dict:
    """
    Находит индексы ключевых колонок по заголовкам.
    Возвращает: {"ur":[i1,i2,i3,i4], "shifr":i, "name":i, "unit":i, "qty":i}
    Фолбэк — твой пример: ур1..ур4=5..8, ШИФР=11, НАИМЕНОВАНИЕ=12, ЕД.ИЗМ.=13, КОЛ-ВО=14.
    """
    idx = {"ur": [], "shifr": 11, "name": 12, "unit": 13, "qty": 14}
    hdr_candidates = rows[:8]  # ищем шапку среди первых строк
    # явные ключевые слова
    for r in hdr_candidates:
        cells = [(_norm(c) if c is not None else "") for c in r.get("cells", [])]
        for ci, val in enumerate(cells):
            low = val.lower()
            if "шифр" in low:
                idx["shifr"] = ci
            if "наименован" in low and "работ" in low:
                idx["name"] = ci
            if "ед.изм" in low or "ед. изм" in low:
                idx["unit"] = ci
            if "кол-во" in low or "количество" in low:
                idx["qty"] = ci
            if re.fullmatch(r"ур\d+", low):  # ур1, ур2, ...
                idx["ur"].append(ci)
    # если «ур» не нашли, примем 5..8
    if not idx["ur"]:
        idx["ur"] = [5, 6, 7, 8]
    return idx


def _node_id(sheet_i: int, tag: str, val: str) -> str:
    return f"s{sheet_i}-{tag}-{_short_hash(val)}"


def _add_node(
    nodes_map: dict,
    nid: str,
    label: str,
    ntype: str,
    path: str,
    role: str,
    meta: dict | None = None,
):
    if nid not in nodes_map:
        nodes_map[nid] = {
            "data": {
                "id": nid,
                "label": label or nid,
                "type": ntype
                or "GROUP",  # фактический тип (из annotation) — перезапишется на клиенте/через API
                "role": role,  # происхождение узла: UR1/UR2/UR3/UR4/SHIFR/NAME
                "path": path,
                **(meta or {}),
            }
        }


def _add_edge(edges: list, src: str, dst: str, rel: str = "parent"):
    eid = f"{src}->{dst}" if rel == "parent" else f"{src}=>{rel}:{dst}"
    edges.append({"data": {"id": eid, "source": src, "target": dst, "rel": rel}})


def _build_graph(data: dict, annotation: dict) -> dict:
    """
    Строим граф из табличного JSON: слои по колонкам.
    - Для каждого листа добавляем корень `sheet:{i}`
    - По каждой строке соединяем непустые колонки ур1..ур4 → ШИФР → НАИМЕНОВАНИЕ
    - Узлы дедупим: (лист, колонка/роль, текст)
    - Перекрашивание по меткам из annotation.labels остаётся на клиенте (type)
    - Добавляем связи TECH_CARD→WORK/MATERIAL из annotation.tech_cards
    """
    labels = (annotation or {}).get("labels", {})
    nodes_map: dict[str, dict] = {}
    edges: list[dict] = []

    sheets = data.get("sheets") or []
    for si, sheet in enumerate(sheets):
        sheet_name = sheet.get("name") or f"Лист {si+1}"
        sheet_id = f"sheet:{si}"
        _add_node(
            nodes_map,
            sheet_id,
            f"Лист: {sheet_name}",
            "GROUP",
            sheet_name,
            role="SHEET",
        )

        rows = sheet.get("rows") or []
        sch = _detect_schema(rows)

        for row in rows:
            cells = row.get("cells") or []

            # 1) уровни ур1..ур4
            level_ids = []
            path_parts = [sheet_name]
            for li, col in enumerate(sch["ur"]):
                val = (
                    _norm(cells[col])
                    if col < len(cells)
                    and cells[col]
                    not in (
                        None,
                        "",
                    )
                    else ""
                )
                if not val:
                    continue
                nid = _node_id(si, f"UR{li+1}", val)
                ntype = labels.get(nid, "GROUP")
                _add_node(
                    nodes_map,
                    nid,
                    val,
                    ntype,
                    " / ".join([*path_parts, val]),
                    role=f"UR{li+1}",
                )
                level_ids.append(nid)
                path_parts.append(val)

            # 2) шифр (кандидат на TECH_CARD)
            shifr_val = ""
            shifr_id = ""
            col = sch["shifr"]
            if col is not None and col < len(cells):
                shifr_val = _norm(cells[col])
            if shifr_val:
                shifr_id = _node_id(si, "SHIFR", shifr_val)
                ntype = labels.get(shifr_id, "GROUP")
                _add_node(
                    nodes_map,
                    shifr_id,
                    shifr_val,
                    ntype,
                    " / ".join([*path_parts, shifr_val]),
                    role="SHIFR",
                )

            # 3) наименование работ (кандидат на WORK/MATERIAL или даже имя ТК)
            name_val = ""
            name_id = ""
            col = sch["name"]
            if col is not None and col < len(cells):
                name_val = _norm(cells[col])
            if name_val:
                meta = {}
                ucol = sch.get("unit")
                qcol = sch.get("qty")
                unit = (
                    _norm(cells[ucol])
                    if (ucol is not None and ucol < len(cells))
                    else ""
                )
                qty = (
                    _norm(cells[qcol])
                    if (qcol is not None and qcol < len(cells))
                    else ""
                )
                if unit:
                    meta["unit"] = unit
                if qty:
                    meta["qty"] = qty
                name_id = _node_id(si, "NAME", name_val)
                ntype = labels.get(name_id, "GROUP")
                _add_node(
                    nodes_map,
                    name_id,
                    name_val,
                    ntype,
                    " / ".join([*path_parts, name_val]),
                    role="NAME",
                    meta=meta,
                )

            # 4) рёбра: sheet → ур* → шифр → имя
            prev = sheet_id
            for nid in level_ids:
                _add_edge(edges, prev, nid, "parent")
                prev = nid
            if shifr_id:
                _add_edge(edges, prev, shifr_id, "parent")
                prev = shifr_id
            if name_id:
                _add_edge(edges, prev, name_id, "parent")

    # TECH_CARD → WORK/MATERIAL (из разметки)
    for tc in (annotation or {}).get("tech_cards") or []:
        tcu = tc.get("uid")
        for w in tc.get("works") or []:
            _add_edge(edges, tcu, w, "work")
        for m in tc.get("materials") or []:
            _add_edge(edges, tcu, m, "material")

    return {"nodes": list(nodes_map.values()), "edges": edges}
