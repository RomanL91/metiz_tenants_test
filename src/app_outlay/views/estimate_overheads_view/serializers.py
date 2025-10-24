"""
Сериализаторы для API накладных расходов.
"""

from rest_framework import serializers


class OverheadLinkSerializer(serializers.Serializer):
    """Связь НР со сметой (агрегированная)."""

    id = serializers.IntegerField()
    container_id = serializers.IntegerField()
    name = serializers.CharField()
    snapshot_total = serializers.FloatField()
    current_total = serializers.FloatField()
    materials_pct = serializers.FloatField()
    works_pct = serializers.FloatField()
    quantity = serializers.IntegerField()
    is_active = serializers.BooleanField()
    order = serializers.IntegerField()
    applied_at = serializers.CharField(allow_null=True)
    has_changes = serializers.BooleanField()


class OverheadContainerSerializer(serializers.Serializer):
    """Контейнер НР."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    total = serializers.FloatField()
    materials_pct = serializers.FloatField()
    works_pct = serializers.FloatField()


class OverheadListResponseSerializer(serializers.Serializer):
    """Ответ списка НР."""

    ok = serializers.BooleanField(default=True)
    links = serializers.ListField(child=OverheadLinkSerializer())
    containers = serializers.ListField(child=OverheadContainerSerializer())
    overhead_total = serializers.FloatField()
    avg_materials_pct = serializers.FloatField()
    avg_works_pct = serializers.FloatField()


class OverheadApplyRequestSerializer(serializers.Serializer):
    """Запрос добавления НР."""

    container_id = serializers.IntegerField(min_value=1)


class OverheadToggleRequestSerializer(serializers.Serializer):
    """Запрос переключения активности НР."""

    link_id = serializers.IntegerField(min_value=1)
    is_active = serializers.BooleanField()


class OverheadDeleteRequestSerializer(serializers.Serializer):
    """Запрос удаления НР."""

    link_id = serializers.IntegerField(min_value=1)


class OverheadQuantityRequestSerializer(serializers.Serializer):
    """Запрос изменения количества НР."""

    link_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1, max_value=1000)
