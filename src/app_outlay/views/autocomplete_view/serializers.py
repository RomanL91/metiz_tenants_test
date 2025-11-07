"""
Сериализаторы для валидации запросов автокомплита и batch-сопоставления.

Следует принципам:
- Single Responsibility: каждый сериализатор отвечает за свою область
- Validation: строгая проверка входных данных
- Clear Error Messages: понятные сообщения об ошибках
"""

from rest_framework import serializers


class AutocompleteQuerySerializer(serializers.Serializer):
    """
    Валидация запроса поиска ТК.

    GET /autocomplete/?q=поиск&limit=20
    """

    q = serializers.CharField(
        required=True,
        min_length=1,
        max_length=500,
        trim_whitespace=True,
        help_text="Поисковый запрос (мин. 1 символ)",
    )

    limit = serializers.IntegerField(
        required=False,
        default=20,
        min_value=1,
        max_value=100,
        help_text="Максимальное количество результатов (1-100)",
    )

    def validate_q(self, value):
        """Дополнительная валидация поискового запроса."""
        if not value or not value.strip():
            raise serializers.ValidationError("Поисковый запрос не может быть пустым")
        return value.strip()


class BatchMatchItemSerializer(serializers.Serializer):
    """
    Валидация одного элемента для batch-сопоставления.

    Каждый элемент должен содержать:
    - row_index: индекс строки в Excel
    - name: название работы/материала
    - unit: единица измерения
    """

    row_index = serializers.IntegerField(
        required=True, min_value=1, help_text="Индекс строки в исходном файле Excel"
    )

    name = serializers.CharField(
        required=True,
        min_length=1,
        max_length=500,
        trim_whitespace=True,
        allow_blank=False,
        help_text="Название работы/материала для сопоставления",
    )

    unit = serializers.CharField(
        required=True,
        max_length=50,
        trim_whitespace=True,
        allow_blank=True,  # Единица может быть пустой
        help_text="Единица измерения (например: м2, шт, м3)",
    )

    def validate_name(self, value):
        """Проверяем, что название не пустое после trim."""
        if not value or not value.strip():
            raise serializers.ValidationError("Название не может быть пустым")
        return value.strip()

    def validate_unit(self, value):
        """Нормализуем единицу измерения."""
        return value.strip() if value else ""


class BatchMatchRequestSerializer(serializers.Serializer):
    """
    Валидация запроса batch-сопоставления.

    POST /autocomplete/batch-match/
    {
        "items": [
            {"row_index": 1, "name": "Установка окна", "unit": "шт"},
            {"row_index": 2, "name": "Штукатурка стен", "unit": "м2"}
        ]
    }
    """

    items = serializers.ListField(
        child=BatchMatchItemSerializer(),
        required=True,
        min_length=1,
        max_length=1000,  # Ограничение для защиты от перегрузки
        help_text="Список элементов для сопоставления (макс. 1000)",
    )

    def validate_items(self, value):
        """Проверяем уникальность row_index."""
        if not value:
            raise serializers.ValidationError("Список не может быть пустым")

        # Проверка на дубликаты row_index
        row_indices = [item["row_index"] for item in value]
        if len(row_indices) != len(set(row_indices)):
            raise serializers.ValidationError(
                "Обнаружены дублирующиеся row_index. "
                "Каждая строка должна быть уникальной."
            )

        return value


class AutocompleteResultSerializer(serializers.Serializer):
    """
    Сериализация результата автокомплита.

    Возвращает минимально необходимый набор данных:
    - id: ID технической карты
    - text: название для отображения
    """

    id = serializers.IntegerField(help_text="ID технической карты")

    text = serializers.CharField(
        help_text="Название технической карты с единицей измерения"
    )


class BatchMatchResultSerializer(serializers.Serializer):
    """
    Сериализация результата batch-сопоставления.

    Возвращает исходные данные + результаты сопоставления:
    - row_index: индекс строки
    - name: исходное название
    - unit: исходная единица
    - matched_tc_id: ID найденной ТК (card_id, или null)
    - matched_tc_card_id: явное поле card_id (для читаемости, или null)
    - matched_tc_version_id: ID версии (опционально, или null)
    - matched_tc_text: название найденной ТК (или пустая строка)
    - similarity: коэффициент схожести (0.0 - 1.0)
    """

    row_index = serializers.IntegerField()
    name = serializers.CharField()
    unit = serializers.CharField()
    matched_tc_id = serializers.IntegerField(allow_null=True)
    matched_tc_card_id = serializers.IntegerField(allow_null=True)
    matched_tc_version_id = serializers.IntegerField(allow_null=True)
    matched_tc_text = serializers.CharField()
    similarity = serializers.FloatField()
