from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

User = get_user_model()


class UserForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, help_text="Required when creating a user.")

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name", "role", "is_active", "password"]

    def save(self, commit=True):
        original_password = self._original_password
        user = super().save(commit=False)
        password = self.cleaned_data["password"]
        if password:
            user.set_password(password)
        elif original_password is not None:
            user.password = original_password
        if commit:
            user.save()
        return user

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_password = self.instance.password if self.instance.pk else None
        if self.instance.pk:
            self.fields["password"].required = False


@login_required
def user_list(request):
    if request.user.role != "admin":
        raise PermissionDenied
    return render(request, "accounts/users.html", {"users": User.objects.all().order_by("role", "email")})


@login_required
def user_edit(request, pk=None):
    if request.user.role != "admin":
        raise PermissionDenied
    instance = get_object_or_404(User, pk=pk) if pk else None
    form = UserForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "User saved.")
        return redirect("accounts:users")
    return render(
        request,
        "accounts/user_form.html",
        {"form": form, "heading": "Edit user" if instance else "Create user"},
    )
