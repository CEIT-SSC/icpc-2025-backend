from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import Competition, TeamRequest
from .serializers import (
    CompetitionSerializer, FieldConfigSerializer,
    TeamRequestCreateSerializer, TeamRequestSerializer,
    ApproveTokenSerializer, CancelRequestSerializer,
)
from .services import (
    submit_team_request, approve_or_reject_member, cancel_request,
)

class CompetitionDetailView(generics.RetrieveAPIView):
    queryset = Competition.objects.filter(is_active=True)
    serializer_class = CompetitionSerializer
    lookup_field = "slug"
    permission_classes = []

class CompetitionFieldConfigView(generics.RetrieveAPIView):
    permission_classes = []
    serializer_class = FieldConfigSerializer

    def get_object(self):
        comp = get_object_or_404(Competition, slug=self.kwargs["slug"], is_active=True)
        return comp.field_config

class MyTeamRequestsView(generics.ListAPIView):
    serializer_class = TeamRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return TeamRequest.objects.filter(submitter=self.request.user).prefetch_related("members")

class TeamRequestCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        s = TeamRequestCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        comp = get_object_or_404(Competition, id=data["competition_id"], is_active=True)
        tr = submit_team_request(
            competition=comp,
            submitter=request.user,
            team_name=data.get("team_name"),
            participants=data["participants"],
        )
        return Response(TeamRequestSerializer(tr).data, status=status.HTTP_201_CREATED)

class MemberApproveView(APIView):
    permission_classes = []  # token-based

    def post(self, request):
        s = ApproveTokenSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        m = approve_or_reject_member(**s.validated_data)
        return Response({"member": m.id, "status": m.approval_status})

class CancelRequestView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        s = CancelRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        tr = get_object_or_404(TeamRequest, id=s.validated_data["request_id"], submitter=request.user)
        tr = cancel_request(tr=tr, by_user=request.user)
        return Response(TeamRequestSerializer(tr).data)