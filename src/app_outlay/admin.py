from django.contrib import admin

from app_outlay.models import Estimate


@admin.register(Estimate)
class AdminEstimate(admin.ModelAdmin):
    pass
