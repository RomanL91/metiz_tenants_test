from rest_framework import serializers
from django.utils.translation import gettext_lazy as _


class WorkImportFileSerializer(serializers.Serializer):
    """Сериализатор для загрузки файла импорта работ"""

    file = serializers.FileField(
        required=True,
        allow_empty_file=False,
        help_text=_("Excel файл (.xlsx или .xls) с данными работ"),
    )

    def validate_file(self, value):
        """Валидация файла"""
        allowed_extensions = [".xlsx", ".xls"]
        file_name = value.name.lower()

        if not any(file_name.endswith(ext) for ext in allowed_extensions):
            raise serializers.ValidationError(
                _("Неверный формат файла. Разрешены только .xlsx и .xls")
            )

        max_size = 10 * 1024 * 1024  # 10MB
        if value.size > max_size:
            raise serializers.ValidationError(
                _("Файл слишком большой. Максимальный размер: 10MB")
            )

        return value


class WorkImportResultSerializer(serializers.Serializer):
    """Сериализатор результата импорта работ"""

    status = serializers.ChoiceField(
        choices=["success", "partial", "error"],
        help_text=_("Статус импорта"),
    )
    created = serializers.IntegerField(help_text=_("Количество созданных записей"))
    updated = serializers.IntegerField(help_text=_("Количество обновленных записей"))
    skipped = serializers.IntegerField(help_text=_("Количество пропущенных записей"))
    errors = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=True,
        help_text=_("Список ошибок"),
    )
    message = serializers.CharField(
        allow_blank=True,
        help_text=_("Сообщение о результате"),
    )


class WorkImportErrorSerializer(serializers.Serializer):
    """Сериализатор ошибки импорта"""

    row = serializers.IntegerField(help_text=_("Номер строки в файле"))
    field = serializers.CharField(help_text=_("Поле с ошибкой"), allow_blank=True)
    error = serializers.CharField(help_text=_("Описание ошибки"))
