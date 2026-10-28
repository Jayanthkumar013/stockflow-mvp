from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Organization, Product, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Organization", {"fields": ("organization",)}),)
    list_display = ("username", "email", "organization", "is_staff")


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "default_low_stock_threshold", "created_at")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "organization", "quantity_on_hand", "selling_price")
    list_filter = ("organization",)
    search_fields = ("name", "sku")
