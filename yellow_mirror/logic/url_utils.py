from urllib.parse import urlparse
from .config import ALLOWED_SCHEMES, DISALLOWED_IPS


def is_safe_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        return False
    netloc = parsed.netloc.split(':')[0]
    if netloc in DISALLOWED_IPS or netloc.startswith(('127.', '192.168.', '10.')):
        return False
    return True