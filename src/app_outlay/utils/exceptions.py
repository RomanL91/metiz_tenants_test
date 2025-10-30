"""
Исключения для работы с Excel.
"""


class ExcelError(Exception):
    """Базовое исключение для Excel операций."""

    def __init__(self, message: str, details: dict = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class ExcelFileNotFoundError(ExcelError):
    """Файл Excel не найден."""

    def __init__(self, path: str):
        super().__init__(
            message=f"Excel файл не найден: {path}",
            details={"path": path},
        )


class ExcelSheetNotFoundError(ExcelError):
    """Лист Excel не найден."""

    def __init__(self, sheet_index: int, total_sheets: int):
        super().__init__(
            message=f"Лист с индексом {sheet_index} не найден (всего листов: {total_sheets})",
            details={"sheet_index": sheet_index, "total_sheets": total_sheets},
        )


class ExcelReadError(ExcelError):
    """Ошибка чтения Excel файла."""

    def __init__(self, path: str, error: str):
        super().__init__(
            message=f"Ошибка чтения файла: {error}",
            details={"path": path, "error": error},
        )
