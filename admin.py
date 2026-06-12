import asyncio
import logging
import time
from datetime import datetime

from logging_config import read_log_tail, LOG_FILE

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    FSInputFile,
    InputMediaPhoto
)

import config
from config import ADMIN_ID
from database.db import (
    get_users_count,
    get_last_users,
    get_funnel_stats,
    get_user,
    find_users,
    get_all_user_ids,
    get_segment_ids,
    count_segment,
    enroll_unenrolled,
    reset_funnel,
)
from funnel import (
    STEP_LABELS,
    STEP_KEYS,
    SEND_BY_KEY,
    STEPS,
    OFFSET_BY_KEY,
    prev_step_key,
)

# Конфигурация логирования централизована в logging_config.setup_logging()
# (вызывается в run.py). Здесь только получаем логгер модуля.
logger = logging.getLogger(__name__)

router = Router()


# ============================================================
#  ВСПОМОГАТЕЛЬНОЕ
# ============================================================
def is_admin(message_or_cb) -> bool:
    return message_or_cb.from_user.id == ADMIN_ID


def fmt_ts(ts):
    """unix-время -> читаемая дата, либо '—'."""
    if not ts:
        return "—"
    try:
        return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return "—"


class AdminState(StatesGroup):
    broadcast_wait = State()     # ждём контент рассылки
    broadcast_confirm = State()  # показали предпросмотр, ждём подтверждение
    finduser_wait = State()      # ждём поисковый запрос


# Сегменты аудитории: ключ -> подпись для админа.
SEGMENT_LABELS = {
    "all":           "👥 Все пользователи",
    "not_purchased": "🙅 Не купившие",
    "purchased":     "💰 Купившие",
    "active":        "🟢 Сейчас в воронке",
    "done":          "🏁 Прошли воронку",
    "not_in_funnel": "🆕 Не в воронке (старые)",
}


# ============================================================
#  ГЛАВНОЕ МЕНЮ
# ============================================================
def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика воронки", callback_data="adm:stats")],
        [InlineKeyboardButton(text="👥 Последние юзеры", callback_data="adm:last")],
        [InlineKeyboardButton(text="🔍 Найти пользователя", callback_data="adm:find")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="adm:broadcast")],
        [InlineKeyboardButton(text="🆕 Старые юзеры → в воронку", callback_data="adm:backfill")],
        [InlineKeyboardButton(text="📜 Логи", callback_data="adm:logs")],
    ])


@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message):
        return
    await message.answer(
        "🛠 <b>Админ-панель Dolmyan Fit</b>\n\nВыбери действие:",
        parse_mode="HTML",
        reply_markup=admin_menu(),
    )


@router.callback_query(F.data == "adm:menu")
async def cb_menu(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback):
        return
    await state.clear()
    await callback.message.edit_text(
        "🛠 <b>Админ-панель Dolmyan Fit</b>\n\nВыбери действие:",
        parse_mode="HTML",
        reply_markup=admin_menu(),
    )
    await callback.answer()


# ============================================================
#  СТАТИСТИКА ВОРОНКИ
# ============================================================
def _stats_text():
    s = get_funnel_stats()
    total = s["total"] or 1  # защита от деления на 0

    conv = s["purchased"] / total * 100

    text = (
        "📊 <b>Статистика воронки</b>\n\n"
        f"👥 Всего пользователей: <b>{s['total']}</b>\n"
        f"🟢 В активной воронке: <b>{s['active']}</b>\n"
        f"🏁 Завершили цепочку: <b>{s['done']}</b>\n"
        f"💰 Купили гайд: <b>{s['purchased']}</b>\n"
        f"📈 Конверсия в покупку: <b>{conv:.1f}%</b>\n\n"
        "<b>Распределение по последнему касанию:</b>\n"
    )

    by_step = s["by_step"]
    # выводим в порядке воронки + block_6
    order = STEP_KEYS + ["block_6"]
    any_step = False
    for key in order:
        cnt = by_step.get(key, 0)
        if cnt:
            any_step = True
            label = STEP_LABELS.get(key, key)
            text += f"• {label}: <b>{cnt}</b>\n"
    if not any_step:
        text += "<i>пока никого</i>\n"

    return text


@router.callback_query(F.data == "adm:stats")
async def cb_stats(callback: CallbackQuery):
    if not is_admin(callback):
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="adm:stats")],
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="adm:menu")],
    ])
    await callback.message.edit_text(_stats_text(), parse_mode="HTML", reply_markup=kb)
    await callback.answer()


