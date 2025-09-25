from django.db import migrations

def seed(apps, schema_editor):
    EmailTemplate = apps.get_model("notification", "EmailTemplate")

    templates = [
        {
            "code": "COMPETITION_MEMBER_APPROVAL",
            "subject": "Confirm your participation: {{ competition }}",
            "html": (
                "<html><body>"
                "<p>Hello {{ first_name }} {{ last_name }},</p>"
                "<p>You were added to the team <strong>{{ team_name }}</strong> for <strong>{{ competition }}</strong>.</p>"
                "<p>Please confirm your participation:</p>"
                "<p><a href=\"{{ action_link }}\" style=\"background:#0ea5e9;color:#fff;padding:10px 16px;border-radius:8px;text-decoration:none;\">Approve</a></p>"
                "<p>If you do not wish to participate, ignore this email or contact the submitter.</p>"
                "<p>This link expires in 24 hours.</p>"
                "</body></html>"
            ),
            "text": (
                "You were added to team '{{ team_name }}' for '{{ competition }}'."
                "Approve: {{ action_link }} (expires in 24h)"
            ),
        },
        {
            "code": "COMPETITION_REQUEST_SUBMITTED",
            "subject": "Submission received: {{ competition }}",
            "html": (
                "<html><body>"
                "<p>We received your team submission for <strong>{{ competition }}</strong> {{ team_name|default_if_none:'' }}.</p>"
                "<p>Each member will get an email to approve participation.</p>"
                "</body></html>"
            ),
            "text": "Submission received for {{ competition }} {{ team_name }}. Members must approve via email.",
        },
        {
            "code": "COMPETITION_REQUEST_PENDING_INVESTIGATION",
            "subject": "Under review: {{ competition }}",
            "html": (
                "<html><body><p>Your submission for <strong>{{ competition }}</strong> is under review by our team.</p></body></html>"
            ),
            "text": "Your submission for {{ competition }} is under review.",
        },
        {
            "code": "COMPETITION_REQUEST_PENDING_PAYMENT",
            "subject": "Payment required: {{ competition }}",
            "html": (
                "<html><body>"
                "<p>Your submission for <strong>{{ competition }}</strong> is approved. Please complete payment:</p>"
                "<p><a href=\"{{ link }}\">Pay here</a></p>"
                "</body></html>"
            ),
            "text": "Complete payment for {{ competition }}: {{ link }}",
        },
        {
            "code": "COMPETITION_REQUEST_REJECTED",
            "subject": "Submission rejected: {{ competition }}",
            "html": (
                "<html><body>"
                "<p>We’re sorry—your submission for <strong>{{ competition }}</strong> was rejected.</p>"
                "{% if reason %}<p>Reason: {{ reason }}</p>{% endif %}"
                "</body></html>"
            ),
            "text": "Your submission for {{ competition }} was rejected. {% if reason %}Reason: {{ reason }}{% endif %}",
        },
        {
            "code": "COMPETITION_REQUEST_FINAL",
            "subject": "Registration confirmed: {{ competition }}",
            "html": (
                "<html><body><p>Your registration for <strong>{{ competition }}</strong> is finalized. See you there!</p></body></html>"
            ),
            "text": "Registration finalized for {{ competition }}.",
        },
        {
            "code": "COMPETITION_PAYMENT_REJECTED",
            "subject": "Payment failed: {{ competition }}",
            "html": (
                "<html><body>"
                "<p>Your payment for <strong>{{ competition }}</strong> was not successful.</p>"
                "<p>Please retry using the payment link in your account or contact support.</p>"
                "</body></html>"
            ),
            "text": "Payment failed for {{ competition }}. Please retry.",
        },
    ]

    for t in templates:
        EmailTemplate.objects.update_or_create(code=t["code"], defaults=t)


def unseed(apps, schema_editor):
    EmailTemplate = apps.get_model("notification", "EmailTemplate")
    EmailTemplate.objects.filter(code__in=[
        "COMPETITION_MEMBER_APPROVAL",
        "COMPETITION_REQUEST_SUBMITTED",
        "COMPETITION_REQUEST_PENDING_INVESTIGATION",
        "COMPETITION_REQUEST_PENDING_PAYMENT",
        "COMPETITION_REQUEST_REJECTED",
        "COMPETITION_REQUEST_FINAL",
        "COMPETITION_PAYMENT_REJECTED",
    ]).delete()

class Migration(migrations.Migration):
    dependencies = [("notification", "0002_seed_templates")]
    operations = [migrations.RunPython(seed, reverse_code=unseed)]