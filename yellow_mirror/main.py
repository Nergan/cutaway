from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from session import get_session_id
from browser_manager import manager
from streaming import generate_frames

app = FastAPI(title="Yellow Mirror (Browser Streaming)")
BASE_DIR = Path(__file__).parent

app.mount('/static', StaticFiles(directory=BASE_DIR / 'static'), name='static')
app.mount('/scripts', StaticFiles(directory=BASE_DIR / 'scripts'), name='scripts')


@app.get('/', response_class=FileResponse)
async def index():
    return FileResponse(BASE_DIR / 'yellow-mirror.html')


@app.post('/api/start')
async def start_browser(request: Request):
    data = await request.json()
    url = data.get('url')
    if not url:
        raise HTTPException(400, 'Missing url')

    session_id = get_session_id(request)
    session = await manager.get_or_create_session(session_id)
    try:
        await session.goto(url)
    except Exception as e:
        raise HTTPException(500, f"Failed to navigate: {str(e)}")
    return {'session_id': session_id, 'url': session.current_url}


@app.get('/api/stream/{session_id}')
async def video_stream(session_id: str):
    return StreamingResponse(
        generate_frames(session_id),
        media_type='multipart/x-mixed-replace; boundary=frame'
    )


@app.post('/api/click/{session_id}')
async def handle_click(session_id: str, request: Request):
    data = await request.json()
    x = data.get('x')
    y = data.get('y')
    if x is None or y is None:
        raise HTTPException(400, 'Missing coordinates')

    session = await manager.get_or_create_session(session_id)
    await session.click(int(x), int(y))
    return {'ok': True}


@app.post('/api/key/{session_id}')
async def handle_key(session_id: str, request: Request):
    data = await request.json()
    key = data.get('key')
    if key:
        session = await manager.get_or_create_session(session_id)
        await session.press_key(key)
    text = data.get('text')
    if text:
        session = await manager.get_or_create_session(session_id)
        await session.type(text)
    return {'ok': True}


@app.on_event('startup')
async def startup():
    manager.start_cleanup()


@app.on_event('shutdown')
async def shutdown():
    await manager.close_all()