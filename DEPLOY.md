# Деплой Dolmyan Fit на VPS

Бот: Telegram (aiogram 3) + воронка прогрева + оплата ЮKassa + SQLite + админ-панель.
Запуск под `systemd`, автоперезапуск, логи в файл с ротацией.

---

## 0. Что важно знать перед деплоем

На сервере **уже работает старая версия бота**. Новая сильно отличается
(появилась воронка, оплата, новые колонки в БД). Поэтому:

1. **Нельзя запускать два бота с одним и тем же `BOT_TOKEN` одновременно** —
   Telegram отдаёт апдейты только одному поллингу, будет конфликт
   (`TelegramConflictError`). Старую версию нужно **остановить** перед запуском новой.
2. **Базу `users.db` с реальными пользователями нельзя перезаписывать** локальной.
   Новая схема добавляет колонки воронки автоматически (`init_db()` делает
   `ALTER TABLE` идемпотентно) — старые пользователи сохранятся, у них просто
   появятся пустые поля воронки. Старых юзеров потом можно «забросить» в воронку
   через админку (кнопка «🆕 Старые юзеры → в воронку»).
3. **`TEST_MODE` на проде должен быть `false`.** В тестовом режиме вся воронка
   рассылается за секунды. По умолчанию теперь `false`, но проверь `.env`.

---

## 1. Подготовка сервера (один раз)

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip git
# отдельный пользователь под бота (без sudo) — безопаснее
sudo useradd -m -d /opt/dolmyanfit -s /bin/bash dolmyan
```

## 2. Залить код

Вариант A — через git (рекомендуется, если заведёшь репозиторий):
```bash
sudo -u dolmyan -i
cd /opt/dolmyanfit
git clone <URL_РЕПО> .
```

Вариант B — скопировать с локальной машины (rsync, БЕЗ .venv/.env/logs/*.db):
```bash
rsync -av --exclude '.venv' --exclude '.env' --exclude 'logs' \
      --exclude '__pycache__' --exclude '*.db' \
      ./ user@SERVER:/opt/dolmyanfit/
```
> `*.db` исключён намеренно — на сервере используем боевую базу, а не локальную.
> Картинки слайдов (`block_0..block_4/slide_*.jpg`) и `guide.pdf` — нужны, их копируем.

## 3. Виртуальное окружение и зависимости

```bash
cd /opt/dolmyanfit
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

## 4. Конфигурация `.env`

```bash
cp .env.example .env
nano .env   # вставить BOT_TOKEN, YOOKASSA_*, TEST_MODE=false
```

## 5. База данных

- Если у старой версии база лежит на том же сервере — **скопируй её** в проект:
  ```bash
  cp /путь/к/старой/users.db /opt/dolmyanfit/users.db
  ```
  При первом запуске `init_db()` сам добавит недостающие колонки воронки.
- Если базы нет — она создастся пустой автоматически.

В обоих случаях перед запуском сделай бэкап:
```bash
cp users.db users.db.bak.$(date +%F)
```

## 6. Остановить старую версию

Найди и останови старый процесс/сервис (пример для systemd):
```bash
sudo systemctl stop <старый_сервис>
sudo systemctl disable <старый_сервис>
# либо, если запускался вручную: pkill -f 'старый_скрипт.py'
```
Убедись, что со старым токеном больше ничего не поллит.

## 7. Установить и запустить новый сервис

```bash
sudo cp /opt/dolmyanfit/deploy/dolmyanfit.service /etc/systemd/system/
# при необходимости поправь User/WorkingDirectory/ExecStart в юните
sudo systemctl daemon-reload
sudo systemctl enable --now dolmyanfit
sudo systemctl status dolmyanfit
```

## 8. Проверка

```bash
# системные логи сервиса
journalctl -u dolmyanfit -f
# логи приложения (то же, что отдаёт админка)
tail -f /opt/dolmyanfit/logs/bot.log
```
В Telegram: отправь боту `/start`, проверь расчёт КБЖУ. Затем `/admin` →
кнопка «📜 Логи» или команда `/logs 100`.

---

## Обновление новой версии в будущем

```bash
cd /opt/dolmyanfit
git pull                    # или rsync
.venv/bin/pip install -r requirements.txt
sudo systemctl restart dolmyanfit
```

## Полезные команды

| Действие | Команда |
|---|---|
| Перезапуск | `sudo systemctl restart dolmyanfit` |
| Остановка | `sudo systemctl stop dolmyanfit` |
| Статус | `sudo systemctl status dolmyanfit` |
| Логи сервиса | `journalctl -u dolmyanfit -f` |
| Логи бота | `tail -f logs/bot.log` |
| Логи в Telegram | `/logs` или `/logs 200` (только админ) |

## Логи

- Файл: `logs/bot.log`, ротация 5 файлов × 5 МБ (`bot.log`, `bot.log.1`, …).
- Команда `/logs [N]` и кнопка «📜 Логи» в `/admin` — последние строки прямо в чат,
  плюс кнопка «📎 Скачать файл целиком».
