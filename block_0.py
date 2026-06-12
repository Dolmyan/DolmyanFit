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


async def send_block_0(message: Message):
    folder = Path("block_0")

    files = sorted([
        f for f in folder.iterdir()
        if f.name.startswith("slide_") and f.suffix.lower() in [".jpg", ".jpeg", ".png"]
    ])

    logger.info(f"FOUND FILES: {len(files)}")

    media = []

    caption = (
        " "

    )
    for i, file in enumerate(files[:5]):
        if i == 0:
            media.append(
                    InputMediaPhoto(
                            media=FSInputFile(str(file)),
                            caption=caption, parse_mode="html"
                    )
            )
        else:
            media.append(InputMediaPhoto(media=FSInputFile(str(file))))

    await message.answer_media_group(media)
