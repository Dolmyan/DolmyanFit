import logging
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    FSInputFile,
    InputMediaPhoto
)
from database.db import (
    init_db,
    save_user,
    get_users_count,
    get_last_users
)
from config import ADMIN_ID
from database.db import get_users_count, get_last_users

logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)

router = Router()


async def send_block_1(message: Message):
    await message.answer("text")
