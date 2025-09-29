"""Инициализация и регистрация всех обработчиков"""

from app_estimate_imports.handlers.base_handler import HandlerFactory
from app_estimate_imports.handlers.parse_handler import ParseHandler
from app_estimate_imports.handlers.markup_handler import MarkupHandler
from app_estimate_imports.handlers.grid_handler import GridHandler
from app_estimate_imports.handlers.graph_handler import GraphHandler
from app_estimate_imports.handlers.api_handler import ApiHandler
from app_estimate_imports.handlers.compose_handler import ComposeHandler


# Регистрируем все обработчики
HandlerFactory.register("parse", ParseHandler)
HandlerFactory.register("markup", MarkupHandler)
HandlerFactory.register("grid", GridHandler)
HandlerFactory.register("graph", GraphHandler)
HandlerFactory.register("api", ApiHandler)
HandlerFactory.register("compose", ComposeHandler)

__all__ = [
    "HandlerFactory",
    "ParseHandler",
    "MarkupHandler",
    "GridHandler",
    "GraphHandler",
    "ApiHandler",
    "ComposeHandler",
]
