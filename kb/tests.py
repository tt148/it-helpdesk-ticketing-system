import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from tickets.models import Category, Ticket

from .models import Article

User = get_user_model()


@pytest.fixture
def kb_users(db):
    return {
        role: User.objects.create_user(
            username=role,
            email=f"{role}@example.com",
            password="GoodPass123!",
            role=role,
        )
        for role in ("employee", "technician", "admin")
    }


@pytest.fixture
def resolved_ticket(kb_users, db):
    category = Category.objects.create(name="Knowledge Hardware", slug="knowledge-hardware")
    return Ticket.objects.create(
        title="Resolve VPN connection drops",
        description="Reconnect the VPN profile and apply the approved network settings.",
        category=category,
        requester=kb_users["employee"],
        assignee=kb_users["technician"],
        status=Ticket.Status.RESOLVED,
    )


def test_technician_can_create_and_search_article_from_resolved_ticket(client, kb_users, resolved_ticket):
    client.force_login(kb_users["technician"])
    create_response = client.post(
        reverse("kb:from_ticket", args=[resolved_ticket.pk]),
        {
            "title": "VPN profile recovery",
            "summary": "Restore a dropped VPN connection.",
            "content": "Recreate the approved VPN profile and reconnect.",
            "category": resolved_ticket.category_id,
            "published": "on",
        },
    )

    assert create_response.status_code == 302
    article = Article.objects.get(slug="vpn-profile-recovery")
    assert article.source_ticket == resolved_ticket
    assert article.author == kb_users["technician"]
    assert article.category == resolved_ticket.category

    search_response = client.get(reverse("kb:list"), {"q": "VPN profile"})
    assert search_response.status_code == 200
    assert list(search_response.context["articles"]) == [article]


def test_employee_cannot_create_knowledge_article(client, kb_users):
    client.force_login(kb_users["employee"])

    assert client.get(reverse("kb:create")).status_code == 403
