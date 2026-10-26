import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


@pytest.fixture
def account_users(db):
    return {
        role: User.objects.create_user(
            username=role,
            email=f"{role}@example.com",
            password="GoodPass123!",
            role=role,
        )
        for role in ("employee", "technician", "admin")
    }


@pytest.mark.parametrize("role", ["employee", "technician"])
def test_non_admin_cannot_access_user_management(client, account_users, role):
    client.force_login(account_users[role])

    assert client.get(reverse("accounts:users")).status_code == 403
    assert client.get(reverse("accounts:user_create")).status_code == 403


def test_admin_can_list_create_and_edit_users(client, account_users):
    admin = account_users["admin"]
    client.force_login(admin)

    listing = client.get(reverse("accounts:users"))
    assert listing.status_code == 200
    assert set(listing.context["users"]) == set(account_users.values())

    create_response = client.post(
        reverse("accounts:user_create"),
        {
            "username": "new-employee",
            "email": "new-employee@example.com",
            "first_name": "New",
            "last_name": "Employee",
            "role": "employee",
            "is_active": "on",
            "password": "NewPass123!",
        },
    )
    assert create_response.status_code == 302
    new_user = User.objects.get(email="new-employee@example.com")
    assert new_user.check_password("NewPass123!")

    edit_response = client.post(
        reverse("accounts:user_edit", args=[new_user.pk]),
        {
            "username": "new-employee",
            "email": "updated-employee@example.com",
            "first_name": "Updated",
            "last_name": "Employee",
            "role": "technician",
            "is_active": "on",
            "password": "",
        },
    )
    assert edit_response.status_code == 302
    new_user.refresh_from_db()
    assert new_user.email == "updated-employee@example.com"
    assert new_user.role == "technician"
    assert new_user.check_password("NewPass123!")


def test_admin_can_change_existing_users_password(client, account_users):
    user = account_users["employee"]
    user.set_password("OldPass123!")
    user.save()
    client.force_login(account_users["admin"])

    response = client.post(
        reverse("accounts:user_edit", args=[user.pk]),
        {
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
            "is_active": "on",
            "password": "NewPass123!",
        },
    )

    assert response.status_code == 302
    user.refresh_from_db()
    assert user.check_password("NewPass123!")
    assert not user.check_password("OldPass123!")


def test_user_create_requires_password(db):
    from .views import UserForm

    form = UserForm(
        {
            "username": "no-password",
            "email": "no-password@example.com",
            "role": "employee",
            "is_active": "on",
            "password": "",
        }
    )
    assert not form.is_valid()
    assert "password" in form.errors
