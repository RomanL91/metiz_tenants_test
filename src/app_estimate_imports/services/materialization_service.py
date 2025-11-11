"""Сервис материализации смет из разметки"""

from typing import Iterable

from app_outlay.estimate_mapping_utils.exceptions import InvalidSchemaError
from app_outlay.services_materialize import materialize_estimate_from_markup

from .base_service import BaseService
from .markup_service import MarkupService
from .schema_service import SchemaService
from ..utils.constants import ROLE_DEFS, REQUIRED_ROLE_IDS


class MaterializationService(BaseService):
    """Сервис для создания смет из размеченных данных"""

    def __init__(self):
        super().__init__()
        self.markup_service = MarkupService()
        self.schema_service = SchemaService()
        self._role_titles = {role["id"]: role["title"] for role in ROLE_DEFS}

    def materialize_estimate(self, file_obj, sheet_index: int = 0):
        """Создает смету из разметки файла"""
        self.clear_messages()

        try:
            markup = self.markup_service.ensure_markup_exists(file_obj)
        except Exception as exc:  # pragma: no cover - guard branch
            self.add_error(f"Ошибка материализации: {exc}")
            return False

        col_roles, _, _ = self.schema_service.get_schema_config(markup, sheet_index)
        missing_roles = [
            role for role in REQUIRED_ROLE_IDS if role not in (col_roles or [])
        ]
        if missing_roles:
            self._add_missing_roles_error(sheet_index, missing_roles)
            return False

        try:
            estimate = materialize_estimate_from_markup(markup, sheet_index=sheet_index)
            return estimate
        except InvalidSchemaError as exc:
            details = getattr(exc, "details", {}) or {}
            missing = details.get("missing_roles") or missing_roles
            idx = details.get("sheet_index", sheet_index)
            self._add_missing_roles_error(idx, missing)
        except Exception as exc:  # pragma: no cover - unexpected branch
            self.add_error(f"Ошибка материализации: {exc}")
            return False

    def _add_missing_roles_error(
        self, sheet_index: int, missing_roles: Iterable[str]
    ) -> None:
        missing_list = list(missing_roles or [])
        if not missing_list:
            missing_text = "обязательные роли"
        else:
            readable = [self._role_titles.get(role, role) for role in missing_list]
            missing_text = ", ".join(readable)

        sheet_human = sheet_index + 1 if isinstance(sheet_index, int) else sheet_index
        self.add_error(
            "Не заданы обязательные роли колонок"
            f" ({missing_text}) для листа {sheet_human}. "
            "Назначьте роли колонкам и повторите создание сметы."
        )
