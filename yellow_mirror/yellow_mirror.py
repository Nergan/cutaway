import asyncio
import os
import shutil
from pathlib import Path
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from playwright.async_api import async_playwright

router = APIRouter()

active_sessions = {}
MAX_SESSIONS = 10
BASE_DIR = Path(__file__).parent

@router.get("/")
async def yellow_mirror_page():
    return FileResponse(BASE_DIR / "yellow-mirror.html")

@router.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()

    if len(active_sessions) >= MAX_SESSIONS:
        await websocket.send_json({"type": "error", "message": "Server at maximum capacity (10)."})
        await websocket.close()
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
    except WebSocketDisconnect:
        await cleanup_session(client_id)

async def handle_client_message(client_id: str, data: dict):
    session = active_sessions.get(client_id)
    if not session: return
    
    msg_type = data.get("type")
    
    if msg_type == "init":
        url = data.get("url")
        width, height = data.get("width", 1280), data.get("height", 720)
        
        p = await async_playwright().start()
        session["playwright"] = p
        
        user_data_dir = f"/tmp/ym_{client_id}"
        
        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=True, # Runs perfectly on HF Spaces!
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
        
        async def on_nav(frame):
            if frame == page.main_frame:
                try: await session["client_ws"].send_json({"type": "navigated", "url": frame.url})
                except: pass
        page.on("framenavigated", on_nav)
        
        await page.goto(url)
        
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
        if session.get("page"): await session["page"].goto(data.get("url"))
        
    elif msg_type == "resize":
        if session.get("page"): 
            await session["page"].set_viewport_size({"width": data.get("width"), "height": data.get("height")})
            if session.get("cdp"):
                try: await session["cdp"].send("Page.startScreencast", {"format": "jpeg", "quality": 60, "maxWidth": data.get("width"), "maxHeight": data.get("height")})
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
        shutil.rmtree(f"/tmp/ym_{client_id}", ignore_errors=True)
        
async def shutdown_clients():
    for client_id in list(active_sessions.keys()):
        await cleanup_session(client_id)