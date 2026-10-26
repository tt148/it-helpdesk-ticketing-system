from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

User = get_user_model()


class UserForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput, required=False, help_text="Required when creating a user."
    )

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name", "role", "is_active", "password"]

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get("password"):
            user.set_password(self.cleaned_data["password"])
        elif not user.pk:
            user.set_unusable_password()
        if commit:
            user.save()
        return user


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
