"""
Централизованная настройка логирования для всего бота.

Один вызов setup_logging() в самом начале run.py конфигурирует:
  • запись в файл logs/bot.log с ротацией (чтобы файл не рос бесконечно);
  • вывод в консоль (удобно при ручном запуске и в `journalctl`);
  • единый формат с датой, уровнем, модулем, функцией и номером строки;
  • перехват необработанных исключений в лог (а не только в stderr).

ВАЖНО: эта функция должна вызываться ДО импорта main/admin/payment,
иначе их модульные logging.basicConfig успеют навесить свой handler.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Папка с логами рядом с проектом: <project>/logs/
LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_FILE = LOG_DIR / "bot.log"

# Формат: 2026-06-12 14:00:01 | INFO | main:calc:164 | NEW USER: ...
LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s:%(funcName)s:%(lineno)d | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Сколько хранить: 5 файлов по 5 МБ = ~25 МБ истории.
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 5

_configured = False


def setup_logging(level: int = logging.INFO) -> Path:
    """Настроить корневой логгер. Возвращает путь к файлу логов.

    Повторный вызов безопасен — настройка применяется один раз.
    """
    global _configured
    if _configured:
        return LOG_FILE

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # Файл с ротацией
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    # Консоль / journalctl
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    root = logging.getLogger()
    root.setLevel(level)
    # Сносим возможные handler-ы от чужих basicConfig, чтобы не было дублей.
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # aiogram болтлив на DEBUG — оставляем INFO, но события апдейтов пишем.
    logging.getLogger("aiogram.event").setLevel(logging.INFO)
    # httpx/yookassa на INFO сыпят запросами — приглушаем до WARNING.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Перехват необработанных исключений в лог.
    def _excepthook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logging.getLogger("uncaught").critical(
            "Необработанное исключение", exc_info=(exc_type, exc_value, exc_tb)
        )

    sys.excepthook = _excepthook

    _configured = True
    logging.getLogger(__name__).info("Логирование настроено -> %s", LOG_FILE)
    return LOG_FILE


def read_log_tail(lines: int = 50) -> str:
    """Вернуть последние `lines` строк из файла логов (для админ-команды)."""
    if not LOG_FILE.exists():
        return ""
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-lines:])
    except Exception as e:  # noqa: BLE001
        return f"Не удалось прочитать лог: {e}"
