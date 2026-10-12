#!/bin/sh

# IW03 — точка входа контейнера.
# Настраивает cron (расписание уже установлено в образе через
# `crontab /app/cronjob`) и запускает демон cron в foreground,
# чтобы контейнер оставался запущенным.

create_log_file() {
    echo "Creating log file..."
    touch /var/log/cron.log
    chmod 666 /var/log/cron.log
    echo "Log file created at /var/log/cron.log"
}

monitor_logs() {
    echo "=== Monitoring cron logs ==="
    tail -f /var/log/cron.log
}

run_cron() {
    echo "=== Starting cron daemon ==="
    exec cron -f
}

# Передаём переменные окружения контейнера (API_KEY, API_URL, TZ)
# cron-задачам: cron работает с минимальным окружением, а Debian
# cron читает переменные из /etc/environment.
env > /etc/environment
create_log_file
monitor_logs &
run_cron
