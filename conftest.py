import pytest


@pytest.fixture(autouse=True)
def plain_static_storage(settings):
    """Avoid the manifest storage requiring `collectstatic` when tests render templates."""
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
