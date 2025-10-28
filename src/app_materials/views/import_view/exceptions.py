class MaterialImportException(Exception):
    """Базовое исключение для импорта материалов"""

    pass


class InvalidFileFormatException(MaterialImportException):
    """Неверный формат файла"""

    pass


class InvalidFileStructureException(MaterialImportException):
    """Неверная структура файла (отсутствуют обязательные колонки)"""

    pass


class FileProcessingException(MaterialImportException):
    """Ошибка при обработке файла"""

    pass


class ValidationException(MaterialImportException):
    """Ошибка валидации данных в строках файла"""

    def __init__(self, message: str, errors: list = None):
        super().__init__(message)
        self.errors = errors or []
