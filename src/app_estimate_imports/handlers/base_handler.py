"""Инфраструктурный модуль обработчиков (handlers).

Содержит:
- BaseHandler: базовый класс с общими вспомогательными методами для админских обработчиков,
  а также доступ к доменным сервисам (MarkupService, SchemaService, GroupService).
- HandlerFactory: простая фабрика/реестр обработчиков по имени, чтобы admin.py мог
  создавать нужный handler, не зная его конкретного класса.

Идея: админ-класс остаётся тонким, делегируя бизнес-логику специализированным обработчикам.
"""

from abc import ABC
from typing import Dict, Type

from django.contrib import messages
from django.http import HttpRequest, HttpResponseRedirect

from app_estimate_imports.services.group_service import GroupService
from app_estimate_imports.services.markup_service import MarkupService
from app_estimate_imports.services.schema_service import SchemaService


class BaseHandler(ABC):
    """Базовый класс для обработчиков представлений.

    Назначение:
      - Инкапсулирует общий вспомогательный функционал, общий для всех обработчиков:
        * доступ к admin-инстансу (для each_context, message_user и др.);
        * инициализация и доступ к доменным сервисам (markup/schema/group);
        * типовые утилиты: получение объекта по pk с показом ошибки, удобный редирект;
        * сбор и прокидывание сообщений из сервисов в request (Django messages framework).

    Контракт:
      - Наследники получают готовые сервисы и могут их использовать.
      - Наследники должны вызывать add_service_messages() после операций сервисов,
        чтобы сообщения (ошибки/варнинги/инфо) попали в UI.
    """

    def __init__(self, admin_instance):
        # ссылка на админ класс, чтобы пользоваться его методами
        self.admin = admin_instance
        # доступ к доменным сервисам: разметка, схема колонок, группировка строк
        self.markup_service = MarkupService()
        self.schema_service = SchemaService()
        self.group_service = GroupService()

    def get_object_or_error(self, request: HttpRequest, pk: int):
        """Получает объект или возвращает ошибку"""
        obj = self.admin.get_object(request, pk)
        if not obj:
            messages.error(request, "Файл не найден")
            return None
        return obj

    def redirect_back_or_change(self, request: HttpRequest, obj=None):
        """Перенаправляет пользователя «назад» или на страницу изменения объекта.
        Поведение:
          - Если obj передан → редирект на страницу изменения этого объекта:
              ../<pk>/change/
          - Иначе → редирект на HTTP_REFERER (если нет — на '..').
        """
        if obj:
            return HttpResponseRedirect(f"../{obj.pk}/change/")
        return HttpResponseRedirect(request.META.get("HTTP_REFERER", ".."))

    def add_service_messages(self, request: HttpRequest):
        """Добавляет в request сообщения, накопленные доменными сервисами.
        Контекст:
          Сервисы (MarkupService, SchemaService, GroupService) могут складывать
          свои сообщения (errors/warnings/info) во внутренние буферы. Этот метод
          переносит их , чтобы они отобразились в админке.
        """
        self.markup_service.add_messages_to_request(request)
        self.schema_service.add_messages_to_request(request)
        self.group_service.add_messages_to_request(request)


class HandlerFactory:
    """Фабрика/реестр обработчиков по строковому ключу.

    Задача:
      - Централизованно регистрировать доступные Handler-классы;
      - Создавать экземпляры по имени из admin.py или других модулей.

    Пример:
      HandlerFactory.register("grid", GridHandler)
      handler = HandlerFactory.create("grid", self)  # self — admin instance
    """

    # внутренний реестр: имя → класс обработчика
    _handlers: Dict[str, Type[BaseHandler]] = {}

    @classmethod
    def register(cls, name: str, handler_class: Type[BaseHandler]):
        """Регистрирует обработчик"""
        cls._handlers[name] = handler_class

    @classmethod
    def create(cls, name: str, admin_instance) -> BaseHandler:
        """Создаёт экземпляр обработчика по имени.

        :param name: зарегистрированное имя обработчика
        :param admin_instance: instance класса ModelAdmin (передаётся в handler)

        :raises ValueError: если имя не зарегистрировано

        Возвращает:
          Экземпляр нужного обработчика, готовый к использованию.
        """
        if name not in cls._handlers:
            raise ValueError(f"Handler '{name}' not registered")
        return cls._handlers[name](admin_instance)
