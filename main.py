import asyncio
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from aiogram.fsm.context import FSMContext

import config
from config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, BOT_TOKEN
from funnel import send_block_0, BLOCK_0_INTRO_TEXT, STEPS
from states import *
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
from dotenv import load_dotenv

from yookassa import Configuration, Payment

from database.db import (
    init_db,
    save_user,
    enroll_user,
    get_users_count,
    get_last_users
)
from payment import create_payment, user_payments
from services.calculator import calculate_kbju
import logging

# Конфигурация логирования централизована в logging_config.setup_logging(),
# который вызывается в run.py до импорта этого модуля.
logger = logging.getLogger(__name__)

# YooKassa init
Configuration.account_id = YOOKASSA_SHOP_ID
Configuration.secret_key = YOOKASSA_SECRET_KEY

router = Router()

BLOCK_FILES = "slide_"
BLOCK_COUNT = 7

mentor_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                        text="💬 Хочу задать вопросы наставнику",
                        url="https://t.me/dolmyanfit"
                )
            ]
        ]
)


def payment_keyboard(url: str):
    return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                            text="💳 Купить гайд за 190 ₽",
                            url=url
                    )
                ],
                [
                    InlineKeyboardButton(
                            text="✅ Я оплатил",
                            callback_data="check_payment"
                    )
                ]
            ]
    )





@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.set_state(CalcState.waiting_for_data)
    WELCOME_TEXT = """
    👋 <b>Добро пожаловать в Dolmyan Fit!</b>

    Я помогу рассчитать вашу персональную норму калорий и КБЖУ для снижения веса.

    📩 Отправьте данные одним сообщением:

    <code>пол возраст вес рост активность</code>

    <b>Пример:</b>
    <code>м 21 66 168 3</code>

    📊 <b>Уровни активности:</b>

    <b>1</b> — сидячий образ жизни
    • офисная работа
    • до 5 000 шагов в день

    <b>2</b> — лёгкая активность
    • 5 000–8 000 шагов
    • 1–3 тренировки в неделю

    <b>3</b> — умеренная активность
    • 8 000–12 000 шагов
    • 3–5 тренировок в неделю

    <b>4</b> — высокая активность
    • активная работа или спорт почти каждый день
    • 12 000+ шагов

    <b>5</b> — очень высокая активность
    • тяжёлый физический труд
    • интенсивные тренировки 6–7 раз в неделю

    ⚠️ Если сомневаетесь между двумя уровнями — выбирайте меньший.
    """
    await message.answer(text=WELCOME_TEXT, parse_mode="HTML")





@router.message(CalcState.waiting_for_data)
async def calc(message: Message, state: FSMContext):
    try:
        logger.info(f"NEW USER: {message.from_user.id} | {message.text}")

        sex, age, weight, height, activity = message.text.split()

        result = calculate_kbju(
                sex=sex.lower(),
                age=int(age),
                weight=float(weight),
                height=float(height),
                activity=int(activity)
        )

        now = datetime.now()

        save_user(
                tg_id=message.from_user.id,
                username=message.from_user.username or "",
                full_name=message.from_user.full_name,
                sex=sex,
                age=int(age),
                weight=float(weight),
                height=float(height),
                activity=int(activity),
                calculated_at=now.strftime("%d.%m.%Y %H:%M")
        )

        logger.info(f"CALC DONE: {message.from_user.id}")
        final_message = (
            f"👋 <b>{message.from_user.first_name}, ваш расчёт готов</b>\n\n"
            f"📅 Дата расчёта: "
            f"<b>{now.strftime('%d.%m.%Y')}</b>\n\n"
            f"{result}\n\n"
            f"💬 Если остались вопросы по питанию, "
            f"похудению или тренировкам — "
            f"напишите наставнику."
        )
        await message.answer(
                f"{final_message}", parse_mode="HTML"
        )
        await state.clear()

        # Подводка перед каруселью block_0
        await message.answer(BLOCK_0_INTRO_TEXT, parse_mode="HTML")
        await asyncio.sleep(config.DELAY_BLOCK_0_INTRO)

        # block_0 — отправляем сразу
        logger.info(f"SENDING block 0: {message.from_user.id}")
        await send_block_0(message.bot, message.chat.id)
        logger.info(f"block 0 SENT: {message.from_user.id}")

        # Ставим пользователя в воронку: block_0 уже отправлен,
        # следующий шаг (STEPS[0] = teaser) запланирован от текущего момента.
        now_ts = time.time()
        first = STEPS[0]
        enroll_user(
                tg_id=message.from_user.id,
                first_step="block_0",
                next_send_at=now_ts + first["offset"],
                now=now_ts,
        )
        logger.info(f"ENROLLED in funnel: {message.from_user.id}")


    except Exception as e:
        logger.error(f"CALC ERROR: {e}")
        await message.answer(
                "❌ Неверный формат данных.\n\n"
                "Используйте:\n"
                "<code>м 21 66 168 3</code>"
        )


@router.message(Command('t'))
async def cmd_start(message: Message, state: FSMContext):
    await send_block_0(message.bot, message.chat.id)
    button = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='t', callback_data='get_task_sis'), ],
    ])
    await message.answer(text='t', reply_markup=button)