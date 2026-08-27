import asyncio
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from playwright.async_api import async_playwright
from shared_network import NetworkPolicyError, validate_outbound_url_async

router = APIRouter()

active_sessions = {}
MAX_SESSIONS = max(1, int(os.getenv("YELLOW_MIRROR_MAX_SESSIONS", "2")))
BASE_DIR = Path(__file__).parent
SESSION_ROOT = Path(tempfile.gettempdir()) / "yellow_mirror"
SESSION_ROOT.mkdir(parents=True, exist_ok=True)
CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _allowed_hosts() -> tuple[str, ...]:
    configured = os.getenv("YELLOW_MIRROR_ALLOWED_HOSTS")
    if configured is None:
        configured = os.getenv("CUTAWAY_PROJECT_NETWORK_HOSTS", "")
    return tuple(item.strip().lower() for item in configured.split(",") if item.strip())


async def _validate_navigation(url: str) -> None:
    await validate_outbound_url_async(url, allowed_hosts=_allowed_hosts())

@router.get("/")
async def yellow_mirror_page():
    return FileResponse(BASE_DIR / "yellow-mirror.html")

@router.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()

    if not CLIENT_ID_RE.fullmatch(client_id) or client_id in active_sessions:
        await websocket.send_json({"type": "error", "message": "Invalid or duplicate session id."})
        await websocket.close(code=1008)
        return
    if len(active_sessions) >= MAX_SESSIONS:
        await websocket.send_json({"type": "error", "message": "Server at maximum capacity."})
        await websocket.close(code=1013)
        return
        
    active_sessions[client_id] = {
        "client_ws": websocket, 
        "playwright": None, 
        "context": None, 
        "page": None, 
        "cdp": None
    }
    
    try:
        while True:
            data = await websocket.receive_json()
            await handle_client_message(client_id, data)
    except NetworkPolicyError as exc:
        await websocket.send_json({"type": "error", "message": str(exc)})
    except WebSocketDisconnect:
        pass
    except Exception:
        logging.exception("yellow_mirror session failed")
        try:
            await websocket.send_json({"type": "error", "message": "Browser session failed."})
        except Exception:
            pass
    finally:
        await cleanup_session(client_id)

async def handle_client_message(client_id: str, data: dict):
    session = active_sessions.get(client_id)
    if not session: return
    
    msg_type = data.get("type")
    
    if msg_type == "init":
        if session.get("playwright") is not None:
            raise NetworkPolicyError("Browser session is already initialised.")
        url = str(data.get("url") or "")
        await _validate_navigation(url)
        width = max(320, min(1920, int(data.get("width", 1280))))
        height = max(240, min(1080, int(data.get("height", 720))))
        
        p = await async_playwright().start()
        session["playwright"] = p
        
        user_data_dir = SESSION_ROOT / f"ym_{client_id}"
        
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=True,
            args=[
                "--autoplay-policy=no-user-gesture-required",
                "--mute-audio",
                "--window-size=1920,1080",
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ],
            viewport={"width": width, "height": height}
        )
        session["context"] = context
        page = context.pages[0] if context.pages else await context.new_page()
        session["page"] = page
        page.set_default_navigation_timeout(30_000)

        async def enforce_network_policy(route):
            request_url = route.request.url
            if request_url.startswith(("data:", "blob:", "about:")):
                await route.continue_()
                return
            try:
                await _validate_navigation(request_url)
            except NetworkPolicyError:
                await route.abort()
                return
            await route.continue_()

        await page.route("**/*", enforce_network_policy)
        
        async def on_nav(frame):
            if frame == page.main_frame:
                try: await session["client_ws"].send_json({"type": "navigated", "url": frame.url})
                except: pass
        page.on("framenavigated", on_nav)
        
        await page.goto(url, wait_until="domcontentloaded")
        
        # ⚡ High-Speed CDP Screencast Setup
        cdp = await context.new_cdp_session(page)
        session["cdp"] = cdp
        
        async def on_screencast(event):
            try:
                # Send the compressed base64 frame straight to JS
                await session["client_ws"].send_text(event["data"])
                # Acknowledge receipt to unblock the next frame
                await session["cdp"].send("Page.screencastFrameAck", {"sessionId": event["sessionId"]})
            except Exception:
                pass

        cdp.on("Page.screencastFrame", on_screencast)
        await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 60, "maxWidth": width, "maxHeight": height})
            
    elif msg_type == "navigate":
        url = str(data.get("url") or "")
        await _validate_navigation(url)
        if session.get("page"):
            await session["page"].goto(url, wait_until="domcontentloaded")
        
    elif msg_type == "resize":
        width = max(320, min(1920, int(data.get("width", 1280))))
        height = max(240, min(1080, int(data.get("height", 720))))
        if session.get("page"): 
            await session["page"].set_viewport_size({"width": width, "height": height})
            if session.get("cdp"):
                try: await session["cdp"].send("Page.startScreencast", {"format": "jpeg", "quality": 60, "maxWidth": width, "maxHeight": height})
                except: pass
            
    elif msg_type == "input" and session.get("page"):
        page = session["page"]
        action = data.get("action")
        try:
            if action == "mousemove": 
                await page.mouse.move(data["x"], data["y"])
            elif action == "mousedown": 
                await page.mouse.down(button=data.get("button", "left"))
            elif action == "mouseup": 
                await page.mouse.up(button=data.get("button", "left"))
            elif action == "wheel": 
                await page.mouse.wheel(data.get("deltaX", 0), data.get("deltaY", 0))
            
            # Robust keyboard handling (Supports Cyrillic and Shortcuts)
            elif action == "keydown":
                key = data.get("key", "")
                code = data.get("code", "")
                ctrl = data.get("ctrlKey")
                meta = data.get("metaKey")
                
                if (ctrl or meta) and code.startswith("Key"):
                    char = code.replace("Key", "").lower()
                    prefix = "Meta+" if meta else "Control+"
                    await page.keyboard.press(f"{prefix}{char}")
                elif len(key) == 1 and not (ctrl or meta or data.get("altKey")):
                    await page.keyboard.insert_text(key)
                else:
                    await page.keyboard.down(key)
                    
            elif action == "keyup":
                key = data.get("key", "")
                if len(key) > 1:
                    await page.keyboard.up(key)
        except Exception:
            pass 

async def cleanup_session(client_id: str):
    session = active_sessions.pop(client_id, None)
    if session:
        if session.get("context"):
            try: await session["context"].close()
            except: pass
        if session.get("playwright"):
            try: await session["playwright"].stop()
            except: pass
        shutil.rmtree(SESSION_ROOT / f"ym_{client_id}", ignore_errors=True)
        
async def shutdown_clients():
    for client_id in list(active_sessions.keys()):
        await cleanup_session(client_id)