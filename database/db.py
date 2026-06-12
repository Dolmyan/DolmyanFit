import sqlite3
import time

DB = "users.db"


# Колонки воронки, которые мы добавляем к существующей таблице users.
# Формат: имя -> SQL-определение (тип + DEFAULT).
FUNNEL_COLUMNS = {
    # момент старта воронки (unix-время, секунды); NULL = не в воронке
    "enrolled_at": "REAL",
    # последний УЖЕ отправленный шаг воронки ("block_0", "teaser", ...)
    "funnel_step": "TEXT",
    # unix-время, когда нужно отправить следующий шаг; NULL = нечего слать
    "next_send_at": "REAL",
    # 1 = основная цепочка (block_0..block_5) завершена
    "funnel_done": "INTEGER DEFAULT 0",
    # 1 = пользователь купил гайд
    "purchased": "INTEGER DEFAULT 0",
    # unix-время покупки
    "purchased_at": "REAL",
    # unix-время, когда отправить block_6 (наставничество); NULL = не запланирован
    "block6_at": "REAL",
    # 1 = block_6 уже отправлен
    "block6_sent": "INTEGER DEFAULT 0",
}


def _connect():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users(
            tg_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            sex TEXT,
            age INTEGER,
            weight REAL,
            height REAL,
            activity INTEGER,
            calculated_at TEXT
        )
    """)

    # --- Миграция: добавляем колонки воронки, если их ещё нет ---
    cur.execute("PRAGMA table_info(users)")
    existing = {row[1] for row in cur.fetchall()}
    for name, definition in FUNNEL_COLUMNS.items():
        if name not in existing:
            cur.execute(f"ALTER TABLE users ADD COLUMN {name} {definition}")

    conn.commit()
    conn.close()


# ============================================================
#  ВОРОНКА: запись прогресса и выборка тех, кому пора слать
# ============================================================

def enroll_user(tg_id, first_step, next_send_at, now=None):
    """Поставить пользователя в начало воронки.

    first_step   — шаг, который уже отправлен прямо сейчас (обычно "block_0")
    next_send_at — unix-время следующего касания
    """
    if now is None:
        now = time.time()

    conn = _connect()
    cur = conn.cursor()
    cur.execute("""
        UPDATE users
        SET enrolled_at = ?,
            funnel_step = ?,
            next_send_at = ?,
            funnel_done = 0,
            block6_sent = 0
        WHERE tg_id = ?
    """, (now, first_step, next_send_at, tg_id))
    conn.commit()
    conn.close()


def get_due_users(now=None):
    """Пользователи, которым пора отправить следующий шаг основной цепочки."""
    if now is None:
        now = time.time()

    conn = _connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM users
        WHERE funnel_done = 0
          AND next_send_at IS NOT NULL
          AND next_send_at <= ?
        ORDER BY next_send_at ASC
    """, (now,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def advance_funnel(tg_id, new_step, next_send_at, done=False):
    """Зафиксировать, что new_step отправлен, и запланировать следующий.

    next_send_at = None  -> больше нечего слать в основной цепочке
    done = True          -> основная цепочка завершена
    """
    conn = _connect()
    cur = conn.cursor()
    cur.execute("""
        UPDATE users
        SET funnel_step = ?,
            next_send_at = ?,
            funnel_done = ?
        WHERE tg_id = ?
    """, (new_step, next_send_at, 1 if done else 0, tg_id))
    conn.commit()
    conn.close()


def mark_purchased(tg_id, block6_at, now=None):
    """Отметить покупку и запланировать block_6 (наставничество).

    Дожим block_5 при этом перестанет отправляться —
    scheduler проверяет purchased перед отправкой block_5.
    """
    if now is None:
        now = time.time()

    conn = _connect()
    cur = conn.cursor()
    cur.execute("""
        UPDATE users
        SET purchased = 1,
            purchased_at = ?,
            block6_at = ?
        WHERE tg_id = ?
    """, (now, block6_at, tg_id))
    conn.commit()
    conn.close()


def is_purchased(tg_id):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT purchased FROM users WHERE tg_id = ?", (tg_id,))
    row = cur.fetchone()
    conn.close()
    return bool(row and row[0])


def get_due_block6(now=None):
    """Купившие, которым пора отправить block_6 (наставничество)."""
    if now is None:
        now = time.time()

    conn = _connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM users
        WHERE purchased = 1
          AND block6_sent = 0
          AND block6_at IS NOT NULL
          AND block6_at <= ?
        ORDER BY block6_at ASC
    """, (now,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def mark_block6_sent(tg_id):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("UPDATE users SET block6_sent = 1 WHERE tg_id = ?", (tg_id,))
    conn.commit()
    conn.close()


def save_user(
    tg_id,
    username,
    full_name,
    sex,
    age,
    weight,
    height,
    activity,
    calculated_at
):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("""
        INSERT OR REPLACE INTO users (
            tg_id,
            username,
            full_name,
            sex,
            age,
            weight,
            height,
            activity,
            calculated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        tg_id,
        username,
        full_name,
        sex,
        age,
        weight,
        height,
        activity,
        calculated_at
    ))

    conn.commit()
    conn.close()


