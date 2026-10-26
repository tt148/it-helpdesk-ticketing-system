import csv
from datetime import datetime

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .forms import CommentForm, TechnicianTicketForm, TicketForm
from .models import Category, Ticket
from .permissions import TicketObjectPermission
from .serializers import CategorySerializer, CommentSerializer, TicketSerializer
from .services import audit, notify

User = get_user_model()


def staff(user):
    return user.role in {User.Role.TECHNICIAN, User.Role.ADMIN}


def visible_tickets(user):
    qs = Ticket.objects.select_related("category", "requester", "assignee")
    return qs if staff(user) else qs.filter(requester=user)


@login_required
def ticket_list(request):
    qs = visible_tickets(request.user)
    for field in ("status", "priority", "category", "assignee"):
        value = request.GET.get(field)
        if value:
            qs = qs.filter(**{f"{field}_id" if field in {"category", "assignee"} else field: value})
    keyword = request.GET.get("q", "").strip()
    if keyword:
        qs = qs.filter(
            Q(title__icontains=keyword) | Q(description__icontains=keyword) | Q(pk__icontains=keyword)
        )
    start, end = request.GET.get("start"), request.GET.get("end")
    if start:
        try:
            qs = qs.filter(created_at__date__gte=datetime.strptime(start, "%Y-%m-%d").date())
        except ValueError:
            messages.warning(request, "Invalid start date was ignored.")
    if end:
        try:
            qs = qs.filter(created_at__date__lte=datetime.strptime(end, "%Y-%m-%d").date())
        except ValueError:
            messages.warning(request, "Invalid end date was ignored.")
    return render(
        request,
        "tickets/list.html",
        {
            "tickets": qs,
            "categories": Category.objects.all(),
            "technicians": User.objects.filter(role__in=["technician", "admin"]),
            "filters": request.GET,
        },
    )


@login_required
def ticket_create(request):
    form = TicketForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        ticket = form.save(commit=False)
        ticket.requester = request.user
        ticket.save()
        audit(ticket, request.user, "created", {"status": ticket.status})
        messages.success(request, f"Ticket HD-{ticket.pk} created successfully.")
        return redirect("tickets:detail", pk=ticket.pk)
    return render(request, "tickets/form.html", {"form": form, "heading": "Create a ticket"})


@login_required
def ticket_detail(request, pk):
    ticket = get_object_or_404(Ticket.objects.select_related("requester", "assignee", "category"), pk=pk)
    if not staff(request.user) and ticket.requester_id != request.user.id:
        raise PermissionDenied
    comments = ticket.comments.select_related("author")
    if not staff(request.user):
        comments = comments.filter(is_internal=False)
    form = CommentForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        comment = form.save(commit=False)
        comment.ticket = ticket
        comment.author = request.user
        if not staff(request.user):
            comment.is_internal = False
        comment.save()
        if not ticket.first_response_at and staff(request.user):
            ticket.first_response_at = timezone.now()
            ticket.save(update_fields=["first_response_at", "updated_at"])
        audit(ticket, request.user, "comment_added", {"internal": comment.is_internal})
        recipients = []
        if not comment.is_internal and comment.author_id != ticket.requester_id:
            recipients.append(ticket.requester.email)
        if comment.author_id == ticket.requester_id and ticket.assignee:
            recipients.append(ticket.assignee.email)
        notify(f"New comment on {ticket}", comment.body, recipients)
        messages.success(request, "Your comment has been added.")
        return redirect("tickets:detail", pk=pk)
    update_form = (
        TechnicianTicketForm(instance=ticket) if staff(request.user) else TicketForm(instance=ticket)
    )
    return render(
        request,
        "tickets/detail.html",
        {
            "ticket": ticket,
            "comments": comments,
            "form": form,
            "update_form": update_form,
            "is_staff": staff(request.user),
            "audit_logs": ticket.audit_logs.select_related("actor")[:20],
        },
    )


