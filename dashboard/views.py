from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import render

from tickets.models import Ticket
from tickets.views import staff


@login_required
def home(request):
    qs = Ticket.objects.all() if staff(request.user) else Ticket.objects.filter(requester=request.user)
    open_count = qs.exclude(status__in=["resolved", "closed"]).count()
    overdue_count = sum(1 for t in qs.select_related("category", "requester", "assignee") if t.is_overdue)
    resolved = qs.filter(resolved_at__isnull=False)
    durations = [t.resolved_at - t.created_at for t in resolved.only("created_at", "resolved_at")]
    avg_hours = round(sum((d.total_seconds() / 3600 for d in durations), 0) / len(durations), 1) if durations else None
    categories = list(qs.values("category__name").annotate(total=Count("id")).order_by("-total"))
    technicians = list(qs.filter(assignee__isnull=False).values("assignee__email").annotate(total=Count("id")).order_by("-total")[:8]) if staff(request.user) else []
    recent = qs.select_related("category", "requester", "assignee")[:8]
    return render(request, "dashboard/home.html", {"open_count": open_count, "overdue_count": overdue_count, "avg_hours": avg_hours, "categories": categories, "technicians": technicians, "recent": recent, "is_staff": staff(request.user)})
