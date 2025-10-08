"""Админ-панель для управления накладными расходами."""

import nested_admin

from django.db import models
from django import forms
from django.contrib import admin
from django.db.models import Sum, Count
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html

from .models import OverheadCostContainer, OverheadCostItem


class OverheadCostItemInline(nested_admin.NestedTabularInline):
    """Инлайн для редактирования статей расходов внутри контейнера."""

    model = OverheadCostItem
    extra = 1
    fields = (
        "order",
        "name",
        "quantity",
        "unit",
        "price_per_unit",
        "total_cost_display",
        "comment",
    )
    readonly_fields = ("total_cost_display",)
    ordering = ("order", "id")

    formfield_overrides = {
        models.TextField: {"widget": forms.TextInput(attrs={"size": "40"})},
    }

    @admin.display(description=_("Итого"))
    def total_cost_display(self, obj):
        if obj.pk:
            return f"{obj.total_cost:,.2f}"
        return "—"


@admin.register(OverheadCostContainer)
class OverheadCostContainerAdmin(nested_admin.NestedModelAdmin):
    """Админка контейнеров накладных расходов."""

    list_display = (
        "name",
        "distribution_display",
        "items_count_display",
        "total_amount_display",
        "is_active",
        "updated_at",
    )
    list_filter = ("is_active", "created_at")
    search_fields = ("name", "description")
    readonly_fields = (
        "total_amount_display",
        "items_count_display",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            _("Основная информация"),
            {
                "fields": ("name", "description", "is_active"),
            },
        ),
        (
            _("Настройка распределения"),
            {
                "fields": ("materials_percentage", "works_percentage"),
                "description": _("Сумма процентов должна равняться 100%"),
            },
        ),
        (
            _("Статистика"),
            {
                "fields": ("items_count_display", "total_amount_display"),
                "classes": ("collapse",),
            },
        ),
        (
            _("Служебная информация"),
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    inlines = [OverheadCostItemInline]

    def get_queryset(self, request):
        """Оптимизация: аннотируем количество статей."""
        qs = super().get_queryset(request)
        return qs.annotate(
            _items_count=Count("items"),
        )

    @admin.display(description=_("Распределение"), ordering="materials_percentage")
    def distribution_display(self, obj):
        """Визуальное отображение настройки распределения."""
        mat_pct = float(obj.materials_percentage or 0)
        work_pct = float(obj.works_percentage or 0)

        # Проверка корректности
        total = mat_pct + work_pct
        if total != 100:
            color = "#dc3545"  # красный
            icon = "⚠️"
        else:
            color = "#28a745"  # зелёный
            icon = "✓"

        return format_html(
            '<span style="color: {};">{} МАТ: {}% / РАБ: {}%</span>',
            color,
            icon,
            mat_pct,
            work_pct,
        )

    @admin.display(description=_("Статей"))
    def items_count_display(self, obj):
        """Количество статей расходов."""
        if hasattr(obj, "_items_count"):
            return obj._items_count
        return obj.items.count()

    @admin.display(description=_("Общая сумма"))
    def total_amount_display(self, obj):
        """Общая сумма всех статей."""
        total = obj.total_amount
        if total > 0:
            formatted_total = f"{total:,.2f}"
            return format_html(
                '<strong style="color: #007bff;">{}</strong>', formatted_total
            )
        return "0.00"


@admin.register(OverheadCostItem)
class OverheadCostItemAdmin(admin.ModelAdmin):
    """Админка для прямого редактирования статей расходов (опционально)."""

    list_display = (
        "name",
        "container",
        "quantity",
        "unit",
        "price_per_unit",
        "total_cost_display",
    )
    list_filter = ("container", "unit")
    search_fields = ("name", "comment", "container__name")
    raw_id_fields = ("container",)

    fieldsets = (
        (
            None,
            {
                "fields": ("container", "name", "order"),
            },
        ),
        (
            _("Расчёт"),
            {
                "fields": ("quantity", "unit", "price_per_unit", "total_cost_display"),
            },
        ),
        (
            _("Дополнительно"),
            {
                "fields": ("comment",),
                "classes": ("collapse",),
            },
        ),
    )

    readonly_fields = ("total_cost_display",)

    @admin.display(description=_("Итого"))
    def total_cost_display(self, obj):
        return f"{obj.total_cost:,.2f}"
