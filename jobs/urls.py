from django.urls import path
from jobs import views

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path("discovery/trigger/", views.trigger_discovery_view, name="trigger_discovery"),
    path("discovery/status/", views.discovery_status_api, name="discovery_status"),
    path("boards/inspect/", views.trigger_board_inspection_view, name="trigger_board_inspection"),
    path("runs/", views.runs_view, name="runs"),
    path("profile/", views.profile_view, name="profile"),
    path("jobs/<str:job_id>/", views.job_detail_view, name="job_detail"),
]

