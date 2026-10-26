import csv
from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from kb.models import Article

from .models import AuditLog, Category, Comment, Ticket

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


def test_ticket_creation_status_and_assignment_are_audited(users, category):
    client = APIClient()
    client.force_authenticate(users["employee"])

    created = client.post(
        "/api/tickets/",
        {
            "title": "Audited ticket",
            "description": "Check the audit trail",
            "category": category.pk,
            "priority": "high",
        },
        format="json",
    )
    assert created.status_code == 201
    ticket = Ticket.objects.get(pk=created.data["id"])
    creation_log = AuditLog.objects.get(ticket=ticket, action="created")
    assert creation_log.actor == users["employee"]
    assert creation_log.details == {"status": "open"}

    client.force_authenticate(users["technician"])
    status_response = client.patch(
        f"/api/tickets/{ticket.pk}/",
        {"status": "in_progress"},
        format="json",
    )
    assert status_response.status_code == 200
    status_log = AuditLog.objects.get(ticket=ticket, action="updated")
    assert status_log.actor == users["technician"]
    assert status_log.details == {"status": {"from": "open", "to": "in_progress"}}

    assignment_response = client.patch(
        f"/api/tickets/{ticket.pk}/",
        {"assignee": users["admin"].pk},
        format="json",
    )
    assert assignment_response.status_code == 200
    assignment_log = AuditLog.objects.filter(ticket=ticket, action="updated").latest("created_at")
    assert assignment_log.actor == users["technician"]
    assert assignment_log.details == {"assignee": {"from": "None", "to": str(users["admin"])}}
    assert AuditLog.objects.filter(ticket=ticket).count() == 3


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_assignment_sends_one_email_to_assignee(users, category):
    ticket = Ticket.objects.create(
        title="Assignment notification",
        description="Notify the new assignee",
        category=category,
        requester=users["employee"],
    )
    client = APIClient()
    client.force_authenticate(users["technician"])

    response = client.patch(
        f"/api/tickets/{ticket.pk}/",
        {"assignee": users["admin"].pk},
        format="json",
    )

    assert response.status_code == 200
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [users["admin"].email]
    assert mail.outbox[0].subject.startswith("Ticket assigned:")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_status_change_sends_one_email_to_requester(users, category):
    ticket = Ticket.objects.create(
        title="Status notification",
        description="Notify the requester",
        category=category,
        requester=users["employee"],
    )
    client = APIClient()
    client.force_authenticate(users["technician"])

    response = client.patch(
        f"/api/tickets/{ticket.pk}/",
        {"status": "in_progress"},
        format="json",
    )

    assert response.status_code == 200
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [users["employee"].email]
    assert mail.outbox[0].subject.startswith("Ticket status changed:")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_new_requester_comment_sends_one_email_to_assignee(client, users, category):
    ticket = Ticket.objects.create(
        title="Comment notification",
        description="Notify the assigned technician",
        category=category,
        requester=users["employee"],
        assignee=users["technician"],
    )
    client.force_login(users["employee"])

    response = client.post(
        f"/tickets/{ticket.pk}/",
        {"body": "Additional details for the technician"},
    )

    assert response.status_code == 302
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [users["technician"].email]
    assert mail.outbox[0].subject.startswith("New comment on")


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


@pytest.mark.django_db
def test_seed_demo_creates_expected_accounts_and_data(capsys):
    demo_accounts = {
        "admin@demo.com": "admin",
        "tech@demo.com": "technician",
        "tech2@demo.com": "technician",
        "employee@demo.com": "employee",
        "employee2@demo.com": "employee",
        "employee3@demo.com": "employee",
    }

    call_command("seed_demo")

    users = User.objects.filter(email__in=demo_accounts)
    assert users.count() == len(demo_accounts)
    assert {user.email: user.role for user in users} == demo_accounts
    assert all(user.check_password("DemoPass123!") for user in users)
    assert Ticket.objects.count() == 30
    assert Article.objects.count() == 4
    assert "Demo data ready." in capsys.readouterr().out

    call_command("seed_demo")

    assert User.objects.filter(email__in=demo_accounts).count() == len(demo_accounts)
    assert Ticket.objects.count() == 30
    assert Article.objects.count() == 4


