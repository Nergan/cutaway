import hashlib

def get_session_id(request) -> str:
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "")
    raw = f"{ip}|{ua}"
    return hashlib.md5(raw.encode()).hexdigest()