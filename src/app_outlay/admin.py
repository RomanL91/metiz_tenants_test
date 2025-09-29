from django.contrib import admin

from app_outlay.models import Estimate, Group, GroupTechnicalCardLink


# ---------- INLINES ----------


class GroupTechnicalCardLinkInline(admin.TabularInline):
    model = GroupTechnicalCardLink
    extra = 0
    ordering = ("order", "id")
    raw_id_fields = ("technical_card_version",)
    fields = (
        "order",
        "technical_card_version",
        "quantity",
        "unit_display",
        "unit_cost_materials_display",
        "unit_cost_works_display",
        "unit_cost_total_display",
        "total_cost_materials_display",
        "total_cost_works_display",
        "total_cost_display",
        "pinned_at",
    )
    readonly_fields = (
        "unit_display",
        "unit_cost_materials_display",
        "unit_cost_works_display",
        "unit_cost_total_display",
        "total_cost_materials_display",
        "total_cost_works_display",
        "total_cost_display",
        "pinned_at",
    )

    # — отрисовка вычисляемых полей «как в смете»
    def unit_display(self, obj):
        return obj.unit or ""

    unit_display.short_description = "Ед. ТК"

    def unit_cost_materials_display(self, obj):
        v = obj.unit_cost_materials
        return "—" if v in (None, "") else f"{v:.2f}"

    unit_cost_materials_display.short_description = "Цена МАТ/ед"

    def unit_cost_works_display(self, obj):
        v = obj.unit_cost_works
        return "—" if v in (None, "") else f"{v:.2f}"

    unit_cost_works_display.short_description = "Цена РАБ/ед"

    def unit_cost_total_display(self, obj):
        v = obj.unit_cost_total
        return "—" if v in (None, "") else f"{v:.2f}"

    unit_cost_total_display.short_description = "Итого / ед (ТК)"

    def total_cost_materials_display(self, obj):
        v = obj.total_cost_materials
        return "—" if v in (None, "") else f"{v:.2f}"

    total_cost_materials_display.short_description = "МАТ × кол-во"

    def total_cost_works_display(self, obj):
        v = obj.total_cost_works
        return "—" if v in (None, "") else f"{v:.2f}"

    total_cost_works_display.short_description = "РАБ × кол-во"

    def total_cost_display(self, obj):
        v = obj.total_cost
        return "—" if v in (None, "") else f"{v:.2f}"

    total_cost_display.short_description = "Итого (МАТ+РАБ) × кол-во"


# ---------- АДМИНКИ ----------


@admin.register(Estimate)
class EstimateAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "currency",
        "groups_count",
        "tc_links_count",
    )
    search_fields = ("name",)

    def groups_count(self, obj):
        return obj.groups.count()

    groups_count.short_description = "Групп"

    def tc_links_count(self, obj):
        # Быстрый подсчёт через related name
        return GroupTechnicalCardLink.objects.filter(group__estimate=obj).count()

    tc_links_count.short_description = "ТК в смете"


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "estimate", "parent", "order")
    list_filter = ("estimate",)
    search_fields = ("name",)
    raw_id_fields = ("estimate", "parent")
    inlines = (GroupTechnicalCardLinkInline,)

    # Немного удобства: группируем по смете и порядку
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("estimate", "parent")
