# Лабораторная работа №3 (IW03) — Task Scheduler (cron) в Docker

Контейнер с cron, который по расписанию запускает скрипт
`currency_exchange_rate.py` (IW02) для получения курса валют и
записывает вывод задач в файл `/var/log/cron.log`.

## Расписание задач

| Задача | Расписание | Строка cron |
| --- | --- | --- |
| Курс MDL → EUR за предыдущий день | ежедневно в 06:00 | `0 6 * * *` |
| Курс MDL → USD за предыдущую неделю | каждую пятницу в 17:00 | `0 17 * * 5` |

Дата запроса вычисляется при запуске: `$(date -d "yesterday" +%F)` и
`$(date -d "1 week ago" +%F)`. В crontab символ `%` экранируется
обратным слэшем (`\%`), поэтому в файле `cronjob` он записан как `+\%F`.

## Структура проекта

```
lab03_test/
├── currency_exchange_rate.py  # скрипт получения курса (из lab02)
├── requirements.txt           # зависимости Python (requests)
├── cronjob                    # расписание cron (две задачи)
├── entrypoint.sh              # настраивает окружение, лог и запускает cron
├── Dockerfile                 # сборка образа (python:3.12-slim + cron)
├── docker-compose.yml         # сборка и запуск контейнера (+ сервис API)
└── readme.md                  # этот файл
```

- **Dockerfile** — на базе официального образа `python:3.12-slim`
  доустанавливает `cron` и `tzdata`, ставит зависимости Python,
  копирует скрипт, `cronjob` и `entrypoint.sh`, устанавливает
  расписание командой `crontab /app/cronjob` и запускает
  `entrypoint.sh`.
- **cronjob** — две задачи cron; вывод каждой (`stdout` и `stderr`)
  перенаправляется в `/var/log/cron.log`.
- **entrypoint.sh** — создаёт `/var/log/cron.log`, сохраняет переменные
  окружения контейнера в `/etc/environment` (Debian cron передаёт их
  задачам — так `API_KEY` и `API_URL` доступны в cron), следит за логом
  (`tail -f`) и запускает демон `cron -f` в foreground.
- **docker-compose.yml** — собирает и запускает контейнер
  `currency-cron` с расписанием. API-сервис (lab02prep)
  запускается отдельно на хосте; из контейнера он доступен
  по адресу `http://host.docker.internal:8080/`
  (переменная `API_URL`).

## Как собрать и запустить

Подготовка: API-сервис курсов должен быть запущен на хосте
(проект-поддержка lab02prep):

```bash
cd ../lab02prep
docker compose up -d          # сервис на http://localhost:8080
```

Затем — контейнер с cron:

```bash
cd lab03_test
docker compose up -d --build
```

Переменные окружения (можно переопределить в `.env` или через
`API_KEY=... docker compose up`):

| Переменная | По умолчанию | Назначение |
| --- | --- | --- |
| `API_KEY` | `EXAMPLE_API_KEY` | ключ API сервиса курсов (как в lab02prep) |
| `API_URL` | `http://host.docker.internal:8080/` | адрес API-сервиса (lab02prep на хосте) |
| `TZ` | `Europe/Chisinau` | часовой пояс (cron в контейнере по UTC) |

Если удобнее держать API-сервис внутри этого compose-файла,
добавьте в него сервис из lab02prep и переключите `API_URL`
на `http://web/` (изнутри сети compose порт контейнера — 80):

```yaml
  web:
    image: php:8.3-apache
    container_name: php_apache
    ports:
      - "8080:80"
    volumes:
      - ../lab02prep/app:/var/www/html
    environment:
      API_KEY: ${API_KEY:-EXAMPLE_API_KEY}
    restart: unless-stopped
```

(при этом lab02prep на хосте нужно остановить — иначе
конфликтуют имя контейнера `php_apache` и порт 8080).

## Как проверить выполнение задач

```bash
# демон cron запущен, расписание установлено
docker compose logs -f currency-cron        # запуск cron и вывод задач
docker exec lab03-cron crontab -l           # установленное расписание
docker exec lab03-cron ps aux | grep cron   # процесс cron

# вывод задач в файле лога
docker exec lab03-cron cat /var/log/cron.log
```

Задачи запускаются в 06:00 и в пятницу в 17:00 — ждать долго, поэтому
для быстрой проверки можно временно добавить в `cronjob` строку
`* * * * * /bin/echo cron-works >> /var/log/cron.log 2>&1`, пересобрать
контейнер и через минуту убедиться в появлении записи в логе, после
чего вернуть исходное расписание.

## Примечания

- Данные сервиса доступны за период **2025-01-01 … 2025-09-15**; для
  дат вне периода скрипту передаётся `--allow-any-date` (сервис молча
  вернёт последний известный курс).
- Cron имеет минимальное окружение и `PATH`, поэтому в `cronjob`
  используются абсолютные пути (`/usr/local/bin/python3`, `/app/...`).
- Скрипт сохраняет JSON-файлы в `/app/data/` внутри контейнера.
