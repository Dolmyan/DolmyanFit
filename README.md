# Dolmyan Fit Bot

> Telegram bot for **@DolmyanFitBot** — a personal KBJU/calorie calculator with an
> automated warm-up funnel, YooKassa payments for a fitness guide, and a full admin panel.

🇬🇧 [English](#english) · 🇷🇺 [Русский](#русский)

---

## English

### Overview

A Telegram sales-funnel bot for a fitness mentor. A user sends their parameters
(sex, age, weight, height, activity), the bot calculates their daily calories and
macros (KBJU), then drips a multi-day warm-up sequence and offers a paid guide.
Purchases go through **YooKassa**; the guide PDF is delivered automatically.

### Features

- 🧮 **KBJU calculator** — daily calories, proteins, fats, carbs from user input.
- 🔥 **Warm-up funnel** — scheduled touches `block_0 … block_5` + teaser, persisted in
  the DB so nothing is lost on restart (overdue touches are re-sent after a reboot).
- 💳 **YooKassa payments** — auto-generated payment link, status check, PDF delivery.
- 🎓 **Post-purchase touch** — mentorship offer (`block_6`) 7 days after purchase.
- 🛠 **Admin panel** (`/admin`) — funnel stats, recent users, user search/cards,
  manual block sending, funnel reset, segmented broadcasts, backfilling old users.
- 📜 **File logging** — rotating `logs/bot.log`, last entries available via `/logs`.

### Tech stack

`Python 3.10+` · `aiogram 3.28` · `SQLite` · `YooKassa SDK` · `python-dotenv` · `systemd`

### Project structure

```
run.py              # entry point: sets up logging, DB, routers, funnel worker
main.py             # /start, KBJU calculation, funnel enrollment
funnel.py           # funnel texts, step config, send functions
scheduler.py        # background worker: sends due touches by schedule
payment.py          # YooKassa payment creation & verification
admin.py            # admin panel (stats, broadcast, logs, user cards)
config.py           # settings, schedule timings, TEST_MODE
logging_config.py   # centralized rotating file logging + log tail reader
database/db.py      # SQLite schema, migrations, queries
services/           # KBJU calculator
block_0 … block_4/  # carousel slides (slide_*.jpg)
deploy/             # systemd unit
DEPLOY.md           # step-by-step VPS deployment guide
```

### Setup

```bash
git clone https://github.com/Dolmyan/DolmyanFit.git
cd DolmyanFit
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# create .env with your values (see Configuration below)
.venv/bin/python run.py
```

### Configuration (`.env`)

| Variable | Description |
|---|---|
| `BOT_TOKEN` | Telegram bot token from [@BotFather](https://t.me/BotFather) |
| `YOOKASSA_SHOP_ID` | YooKassa shop ID |
| `YOOKASSA_SECRET_KEY` | YooKassa secret key (`live_…` for production) |
| `TEST_MODE` | `false` = production (delays in hours/days), `true` = test (whole funnel in ~1 min) |

> ⚠️ `TEST_MODE=true` compresses the entire funnel into seconds — **never** use it in
> production, or every user gets the whole sequence at once. Default is `false`.

`ADMIN_ID` is set in `config.py` (the admin's Telegram user id).

### Admin commands

| Command | Action |
|---|---|
| `/admin` | Open the admin panel (inline buttons) |
| `/user <id>` | Open a user card |
| `/logs [N]` | Last `N` log lines in chat (default 40, max 1000) + download button |
| `/enroll_old [block]` | Backfill users who predate the funnel |
| `/database` | Legacy stats command |

### Logging

- Written to `logs/bot.log`, rotated (5 files × 5 MB).
- Console / `journalctl` output mirrors the file.
- Admin can read the tail in Telegram via `/admin → 📜 Логи` or `/logs`.

### Deployment

Runs under `systemd` with auto-restart. See **[DEPLOY.md](DEPLOY.md)** for a full
VPS guide (migrating from an old version, stopping the old service, preserving the
real `users.db`, etc.).

---

## Русский

### Описание

Telegram-бот воронки продаж для фитнес-наставника. Пользователь отправляет свои
данные (пол, возраст, вес, рост, активность), бот считает суточную норму калорий и
КБЖУ, затем ведёт многодневную цепочку прогрева и предлагает платный гайд. Оплата —
через **ЮKassa**, PDF-гайд отправляется автоматически.

### Возможности

- 🧮 **Калькулятор КБЖУ** — калории, белки, жиры, углеводы по данным пользователя.
- 🔥 **Воронка прогрева** — касания по расписанию `block_0 … block_5` + тизер; прогресс
  хранится в БД, поэтому при перезапуске ничего не теряется (просроченные касания
  дошлются после рестарта).
- 💳 **Оплата через ЮKassa** — автогенерация ссылки, проверка статуса, выдача PDF.
- 🎓 **Касание после покупки** — предложение наставничества (`block_6`) через 7 дней.
- 🛠 **Админ-панель** (`/admin`) — статистика воронки, последние юзеры, поиск и карточки,
  ручная отправка блоков, сброс воронки, сегментированные рассылки, заброс старых юзеров.
- 📜 **Логи в файл** — ротация `logs/bot.log`, последние записи доступны через `/logs`.

### Стек

`Python 3.10+` · `aiogram 3.28` · `SQLite` · `YooKassa SDK` · `python-dotenv` · `systemd`

### Структура проекта

```
run.py              # точка входа: логирование, БД, роутеры, воркер воронки
main.py             # /start, расчёт КБЖУ, постановка в воронку
funnel.py           # тексты воронки, конфиг шагов, функции отправки
scheduler.py        # фоновый воркер: рассылка касаний по расписанию
payment.py          # создание и проверка платежей ЮKassa
admin.py            # админ-панель (статистика, рассылка, логи, карточки)
config.py           # настройки, тайминги расписания, TEST_MODE
logging_config.py   # централизованное логирование в файл + чтение хвоста
database/db.py      # схема SQLite, миграции, запросы
services/           # калькулятор КБЖУ
block_0 … block_4/  # слайды каруселей (slide_*.jpg)
deploy/             # systemd-юнит
DEPLOY.md           # пошаговая инструкция деплоя на VPS
```

### Установка

```bash
git clone https://github.com/Dolmyan/DolmyanFit.git
cd DolmyanFit
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# создать .env со своими значениями (см. Конфигурация ниже)
.venv/bin/python run.py
```

### Конфигурация (`.env`)

| Переменная | Описание |
|---|---|
| `BOT_TOKEN` | Токен бота от [@BotFather](https://t.me/BotFather) |
| `YOOKASSA_SHOP_ID` | ID магазина ЮKassa |
| `YOOKASSA_SECRET_KEY` | Секретный ключ ЮKassa (`live_…` для боевого режима) |
| `TEST_MODE` | `false` = боевой (задержки в часах/днях), `true` = тест (вся воронка за ~1 мин) |

> ⚠️ `TEST_MODE=true` сжимает всю воронку до секунд — **никогда** не используй на проде,
> иначе пользователь получит всю цепочку разом. По умолчанию `false`.

`ADMIN_ID` задаётся в `config.py` (Telegram-id администратора).

### Админ-команды

| Команда | Действие |
|---|---|
| `/admin` | Открыть админ-панель (inline-кнопки) |
| `/user <id>` | Открыть карточку пользователя |
| `/logs [N]` | Последние `N` строк лога в чат (по умолчанию 40, макс 1000) + кнопка скачать |
| `/enroll_old [block]` | Завести в воронку старых юзеров (до её внедрения) |
| `/database` | Старая команда статистики |

### Логи

- Пишутся в `logs/bot.log`, ротация (5 файлов × 5 МБ).
- Вывод в консоль / `journalctl` дублирует файл.
- Админ читает хвост прямо в Telegram: `/admin → 📜 Логи` или `/logs`.

### Деплой

Работает под `systemd` с автоперезапуском. Полная инструкция по развёртыванию на VPS
(миграция со старой версии, остановка старого сервиса, сохранение реальной `users.db`)
— в **[DEPLOY.md](DEPLOY.md)**.
