from django.urls import path

from . import views

app_name = "accounts"
urlpatterns = [
    path("", views.user_list, name="users"),
    path("new/", views.user_edit, name="user_create"),
    path("<int:pk>/edit/", views.user_edit, name="user_edit"),
]
