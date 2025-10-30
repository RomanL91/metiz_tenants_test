"""
Исключения для детектирования техкарт.
"""


class MappingUtilsError(Exception):
    """Базовое исключение для mapping utilities."""

    def __init__(self, message: str, details: dict = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class InvalidSchemaError(MappingUtilsError):
    """Неверная схема колонок."""

    def __init__(self, sheet_index: int, missing_roles: list = None):
        super().__init__(
            message=f"Неверная схема для листа {sheet_index}",
            details={
                "sheet_index": sheet_index,
                "missing_roles": missing_roles or [],
            },
        )


class NoTechnicalCardsDetectedError(MappingUtilsError):
    """Техкарты не обнаружены."""

    def __init__(self, sheet_index: int):
        super().__init__(
            message=f"На листе {sheet_index} не обнаружено техкарт",
            details={"sheet_index": sheet_index},
        )
