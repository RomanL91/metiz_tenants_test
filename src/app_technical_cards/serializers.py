from decimal import Decimal

from rest_framework import serializers


class LiveMaterialCompositionSerializer(serializers.Serializer):
    """Материал из версии ТК с актуальной ценой из справочника."""

    id = serializers.IntegerField(source="material.id")
    name = serializers.CharField(source="material.name")
    unit = serializers.CharField(source="material.unit_ref.name")

    # Снапшот из версии
    version_price = serializers.DecimalField(
        source="price_per_unit", max_digits=12, decimal_places=2
    )

    # Живая цена из справочника
    live_price = serializers.DecimalField(
        source="material.price_per_unit", max_digits=12, decimal_places=2
    )

    qty_per_unit = serializers.DecimalField(max_digits=16, decimal_places=6)

    # Расчетные поля
    version_line_cost = serializers.SerializerMethodField()
    live_line_cost = serializers.SerializerMethodField()
    price_changed = serializers.SerializerMethodField()

    def get_version_line_cost(self, obj):
        return (obj.price_per_unit or Decimal("0")) * (obj.qty_per_unit or Decimal("0"))

    def get_live_line_cost(self, obj):
        return (obj.material.price_per_unit or Decimal("0")) * (
            obj.qty_per_unit or Decimal("0")
        )

    def get_price_changed(self, obj):
        return obj.price_per_unit != obj.material.price_per_unit


class LiveWorkCompositionSerializer(serializers.Serializer):
    """Работа из версии ТК с актуальной ценой из справочника."""

    id = serializers.IntegerField(source="work.id")
    name = serializers.CharField(source="work.name")
    unit = serializers.SerializerMethodField()
    calculation_method = serializers.CharField()
    calculation_method_label = serializers.CharField(
        source="get_calculation_method_display"
    )

    # Снапшот из версии
    version_price = serializers.DecimalField(
        source="price_per_unit", max_digits=12, decimal_places=2
    )

    # Живая цена из справочника
    live_price = serializers.SerializerMethodField()

    qty_per_unit = serializers.DecimalField(max_digits=16, decimal_places=6)

    # Расчетные поля
    version_line_cost = serializers.SerializerMethodField()
    live_line_cost = serializers.SerializerMethodField()
    price_changed = serializers.SerializerMethodField()

    def get_unit(self, obj):
        unit = getattr(obj, "unit_ref", None)
        if unit and getattr(unit, "symbol", None):
            return unit.symbol
        if unit and getattr(unit, "name", None):
            return unit.name
        live_unit = obj.work.get_unit_for_method(obj.calculation_method)
        if live_unit and getattr(live_unit, "symbol", None):
            return live_unit.symbol
        if live_unit and getattr(live_unit, "name", None):
            return live_unit.name
        return ""

    def get_version_line_cost(self, obj):
        return (obj.price_per_unit or Decimal("0")) * (obj.qty_per_unit or Decimal("0"))

    def get_live_line_cost(self, obj):
        live_price = self.get_live_price(obj)
        return live_price * (obj.qty_per_unit or Decimal("0"))

    def get_price_changed(self, obj):
        return self.get_live_price(obj) != (obj.price_per_unit or Decimal("0"))

    def get_live_price(self, obj):
        price = obj.work.get_price_for_method(obj.calculation_method)
        return price or Decimal("0")


class LiveCompositionSerializer(serializers.Serializer):
    """Полный состав ТК с живыми ценами."""

    version_id = serializers.IntegerField()
    version_number = serializers.CharField()
    created_at = serializers.DateTimeField()

    materials = LiveMaterialCompositionSerializer(many=True)
    works = LiveWorkCompositionSerializer(many=True)

    # Итоги
    totals = serializers.SerializerMethodField()

    def get_totals(self, data):
        """Расчет итогов по версии и с живыми ценами."""
        materials = data["materials"]
        works = data["works"]

        version_materials_total = sum(
            (m.price_per_unit or Decimal("0")) * (m.qty_per_unit or Decimal("0"))
            for m in materials
        )
        version_works_total = sum(
            (w.price_per_unit or Decimal("0")) * (w.qty_per_unit or Decimal("0"))
            for w in works
        )

        live_materials_total = sum(
            (m.material.price_per_unit or Decimal("0"))
            * (m.qty_per_unit or Decimal("0"))
            for m in materials
        )
        live_works_total = sum(
            (w.work.get_price_for_method(w.calculation_method) or Decimal("0"))
            * (w.qty_per_unit or Decimal("0"))
            for w in works
        )

        return {
            "version": {
                "materials": version_materials_total,
                "works": version_works_total,
                "total": version_materials_total + version_works_total,
            },
            "live": {
                "materials": live_materials_total,
                "works": live_works_total,
                "total": live_materials_total + live_works_total,
            },
        }
