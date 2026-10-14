import re
import uuid
from typing import Optional

from netlazy.domain.models import Profile

CUSTOM_FORM_RE = re.compile(r"^[a-z]+(?:-[a-z]+)*$")
GENERATED_FORM_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
MAX_FORM_LINKS = 8
MIN_CUSTOM_LENGTH = 2
MAX_CUSTOM_LENGTH = 48


class FormInvalidError(Exception):
    pass


class FormTakenError(Exception):
    pass


class FormNotFoundError(Exception):
    pass


class FormLimitError(Exception):
    pass


class FormSlugConflict(Exception):
    pass


def normalize_custom_form(value: str) -> str:
    text = (value or "").strip().lower()
    if not (MIN_CUSTOM_LENGTH <= len(text) <= MAX_CUSTOM_LENGTH) or not CUSTOM_FORM_RE.fullmatch(text):
        raise FormInvalidError(text)
    return text


def is_public_form(value: str) -> bool:
    text = (value or "").strip().lower()
    return bool(CUSTOM_FORM_RE.fullmatch(text) or GENERATED_FORM_RE.fullmatch(text))


def generate_form() -> str:
    return str(uuid.uuid4())


def primary_form_of(profile: Profile) -> Optional[str]:
    forms = profile.forms or []
    if profile.primary_form in forms:
        return profile.primary_form
    return forms[-1] if forms else None
