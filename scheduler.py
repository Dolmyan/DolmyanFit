"""
Фоновый воркер воронки.

Раз в SCHEDULER_INTERVAL секунд проверяет БД:
  1) кому пора отправить следующий шаг основной цепочки (block_0..block_5);
  2) кому пора отправить block_6 (наставничество) — через 7 дней после покупки.

Прогресс хранится в БД, поэтому при перезапуске бота ничего не теряется:
после рестарта все просроченные касания будут досланы.
"""

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

import config
from database.db import (
    get_due_users,
    advance_funnel,
    get_due_block6,
    mark_block6_sent,
)
from funnel import next_step_after, send_block_6

logger = logging.getLogger(__name__)


async def _process_main_chain(bot: Bot):
    """Отправить следующий шаг тем, у кого подошло время."""
    for user in get_due_users():
        tg_id = user["tg_id"]
        enrolled_at = user["enrolled_at"]
        current = user["funnel_step"]
        purchased = bool(user["purchased"])

        step = next_step_after(current)

        # цепочка закончилась
        if step is None:
            advance_funnel(tg_id, current, None, done=True)
            continue

        # пропускаем продающие/дожимающие шаги, если уже купил
        if purchased and step["skip_if_purchased"]:
            logger.info(f"SKIP {step['key']} for {tg_id} (purchased)")
            # двигаем указатель дальше, чтобы не застрять на этом шаге
            following = next_step_after(step["key"])
            if following is None:
                advance_funnel(tg_id, step["key"], None, done=True)
            else:
                advance_funnel(
                    tg_id, step["key"], enrolled_at + following["offset"]
                )
            continue

        # отправляем шаг
        try:
            await step["send"](bot, tg_id)
            logger.info(f"SENT {step['key']} -> {tg_id}")
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            # пользователь заблокировал бота / чат недоступен — снимаем с воронки
            logger.warning(f"DELIVERY FAIL {step['key']} -> {tg_id}: {e}; dropping")
            advance_funnel(tg_id, step["key"], None, done=True)
            continue
        except Exception as e:
            logger.error(f"SEND ERROR {step['key']} -> {tg_id}: {e}")
            # не двигаем указатель — попробуем снова на следующем тике
            continue

        # планируем следующий шаг
        following = next_step_after(step["key"])
        if following is None:
            advance_funnel(tg_id, step["key"], None, done=True)
        else:
            advance_funnel(tg_id, step["key"], enrolled_at + following["offset"])

        await asyncio.sleep(config.SEND_THROTTLE)


async def _process_block6(bot: Bot):
    """Отправить block_6 (наставничество) купившим, у кого прошло 7 дней."""
    for user in get_due_block6():
        tg_id = user["tg_id"]
        try:
            await send_block_6(bot, tg_id)
            mark_block6_sent(tg_id)
            logger.info(f"SENT block_6 -> {tg_id}")
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            logger.warning(f"DELIVERY FAIL block_6 -> {tg_id}: {e}; marking sent")
            mark_block6_sent(tg_id)
        except Exception as e:
            logger.error(f"SEND ERROR block_6 -> {tg_id}: {e}")
            continue

        await asyncio.sleep(config.SEND_THROTTLE)


async def funnel_worker(bot: Bot):
    """Бесконечный цикл воркера. Запускается как фоновая задача в run.py."""
    logger.info(
        f"FUNNEL WORKER STARTED (interval={config.SCHEDULER_INTERVAL}s, "
        f"TEST_MODE={config.TEST_MODE})"
    )
    while True:
        try:
            await _process_main_chain(bot)
            await _process_block6(bot)
        except Exception as e:
            logger.error(f"WORKER LOOP ERROR: {e}")
        await asyncio.sleep(config.SCHEDULER_INTERVAL)
