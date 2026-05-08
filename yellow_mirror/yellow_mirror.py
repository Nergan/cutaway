import re
import urllib.parse
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import FileResponse
from curl_cffi import requests as cffi_requests
from .core.rewriter import rewrite_html

router = APIRouter()

async def shutdown_clients():
    pass

@router.get("/")
async def yellow_mirror_page():
    return FileResponse("yellow_mirror/yellow-mirror.html")

@router.get("/sw.js")
async def service_worker():
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
    
    target_url = full_url.split("/proxy/", 1)[1]
    target_url = re.sub(r"^(https?:)/+", r"\1//", target_url)
    
    if not target_url.startswith(("http://", "https://")):
        target_url = "https://" + target_url

    parsed_target = urllib.parse.urlparse(target_url)
    target_origin = f"{parsed_target.scheme}://{parsed_target.netloc}"

    headers = dict(request.headers)
    
    # 1. Strip headers that reveal our Vercel proxy
    headers.pop("host", None)
    headers.pop("connection", None)
    headers.pop("accept-encoding", None)
    
    # 2. SPOOFING: Trick the target server into thinking we are on their domain (Fixes Google/YouTube Blocks)
    headers["origin"] = target_origin
    headers["referer"] = target_url
    
    # Emulate standard browser fetch metadata
    headers["sec-fetch-dest"] = "empty"
    headers["sec-fetch-mode"] = "cors"
    headers["sec-fetch-site"] = "same-origin"

    body = await request.body()
    
    try:
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
    
    # 3. Strip hostile headers and modify cookies
    prohibited_headers =[
        "content-encoding", "content-length", "transfer-encoding",
        "x-frame-options", "content-security-policy", "content-security-policy-report-only",
        "x-content-type-options", "x-xss-protection", "strict-transport-security",
        "cross-origin-embedder-policy", "cross-origin-opener-policy", "cross-origin-resource-policy"
    ]

    for k, v in resp.headers.items():
        k_lower = k.lower()
        if k_lower in prohibited_headers:
            continue
            
        if k_lower == "set-cookie":
            parts = v.split(";")
            new_parts =[p for p in parts if not p.strip().lower().startswith("domain=")]
            new_parts =[p if not p.strip().lower().startswith("path=") else "Path=/" for p in new_parts]
            # Strip secure flag to ensure cookies stick on http/localhost environments
            new_parts =[p for p in new_parts if p.strip().lower() != "secure"]
            resp_headers[k] = "; ".join(new_parts)
            continue
            
        if k_lower == "location":
            loc = urllib.parse.urljoin(target_url, v)
            resp_headers[k] = f"/yellow-mirror/proxy/{loc}"
            continue
            
        resp_headers[k] = v

    # 4. FORCE CORS ALLOWANCE: Tells the browser it's allowed to load Twitch/YouTube modules via our proxy
    resp_headers["access-control-allow-origin"] = "*"
    resp_headers["access-control-allow-methods"] = "*"
    resp_headers["access-control-allow-headers"] = "*"
    resp_headers["access-control-expose-headers"] = "*"

    content = resp.content
    content_type = resp_headers.get("content-type", "").lower()
    
    if "text/html" in content_type:
        html_str = content.decode("utf-8", errors="ignore")
        content = rewrite_html(html_str, target_url).encode("utf-8")

    return Response(content=content, status_code=resp.status_code, headers=resp_headers)