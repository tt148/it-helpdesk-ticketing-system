from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Category, Comment, Ticket

User = get_user_model()


@pytest.fixture
def users(db):
    return {
        role: User.objects.create_user(
            username=role, email=f"{role}@example.com", password="GoodPass123!", role=role
        )
        for role in ["employee", "technician", "admin"]
    }


@pytest.fixture
def category(db):
    return Category.objects.create(name="Hardware", slug="hardware")


@pytest.fixture
def ticket(users, category):
    return Ticket.objects.create(
        title="Broken laptop",
        description="Won't boot",
        category=category,
        requester=users["employee"],
        priority="high",
    )


def test_employee_api_only_sees_own_tickets(users, category, ticket):
    other = User.objects.create_user(
        username="other", email="other@example.com", password="GoodPass123!", role="employee"
    )
    Ticket.objects.create(title="Other ticket", description="Other", category=category, requester=other)
    client = APIClient()
    client.force_authenticate(users["employee"])
    response = client.get("/api/tickets/")
    assert response.status_code == 200
    assert response.data["count"] == 1


def test_employee_cannot_read_another_ticket(users, category, ticket):
    other = User.objects.create_user(
        username="other", email="other@example.com", password="GoodPass123!", role="employee"
    )
    other_ticket = Ticket.objects.create(
        title="Private ticket", description="Private", category=category, requester=other
    )
    client = APIClient()
    client.force_authenticate(users["employee"])
    assert client.get(f"/api/tickets/{other_ticket.pk}/").status_code == 404


def test_status_transitions_enforced(ticket):
    ticket.transition_to("in_progress")
    assert ticket.status == "in_progress"
    with pytest.raises(ValidationError):
        ticket.transition_to("closed")


def test_sla_deadline_by_priority(ticket):
    ticket.created_at = timezone.now() - timedelta(hours=9)
    ticket.priority = "high"
    assert ticket.resolution_due_at == ticket.created_at + timedelta(hours=8)


def test_overdue_flag(ticket):
    Ticket.objects.filter(pk=ticket.pk).update(created_at=timezone.now() - timedelta(hours=9))
    ticket.refresh_from_db()
    assert ticket.is_overdue is True


def test_internal_notes_hidden_from_employee_api(users, category, ticket):
    Comment.objects.create(ticket=ticket, author=users["technician"], body="Do not expose", is_internal=True)
    Comment.objects.create(ticket=ticket, author=users["technician"], body="Public update", is_internal=False)
    client = APIClient()
    client.force_authenticate(users["employee"])
    response = client.get(f"/api/tickets/{ticket.pk}/comments/")
    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["body"] == "Public update"


def test_employee_cannot_create_internal_note(users, category, ticket):
    client = APIClient()
    client.force_authenticate(users["employee"])
    response = client.post(
        f"/api/tickets/{ticket.pk}/comments/", {"body": "secret", "is_internal": True}, format="json"
    )
    assert response.status_code == 403


def test_token_endpoint_available(users):
    client = APIClient()
    response = client.post("/api/token/", {"username": users["employee"].email, "password": "GoodPass123!"})
    assert response.status_code == 200
    assert "token" in response.data