# ============================================================
#  ПОСЛЕДНИЕ ПОЛЬЗОВАТЕЛИ
# ============================================================
@router.callback_query(F.data == "adm:last")
async def cb_last(callback: CallbackQuery):
    if not is_admin(callback):
        return

    users = get_last_users(15)
    text = f"👥 <b>Последние {len(users)} пользователей</b>\n\n"
    for u in users:
        username = f"@{u['username']}" if u["username"] else "без username"
        paid = "💰" if u.get("purchased") else ""
        step = STEP_LABELS.get(u.get("funnel_step"), u.get("funnel_step") or "—")
        text += (
            f"👤 <b>{u['full_name']}</b> {paid}\n"
            f"🆔 <code>{u['tg_id']}</code> · {username}\n"
            f"📍 {step}\n"
            f"📅 {u['calculated_at']}\n\n"
        )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="adm:menu")],
    ])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


# ============================================================
#  КАРТОЧКА ПОЛЬЗОВАТЕЛЯ + ручные действия
# ============================================================
def _user_card(u):
    username = f"@{u['username']}" if u["username"] else "без username"
    paid = "✅ да" if u.get("purchased") else "❌ нет"
    step = STEP_LABELS.get(u.get("funnel_step"), u.get("funnel_step") or "—")

    return (
        f"👤 <b>{u['full_name']}</b>\n"
        f"🆔 <code>{u['tg_id']}</code> · {username}\n\n"
        f"📊 Пол/возраст: {u['sex']}, {u['age']} лет\n"
        f"⚖️ Вес/рост: {u['weight']} кг / {u['height']} см\n"
        f"🏃 Активность: {u['activity']}\n\n"
        f"📍 Последнее касание: {step}\n"
        f"⏰ Следующее: {fmt_ts(u.get('next_send_at'))}\n"
        f"🚀 В воронке с: {fmt_ts(u.get('enrolled_at'))}\n"
        f"🏁 Цепочка завершена: {'да' if u.get('funnel_done') else 'нет'}\n\n"
        f"💰 Купил: {paid}"
        + (f" ({fmt_ts(u.get('purchased_at'))})" if u.get("purchased") else "")
        + f"\n📅 Расчёт: {u['calculated_at']}"
    )


def _user_card_kb(tg_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Отправить блок вручную", callback_data=f"adm:send:{tg_id}")],
        [InlineKeyboardButton(text="🔁 Сбросить воронку", callback_data=f"adm:reset:{tg_id}")],
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="adm:menu")],
    ])


async def _show_card(target_message, tg_id):
    u = get_user(tg_id)
    if not u:
        await target_message.answer("❌ Пользователь не найден")
        return
    await target_message.answer(
        _user_card(u), parse_mode="HTML", reply_markup=_user_card_kb(tg_id)
    )


# /user <id>  — быстрый доступ к карточке
@router.message(Command("user"))
async def cmd_user(message: Message):
    if not is_admin(message):
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].lstrip("-").isdigit():
        await message.answer("Использование: <code>/user 123456789</code>", parse_mode="HTML")
        return
    await _show_card(message, int(parts[1]))


# ---- Поиск пользователя ----
@router.callback_query(F.data == "adm:find")
async def cb_find(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback):
        return
    await state.set_state(AdminState.finduser_wait)
    await callback.message.answer(
        "🔍 Пришли username, имя или ID для поиска:"
    )
    await callback.answer()


