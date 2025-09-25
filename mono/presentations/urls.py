from django.urls import path
from .views import CourseDetailView, RegistrationCreateView, MyRegistrationsView

urlpatterns = [
    # Fetch the course by slug (e.g., "algorithms-bootcamp")
    path("course/<slug:slug>/", CourseDetailView.as_view()),
    # Create a registration (must be logged in & verified)
    path("register/", RegistrationCreateView.as_view()),
    # List my registrations
    path("me/registrations/", MyRegistrationsView.as_view()),
]