from django.db import migrations

def seed(apps, schema_editor):
    EmailTemplate = apps.get_model("notification", "EmailTemplate")
    EmailTemplate.objects.update_or_create(
        code="otp_email",
        defaults={
            "subject": "Your verification code: {{ code }}",
            "html": """
                <html><body>
                <p>Your verification code is:</p>
                <h2 style=\"font-family:monospace\">{{ code }}</h2>
                <p>This code expires in 5 minutes.</p>
                </body></html>
            """,
            "text": "Your verification code is {{ code }} (expires in 5 minutes)",
        },
    )
    EmailTemplate.objects.update_or_create(
        code="status_change",
        defaults={
            "subject": "Your status changed: {{ status }}",
            "html": """
                <html><body>
                <p>Hello,</p>
                <p>Your status is now: <strong>{{ status }}</strong></p>
                {% if link %}<p>Details: <a href=\"{{ link }}\">{{ link }}</a></p>{% endif %}
                </body></html>
            """,
            "text": "Your status is now: {{ status }}",
        },
    )

def unseed(apps, schema_editor):
    EmailTemplate = apps.get_model("notification", "EmailTemplate")
    EmailTemplate.objects.filter(code__in=["otp_email", "status_change"]).delete()

class Migration(migrations.Migration):
    dependencies = [("notification", "0001_initial")]
    operations = [migrations.RunPython(seed, reverse_code=unseed)]