from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, serializers
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse, inline_serializer

from .storage_utils import s3_save_and_get_url


class UploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="upload_file_to_s3",
        summary="Upload a file and get its URL",
        description=(
            "Accepts **multipart/form-data** with a single `file` field. "
            "Backend stores it under a fixed folder and returns only the public URL."
        ),
        request=inline_serializer(
            name="UploadRequest",
            fields={
                "file": serializers.FileField(help_text="Binary file to upload"),
            },
        ),
        responses={
            201: inline_serializer(
                name="UploadResponse",
                fields={
                    "url": serializers.URLField(help_text="Public URL of the uploaded file"),
                },
            ),
            400: OpenApiResponse(description="No file provided"),
            401: OpenApiResponse(description="Unauthorized"),
        },
        examples=[
            OpenApiExample(
                "cURL Multipart",
                description="Basic curl example",
                value={"file": "(binary)"},
                request_only=True,
            ),
            OpenApiExample(
                "Success Response",
                value={"url": "https://your-endpoint/bucket/uploads/2025/10/17/uuid.jpg"},
                response_only=True,
            ),
        ],
        tags=["Uploads"],
    )
    def post(self, request, *args, **kwargs):
        f = request.FILES.get("file")
        if not f:
            return Response({"detail": "Provide a 'file' field."}, status=status.HTTP_400_BAD_REQUEST)

        folder = getattr(settings, "UPLOADS_DEFAULT_FOLDER", "user_uploads")

        saved = s3_save_and_get_url(
            f,
            folder=folder,
            filename=None,
            overwrite=False,
        )
        return Response({"url": saved.url}, status=status.HTTP_201_CREATED)
