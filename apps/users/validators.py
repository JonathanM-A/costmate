import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class ComplexityValidator:
    def __init__(self, **kwargs):
        pass

    def validate(self, password, user=None):
        errors = []

        if not re.search(r"[A-Z]", password):
            errors.append(_("at least one uppercase letter"))

        if not re.search(r"[0-9]", password):
            errors.append(_("at least one digit"))

        if not re.search(r'[!@#$%^&*(),.?":{}|<>+]', password):
            errors.append(_("at least one special character"))
        
        if re.search(r"\s", password):
            errors.append(_("no whitespace characters"))

        if errors:
            joined_errors = ", ".join([str(e) for e in errors])
            message = _("This password must contain: {requirements}.").format(
                requirements=joined_errors
            )
            raise ValidationError(message, code="password_complexity_failure")

    def get_help_text(self):
        return _(
            "Your password must contain at least one uppercase letter, "
            "one digit, and one special character."
        )
