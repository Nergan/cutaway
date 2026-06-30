import logging
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

logger = logging.getLogger(__name__)

dp = Dispatcher()
bot_instance = None
db_instance = None

def get_bot(token: str) -> Bot:
    """Singleton getter configured for standard long polling."""
    global bot_instance
    if not bot_instance:
        bot_instance = Bot(
            token=token, 
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        logger.info("Telegram Bot initialized with standard polling.")
    return bot_instance

def set_db(database):
    global db_instance
    db_instance = database

@dp.message()
async def process_message(message: types.Message):
    if message.from_user.is_bot:
        return
    
    if db_instance is None:
        logger.error("Database not initialized for Bot!")
        return
        
    user_id = message.from_user.id
    username = message.from_user.username or "unknown"
    text = message.text or "[non-text message]"
    
    try:
        await db_instance.users.update_one(
            {"user_id": user_id},
            {"$addToSet": {"usernames": username}},
            upsert=True
        )

        await db_instance.chat_logs.insert_one({
            "user_id": user_id, "type": "incoming", "text": text, "date": message.date
        })

        # Repetitive behavior: Echoes back what the user sent
        sent_message = await message.answer(text)

        await db_instance.chat_logs.insert_one({
            "user_id": user_id, "type": "outgoing", "text": sent_message.text, "date": sent_message.date
        })
        
    except Exception as e:
        logger.error(f"Telegram Bot Worker Error: {e}", exc_info=True)