"""
Воронка прогрева: контент всех касаний + логика отправки.

Порядок шагов (offset считается от момента расчёта КБЖУ = enrolled_at):

    block_0  -> сразу (отправляется inline из main.py)
    teaser   -> +10 мин   тизер про гайд
    block_1  -> +24 ч      продукты-обманщики
    block_2  -> +48 ч      продукты-герои
    block_3  -> +72 ч      инсайды + лайфхаки
    block_4  -> +96 ч      психология + ПРОДАЖА (кнопка оплаты)
    block_5  -> +120 ч     дожим (ТОЛЬКО если не купил)

    block_6  -> +7 дней от ПОКУПКИ — наставничество (отдельная ветка,
                планируется в payment.py, шлётся scheduler'ом)

Тексты ниже можно свободно править — это просто строки.
"""

import asyncio
import logging
from pathlib import Path

from aiogram import Bot
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
    InputMediaPhoto,
)

import config
from payment import create_payment, user_payments

logger = logging.getLogger(__name__)


# ============================================================
#  КНОПКИ
# ============================================================
def mentor_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=config.MENTOR_BUTTON_TEXT, url=config.MENTOR_URL)
    ]])


def payment_keyboard(url: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=config.BUY_BUTTON_TEXT, url=url)],
        [InlineKeyboardButton(text=config.PAID_BUTTON_TEXT, callback_data="check_payment")],
    ])


# ============================================================
#  ТЕКСТЫ КАСАНИЙ
# ============================================================

# --- block_0: подводка перед каруселью (после неё идёт сама карусель) ---
BLOCK_0_INTRO_TEXT = (
    "Твои цифры готовы 👆\n\n"
    "Но вот что важно знать:\n"
    "80% людей получают расчёт — и ничего не меняют.\n"
    "Не потому что ленивые. А потому что не знают,\n"
    "что реально мешает именно им.\n\n"
    "Через минуту пришлю тебе кое-что важное 👇"
)

# --- teaser: через 10 минут ---
TEASER_TEXT = (
    "Хочешь знать, что конкретно есть под твои цифры?\n\n"
    "Есть гайд с готовым рационом на неделю, списком продуктов\n"
    "и протоколом выхода из срыва.\n\n"
    f"Сейчас он стоит {config.PRICE_LABEL}.\n\n"
    "Но сначала — 4 дня я бесплатно покажу тебе самое важное 👇\n"
    "<i>Завтра расскажу про продукты, которые тихо убивают твой дефицит.</i>"
)

# --- block_1: продукты-обманщики (+24ч) ---
BLOCK_1_TEXT = (
    "Вчера ты получил свой КБЖУ.\n"
    "Сегодня — первый инсайт, который меняет всё 👇\n\n"
    "<b>Продукты-обманщики</b> — то, что все едят на диете, и зря 🚫"
)

# --- block_2: продукты-герои (+48ч) ---
BLOCK_2_TEXT = (
    "<b>Продукты-герои</b> — то, что недооценивают, а зря 💪\n\n"
    "Творог 5%, яйца, красная чечевица — дешёвый белок,\n"
    "который держит сытость часами.\n\n"
    "<i>Завтра — то, из-за чего ломаются все диеты. Не продукты. Кое-что важнее.</i>"
)

# --- block_3: инсайды + лайфхаки (+72ч) ---
BLOCK_3_TEXT = (
    "<b>Контринтуитивные вещи, которые меняют всё</b> 🧠\n\n"
    "Есть на ночь — не убивает дефицит. Голод ≠ сигнал есть.\n"
    "Готовь белок на 3 дня вперёд. Тарелка поменьше — ешь на 22% меньше.\n\n"
    "<i>Завтра — самый важный блок. Именно здесь ломается большинство.</i>"
)

# --- block_4: психология + ПРОДАЖА (+96ч) ---
BLOCK_4_PRE_TEXT = (
    "Это последний инсайт, который я отправлю бесплатно.\n"
    "Он же — самый важный 👇"
)
BLOCK_4_POST_TEXT = (
    "Всё, что я показывал тебе 4 дня — это 20% того, что внутри.\n\n"
    "<b>5 блоков · 12 продуктов-обманщиков · 8 продуктов-героев ·\n"
    "15 инсайдов · 10 лайфхаков · протокол выхода из срыва.</b>\n\n"
    f"Гайд стоит {config.PRICE_LABEL}.\n"
    "Это меньше одного похода в кафе — где ты, скорее всего,\n"
    "съешь то, что замедлит твой результат 😄\n\n"
    "👇 Ссылка на оплату"
)