@router.message(AdminState.finduser_wait)
async def finduser_input(message: Message, state: FSMContext):
    if not is_admin(message):
        return
    await state.clear()
    query = message.text.strip().lstrip("@")
    users = find_users(query, limit=10)
    if not users:
        await message.answer("Ничего не найдено.")
        return
    if len(users) == 1:
        await _show_card(message, users[0]["tg_id"])
        return
    # несколько совпадений — список кнопок
    rows = []
    for u in users:
        uname = f"@{u['username']}" if u["username"] else u["full_name"]
        rows.append([InlineKeyboardButton(
            text=f"{u['full_name']} · {uname}",
            callback_data=f"adm:card:{u['tg_id']}"
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Меню", callback_data="adm:menu")])
    await message.answer(
        f"Найдено {len(users)}. Выбери:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("adm:card:"))
async def cb_card(callback: CallbackQuery):
    if not is_admin(callback):
        return
    tg_id = int(callback.data.split(":")[2])
    await _show_card(callback.message, tg_id)
    await callback.answer()


# ---- Ручная отправка блока ----
@router.callback_query(F.data.startswith("adm:send:"))
async def cb_send_pick(callback: CallbackQuery):
    if not is_admin(callback):
        return
    tg_id = int(callback.data.split(":")[2])
    rows = []
    for key in SEND_BY_KEY:
        rows.append([InlineKeyboardButton(
            text=STEP_LABELS.get(key, key),
            callback_data=f"adm:do_send:{tg_id}:{key}"
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Меню", callback_data="adm:menu")])
    await callback.message.answer(
        "Какой блок отправить этому пользователю?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:do_send:"))
async def cb_do_send(callback: CallbackQuery):
    if not is_admin(callback):
        return
    _, _, tg_id, key = callback.data.split(":")
    tg_id = int(tg_id)
    send_fn = SEND_BY_KEY.get(key)
    if not send_fn:
        await callback.answer("Неизвестный блок", show_alert=True)
        return
    try:
        await send_fn(callback.bot, tg_id)
        await callback.answer(f"Отправлено: {key}")
        await callback.message.answer(f"✅ <b>{key}</b> отправлен пользователю <code>{tg_id}</code>", parse_mode="HTML")
    except Exception as e:
        logger.error(f"ADMIN manual send {key} -> {tg_id}: {e}")
        await callback.answer("Ошибка отправки", show_alert=True)
        await callback.message.answer(f"❌ Не удалось отправить: {e}")


# ---- Сброс воронки ----
@router.callback_query(F.data.startswith("adm:reset:"))
async def cb_reset(callback: CallbackQuery):
    if not is_admin(callback):
        return
    tg_id = int(callback.data.split(":")[2])
    now = time.time()
    reset_funnel(tg_id, next_send_at=now + STEPS[0]["offset"], now=now)
    await callback.answer("Воронка сброшена")
    await callback.message.answer(
        f"🔁 Воронка пользователя <code>{tg_id}</code> сброшена в начало.\n"
        f"Следующее касание (тизер) уйдёт по расписанию.",
        parse_mode="HTML",
    )


# ============================================================
#  РАССЫЛКА (сегменты → контент → предпросмотр → подтверждение)
# ============================================================
def _segment_menu():
    rows = []
    for key, label in SEGMENT_LABELS.items():
        cnt = count_segment(key)
        rows.append([InlineKeyboardButton(
            text=f"{label} ({cnt})",
            callback_data=f"adm:bc_seg:{key}"
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Меню", callback_data="adm:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "adm:broadcast")
async def cb_broadcast(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback):
        return
    await state.clear()
    await callback.message.answer(
        "📢 <b>Рассылка</b>\n\nКому отправляем? Выбери сегмент:",
        parse_mode="HTML",
        reply_markup=_segment_menu(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:bc_seg:"))
async def cb_bc_segment(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback):
        return
    segment = callback.data.split(":")[2]
    cnt = count_segment(segment)
    if cnt == 0:
        await callback.answer("В этом сегменте никого нет", show_alert=True)
        return
    await state.set_state(AdminState.broadcast_wait)
    await state.update_data(segment=segment)
    await callback.message.answer(
        f"Сегмент: <b>{SEGMENT_LABELS.get(segment, segment)}</b> — {cnt} чел.\n\n"
        "Теперь пришли <b>само сообщение</b> для рассылки.\n"
        "Можно текст, фото, видео, документ — с любой разметкой и кнопками.\n"
        "Отправлю ровно то, что пришлёшь. Отмена — /admin",
        parse_mode="HTML",
    )
    await callback.answer()


def _confirm_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправить", callback_data="adm:bc_go")],
        [InlineKeyboardButton(text="✏️ Переписать", callback_data="adm:broadcast")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="adm:menu")],
    ])


@router.message(AdminState.broadcast_wait)
async def broadcast_input(message: Message, state: FSMContext):
    if not is_admin(message):
        return
    data = await state.get_data()
    segment = data.get("segment", "all")

    # Запоминаем источник: откуда копировать сообщение при рассылке.
    await state.update_data(
        src_chat_id=message.chat.id,
        src_message_id=message.message_id,
    )
    await state.set_state(AdminState.broadcast_confirm)

    cnt = count_segment(segment)

    # Предпросмотр: копируем сообщение обратно админу — это 1-в-1 то,
    # что увидят получатели.
    await message.answer("👀 <b>Предпросмотр сообщения:</b>", parse_mode="HTML")
    await message.bot.copy_message(
        chat_id=message.chat.id,
        from_chat_id=message.chat.id,
        message_id=message.message_id,
    )
    await message.answer(
        f"📨 Уйдёт сегменту <b>{SEGMENT_LABELS.get(segment, segment)}</b> — "
        f"<b>{cnt}</b> получателей.\n\nОтправляем?",
        parse_mode="HTML",
        reply_markup=_confirm_kb(),
    )


@router.callback_query(F.data == "adm:bc_go", AdminState.broadcast_confirm)
async def cb_bc_go(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback):
        return
    data = await state.get_data()
    await state.clear()

    segment = data.get("segment", "all")
    src_chat_id = data.get("src_chat_id")
    src_message_id = data.get("src_message_id")

    ids = get_segment_ids(segment)
    await callback.message.edit_reply_markup(reply_markup=None)
    progress = await callback.message.answer(
        f"⏳ Рассылаю {len(ids)} получателям..."
    )
    await callback.answer()

    sent, failed, blocked = 0, 0, 0
    for i, uid in enumerate(ids, 1):
        try:
            await callback.bot.copy_message(
                chat_id=uid,
                from_chat_id=src_chat_id,
                message_id=src_message_id,
            )
            sent += 1
        except TelegramForbiddenError:
            blocked += 1
        except Exception as e:
            failed += 1
            logger.warning(f"BROADCAST fail -> {uid}: {e}")
        # периодически обновляем прогресс
        if i % 25 == 0:
            try:
                await progress.edit_text(f"⏳ Отправлено {i}/{len(ids)}...")
            except Exception:
                pass
        await asyncio.sleep(config.SEND_THROTTLE)

    await progress.edit_text(
        "✅ <b>Рассылка завершена</b>\n\n"
        f"📨 Доставлено: <b>{sent}</b>\n"
        f"🚫 Заблокировали бота: <b>{blocked}</b>\n"
        f"⚠️ Прочие ошибки: <b>{failed}</b>",
        parse_mode="HTML",
    )


# ============================================================
#  ЗАБРОС СТАРЫХ ПОЛЬЗОВАТЕЛЕЙ В ВОРОНКУ
# ------------------------------------------------------------
#  Берём тех, кто в базе, но НИКОГДА не был в воронке
#  (enrolled_at IS NULL — пользовались ботом до её внедрения),
#  и ставим их в цепочку с выбранного касания.
#
#  Трюк с enrolled_at: чтобы выбранный блок ушёл сразу, а
#  следующие — с нормальными интервалами, мы выставляем
#  enrolled_at = now - offset(старт), funnel_step = шаг ПЕРЕД
#  стартом, next_send_at = now. Тогда worker сразу отправит
#  стартовый блок, а дальше всё спланируется штатно.
# ============================================================
BACKFILL_START_STEPS = ["block_1", "block_2", "block_3", "block_4"]


def _backfill_menu():
    cnt = count_segment("not_in_funnel")
    rows = [[InlineKeyboardButton(
        text=f"▶️ Начать с «{STEP_LABELS.get(k, k)}»"[:60],
        callback_data=f"adm:bf:{k}"
    )] for k in BACKFILL_START_STEPS]
    rows.append([InlineKeyboardButton(text="⬅️ Меню", callback_data="adm:menu")])
    return cnt, InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "adm:backfill")
async def cb_backfill(callback: CallbackQuery):
    if not is_admin(callback):
        return
    cnt, kb = _backfill_menu()
    if cnt == 0:
        await callback.answer("Старых пользователей вне воронки нет", show_alert=True)
        return
    await callback.message.answer(
        f"🆕 <b>Заброс старых пользователей в воронку</b>\n\n"
        f"Не были в воронке: <b>{cnt}</b> чел.\n\n"
        "С какого касания начать? Выбранный блок уйдёт им в ближайшую минуту, "
        "дальше — по обычному расписанию.",
        parse_mode="HTML",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:bf:"))
async def cb_backfill_confirm(callback: CallbackQuery):
    if not is_admin(callback):
        return
    start_key = callback.data.split(":")[2]
    if start_key not in OFFSET_BY_KEY:
        await callback.answer("Неизвестный блок", show_alert=True)
        return

    now = time.time()
    # enrolled_at сдвигаем назад так, чтобы стартовый блок был «уже пора»,
    # а последующие сохранили штатные интервалы.
    enrolled_at = now - OFFSET_BY_KEY[start_key]
    funnel_step = prev_step_key(start_key)  # шаг перед стартовым

    n = enroll_unenrolled(
        funnel_step=funnel_step,
        enrolled_at=enrolled_at,
        next_send_at=now,
    )
    await callback.answer("Готово")
    await callback.message.answer(
        f"✅ Заброшено в воронку: <b>{n}</b> чел.\n"
        f"Старт с «{STEP_LABELS.get(start_key, start_key)}».\n"
        f"Первый блок уйдёт в течение ~{config.SCHEDULER_INTERVAL} сек.",
        parse_mode="HTML",
    )


# /enroll_old — то же самое командой (по умолчанию с block_1)
@router.message(Command("enroll_old"))
async def cmd_enroll_old(message: Message):
    if not is_admin(message):
        return
    parts = message.text.split()
    start_key = parts[1] if len(parts) > 1 else "block_1"
    if start_key not in OFFSET_BY_KEY:
        await message.answer(
            "Использование: <code>/enroll_old block_1</code>\n"
            f"Доступно: {', '.join(BACKFILL_START_STEPS)}",
            parse_mode="HTML",
        )
        return
    now = time.time()
    n = enroll_unenrolled(
        funnel_step=prev_step_key(start_key),
        enrolled_at=now - OFFSET_BY_KEY[start_key],
        next_send_at=now,
    )
    await message.answer(
        f"✅ Заброшено в воронку: <b>{n}</b> чел. (старт с {start_key})",
        parse_mode="HTML",
    )


# ============================================================
#  ЛОГИ
# ------------------------------------------------------------
#  Хвост лог-файла прямо в Telegram + кнопка скачать весь файл.
#    /logs       — последние 40 строк
#    /logs 100   — последние 100 строк
#  Telegram-сообщение ограничено 4096 символами, поэтому длинный
#  хвост обрезаем с начала и добавляем пометку.
# ============================================================
TG_MSG_LIMIT = 4096
DEFAULT_LOG_LINES = 40


def _logs_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="adm:logs")],
        [InlineKeyboardButton(text="📎 Скачать файл целиком", callback_data="adm:logs_file")],
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="adm:menu")],
    ])


def _format_log_tail(lines: int) -> str:
    tail = read_log_tail(lines)
    if not tail.strip():
        return "📜 <b>Логи</b>\n\n<i>Файл логов пуст или ещё не создан.</i>"

    body = tail
    # Оставляем место под заголовок и теги <pre>.
    budget = TG_MSG_LIMIT - 120
    truncated = False
    if len(body) > budget:
        body = body[-budget:]
        truncated = True

    # Экранируем угловые скобки, чтобы HTML-парсер Telegram не падал на логах.
    body = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    header = f"📜 <b>Последние {lines} строк лога</b>"
    if truncated:
        header += " <i>(обрезано сверху)</i>"
    return f"{header}\n\n<pre>{body}</pre>"


@router.callback_query(F.data == "adm:logs")
async def cb_logs(callback: CallbackQuery):
    if not is_admin(callback):
        return
    text = _format_log_tail(DEFAULT_LOG_LINES)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=_logs_kb())
    except TelegramBadRequest:
        # «message is not modified» при повторном обновлении — игнорируем.
        await callback.message.answer(text, parse_mode="HTML", reply_markup=_logs_kb())
    await callback.answer()


