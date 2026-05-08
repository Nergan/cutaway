import re
import urllib.parse
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import FileResponse
from curl_cffi import requests as cffi_requests
from .core.rewriter import rewrite_html

router = APIRouter()

async def shutdown_clients():
    """Stateless proxy, no connections to close."""
    pass

@router.get("/")
async def yellow_mirror_page():
    return FileResponse("yellow_mirror/yellow-mirror.html")

@router.get("/sw.js")
async def service_worker():
    """Serves the Service Worker. Service-Worker-Allowed permits root interception."""
    return FileResponse(
        "yellow_mirror/scripts/sw.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"}
    )

@router.api_route("/proxy/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_route(request: Request, path: str):
    full_url = str(request.url)
    if "/proxy/" not in full_url:
        raise HTTPException(status_code=400, detail="Invalid proxy format")
    
    # Safely extract target url
    target_url = full_url.split("/proxy/", 1)[1]
    
    # FIX FOR CURL ERROR (6): 
    # FastAPI path routing strips double slashes (https:// -> https:/). We restore them.
    target_url = re.sub(r"^(https?:)/+", r"\1//", target_url)
    
    if not target_url.startswith(("http://", "https://")):
        target_url = "https://" + target_url

    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("connection", None)
    headers.pop("accept-encoding", None) # Prevent compression to easily parse HTML

    body = await request.body()
    
    try:
        # Impersonate Chrome to bypass Cloudflare and WAF blocks
        async with cffi_requests.AsyncSession(impersonate="chrome") as session:
            resp = await session.request(
                method=request.method,
                url=target_url,
                headers=headers,
                data=body if body else None,
                allow_redirects=False,
                timeout=15.0
            )
    except Exception as e:
        return Response(content=f"Proxy error: {str(e)}", status_code=502)

    resp_headers = {}
    for k, v in resp.headers.items():
        k_lower = k.lower()
        if k_lower in["content-encoding", "content-length", "transfer-encoding"]:
            continue
            
        if k_lower == "set-cookie":
            parts = v.split(";")
            new_parts =[p for p in parts if not p.strip().lower().startswith("domain=")]
            new_parts =[p if not p.strip().lower().startswith("path=") else "Path=/" for p in new_parts]
            resp_headers[k] = "; ".join(new_parts)
            continue
            
        if k_lower == "location":
            loc = urllib.parse.urljoin(target_url, v)
            resp_headers[k] = f"/yellow-mirror/proxy/{loc}"
            continue
            
        if k_lower in["x-frame-options", "content-security-policy", "x-content-type-options", "x-xss-protection"]:
            continue
            
        resp_headers[k] = v

    content = resp.content
    content_type = resp_headers.get("content-type", "").lower()
    
    # Inject our history hook and relative link resolver
    if "text/html" in content_type:
        html_str = content.decode("utf-8", errors="ignore")
        content = rewrite_html(html_str, target_url).encode("utf-8")

    return Response(content=content, status_code=resp.status_code, headers=resp_headers)