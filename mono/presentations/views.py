# presentations/views.py

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Course, Registration
from .serializers import (
    CourseSerializer,
    RegistrationCreateSerializer,
    RegistrationSerializer,
)
from .services import submit_registration

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
