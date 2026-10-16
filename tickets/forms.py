from django import forms
from django.contrib.auth import get_user_model
from .models import Ticket, Comment, Category
User = get_user_model()
class TicketForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ["title", "description", "category", "priority"]
        widgets = {"description": forms.Textarea(attrs={"rows": 5})}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values(): field.widget.attrs.setdefault("class", "form-control")
class TechnicianTicketForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ["title", "description", "category", "priority", "status", "assignee"]
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assignee"].queryset = User.objects.filter(role__in=[User.Role.TECHNICIAN, User.Role.ADMIN], is_active=True)
        for field in self.fields.values(): field.widget.attrs.setdefault("class", "form-select" if isinstance(field.widget, forms.Select) else "form-control")
class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ["body", "is_internal"]
        widgets = {"body": forms.Textarea(attrs={"rows": 3})}
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and user.role == User.Role.EMPLOYEE: self.fields.pop("is_internal")
        for field in self.fields.values(): field.widget.attrs.setdefault("class", "form-control")
class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "slug", "description"]
