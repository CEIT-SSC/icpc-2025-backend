from .smtp_provider import SmtpEmailProvider

def get_email_provider():
    return SmtpEmailProvider()