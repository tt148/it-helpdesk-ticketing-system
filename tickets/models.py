from datetime import timedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

class Category(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(unique=True)
    description = models.CharField(max_length=255, blank=True)
    def __str__(self): return self.name

class Ticket(models.Model):
    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "In Progress"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"
    TRANSITIONS = {"open": {"in_progress", "resolved"}, "in_progress": {"open", "resolved"}, "resolved": {"in_progress", "closed"}, "closed": set()}
    SLA_HOURS = {"critical": 4, "high": 8, "medium": 48, "low": 72}
    title = models.CharField(max_length=180)
    description = models.TextField()
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="tickets")
    priority = models.CharField(max_length=12, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="requested_tickets")
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_tickets")
    first_response_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "priority"]), models.Index(fields=["created_at"])]
    def __str__(self): return f"HD-{self.pk or 'NEW'}: {self.title}"
    @property
    def response_due_at(self): return self.created_at + timedelta(hours=self.SLA_HOURS[self.priority])
    @property
    def resolution_due_at(self): return self.created_at + timedelta(hours=self.SLA_HOURS[self.priority])
    @property
    def is_overdue(self):
        if self.status in {self.Status.RESOLVED, self.Status.CLOSED}: return False
        return timezone.now() > self.resolution_due_at
    def transition_to(self, new_status):
        if new_status == self.status: return
        if new_status not in self.TRANSITIONS.get(self.status, set()):
            raise ValidationError(f"Cannot transition a ticket from {self.get_status_display()} to {dict(self.Status.choices).get(new_status, new_status)}.")
        self.status = new_status
        if new_status == self.Status.RESOLVED: self.resolved_at = timezone.now()
        elif new_status == self.Status.IN_PROGRESS and self.resolved_at: self.resolved_at = None
        self.save()

class Comment(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ticket_comments")
    body = models.TextField()
    is_internal = models.BooleanField(default=False, help_text="Internal notes are visible to technicians and admins only.")
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ["created_at"]
    def __str__(self): return f"Comment on {self.ticket_id} by {self.author}"

class AuditLog(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="audit_logs")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ticket_audit_logs")
    action = models.CharField(max_length=80)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ["-created_at"]