@login_required
@require_POST
def ticket_update(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    if not staff(request.user) and ticket.requester_id != request.user.id:
        raise PermissionDenied
    old_status, old_assignee = ticket.status, ticket.assignee_id
    form = (
        TechnicianTicketForm(request.POST, instance=ticket)
        if staff(request.user)
        else TicketForm(request.POST, instance=ticket)
    )
    if form.is_valid():
        requested_status = form.cleaned_data.get("status", old_status)
        if requested_status != old_status and requested_status not in Ticket.TRANSITIONS.get(
            old_status, set()
        ):
            messages.error(request, f"Invalid status transition: {old_status} → {requested_status}.")
            return redirect("tickets:detail", pk=pk)
        updated = form.save(commit=False)
        if requested_status == Ticket.Status.RESOLVED and old_status != Ticket.Status.RESOLVED:
            updated.resolved_at = timezone.now()
        elif requested_status == Ticket.Status.IN_PROGRESS and old_status == Ticket.Status.RESOLVED:
            updated.resolved_at = None
        updated.save()
        changes = {}
        if old_status != updated.status:
            changes["status"] = {"from": old_status, "to": updated.status}
        if old_assignee != updated.assignee_id:
            changes["assignee_id"] = {"from": old_assignee, "to": updated.assignee_id}
        if changes:
            audit(updated, request.user, "updated", changes)
        if old_assignee != updated.assignee_id and updated.assignee:
            notify(
                f"Ticket assigned: {updated}", f"You have been assigned {updated}.", [updated.assignee.email]
            )
        if old_status != updated.status:
            notify(
                f"Ticket status changed: {updated}",
                f"Status is now {updated.get_status_display()}.",
                [updated.requester.email],
            )
        messages.success(request, "Ticket updated.")
    else:
        messages.error(request, "Please correct the ticket form and try again.")
    return redirect("tickets:detail", pk=pk)


@login_required
@require_POST
def ticket_delete(request, pk):
    if request.user.role != User.Role.ADMIN:
        raise PermissionDenied
    ticket = get_object_or_404(Ticket, pk=pk)
    ticket.delete()
    messages.success(request, "Ticket deleted.")
    return redirect("tickets:list")


@login_required
def export_csv(request):
    if not staff(request.user):
        raise PermissionDenied
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="helpdesk-ticket-report.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
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
    )
    for t in visible_tickets(request.user).select_related("category", "requester", "assignee"):
        writer.writerow(
            [
                t.pk,
                t.title,
                t.category.name,
                t.priority,
                t.status,
                t.requester.email,
                t.assignee.email if t.assignee else "",
                t.created_at.isoformat(),
                t.resolved_at.isoformat() if t.resolved_at else "",
                t.is_overdue,
            ]
        )
    return response


class TicketViewSet(viewsets.ModelViewSet):
    serializer_class = TicketSerializer
    permission_classes = [IsAuthenticated, TicketObjectPermission]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title", "description", "requester__email"]
    ordering_fields = ["created_at", "updated_at", "priority", "status"]

    def get_queryset(self):
        qs = Ticket.objects.select_related("category", "requester", "assignee").prefetch_related("comments")
        if not staff(self.request.user):
            qs = qs.filter(requester=self.request.user)
        for field in ("status", "priority", "category", "assignee"):
            value = self.request.query_params.get(field)
            if value:
                qs = qs.filter(**{f"{field}_id" if field in {"category", "assignee"} else field: value})
        return qs

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=True, methods=["get", "post"])
    def comments(self, request, pk=None):
        ticket = self.get_object()
        if request.method == "GET":
            qs = ticket.comments.select_related("author")
            if request.user.role == "employee":
                qs = qs.filter(is_internal=False)
            return Response(CommentSerializer(qs, many=True, context={"request": request}).data)
        serializer = CommentSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        comment = serializer.save(ticket=ticket, author=request.user)
        audit(ticket, request.user, "comment_added", {"internal": comment.is_internal})
        notify(
            f"New comment on {ticket}",
            comment.body,
            [ticket.requester.email] if not comment.is_internal else [],
        )
        return Response(CommentSerializer(comment, context={"request": request}).data, status=201)


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
