import asyncio
from browser_manager import manager


async def generate_frames(session_id: str):
    session = await manager.get_or_create_session(session_id)
    while True:
        frame = await session.screenshot()
        if frame:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            )
        await asyncio.sleep(0.1)