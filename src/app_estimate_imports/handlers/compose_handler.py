"""Обработчик для управления составом техкарт.

Назначение:
- Предоставляет представления (handler'ы) для UI админки, позволяющие
  просматривать и редактировать состав конкретной техкарты (список WORK/MATERIAL).
- Вся бизнес-логика вынесена в TechCardService; здесь — только склейка с HTTP/UI.

Потоки:
- GET  -> show_compose: вывести форму редактирования состава для tc_uid.
- POST -> show_compose: принять выбранные WORK/MATERIAL и сохранить через сервис.
"""

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.utils.safestring import mark_safe

from app_estimate_imports.handlers.base_handler import BaseHandler
from app_estimate_imports.services.techcard_service import TechCardService


class ComposeHandler(BaseHandler):
    """
    Обработчик управления составом техкарт.

    Хранит ссылку на TechCardService (доменные операции с техкартами)
    и использует вспомогательные методы BaseHandler:
      - get_object_or_error: получить объект файла или показать сообщение об ошибке
      - redirect_back_or_change: удобный редирект назад/к change-view
      - add_service_messages: перенести накопленные сервисом сообщения в Django messages
    """

    def __init__(self, admin_instance):
        super().__init__(admin_instance)
        # Доменный сервис, отвечающий за валидацию/чтение/сохранение состава ТК
        self.techcard_service = TechCardService()

    def show_compose(self, request: HttpRequest, pk: int) -> HttpResponse:
        """
        Показывает интерфейс настройки состава техкарты или обрабатывает POST.

        Маршрутизация:
          - Если нет ParseResult — сообщение и редирект обратно.
          - Если отсутствует tc_uid в query/post — сообщение и редирект на labeler.
          - Если метод POST — делегируем сохранение в _handle_compose_post.
          - Иначе (GET) — строим и возвращаем HTML-форму через _show_compose_form.

        :param request: текущий HttpRequest
        :param pk: id импортированного файла
        """
        obj = self.get_object_or_error(request, pk)
        if not obj or not hasattr(obj, "parse_result"):
            messages.error(request, "Нет ParseResult")
            return self.redirect_back_or_change(request)

        # Ищем идентификатор техкарты из GET/POST (универсально для обоих методов)
        tc_uid = request.GET.get("tc_uid") or request.POST.get("tc_uid")
        if not tc_uid:
            messages.error(request, "Не указан tc_uid")
            return HttpResponseRedirect(f"../labeler/")  # TODO прочистить это в файле!!

        # POST: принять и сохранить состав
        if request.method == "POST":
            return self._handle_compose_post(request, obj, tc_uid)
        # GET: отрисовать форму
        return self._show_compose_form(request, obj, tc_uid)

    def _handle_compose_post(
        self, request: HttpRequest, obj, tc_uid: str
    ) -> HttpResponse:
        """
        Обрабатывает POST запрос с составом техкарты.

        Ожидаем поля

        """
        works = request.POST.getlist("works")
        materials = request.POST.getlist("materials")

        try:
            if self.techcard_service.validate_techcard_composition(works, materials):
                success = self.techcard_service.update_techcard_composition(
                    obj, tc_uid, works, materials
                )

                if success:
                    messages.success(request, "Состав техкарты обновлён")
                else:
                    self.techcard_service.add_messages_to_request(request)
            else:
                self.techcard_service.add_messages_to_request(request)

            return HttpResponseRedirect(f"../labeler/")

        except Exception as e:
            messages.error(request, f"Ошибка: {e!r}")
            return HttpResponseRedirect(f"../labeler/")

    def _show_compose_form(
        self, request: HttpRequest, obj, tc_uid: str
    ) -> HttpResponse:
        """Показывает форму настройки состава"""
        # Получаем текущий состав техкарты
        composition = self.techcard_service.get_techcard_composition(obj, tc_uid)
        current_works = composition.get("works", [])
        current_materials = composition.get("materials", [])

        # Получаем все доступные работы и материалы
        available_works, available_materials = (
            self.techcard_service.get_available_works_and_materials(obj)
        )

        # Генерируем опции для селектов
        work_options = self._generate_select_options(available_works, current_works)
        material_options = self._generate_select_options(
            available_materials, current_materials
        )

        html = f"""
        <h2>Состав техкарты: {tc_uid}</h2>
        <form method="post">
        <input type="hidden" name="csrfmiddlewaretoken" value="{request.META.get('CSRF_COOKIE', '')}">
        <input type="hidden" name="tc_uid" value="{tc_uid}">
        
        <div style="display:flex; gap:24px;">
            <div>
                <label><strong>РАБОТЫ</strong></label><br>
                <select name="works" multiple size="15" style="min-width:360px;">
                    {''.join(work_options)}
                </select>
            </div>
            <div>
                <label><strong>МАТЕРИАЛЫ</strong></label><br>
                <select name="materials" multiple size="15" style="min-width:360px;">
                    {''.join(material_options)}
                </select>
            </div>
        </div>
        
        <p style="margin-top:16px;">
            <button class="button" type="submit">Сохранить</button>
            <a class="button" href="../labeler/">Отмена</a> 
        </p>
        </form>
        """

        return HttpResponse(mark_safe(html))

    def _generate_select_options(self, items: list, selected: list) -> list:
        """
        Генерирует список HTML-опций для <select multiple>.
        :param items: список словарей предметной области: [{"uid": str, "name": str}, ...]
        :param selected: список uid, которые должны быть отмечены как выбранные
        :return: список строк с готовыми <option>…</option>
        """
        options = []
        for item in items:
            uid = item["uid"]
            name = item["name"]
            selected_attr = "selected" if uid in selected else ""
            options.append(
                f'<option value="{uid}" {selected_attr}>{name} ({uid})</option>'
            )
        return options
