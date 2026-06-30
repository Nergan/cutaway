import os
import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from motor.motor_asyncio import AsyncIOMotorClient

from .bot import get_bot, dp, set_db

logger = logging.getLogger(__name__)
background_tasks = set()
db_client = None

router = APIRouter()

async def run_bot_polling(token):
    """Wrapper task to GUARANTEE exceptions are logged and not swallowed."""
    try:
        bot = get_bot(token)
        # 1. Clear any stuck webhooks before starting Long Polling
        await bot.delete_webhook(drop_pending_updates=True)
        
        # 2. Start polling cleanly
        await dp.start_polling(bot, handle_signals=False)
    except asyncio.CancelledError:
        logger.info("Bot polling cancelled.")
    except Exception as e:
        logger.error(f"FATAL BOT POLLING ERROR: {e}", exc_info=True)

@router.on_event("startup")
async def startup_bot():
    """Uses standard startup event which survives FastAPI's include_router mechanism."""
    global db_client
    
    token = os.getenv("TOKEN")
    mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    
    if not token:
        logger.warning("Telegram Bot skipped: No TOKEN found in environment.")
        return

    # 1. Initialize Database & Push it to bot.py
    db_client = AsyncIOMotorClient(mongodb_uri, tls=True, tlsAllowInvalidCertificates=True)
    set_db(db_client["bot"])
    
    # 2. Start Polling safely in our wrapped background task
    polling_task = asyncio.create_task(run_bot_polling(token))
    background_tasks.add(polling_task)
    
    logger.info("Telegram Bot Plugin initialized: Long Polling active.")

@router.get("/", summary="Redirects to Bot")
async def redirect_to_bot():
    return RedirectResponse(url="https://t.me/hornychat42_bot")

async def shutdown_clients():
    """
    Hook matched dynamically by root main.py via: 
    `if hasattr(plugin_module, "shutdown_clients")`
    """
    logger.info("Shutting down Telegram Bot Plugin...")
    token = os.getenv("TOKEN")
    if token:
        bot = get_bot(token)
        if bot:
            await bot.session.close()
            
    for task in background_tasks:
        task.cancel()
        
    if db_client:
        db_client.close()