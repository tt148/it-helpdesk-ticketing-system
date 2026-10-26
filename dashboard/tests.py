from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from tickets.models import Category, Ticket

User = get_user_model()


@pytest.fixture
def dashboard_data(db):
    users = {
        role: User.objects.create_user(
            username=role,
            email=f"{role}@example.com",
            password="GoodPass123!",
            role=role,
        )
        for role in ("employee", "employee2", "technician", "technician2", "admin")
    }
    hardware = Category.objects.create(name="Dashboard Hardware", slug="dashboard-hardware")
    network = Category.objects.create(name="Dashboard Network", slug="dashboard-network")
    old_created_at = timezone.now() - timedelta(days=5)

    overdue_ticket = Ticket.objects.create(
        title="Overdue hardware ticket",
        description="Past its resolution deadline",
        category=hardware,
        requester=users["employee"],
        assignee=users["technician"],
        priority="high",
        status=Ticket.Status.OPEN,
    )
    Ticket.objects.filter(pk=overdue_ticket.pk).update(created_at=old_created_at)

    Ticket.objects.create(
        title="Recent hardware ticket",
        description="Still within SLA",
        category=hardware,
        requester=users["employee"],
        assignee=users["technician"],
        priority="low",
        status=Ticket.Status.IN_PROGRESS,
    )

    resolved_ticket = Ticket.objects.create(
        title="Resolved network ticket",
        description="Already resolved",
        category=network,
        requester=users["employee2"],
        assignee=users["technician2"],
        priority="critical",
        status=Ticket.Status.RESOLVED,
        resolved_at=timezone.now(),
    )
    Ticket.objects.filter(pk=resolved_ticket.pk).update(created_at=old_created_at)

    return users


@pytest.mark.parametrize("role", ["technician", "admin"])
def test_staff_dashboard_counts_and_breakdowns(client, dashboard_data, role):
    client.force_login(dashboard_data[role])

    response = client.get("/")

    assert response.status_code == 200
    assert response.context["open_count"] == 2
    assert response.context["overdue_count"] == 1
    assert {row["category__name"]: row["total"] for row in response.context["categories"]} == {
        "Dashboard Hardware": 2,
        "Dashboard Network": 1,
    }
    assert {row["assignee__email"]: row["total"] for row in response.context["technicians"]} == {
        "technician@example.com": 2,
        "technician2@example.com": 1,
    }


def test_employee_dashboard_only_counts_their_tickets(client, dashboard_data):
    client.force_login(dashboard_data["employee"])

    response = client.get("/")

    assert response.status_code == 200
    assert response.context["open_count"] == 2
    assert response.context["overdue_count"] == 1
    assert {row["category__name"]: row["total"] for row in response.context["categories"]} == {
        "Dashboard Hardware": 2
    }
    assert response.context["technicians"] == []
