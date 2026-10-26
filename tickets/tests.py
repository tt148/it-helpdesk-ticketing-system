import csv
from datetime import timedelta
from io import StringIO

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


def test_employee_cannot_edit_another_employees_ticket(users, category):
    other_employee = User.objects.create_user(
        username="other-employee",
        email="other-employee@example.com",
        password="GoodPass123!",
        role="employee",
    )
    other_ticket = Ticket.objects.create(
        title="Other employee ticket",
        description="Private",
        category=category,
        requester=other_employee,
    )
    client = APIClient()
    client.force_authenticate(users["employee"])

    response = client.patch(
        f"/api/tickets/{other_ticket.pk}/",
        {"title": "Changed by another employee"},
        format="json",
    )

    assert response.status_code == 404
    other_ticket.refresh_from_db()
    assert other_ticket.title == "Other employee ticket"


@pytest.mark.parametrize("role", ["employee"])
def test_employee_cannot_access_csv_export(client, users, role):
    client.force_login(users[role])

    assert client.get("/tickets/reports/export.csv").status_code == 403


@pytest.mark.parametrize("role", ["technician", "admin"])
def test_staff_can_export_csv_with_headers_and_ticket_rows(client, users, category, role):
    ticket = Ticket.objects.create(
        title="CSV export ticket",
        description="Export row",
        category=category,
        requester=users["employee"],
        assignee=users["technician"],
        priority="critical",
    )
    client.force_login(users[role])

    response = client.get("/tickets/reports/export.csv")

    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    rows = list(csv.reader(StringIO(response.content.decode())))
    assert rows[0] == [
        "ID",
        "Title",
        "Category",
        "Priority",
        "Status",
        "Requester",
        "Assignee",
        "Created",
        "Resolved",
        "Overdue",
    ]
    assert rows[1][:7] == [
        str(ticket.pk),
        "CSV export ticket",
        "Hardware",
        "critical",
        "open",
        "employee@example.com",
        "technician@example.com",
    ]
    assert rows[1][8:] == ["", "False"]


def test_technician_can_see_and_edit_another_employees_ticket(users, category):
    ticket = Ticket.objects.create(
        title="Staff access ticket",
        description="Visible to staff",
        category=category,
        requester=users["employee"],
    )
    client = APIClient()
    client.force_authenticate(users["technician"])

    listing = client.get("/api/tickets/")
    update = client.patch(
        f"/api/tickets/{ticket.pk}/",
        {"title": "Updated by technician"},
        format="json",
    )

    assert listing.status_code == 200
    assert listing.data["count"] == 1
    assert update.status_code == 200
    ticket.refresh_from_db()
    assert ticket.title == "Updated by technician"


def test_status_transitions_enforced(ticket):
    ticket.transition_to("in_progress")
    assert ticket.status == "in_progress"
    with pytest.raises(ValidationError):
        ticket.transition_to("closed")


def test_sla_deadline_by_priority(ticket):
    ticket.created_at = timezone.now() - timedelta(hours=9)
    ticket.priority = "high"
    assert ticket.resolution_due_at == ticket.created_at + timedelta(hours=8)


@pytest.mark.parametrize(
    ("priority", "hours"),
    [("critical", 4), ("high", 8), ("medium", 48), ("low", 72)],
)
def test_sla_deadline_for_each_priority(users, category, priority, hours):
    ticket = Ticket.objects.create(
        title=f"{priority} ticket",
        description="SLA check",
        category=category,
        requester=users["employee"],
        priority=priority,
    )

    assert ticket.resolution_due_at == ticket.created_at + timedelta(hours=hours)


def test_overdue_flag(ticket):
    Ticket.objects.filter(pk=ticket.pk).update(created_at=timezone.now() - timedelta(hours=9))
    ticket.refresh_from_db()
    assert ticket.is_overdue is True


def test_active_ticket_is_not_overdue_before_deadline(ticket):
    ticket.created_at = timezone.now()
    ticket.save(update_fields=["created_at"])

    assert ticket.is_overdue is False


@pytest.mark.parametrize("status", ["resolved", "closed"])
def test_resolved_or_closed_ticket_is_never_overdue(ticket, status):
    Ticket.objects.filter(pk=ticket.pk).update(
        created_at=timezone.now() - timedelta(days=10),
        status=status,
    )
    ticket.refresh_from_db()

    assert ticket.is_overdue is False


@pytest.mark.parametrize(
    ("old_status", "new_status"),
    [
        ("open", "in_progress"),
        ("open", "resolved"),
        ("in_progress", "open"),
        ("in_progress", "resolved"),
        ("resolved", "in_progress"),
        ("resolved", "closed"),
    ],
)
def test_every_allowed_status_transition_succeeds(users, category, old_status, new_status):
    ticket = Ticket.objects.create(
        title="Transition check",
        description="Status transition",
        category=category,
        requester=users["employee"],
        status=old_status,
    )

    ticket.transition_to(new_status)
    ticket.refresh_from_db()

    assert ticket.status == new_status
    if new_status == "resolved":
        assert ticket.resolved_at is not None
    elif new_status == "in_progress":
        assert ticket.resolved_at is None


@pytest.mark.parametrize(
    ("old_status", "new_status"),
    [
        ("open", "closed"),
        ("in_progress", "closed"),
        ("resolved", "open"),
        ("closed", "open"),
        ("closed", "in_progress"),
        ("closed", "resolved"),
    ],
)
def test_invalid_status_transitions_are_rejected(users, category, old_status, new_status):
    ticket = Ticket.objects.create(
        title="Invalid transition check",
        description="Status transition",
        category=category,
        requester=users["employee"],
        status=old_status,
    )

    with pytest.raises(ValidationError):
        ticket.transition_to(new_status)

    ticket.refresh_from_db()
    assert ticket.status == old_status


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
