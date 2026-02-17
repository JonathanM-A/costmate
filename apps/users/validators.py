import re
import os
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from PIL import Image


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


def validate_logo_file_size(value):
    """Validate that the uploaded logo file is not larger than 5MB."""
    max_size = 5 * 1024 * 1024  # 5MB in bytes
    if value.size > max_size:
        raise ValidationError(
            _("Logo file size must not exceed 5MB. Current size: {size}MB.").format(
                size=round(value.size / (1024 * 1024), 2)
            ),
            code="file_size_exceeded"
        )


def validate_logo_file_extension(value):
    """Validate that the uploaded logo has a valid file extension (.jpg, .jpeg, .png)."""
    valid_extensions = ['.jpg', '.jpeg', '.png']
    ext = os.path.splitext(value.name)[1].lower()
    if ext not in valid_extensions:
        raise ValidationError(
            _("Unsupported file extension. Allowed extensions: {extensions}.").format(
                extensions=", ".join(valid_extensions)
            ),
            code="invalid_file_extension"
        )


def validate_logo_dimensions(value):
    """Validate that the uploaded logo dimensions are between 100x100 and 2000x2000 pixels."""
    try:
        img = Image.open(value)
        width, height = img.size
        min_dimension = 100
        max_dimension = 2000

        if width < min_dimension or height < min_dimension:
            raise ValidationError(
                _("Logo dimensions must be at least {min}x{min} pixels. Current size: {width}x{height}.").format(
                    min=min_dimension, width=width, height=height
                ),
                code="dimensions_too_small"
            )

        if width > max_dimension or height > max_dimension:
            raise ValidationError(
                _("Logo dimensions must not exceed {max}x{max} pixels. Current size: {width}x{height}.").format(
                    max=max_dimension, width=width, height=height
                ),
                code="dimensions_too_large"
            )

        # Reset file pointer after reading
        value.seek(0)
    except Exception as e:
        if isinstance(e, ValidationError):
            raise
        raise ValidationError(
            _("Invalid image file. Could not read image dimensions."),
            code="invalid_image"
        )
