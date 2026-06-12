import logging
import time
import uuid
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

import config
from config import BOT_TOKEN, ADMIN_ID
from database.db import (
    init_db,
    save_user,
    get_users_count,
    get_last_users,
    mark_purchased,
)

logger = logging.getLogger(__name__)

router = Router()
bot = Bot(token=BOT_TOKEN)



from yookassa import Payment

user_payments = {}

def create_payment(user_id: int):
    logger.info("Создание платежа ЮKassa для user_id=%s", user_id)
    payment = Payment.create(
        {
            "amount": {
                "value": config.PRICE,
                "currency": config.CURRENCY
            },
            "confirmation": {
                "type": "redirect",
                "return_url": config.PAYMENT_RETURN_URL
            },
            "capture": True,
            "description": f"{config.PAYMENT_DESCRIPTION} {user_id}",
            "metadata": {
                "user_id": str(user_id)
            }
        },
        str(uuid.uuid4())
    )

    logger.info("Платёж создан: id=%s user_id=%s", payment.id, user_id)
    return payment.id, payment.confirmation.confirmation_url
def mentor_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=config.MENTOR_BUTTON_TEXT, url=config.MENTOR_URL)
    ]])
@router.callback_query(F.data == "check_payment")
async def check_payment(callback: CallbackQuery):
    user_id = callback.from_user.id
    payment_id = user_payments.get(user_id)
    logger.info("Проверка оплаты: user_id=%s payment_id=%s", user_id, payment_id)

    if not payment_id:
        logger.warning("Платёж не найден в памяти для user_id=%s", user_id)
        await callback.answer("Платёж не найден", show_alert=True)
        return

    payment = Payment.find_one(payment_id)
    logger.info("Статус платежа %s = %s (user_id=%s)", payment_id, payment.status, user_id)

    if payment.status == "succeeded":

        await callback.message.answer_document(
                FSInputFile(config.GUIDE_FILE),
                caption="✅ Оплата подтверждена. Вот твой гайд",reply_markup=mentor_keyboard()
        )

        # Отмечаем покупку и планируем block_6 (наставничество) через 7 дней.
        # Дожим block_5 после этого отправляться не будет.
        now_ts = time.time()
        mark_purchased(
            callback.from_user.id,
            block6_at=now_ts + config.DELAY_BLOCK_6_AFTER_PURCHASE,
            now=now_ts,
        )

        # уведомление админу
        user = callback.from_user
        text = (
            "💰 Новая покупка\n\n"
            f"👤 Имя: {user.full_name}\n"
            f"🆔 ID: {user.id}\n"
            f"🔗 Username: @{user.username if user.username else 'нет'}\n"
        )

        await callback.bot.send_message(ADMIN_ID, text)
        user_payments.pop(callback.from_user.id, None)
        logger.info("ПОКУПКА подтверждена и гайд отправлен: user_id=%s", user_id)

        await callback.answer("Готово")

    else:
        logger.info("Оплата ещё не прошла: user_id=%s status=%s", user_id, payment.status)
        await callback.answer("Оплата не найдена", show_alert=True)