"""
Сериализаторы для API сохранения маппингов.
"""

from rest_framework import serializers


class MappingItemSerializer(serializers.Serializer):
    """Элемент сопоставления."""

    section = serializers.CharField(default="Без группы")
    tc_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    tc_version_id = serializers.IntegerField(
        min_value=1, required=False, allow_null=True
    )
    quantity = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=0)
    row_index = serializers.IntegerField(min_value=1)
    tc_name = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        tc_id = attrs.get("tc_id")
        tc_version_id = attrs.get("tc_version_id")
        if not tc_id and not tc_version_id:
            raise serializers.ValidationError(
                "Не указан идентификатор технической карты"
            )
        return attrs


class SaveMappingsRequestSerializer(serializers.Serializer):
    """Запрос на сохранение маппингов."""

    mappings = serializers.ListField(
        child=MappingItemSerializer(),
        allow_empty=True,
        default=list,
    )
    deletions = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=True,
        default=list,
    )

    def validate(self, data):
        if not data.get("mappings") and not data.get("deletions"):
            raise serializers.ValidationError("Нет данных для сохранения")
        return data


class SaveMappingsResponseSerializer(serializers.Serializer):
    """Ответ после сохранения маппингов."""

    ok = serializers.BooleanField(default=True)
    created = serializers.IntegerField()
    updated = serializers.IntegerField()
    deleted = serializers.IntegerField()
    total = serializers.IntegerField()
