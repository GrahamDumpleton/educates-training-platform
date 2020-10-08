from django.urls import path

from . import views

urlpatterns = [
    path("access/", views.access, name="workshops_access"),
    path("catalog/", views.catalog, name="workshops_catalog"),
    path(
        "catalog/environments/",
        views.catalog_environments,
        name="workshops_catalog_environments",
    ),
    path("environment/<slug:name>/", views.environment, name="workshops_environment"),
    path(
        "environment/<slug:name>/create/",
        views.environment_create,
        name="workshops_environment_create",
    ),
    path(
        "environment/<slug:name>/request/",
        views.environment_request,
        name="workshops_environment_request",
    ),
    path("session/<slug:name>/", views.session, name="workshops_session"),
    path(
        "session/<slug:name>/activate/",
        views.session_activate,
        name="workshops_session_activate",
    ),
    path(
        "session/<slug:name>/delete/",
        views.session_delete,
        name="workshops_session_delete",
    ),
    path(
        "session/<slug:name>/authorize/",
        views.session_authorize,
        name="workshops_session_authorize",
    ),
    path(
        "session/<slug:name>/schedule/",
        views.session_schedule,
        name="workshops_session_schedule",
    ),
    path(
        "session/<slug:name>/extend/",
        views.session_extend,
        name="workshops_session_extend",
    ),
    path(
        "user/<slug:name>/sessions/",
        views.user_sessions,
        name="workshops_user_sessions",
    ),
]