# --- block_5: дожим, если не купил (+120ч) ---
BLOCK_5_PRE_TEXT = (
    "Видел, что ты ещё не забрал гайд.\n\n"
    "Не буду давить — просто оставлю одну мысль:\n\n"
    "Ты уже потратил время на расчёт КБЖУ.\n"
    "Значит, ты хочешь результата.\n\n"
    "Единственное, что отделяет желание от результата — система.\n"
    "Гайд — это и есть система.\n\n"
    "Ссылка всё ещё работает 👇"
)

# --- block_6: наставничество, +7 дней от покупки ---
BLOCK_6_TEXT = (
    "Как гайд? Уже попробовал что-то применить?\n\n"
    "Я веду людей лично — считаем вместе,\n"
    "корректирую рацион под твой ритм жизни,\n"
    "на связи каждый день.\n\n"
    "Если хочешь пройти путь быстрее и без угадайки —\n"
    "напиши мне, расскажу подробнее."
)


# ============================================================
#  УНИВЕРСАЛЬНАЯ ОТПРАВКА КАРУСЕЛИ
# ============================================================
def _collect_slides(folder_name: str):
    folder = Path(folder_name)
    if not folder.exists() or not folder.is_dir():
        return []
    files = sorted(
        f for f in folder.iterdir()
        if f.name.startswith(config.SLIDES_PREFIX)
        and f.suffix.lower() in config.SLIDE_EXTENSIONS
    )
    return files


async def send_carousel(bot: Bot, chat_id: int, folder_name: str, caption: str = ""):
    """Отправить карусель из папки folder_name.

    Если папки/слайдов ещё нет — отправляем только текст caption,
    чтобы воронка не падала, пока ты не залил картинки.
    """
    files = _collect_slides(folder_name)

    if not files:
        logger.warning(f"NO SLIDES in '{folder_name}' — sending text only")
        if caption:
            await bot.send_message(chat_id, caption, parse_mode="HTML")
        return

    media = []
    for i, file in enumerate(files):
        if i == 0 and caption:
            media.append(InputMediaPhoto(
                media=FSInputFile(str(file)),
                caption=caption,
                parse_mode="HTML",
            ))
        else:
            media.append(InputMediaPhoto(media=FSInputFile(str(file))))

    await bot.send_media_group(chat_id, media)


# ============================================================
#  ОТПРАВКА КОНКРЕТНЫХ ШАГОВ
# ============================================================
async def send_block_0(bot: Bot, chat_id: int):
    """Карусель block_0. Подводка BLOCK_0_INTRO_TEXT отправляется в main.py
    отдельным сообщением до паузы DELAY_BLOCK_0_INTRO."""
    await send_carousel(bot, chat_id, config.BLOCK_0_FOLDER)


async def send_teaser(bot: Bot, chat_id: int):
    await bot.send_message(chat_id, TEASER_TEXT, parse_mode="HTML")


async def send_block_1(bot: Bot, chat_id: int):
    await send_carousel(bot, chat_id, config.BLOCK_1_FOLDER, BLOCK_1_TEXT)


async def send_block_2(bot: Bot, chat_id: int):
    await send_carousel(bot, chat_id, config.BLOCK_2_FOLDER, BLOCK_2_TEXT)


async def send_block_3(bot: Bot, chat_id: int):
    await send_carousel(bot, chat_id, config.BLOCK_3_FOLDER, BLOCK_3_TEXT)


async def send_block_4(bot: Bot, chat_id: int):
    """Психология + продажа. Создаём платёж в ЮKassa и кладём ссылку на кнопку."""
    await bot.send_message(chat_id, BLOCK_4_PRE_TEXT, parse_mode="HTML")
    await send_carousel(bot, chat_id, config.BLOCK_4_FOLDER)

    # создаём персональный платёж
    try:
        payment_id, url = create_payment(chat_id)
        user_payments[chat_id] = payment_id
        keyboard = payment_keyboard(url)
    except Exception as e:
        logger.error(f"PAYMENT CREATE ERROR for {chat_id}: {e}")
        keyboard = None

    await bot.send_message(
        chat_id, BLOCK_4_POST_TEXT, parse_mode="HTML", reply_markup=keyboard
    )


