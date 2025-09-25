from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from .models import Course, Registration
from .serializers import CourseSerializer, RegistrationCreateSerializer, RegistrationSerializer
from .services import submit_registration

User = get_user_model()

class CourseDetailView(generics.RetrieveAPIView):
    queryset = Course.objects.filter(is_active=True).prefetch_related("presenters", "schedule")
    serializer_class = CourseSerializer
    lookup_field = "slug"
    permission_classes = []

class MyRegistrationsView(generics.ListAPIView):
    serializer_class = RegistrationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Registration.objects.filter(user=self.request.user).select_related("course")

class RegistrationCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        s = RegistrationCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        course = get_object_or_404(Course, id=data["course_id"], is_active=True)
        reg = submit_registration(
            course=course,
            user=request.user,
            resume_url=data.get("resume_url"),
            extra_updates=data.get("extra_answers"),
        )
        return Response(RegistrationSerializer(reg).data)