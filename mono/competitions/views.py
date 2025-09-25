from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import Competition, TeamRequest
from .serializers import (
    CompetitionSerializer, FieldConfigSerializer,
    TeamRequestCreateSerializer, TeamRequestSerializer,
    ApproveTokenSerializer, CancelRequestSerializer, MemberApproveResponseSerializer,
)
from .services import (
    submit_team_request, approve_or_reject_member, cancel_request,
)

class CompetitionDetailView(generics.RetrieveAPIView):
    queryset = Competition.objects.filter(is_active=True)
    serializer_class = CompetitionSerializer
    lookup_field = "slug"
    permission_classes = []

    @extend_schema(
        responses={200: CompetitionSerializer},
        description="Get a competition by slug."
    )
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)


class CompetitionFieldConfigView(generics.RetrieveAPIView):
    permission_classes = []
    serializer_class = FieldConfigSerializer

    def get_object(self):
        comp = get_object_or_404(Competition, slug=self.kwargs["slug"], is_active=True)
        return comp.field_config

    @extend_schema(
        responses={200: FieldConfigSerializer},
        description="Get dynamic field requirements (required/optional/hidden) for a competition."
    )
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)


class MyTeamRequestsView(generics.ListAPIView):
    serializer_class = TeamRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return TeamRequest.objects.filter(submitter=self.request.user).prefetch_related("members")

    @extend_schema(
        responses={200: TeamRequestSerializer(many=True)},
        description="List my team requests."
    )
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)


class TeamRequestCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=TeamRequestCreateSerializer,
        responses={201: TeamRequestSerializer, 400: OpenApiResponse(description="Validation error")},
        description="Create a team request for a competition."
    )
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

    @extend_schema(
        request=ApproveTokenSerializer,
        responses={200: MemberApproveResponseSerializer, 400: OpenApiResponse(description="Invalid/expired token")},
        description="Approve or reject a team membership via a secure token."
    )
    def post(self, request):
        s = ApproveTokenSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        m = approve_or_reject_member(**s.validated_data)
        return Response({"member": m.id, "status": m.approval_status})


class CancelRequestView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=CancelRequestSerializer,
        responses={200: TeamRequestSerializer, 400: OpenApiResponse(description="Only pending approval-mode requests can be cancelled")},
        description="Cancel my pending team request (only for approval-mode competitions)."
    )
    def post(self, request):
        s = CancelRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        tr = get_object_or_404(TeamRequest, id=s.validated_data["request_id"], submitter=request.user)
        tr = cancel_request(tr=tr, by_user=request.user)
        return Response(TeamRequestSerializer(tr).data)