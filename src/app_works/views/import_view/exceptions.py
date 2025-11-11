class WorkImportException(Exception):
    """Базовое исключение для импорта работ"""

    pass


class InvalidFileFormatException(WorkImportException):
    """Неверный формат файла"""

    pass


class InvalidFileStructureException(WorkImportException):
    """Неверная структура файла"""

    pass


class FileProcessingException(WorkImportException):
    """Ошибка при обработке файла"""

    pass


class ValidationException(WorkImportException):
    """Ошибка валидации данных в строках файла"""

    def __init__(self, message: str, errors: list = None):
        super().__init__(message)
        self.errors = errors or []
