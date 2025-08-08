# bot/bot.py
# Aiogram v3.x

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

# Роутеры
from handlers import start, fsm, checklist, fallback

# Пытаемся взять токен из config.py, иначе — из .env / окружения
BOT_TOKEN = None
try:
    from config import BOT_TOKEN as CONFIG_TOKEN  # type: ignore
    BOT_TOKEN = CONFIG_TOKEN
except Exception:
    pass

from dotenv import load_dotenv
load_dotenv()
BOT_TOKEN = BOT_TOKEN or os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN не найден. Укажи его в config.py или в .env (BOT_TOKEN=...)."
    )


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(start.router)
    dp.include_router(fsm.router)
    dp.include_router(checklist.router)
    dp.include_router(fallback.router)
    return dp


async def main() -> None:
    setup_logging()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp = build_dispatcher()

    # Сбрасываем вебхук и висячие апдейты на старте
    await bot.delete_webhook(drop_pending_updates=True)

    # Разрешаем только те апдейты, которые реально используются роутерами
    allowed = dp.resolve_used_update_types()

    logging.info("🚀 Бот запускается...")
    try:
        await dp.start_polling(bot, allowed_updates=allowed)
    except Exception as e:
        logging.exception(f"❌ Критическая ошибка бота: {e}")
        raise
    finally:
        logging.info("🧹 Остановка бота. До встречи!")


if __name__ == "__main__":
    asyncio.run(main())