async def send_block_5(bot: Bot, chat_id: int):
    """Дожим. Пересоздаём платёж, чтобы ссылка была свежей."""
    try:
        payment_id, url = create_payment(chat_id)
        user_payments[chat_id] = payment_id
        keyboard = payment_keyboard(url)
    except Exception as e:
        logger.error(f"PAYMENT CREATE ERROR (block_5) for {chat_id}: {e}")
        keyboard = None

    await bot.send_message(
        chat_id, BLOCK_5_PRE_TEXT, parse_mode="HTML", reply_markup=keyboard
    )


async def send_block_6(bot: Bot, chat_id: int):
    await bot.send_message(
        chat_id, BLOCK_6_TEXT, parse_mode="HTML", reply_markup=mentor_keyboard()
    )


# ============================================================
#  ПОСЛЕДОВАТЕЛЬНОСТЬ ОСНОВНОЙ ЦЕПОЧКИ
# ------------------------------------------------------------
#  Каждый шаг: ключ, offset от enrolled_at (сек), функция отправки,
#  skip_if_purchased — пропускать ли шаг, если человек уже купил.
# ============================================================
STEPS = [
    {"key": "teaser",  "offset": config.DELAY_TEASER,  "send": send_teaser,  "skip_if_purchased": True},
    {"key": "block_1", "offset": config.DELAY_BLOCK_1, "send": send_block_1, "skip_if_purchased": False},
    {"key": "block_2", "offset": config.DELAY_BLOCK_2, "send": send_block_2, "skip_if_purchased": False},
    {"key": "block_3", "offset": config.DELAY_BLOCK_3, "send": send_block_3, "skip_if_purchased": False},
    {"key": "block_4", "offset": config.DELAY_BLOCK_4, "send": send_block_4, "skip_if_purchased": True},
    {"key": "block_5", "offset": config.DELAY_BLOCK_5, "send": send_block_5, "skip_if_purchased": True},
]

# Ключи шагов по порядку (для поиска "следующего").
STEP_KEYS = ["block_0"] + [s["key"] for s in STEPS]

# Быстрый доступ по ключу.
STEP_BY_KEY = {s["key"]: s for s in STEPS}

# Человекочитаемые названия шагов (для админ-панели).
STEP_LABELS = {
    "block_0": "🎬 Касание 0 — карусель «Что делать с цифрами»",
    "teaser":  "📨 Тизер про гайд (+10 мин)",
    "block_1": "🚫 Касание 1 — продукты-обманщики (+24ч)",
    "block_2": "💪 Касание 2 — продукты-герои (+48ч)",
    "block_3": "🧠 Касание 3 — инсайды + лайфхаки (+72ч)",
    "block_4": "🛒 Касание 4 — психология + ПРОДАЖА (+96ч)",
    "block_5": "🔁 Касание 5 — дожим (+120ч)",
    "block_6": "🎓 Касание 6 — наставничество (+7д от покупки)",
}

# Карта «ключ шага -> функция отправки» для ручной отправки из админки.
SEND_BY_KEY = {
    "block_0": send_block_0,
    "teaser":  send_teaser,
    "block_1": send_block_1,
    "block_2": send_block_2,
    "block_3": send_block_3,
    "block_4": send_block_4,
    "block_5": send_block_5,
    "block_6": send_block_6,
}


def next_step_after(current_step: str):
    """Вернуть конфиг следующего шага после current_step или None, если цепочка кончилась."""
    try:
        idx = STEP_KEYS.index(current_step)
    except ValueError:
        return None
    # следующий ключ
    if idx + 1 >= len(STEP_KEYS):
        return None
    next_key = STEP_KEYS[idx + 1]
    return STEP_BY_KEY.get(next_key)


# Offset каждого шага от enrolled_at (block_0 = 0, остальные из STEPS).
OFFSET_BY_KEY = {"block_0": 0}
OFFSET_BY_KEY.update({s["key"]: s["offset"] for s in STEPS})


def prev_step_key(key: str):
    """Ключ шага, ПРЕДшествующего данному (или None для block_0)."""
    try:
        idx = STEP_KEYS.index(key)
    except ValueError:
        return None
    return STEP_KEYS[idx - 1] if idx > 0 else None
