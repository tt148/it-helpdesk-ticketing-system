from django.conf import settings
from django.core.mail import send_mail

from .models import AuditLog


def audit(ticket, actor, action, details=None):
    return AuditLog.objects.create(ticket=ticket, actor=actor, action=action, details=details or {})

def notify(subject, message, recipients):
    recipients = [email for email in set(recipients) if email]
    if recipients:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=True)
