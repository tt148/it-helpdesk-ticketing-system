from django.contrib import admin

from .models import AuditLog, Category, Comment, Ticket

admin.site.register(Ticket)
admin.site.register(Category)
admin.site.register(Comment)
admin.site.register(AuditLog)
