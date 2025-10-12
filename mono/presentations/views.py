# presentations/views.py

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import generics, permissions, status
from django.core.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Course, Registration
from .serializers import (
    CourseSerializer,
    RegistrationCreateSerializer,
    RegistrationSerializer, SkyroomLinkGeneratorSerializer, SkyroomLinkGeneratorResponseSerializer,
    CourseSessionSerializer, CourseSessionResponseSerializer,
)
from .services import submit_registration, create_skyroom_link, get_course_sessions

User = get_user_model()


class CourseDetailView(generics.RetrieveAPIView):
    queryset = Course.objects.filter(is_active=True).prefetch_related("presenters", "schedule")
    serializer_class = CourseSerializer
    lookup_field = "slug"
    permission_classes = []

    @extend_schema(
        responses={200: CourseSerializer},
        description="Get a course by slug (with presenters & schedule)."
    )
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)


class MyRegistrationsView(generics.ListAPIView):
    serializer_class = RegistrationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Registration.objects.filter(user=self.request.user).select_related("course")

    @extend_schema(
        responses={200: RegistrationSerializer(many=True)},
        description="List the authenticated user's course registrations."
    )
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)


class RegistrationCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=RegistrationCreateSerializer,
        responses={
            200: RegistrationSerializer,
            400: OpenApiResponse(description="Validation error"),
            404: OpenApiResponse(description="Course not found"),
        },
        description="Submit a registration for a course. Also persists extra answers to UserExtraData."
    )
    def post(self, request):
        try:
            s = RegistrationCreateSerializer(data=request.data)
            s.is_valid(raise_exception=True)
            data = s.validated_data
            course = get_object_or_404(Course, id=data["course_id"], is_active=True)
            reg = submit_registration(
                course=course,
                user=request.user,
                child_ids=data.get("child_ids"),
                extra_updates=data.get("extra_answers"),
            )
            return Response(RegistrationSerializer(reg).data, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({"error": str(e.message)}, status=status.HTTP_400_BAD_REQUEST)


class SkyroomLinkView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=SkyroomLinkGeneratorSerializer,
        responses={
            200: SkyroomLinkGeneratorResponseSerializer,
            400: OpenApiResponse(description="Validation error"),
            404: OpenApiResponse(description="Course not found"),
        },
        description="Submit a registration for a course. Also persists extra answers to UserExtraData."
    )
    def get(self, request):
        course = None
        course_slug = request.query_params.get("course")
        course_id = request.query_params.get("course_id")

        if course_slug:
            course = Course.objects.filter(slug=course_slug, is_active=True).first()
        elif course_id:
            course = Course.objects.filter(id=course_id, is_active=True).first()

        if course is None:
            return Response({"detail": "Course not found."}, status=status.HTTP_400_BAD_REQUEST)

        link = create_skyroom_link(request.user, course)
        if not link:
            return Response(
                {
                    "detail": "You are not registered for this presentation or it's not within the scheduled time window."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"url": link}, status=status.HTTP_200_OK)


class CourseSessionsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses={200: CourseSessionResponseSerializer(many=True)},
        description="List the authenticated user's course sessions."
    )
    def get(self, request, slug):
        course = get_object_or_404(Course, slug=slug, is_active=True)
        current_sessions = get_course_sessions(request.user, course)
        if current_sessions is None:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={"detail": "User's not registered for this course"})
        return Response(current_sessions, status=status.HTTP_200_OK)
