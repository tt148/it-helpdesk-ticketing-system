from django.conf import settings
from django.db import models
from django.utils.text import slugify


class Article(models.Model):
    title = models.CharField(max_length=180)
    slug = models.SlugField(unique=True, blank=True)
    summary = models.CharField(max_length=300)
    content = models.TextField()
    category = models.ForeignKey(
        "tickets.Category", on_delete=models.SET_NULL, null=True, blank=True, related_name="articles"
    )
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="kb_articles")
    source_ticket = models.OneToOneField(
        "tickets.Ticket", on_delete=models.SET_NULL, null=True, blank=True, related_name="knowledge_article"
    )
    published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title
