from django.urls import path

from . import views

app_name = "kb"
urlpatterns = [path("", views.article_list, name="list"), path("new/", views.article_create, name="create"), path("from-ticket/<int:ticket_id>/new/", views.article_create, name="from_ticket"), path("<slug:slug>/", views.article_detail, name="detail")]
