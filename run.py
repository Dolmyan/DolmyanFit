import asyncio
import logging

# Логирование настраиваем ПЕРВЫМ делом — до импорта main/admin/payment,
# чтобы все их логгеры писали в файл с самого старта.
from logging_config import setup_logging

setup_logging()

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, TEST_MODE
from database.db import init_db
from main import router as main_router
from admin import router as admin_router
from payment import router as payment_router
from scheduler import funnel_worker

logger = logging.getLogger(__name__)


async def main():
    logger.info("=" * 60)
    logger.info("ЗАПУСК БОТА Dolmyan Fit (TEST_MODE=%s)", TEST_MODE)
    logger.info("=" * 60)

    # Инициализация / миграция БД (создаёт таблицу и колонки воронки)
    init_db()
    logger.info("База данных инициализирована")

    bot = Bot(token=BOT_TOKEN)
    storage = MemoryStorage()

    dp = Dispatcher(storage=storage)
    dp.include_router(main_router)
    dp.include_router(admin_router)
    dp.include_router(payment_router)

    me = await bot.get_me()
    logger.info("Бот авторизован: @%s (id=%s)", me.username, me.id)

    # Фоновый воркер воронки (рассылка блоков по расписанию)
    worker = asyncio.create_task(funnel_worker(bot))

    try:
        logger.info("Старт polling")
        await dp.start_polling(bot)
    finally:
        worker.cancel()
        await bot.session.close()
        logger.info("Бот остановлен")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Остановка по Ctrl+C")