def test_ticket_list_filters_by_fields_search_and_dates(client, users, category, ticket):
    ticket.assignee = users["technician"]
    ticket.save(update_fields=["assignee"])
    client.force_login(users["technician"])
    today = timezone.localdate().isoformat()

    response = client.get(
        "/tickets/",
        {
            "q": "Broken",
            "status": "open",
            "priority": "high",
            "category": str(category.pk),
            "assignee": str(users["technician"].pk),
            "start": today,
            "end": today,
        },
    )

    assert response.status_code == 200
    assert list(response.context["tickets"]) == [ticket]


def test_ticket_list_ignores_invalid_date_filters(client, users):
    client.force_login(users["technician"])

    response = client.get("/tickets/", {"start": "not-a-date", "end": "also-invalid"})

    assert response.status_code == 200
    assert len(list(response.context["messages"])) == 2


def test_ticket_create_view_saves_requester_and_audit(client, users, category):
    client.force_login(users["employee"])

    response = client.post(
        "/tickets/new/",
        {
            "title": "Created from the web",
            "description": "Use the web form",
            "category": category.pk,
            "priority": "medium",
        },
    )

    assert response.status_code == 302
    ticket = Ticket.objects.get(title="Created from the web")
    assert ticket.requester == users["employee"]
    assert AuditLog.objects.get(ticket=ticket).actor == users["employee"]


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_staff_comment_sets_first_response_and_notifies_requester(client, users, category, ticket):
    ticket.assignee = users["technician"]
    ticket.save(update_fields=["assignee"])
    client.force_login(users["technician"])

    response = client.post(
        f"/tickets/{ticket.pk}/",
        {"body": "We are investigating", "is_internal": ""},
    )

    assert response.status_code == 302
    ticket.refresh_from_db()
    assert ticket.first_response_at is not None
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [users["employee"].email]


def test_ticket_detail_hides_internal_notes_from_employee(client, users, category, ticket):
    Comment.objects.create(
        ticket=ticket,
        author=users["technician"],
        body="Private staff note",
        is_internal=True,
    )
    client.force_login(users["employee"])

    response = client.get(f"/tickets/{ticket.pk}/")

    assert response.status_code == 200
    assert list(response.context["comments"]) == []


def test_ticket_update_view_changes_status_and_assignee(client, users, category, ticket):
    client.force_login(users["technician"])

    response = client.post(
        f"/tickets/{ticket.pk}/update/",
        {
            "title": ticket.title,
            "description": ticket.description,
            "category": category.pk,
            "priority": ticket.priority,
            "status": "in_progress",
            "assignee": users["admin"].pk,
        },
    )

    assert response.status_code == 302
    ticket.refresh_from_db()
    assert ticket.status == "in_progress"
    assert ticket.assignee == users["admin"]
    assert AuditLog.objects.filter(ticket=ticket, actor=users["technician"]).exists()


def test_ticket_update_view_rejects_invalid_status_transition(client, users, category, ticket):
    client.force_login(users["technician"])

    response = client.post(
        f"/tickets/{ticket.pk}/update/",
        {
            "title": ticket.title,
            "description": ticket.description,
            "category": category.pk,
            "priority": ticket.priority,
            "status": "closed",
            "assignee": "",
        },
    )

    assert response.status_code == 302
    ticket.refresh_from_db()
    assert ticket.status == "open"


def test_ticket_delete_is_admin_only(client, users, ticket):
    client.force_login(users["technician"])
    forbidden = client.post(f"/tickets/{ticket.pk}/delete/")
    assert forbidden.status_code == 403
    assert Ticket.objects.filter(pk=ticket.pk).exists()

    client.force_login(users["admin"])
    deleted = client.post(f"/tickets/{ticket.pk}/delete/")
    assert deleted.status_code == 302
    assert not Ticket.objects.filter(pk=ticket.pk).exists()


def test_technician_can_create_api_comment(users, ticket):
    client = APIClient()
    client.force_authenticate(users["technician"])

    response = client.post(
        f"/api/tickets/{ticket.pk}/comments/",
        {"body": "Internal work note", "is_internal": True},
        format="json",
    )

    assert response.status_code == 201
    assert response.data["is_internal"] is True
    assert Comment.objects.get(pk=response.data["id"]).author == users["technician"]
