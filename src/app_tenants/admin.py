from django.contrib import admin
from django_tenants.admin import TenantAdminMixin

from app_tenants.models import Domain, Tenant

# @admin.register(Tenant)
# class TenantAdmin(TenantAdminMixin, admin.ModelAdmin):
#     pass


# @admin.register(Domain)
# class DomainAdmin(admin.ModelAdmin):
#     pass
