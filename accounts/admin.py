from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("email", "username", "role", "is_active", "is_staff")
    fieldsets = UserAdmin.fieldsets + (("Helpdesk role", {"fields": ("role",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Helpdesk role", {"fields": ("email", "role")}),)
