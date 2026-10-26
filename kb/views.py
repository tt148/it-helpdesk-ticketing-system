from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from tickets.models import Ticket
from .models import Article
from .forms import ArticleForm
@login_required
def article_list(request):
    q = request.GET.get("q", "").strip()
    articles = Article.objects.filter(published=True)
    if q: articles = articles.filter(Q(title__icontains=q) | Q(summary__icontains=q) | Q(content__icontains=q))
    return render(request, "kb/list.html", {"articles": articles, "q": q})
@login_required
def article_detail(request, slug):
    article = get_object_or_404(Article, slug=slug, published=True)
    return render(request, "kb/detail.html", {"article": article})
@login_required
def article_create(request, ticket_id=None):
    if request.user.role not in {"technician", "admin"}: raise PermissionDenied
    ticket = get_object_or_404(Ticket, pk=ticket_id) if ticket_id else None
    if ticket and ticket.status != "resolved": messages.warning(request, "You can create a knowledge article from a resolved ticket only."); return redirect("tickets:detail", pk=ticket.pk)
    initial = {"title": ticket.title, "summary": ticket.description[:280], "content": ticket.description, "category": ticket.category_id} if ticket else None
    form = ArticleForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        article = form.save(commit=False); article.author = request.user; article.source_ticket = ticket
        article.slug = slugify(article.title)
        if Article.objects.filter(slug=article.slug).exists(): article.slug = f"{article.slug}-{ticket.pk if ticket else 'kb'}"
        article.save(); messages.success(request, "Knowledge article published."); return redirect("kb:detail", slug=article.slug)
    return render(request, "kb/form.html", {"form": form})