def get_users_count():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()[0]

    conn.close()

    return count


def get_last_users(limit=20):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM users
        ORDER BY rowid DESC
        LIMIT ?
    """, (limit,))

    users = [dict(row) for row in cur.fetchall()]

    conn.close()

    return users


# ============================================================
#  АДМИН-АНАЛИТИКА
# ============================================================

def get_funnel_stats():
    """Сводка по воронке: сколько людей на каждом шаге, покупки, выручка-метрики."""
    conn = _connect()
    cur = conn.cursor()

    stats = {}

    # всего пользователей
    cur.execute("SELECT COUNT(*) FROM users")
    stats["total"] = cur.fetchone()[0]

    # в активной воронке (запущена, не завершена)
    cur.execute("""
        SELECT COUNT(*) FROM users
        WHERE enrolled_at IS NOT NULL AND funnel_done = 0
    """)
    stats["active"] = cur.fetchone()[0]

    # завершили основную цепочку
    cur.execute("SELECT COUNT(*) FROM users WHERE funnel_done = 1")
    stats["done"] = cur.fetchone()[0]

    # купили
    cur.execute("SELECT COUNT(*) FROM users WHERE purchased = 1")
    stats["purchased"] = cur.fetchone()[0]

    # распределение по последнему отправленному шагу
    cur.execute("""
        SELECT funnel_step, COUNT(*) AS c
        FROM users
        WHERE funnel_step IS NOT NULL
        GROUP BY funnel_step
    """)
    stats["by_step"] = {row["funnel_step"]: row["c"] for row in cur.fetchall()}

    conn.close()
    return stats


def get_user(tg_id):
    """Полная карточка одного пользователя или None."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def find_users(query, limit=20):
    """Поиск по username, full_name или tg_id (частичное совпадение)."""
    conn = _connect()
    cur = conn.cursor()
    like = f"%{query}%"
    cur.execute("""
        SELECT * FROM users
        WHERE username LIKE ?
           OR full_name LIKE ?
           OR CAST(tg_id AS TEXT) LIKE ?
        ORDER BY rowid DESC
        LIMIT ?
    """, (like, like, like, limit))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_all_user_ids():
    """Все tg_id — для массовой рассылки."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT tg_id FROM users")
    ids = [row[0] for row in cur.fetchall()]
    conn.close()
    return ids


# Сегменты аудитории для рассылки: ключ -> SQL-условие WHERE.
SEGMENT_SQL = {
    "all":           "1=1",
    "purchased":     "purchased = 1",
    "not_purchased": "(purchased = 0 OR purchased IS NULL)",
    "active":        "enrolled_at IS NOT NULL AND funnel_done = 0",
    "done":          "funnel_done = 1",
    "not_in_funnel": "enrolled_at IS NULL",
}


def get_segment_ids(segment):
    """tg_id пользователей в заданном сегменте."""
    where = SEGMENT_SQL.get(segment, "1=1")
    conn = _connect()
    cur = conn.cursor()
    cur.execute(f"SELECT tg_id FROM users WHERE {where}")
    ids = [row[0] for row in cur.fetchall()]
    conn.close()
    return ids


def count_segment(segment):
    """Сколько пользователей в сегменте."""
    where = SEGMENT_SQL.get(segment, "1=1")
    conn = _connect()
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM users WHERE {where}")
    n = cur.fetchone()[0]
    conn.close()
    return n


def enroll_unenrolled(funnel_step, enrolled_at, next_send_at):
    """Завести в воронку всех, кто ещё ни разу в ней не был (enrolled_at IS NULL).

    Используется для «заброса» старых пользователей, появившихся
    до внедрения воронки. Возвращает число затронутых строк.
    """
    conn = _connect()
    cur = conn.cursor()
    cur.execute("""
        UPDATE users
        SET enrolled_at = ?,
            funnel_step = ?,
            next_send_at = ?,
            funnel_done = 0
        WHERE enrolled_at IS NULL
    """, (enrolled_at, funnel_step, next_send_at))
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n


def reset_funnel(tg_id, next_send_at, now=None):
    """Сбросить воронку пользователя в начало (block_0 уже как бы отправлен).

    Используется админ-командой для повторного прогона цепочки.
    Покупку НЕ трогаем.
    """
    if now is None:
        now = time.time()
    conn = _connect()
    cur = conn.cursor()
    cur.execute("""
        UPDATE users
        SET enrolled_at = ?,
            funnel_step = 'block_0',
            next_send_at = ?,
            funnel_done = 0
        WHERE tg_id = ?
    """, (now, next_send_at, tg_id))
    conn.commit()
    conn.close()
    return cur.rowcount




