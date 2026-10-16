from rest_framework import serializers
from .models import Ticket, Comment, Category
from .services import audit, notify

class CategorySerializer(serializers.ModelSerializer):
    class Meta: model = Category; fields = ["id", "name", "slug", "description"]
class CommentSerializer(serializers.ModelSerializer):
    author_email = serializers.EmailField(source="author.email", read_only=True)
    class Meta: model = Comment; fields = ["id", "ticket", "author", "author_email", "body", "is_internal", "created_at"]; read_only_fields = ["ticket", "author", "created_at"]
    def validate_is_internal(self, value):
        if value and self.context["request"].user.role == "employee": raise serializers.ValidationError("Employees cannot create internal notes.")
        return value
class TicketSerializer(serializers.ModelSerializer):
    requester_email = serializers.EmailField(source="requester.email", read_only=True)
    assignee_email = serializers.EmailField(source="assignee.email", read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    comments = serializers.SerializerMethodField()
    class Meta:
        model = Ticket
        fields = ["id", "title", "description", "category", "priority", "status", "requester", "requester_email", "assignee", "assignee_email", "created_at", "updated_at", "first_response_at", "resolved_at", "is_overdue", "comments"]
        read_only_fields = ["requester", "created_at", "updated_at", "first_response_at", "resolved_at"]
    def get_comments(self, obj):
        qs = obj.comments.select_related("author")
        if self.context["request"].user.role == "employee": qs = qs.filter(is_internal=False)
        return CommentSerializer(qs, many=True, context=self.context).data
    def validate_assignee(self, value):
        if value and value.role not in {"technician", "admin"}: raise serializers.ValidationError("Tickets can only be assigned to technicians or admins.")
        return value
    def validate_status(self, value):
        instance = self.instance
        if instance and value != instance.status and value not in instance.TRANSITIONS.get(instance.status, set()):
            raise serializers.ValidationError(f"Invalid transition from {instance.status} to {value}.")
        if self.context["request"].user.role == "employee" and value != "open": raise serializers.ValidationError("Employees cannot change ticket status.")
        return value
    def create(self, validated_data):
        ticket = Ticket.objects.create(requester=self.context["request"].user, **validated_data)
        audit(ticket, self.context["request"].user, "created", {"status": ticket.status})
        return ticket
    def update(self, instance, validated_data):
        actor = self.context["request"].user
        changes = {key: {"from": str(getattr(instance, key)), "to": str(value)} for key, value in validated_data.items() if getattr(instance, key) != value}
        old_assignee = instance.assignee
        old_status = instance.status
        for key, value in validated_data.items(): setattr(instance, key, value)
        if instance.status == "resolved" and old_status != "resolved":
            from django.utils import timezone
            instance.resolved_at = timezone.now()
        elif instance.status == "in_progress" and old_status == "resolved":
            instance.resolved_at = None
        instance.save()
        if changes: audit(instance, actor, "updated", changes)
        if instance.assignee_id and instance.assignee_id != getattr(old_assignee, "id", None):
            notify(f"Ticket assigned: {instance}", f"You have been assigned {instance}.", [instance.assignee.email])
        if instance.status != old_status:
            notify(f"Ticket status changed: {instance}", f"Status changed to {instance.get_status_display()}.", [instance.requester.email])
        return instance
