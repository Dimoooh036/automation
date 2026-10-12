# IW03 — образ контейнера с cron для автоматического запуска
# скрипта получения курса валют (currency_exchange_rate.py, IW02).
#
# База — официальный образ Python (на Debian): Python уже есть,
# cron доустанавливается пакетом.
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Chisinau \
    API_URL=http://localhost:8080/

# cron — планировщик задач; tzdata — часовой пояс (MDL: Europe/Chisinau);
# procps — утилиты ps/top для проверки работы cron внутри контейнера
RUN apt-get update \
    && apt-get install -y --no-install-recommends cron tzdata procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# зависимости Python (requests)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# скрипт, файл расписания и точка входа
COPY currency_exchange_rate.py ./
COPY cronjob ./cronjob
COPY entrypoint.sh /usr/local/bin/entrypoint.sh

# устанавливаем расписание в crontab пользователя root,
# делаем entrypoint исполняемым и готовим файл лога
RUN chmod +x /usr/local/bin/entrypoint.sh \
    && crontab /app/cronjob \
    && touch /var/log/cron.log

# cron в foreground держит контейнер в рабочем состоянии
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
