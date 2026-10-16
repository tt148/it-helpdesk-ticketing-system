from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from tickets.views import TicketViewSet, CategoryViewSet
router = DefaultRouter()
router.register("tickets", TicketViewSet, basename="api-ticket")
router.register("categories", CategoryViewSet, basename="api-category")
urlpatterns = [
    path("admin/", admin.site.urls), path("accounts/", include("django.contrib.auth.urls")),
    path("users/", include("accounts.urls")), path("tickets/", include("tickets.urls")),
    path("kb/", include("kb.urls")), path("", include("dashboard.urls")),
    path("api/", include(router.urls)), path("api/token/", obtain_auth_token, name="api-token"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
handler403 = "config.error_handlers.permission_denied"
handler404 = "config.error_handlers.not_found"
