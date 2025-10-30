"""
Доменные исключения для экспорта Excel.

Следует принципам:
- Explicit Error Handling: явные типы ошибок
- Clear Messages: понятные сообщения для пользователя
- Domain-Driven Design: ошибки бизнес-логики
"""


class ExcelExportError(Exception):
    """Базовое исключение для ошибок экспорта."""

    def __init__(self, message: str, details: dict = None):
        """
        Args:
            message: Сообщение об ошибке для пользователя
            details: Дополнительные технические детали
        """
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class EstimateNotFoundError(ExcelExportError):
    """Смета не найдена."""

    def __init__(self, estimate_id: int):
        super().__init__(
            message=f"Смета с ID {estimate_id} не найдена",
            details={"estimate_id": estimate_id},
        )


class SourceFileNotFoundError(ExcelExportError):
    """Исходный файл Excel не найден."""

    def __init__(self, estimate_id: int):
        super().__init__(
            message="Исходный файл Excel не найден или удалён",
            details={"estimate_id": estimate_id},
        )


class MarkupNotFoundError(ExcelExportError):
    """Разметка файла не найдена."""

    def __init__(self, estimate_id: int):
        super().__init__(
            message="Разметка файла не найдена. Необходимо выполнить разметку сначала",
            details={"estimate_id": estimate_id},
        )


class SchemaNotFoundError(ExcelExportError):
    """Схема колонок не определена."""

    def __init__(self, sheet_index: int):
        super().__init__(
            message="Не удалось определить структуру колонок в файле",
            details={"sheet_index": sheet_index},
        )


class NoMappingsFoundError(ExcelExportError):
    """Нет сопоставлений для экспорта."""

    def __init__(self, estimate_id: int):
        super().__init__(
            message="Нет сопоставлений для экспорта. Сначала выполните сопоставление и сохраните",
            details={"estimate_id": estimate_id},
        )


class NoWritableColumnsError(ExcelExportError):
    """Нет размеченных колонок для записи."""

    def __init__(self, sheet_index: int):
        super().__init__(
            message="Нет размеченных колонок для записи данных",
            details={"sheet_index": sheet_index},
        )


class CalculationError(ExcelExportError):
    """Ошибка расчёта техкарты."""

    def __init__(self, row_index: int, tc_name: str, error: str):
        super().__init__(
            message=f"Ошибка расчёта в строке {row_index}: {error}",
            details={"row_index": row_index, "tc_name": tc_name, "error": error},
        )


class ExcelWriteError(ExcelExportError):
    """Ошибка записи в Excel файл."""

    def __init__(self, cell_address: str, error: str):
        super().__init__(
            message=f"Ошибка записи в ячейку {cell_address}: {error}",
            details={"cell_address": cell_address, "error": error},
        )
