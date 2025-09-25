from django.urls import path
from .views import (
    CompetitionDetailView, CompetitionFieldConfigView,
    TeamRequestCreateView, MyTeamRequestsView,
    MemberApproveView, CancelRequestView,
)

urlpatterns = [
    path("<slug:slug>/", CompetitionDetailView.as_view()),
    path("<slug:slug>/fields/", CompetitionFieldConfigView.as_view()),
    path("request/", TeamRequestCreateView.as_view()),
    path("me/requests/", MyTeamRequestsView.as_view()),
    path("member/approve/", MemberApproveView.as_view()),
    path("request/cancel/", CancelRequestView.as_view()),
]