@router.callback_query(F.data == "adm:logs_file")
async def cb_logs_file(callback: CallbackQuery):
    if not is_admin(callback):
        return
    if not LOG_FILE.exists():
        await callback.answer("Файл логов ещё не создан", show_alert=True)
        return
    await callback.message.answer_document(
        FSInputFile(str(LOG_FILE)),
        caption=f"📎 Полный лог: {LOG_FILE.name}",
    )
    await callback.answer()


@router.message(Command("logs"))
async def cmd_logs(message: Message):
    if not is_admin(message):
        return
    parts = message.text.split()
    lines = DEFAULT_LOG_LINES
    if len(parts) > 1 and parts[1].isdigit():
        lines = max(1, min(int(parts[1]), 1000))
    await message.answer(
        _format_log_tail(lines), parse_mode="HTML", reply_markup=_logs_kb()
    )


# ============================================================
#  СТАРАЯ КОМАНДА /database (оставляем для совместимости)
# ============================================================
@router.message(Command("database"))
async def database_command(message: Message):
    if not is_admin(message):
        return

    users_count = get_users_count()
    users = get_last_users(20)

    text = (
        f"📊 <b>Статистика Dolmyan Fit</b>\n\n"
        f"👥 Пользователей в базе: <b>{users_count}</b>\n\n"
        f"<b>Последние пользователи:</b>\n\n"
    )

    for user in users:
        username = (
            f"@{user['username']}"
            if user["username"]
            else "без username"
        )

        text += (
            f"👤 <b>{user['full_name']}</b>\n"
            f"🆔 <code>{user['tg_id']}</code>\n"
            f"📱 {username}\n"
            f"📅 {user['calculated_at']}\n\n"
        )

    await message.answer(text)
