#!/usr/bin/env python3
"""
IW02 / лабораторная работа №2 — получение курса валюты по API.

Скрипт обращается к сервису курсов валют (проект-поддержка из
`lab02prep`, по умолчанию http://localhost:8080), получает курс одной
валюты по отношению к другой на заданную дату и сохраняет ответ
в JSON-файл в директории `data` корня проекта.

Контракт API (наблюдается в исходниках сервиса, app/index.php):
  * список валют  — GET  /?currencies   + POST key=<API_KEY>
  * курс валюты  — GET  /?from=USD&to=EUR&date=YYYY-MM-DD + POST key=<API_KEY>
  * ответ всегда имеет HTTP 200, признак ошибки — непустое поле "error":
        {"error":"","data":{"from":"USD","to":"EUR","rate":1.08,"date":"2025-03-17"}}
        {"error":"Invalid API key","data":[]}
  * коды валют принимаются только в верхнем регистре (regexp ^[A-Z]{3}$),
  * дата — строго в формате YYYY-MM-DD (иначе сервис падает с HTML-ошибкой).

Примеры запуска:
    python currency_exchange_rate.py USD EUR 2025-03-17
    python currency_exchange_rate.py --list-currencies
    python currency_exchange_rate.py USD RON 2025-01-01 --verbose

Коды возврата:
    0 — курс получен и сохранён;
    1 — ошибка обращения к API, сети или сохранения файла;
    2 — некорректные аргументы командной строки.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover - зависимость не установлена
    sys.exit(
        "Ошибка: не найдена библиотека 'requests'.\n"
        "Установите зависимости командой: pip install -r requirements.txt"
    )


# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

LOG_FILE_NAME = "error.log"  # журнал ошибок в корне проекта
DATA_DIR_NAME = "data"  # каталог с JSON-файлами в корне проекта

DEFAULT_API_URL = "http://localhost:8080/"
DEFAULT_API_KEY = os.environ.get("API_KEY", "EXAMPLE_API_KEY")
DEFAULT_TIMEOUT = 10.0  # таймаут HTTP-запроса, секунды
DEFAULT_RETRIES = 3  # количество попыток при сетевых сбоях
RETRY_BACKOFF = 1.0  # базовая пауза между попытками, секунды

#: Валютный код: ровно три буквы (регистр приводим к верхнему).
CURRENCY_PATTERN = re.compile(r"^[A-Za-z]{3}$")
#: Дата запроса: строго YYYY-MM-DD — такой формат ждёт сервис.
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: Период, за который в сервисе есть реальные данные (файл app/data.json).
#: За пределами этого диапазона сервис молча подставляет последний известный
#: курс, поэтому такие даты отклоняются по умолчанию.
DATA_PERIOD_START = date(2025, 1, 1)
DATA_PERIOD_END = date(2025, 9, 15)

LOGGER = logging.getLogger("currency_exchange_rate")


# ---------------------------------------------------------------------------
# Исключения
# ---------------------------------------------------------------------------


class CurrencyExchangeError(Exception):
    """Базовая ошибка работы скрипта (все ошибки наследуются от неё)."""


class ValidationError(CurrencyExchangeError):
    """Некорректные входные данные: валюта, дата, адрес API."""


class ApiError(CurrencyExchangeError):
    """Сервис ответил ошибкой или вернул неожиданные данные."""


class NetworkError(CurrencyExchangeError):
    """Не удалось связаться с сервисом (таймаут, отказ в соединении)."""


class StorageError(CurrencyExchangeError):
    """Не удалось подготовить каталог или записать JSON-файл."""


# ---------------------------------------------------------------------------
# Пути и журналирование
# ---------------------------------------------------------------------------


def find_project_root() -> Path:
    """
    Возвращает корень проекта (родительский каталог `lab02`).

    Ищем вверх от каталога скрипта директорию с `.git` — это признак корня
    репозитория; запасной вариант — `README.md`. Так каталоги `data` и файл
    `error.log` создаются именно в корне проекта, а не рядом со скриптом,
    даже если структура репозитория изменится.

    Сам каталог скрипта корнем не считается: в нём лежит собственный
    `readme.md`, который на Windows (регистронезависимая ФС) совпал бы
    с признаком корня проекта.
    """
    current = Path(__file__).resolve().parent
    ancestors = list(current.parents)  # родители скрипта, без него самого
    for candidate in ancestors:
        if (candidate / ".git").exists():
            return candidate
    for candidate in ancestors:
        if (candidate / "README.md").is_file():
            return candidate
    return current.parent


def setup_console() -> None:
    """
    Переводит потоки вывода консоли в UTF-8.

    По умолчанию Windows использует для консоли однобайтовую кодировку
    (cp1251/cp866), где нет, например, символа «→». Без этого вывод
    падал бы с UnicodeEncodeError. `errors="replace"` гарантирует, что
    вывод не упадёт даже в консоли, не поддерживающей UTF-8.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)  # Python 3.7+
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):  # pragma: no cover - экзотические терминалы
            pass


def setup_logging(project_root: Path, verbose: bool = False) -> Path:
    """
    Настраивает вывод: ошибки идут в консоль и в `error.log`,
    остальные сообщения — только в консоль (в файл — с ключом `--verbose`).

    Возвращает путь к файлу журнала.
    """
    log_path = project_root / LOG_FILE_NAME
    file_level = logging.INFO if verbose else logging.WARNING

    LOGGER.setLevel(logging.DEBUG)
    LOGGER.handlers.clear()
    LOGGER.propagate = False  # сообщения не дублируются корневым логгером

    console = logging.StreamHandler(stream=sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(message)s"))

    # delay=True: файл создаётся только когда действительно есть что писать.
    file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8", delay=True)
    file_handler.setLevel(file_level)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s")
    )

    LOGGER.addHandler(console)
    LOGGER.addHandler(file_handler)
    return log_path


# ---------------------------------------------------------------------------
# Разбор и проверка аргументов командной строки
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Разбирает аргументы командной строки."""
    parser = argparse.ArgumentParser(
        prog="currency_exchange_rate.py",
        description=(
            "Получает курс валюты на заданную дату через API сервиса "
            "и сохраняет ответ в JSON-файл каталога data."
        ),
        epilog=(
            "Примеры:\n"
            "  %(prog)s USD EUR 2025-03-17\n"
            "  %(prog)s --list-currencies\n"
            "  %(prog)s EUR MDL 2025-09-15 --verbose"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "base",
        nargs="?",
        help="базовая валюта (курс этой валюты), например USD",
    )
    parser.add_argument(
        "quote",
        nargs="?",
        help="целевая валюта (к курсу этой валюты приводим base), например EUR",
    )
    parser.add_argument(
        "date",
        nargs="?",
        help="дата курса в формате YYYY-MM-DD (данные доступны "
        f"за {DATA_PERIOD_START} — {DATA_PERIOD_END})",
    )
    parser.add_argument(
        "--list-currencies",
        action="store_true",
        help="показать список валют, поддерживаемых сервисом, и выйти",
    )
    parser.add_argument(
        "-u",
        "--api-url",
        default=DEFAULT_API_URL,
        help=f"адрес API-сервиса (по умолчанию {DEFAULT_API_URL})",
    )
    parser.add_argument(
        "-k",
        "--api-key",
        default=DEFAULT_API_KEY,
        help="ключ API (по умолчанию берётся из переменной окружения API_KEY)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"таймаут запроса в секундах (по умолчанию {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=DEFAULT_RETRIES,
        help=f"число попыток при сетевых сбоях (по умолчанию {DEFAULT_RETRIES})",
    )
    parser.add_argument(
        "--allow-any-date",
        action="store_true",
        help=(
            "разрешить даты вне периода данных "
            f"{DATA_PERIOD_START} — {DATA_PERIOD_END}"
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="писать в error.log не только ошибки, но и все события",
    )
    return parser.parse_args(argv)


def validate_currency(value: str | None, argument_name: str) -> str:
    """
    Проверяет код валюты и возвращает его в верхнем регистре.

    Сервис принимает только заглавные буквы, поэтому `usd` нужно
    преобразовать в `USD` до отправки запроса.
    """
    if value is None:
        raise ValidationError(f"Не указан аргумент {argument_name} (код валюты).")

    code = value.strip().upper()
    if not CURRENCY_PATTERN.match(code):
        raise ValidationError(
            f"Некорректный код валюты '{value}': ожидается три буквы, например USD."
        )
    return code


def validate_date(value: str | None, allow_any_date: bool = False) -> date:
    """Проверяет дату: формат YYYY-MM-DD и принадлежность периоду данных."""
    if value is None:
        raise ValidationError("Не указан аргумент date (дата в формате YYYY-MM-DD).")

    raw = value.strip()
    if not DATE_PATTERN.match(raw):
        # Отдельно предупреждаем о перепутанных местах: 17-03-2025 сервис не примет.
        hint = ""
        if re.match(r"^\d{2}-\d{2}-\d{4}$", raw):
            hint = " Возможно, имелось в виду YYYY-MM-DD (например, 2025-03-17)?"
        raise ValidationError(
            f"Некорректная дата '{value}': ожидается формат YYYY-MM-DD.{hint}"
        )

    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:  # например, 2025-02-30
        raise ValidationError(f"Такой даты не существует: '{value}'.") from exc

    if not allow_any_date and not DATA_PERIOD_START <= parsed <= DATA_PERIOD_END:
        raise ValidationError(
            f"Дата {parsed} выходит за период данных "
            f"({DATA_PERIOD_START} — {DATA_PERIOD_END}). "
            "Сервис подставил бы последний известный курс. "
            "Укажите дату из периода или разрешите --allow-any-date."
        )
    return parsed


def validate_connection(args: argparse.Namespace) -> ApiConfig:
    """
    Проверяет параметры подключения к API.

    Вызывается до любого сетевого запроса, поэтому некорректный адрес,
    пустой ключ или бессмысленные таймаут/число попыток отсекаются сразу.
    """
    url = args.api_url.strip()
    if not url:
        raise ValidationError("Не указан адрес API (--api-url).")
    if not url.startswith(("http://", "https://")):
        raise ValidationError(
            f"Некорректный адрес API '{args.api_url}': ожидается http:// или https://."
        )

    if args.api_key is None or not args.api_key.strip():
        raise ValidationError(
            "Не указан ключ API (--api-key или переменная окружения API_KEY)."
        )

    if args.timeout <= 0:
        raise ValidationError(f"Таймаут должен быть больше нуля, получено {args.timeout}.")
    if args.retries < 1:
        raise ValidationError(
            f"Число попыток должно быть не меньше 1, получено {args.retries}."
        )

    return ApiConfig(
        base_url=url,
        api_key=args.api_key.strip(),
        timeout=args.timeout,
        retries=args.retries,
    )


def validate_request_args(args: argparse.Namespace) -> tuple[str, str, date]:
    """
    Проверяет параметры самого запроса: коды валют и дату.

    Возвращает нормализованный набор (base, quote, date).
    """
    base = validate_currency(args.base, "base")
    quote = validate_currency(args.quote, "quote")
    if base == quote:
        raise ValidationError(
            f"Базовая и целевая валюты совпадают ({base}): обмен не требуется."
        )

    requested_date = validate_date(args.date, allow_any_date=args.allow_any_date)
    return base, quote, requested_date


# ---------------------------------------------------------------------------
# Работа с API
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ApiConfig:
    """Параметры подключения к сервису."""

    base_url: str
    api_key: str
    timeout: float = DEFAULT_TIMEOUT
    retries: int = DEFAULT_RETRIES

    @property
    def endpoint(self) -> str:
        """Адрес API без завершающего слэша."""
        return self.base_url.rstrip("/") + "/"


def _log_api_error(message: str) -> ApiError:
    """Пишет сообщение в журнал и возвращает исключение с тем же текстом."""
    LOGGER.error(message)
    return ApiError(message)


def _request(
    session: requests.Session,
    config: ApiConfig,
    params: dict[str, str],
    description: str,
) -> Any:
    """
    Выполняет запрос к сервису и возвращает разобранное поле `data`.

    Сервис всегда отвечает кодом 200, поэтому признаком ошибки служит
    непустое поле `error` в теле ответа. Ошибки сети повторяются
    `config.retries` раз с нарастающей паузой.
    """
    url = config.endpoint
    cause = "причина неизвестна"

    for attempt in range(1, config.retries + 1):
        try:
            response = session.post(
                url,
                params=params,  # GET-параметры
                data={"key": config.api_key},  # POST-данные: ключ API
                timeout=config.timeout,
            )
        except requests.Timeout:
            cause = f"превышено время ожидания ответа ({config.timeout} с)"
        except requests.ConnectionError as exc:
            cause = (
                "не удалось подключиться — проверьте, что сервис запущен "
                f"(docker compose up -d); код: {_short_body(str(exc), 160)}"
            )
        except requests.RequestException as exc:
            # Прочие сетевые ошибки повторять бессмысленно.
            raise _log_api_error(
                f"{description}: сетевая ошибка — {_short_body(str(exc), 200)}"
            ) from exc
        else:
            return _parse_response(response, description)

        LOGGER.warning(
            "%s: %s (попытка %d из %d)", description, cause, attempt, config.retries
        )
        if attempt < config.retries:
            time.sleep(RETRY_BACKOFF * attempt)  # 1 с, 2 с, 3 с ...

    raise _log_api_error(
        f"{description}: исчерпаны все попытки запроса. Последняя причина: {cause}"
    )


def _parse_response(response: requests.Response, description: str) -> Any:
    """
    Проверяет HTTP-ответ и возвращает поле `data`.

    Отдельно обрабатываются: неуспешный HTTP-код, не-JSON ответ
    (например, HTML-страница с ошибкой PHP) и заполненное поле `error`.
    """
    if response.status_code != requests.codes.ok:
        raise _log_api_error(
            f"{description}: сервис вернул HTTP {response.status_code}. "
            f"Тело ответа: {_short_body(response.text)}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise _log_api_error(
            f"{description}: сервис вернул ответ, который не является JSON "
            f"(возможно, внутренняя ошибка сервиса). "
            f"Тело ответа: {_short_body(response.text)}"
        ) from exc

    if not isinstance(payload, dict):
        raise _log_api_error(
            f"{description}: неожиданный формат ответа — ожидался JSON-объект, "
            f"получено {type(payload).__name__}."
        )

    # Главный признак ошибки в этом API — непустое поле "error".
    api_error = str(payload.get("error") or "").strip()
    if api_error:
        raise _log_api_error(f"{description}: сервис вернул ошибку — {api_error}")

    if "data" not in payload:
        raise _log_api_error(f"{description}: в ответе сервиса отсутствует поле 'data'.")

    return payload["data"]


def _short_body(text: str, limit: int = 300) -> str:
    """Готовит короткое читаемое представление тела ответа для журнала."""
    collapsed = " ".join(text.split())
    if not collapsed:
        return "(пусто)"
    return collapsed if len(collapsed) <= limit else collapsed[:limit] + "..."


def fetch_rate(
    session: requests.Session,
    config: ApiConfig,
    base: str,
    quote: str,
    requested_date: date,
) -> dict[str, Any]:
    """Получает курс `base` к `quote` на дату `requested_date`."""
    data = _request(
        session,
        config,
        {"from": base, "to": quote, "date": requested_date.isoformat()},
        f"Запрос курса {base}/{quote} на {requested_date}",
    )

    if not isinstance(data, dict) or "rate" not in data:
        raise _log_api_error(
            f"Курс {base}/{quote} на {requested_date}: в ответе нет поля 'rate'. "
            f"Получено: {data!r}"
        )

    return {
        "from": data.get("from", base),
        "to": data.get("to", quote),
        "rate": data["rate"],
        "date": data.get("date", requested_date.isoformat()),
    }


def fetch_currencies(session: requests.Session, config: ApiConfig) -> list[str]:
    """Получает список валют, поддерживаемых сервисом."""
    data = _request(
        session,
        config,
        {"currencies": ""},  # любое значение — сервис проверяет только наличие параметра
        "Запрос списка валют",
    )
    if not isinstance(data, list):
        raise _log_api_error(
            f"Список валют: ожидался массив кодов, получено {type(data).__name__}."
        )
    return [str(item) for item in data]


# ---------------------------------------------------------------------------
# Сохранение результата
# ---------------------------------------------------------------------------


def build_filename(base: str, quote: str, requested_date: date) -> str:
    """Имя файла: валюты и дата запроса, например `USD_EUR_2025-03-17.json`."""
    return f"{base}_{quote}_{requested_date.isoformat()}.json"


def save_result(
    rate: dict[str, Any],
    base: str,
    quote: str,
    requested_date: date,
    data_dir: Path,
    api_url: str,
) -> Path:
    """
    Сохраняет полученные данные в JSON-файл, создавая каталог `data`.

    Файл пишется через временный файл и подменяется только после успешной
    записи, поэтому прерванный запуск не оставит повреждённый JSON.
    """
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        LOGGER.error("Не удалось создать каталог %s: %s", data_dir, exc)
        raise StorageError(f"Не удалось создать каталог '{data_dir}': {exc}") from exc

    document = {
        "request": {
            "from": base,
            "to": quote,
            "date": requested_date.isoformat(),
        },
        "response": rate,
        "rate": rate["rate"],
        "source": api_url,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }

    target = data_dir / build_filename(base, quote, requested_date)
    temporary = target.with_suffix(".json.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temporary.replace(target)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        LOGGER.error("Не удалось сохранить файл %s: %s", target, exc)
        raise StorageError(f"Не удалось сохранить файл '{target}': {exc}") from exc

    return target


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------


def run_list_currencies(session: requests.Session, config: ApiConfig) -> int:
    """Показывает список валют сервиса."""
    currencies = fetch_currencies(session, config)
    LOGGER.info("Валюты, поддерживаемые сервисом: %s", ", ".join(currencies))
    return 0


def run_rate_request(
    session: requests.Session,
    config: ApiConfig,
    args: argparse.Namespace,
    project_root: Path,
) -> int:
    """Получает курс, сохраняет его в JSON и печатает отчёт."""
    base, quote, requested_date = validate_request_args(args)
    data_dir = project_root / DATA_DIR_NAME

    LOGGER.info("Запрос курса %s → %s на %s ...", base, quote, requested_date)
    LOGGER.debug("Параметры подключения: url=%s, timeout=%s, retries=%s",
                 config.endpoint, config.timeout, config.retries)

    rate = fetch_rate(session, config, base, quote, requested_date)
    LOGGER.debug("Ответ сервиса: %s", rate)

    saved_date = rate.get("date")
    if isinstance(saved_date, str) and saved_date != requested_date.isoformat():
        LOGGER.warning(
            "Сервис вернул курс за дату %s вместо запрошенной %s — "
            "проверьте период данных.",
            saved_date,
            requested_date,
        )

    target = save_result(rate, base, quote, requested_date, data_dir, config.endpoint)

    print()
    print("Курс валюты")
    print("-----------")
    print(f"  Пара валют : {rate['from']} → {rate['to']}")
    print(f"  Курс       : {rate['rate']}")
    print(f"  Дата       : {rate['date']}")
    print(f"  Источник   : {config.endpoint}")
    print(f"  Файл       : {target}")
    print()
    LOGGER.info("Готово: данные сохранены в %s", target)
    return 0


def main(argv: list[str] | None = None) -> int:
    """
    Основная логика программы.

    Возвращает код возврата: 0 — успех, 1 — ошибка API/сети/файла,
    2 — некорректные аргументы (формируется argparse).
    """
    args = parse_args(argv)
    setup_console()
    project_root = find_project_root()
    log_path = setup_logging(project_root, verbose=args.verbose)

    # Списку валют и запросу курса нужны разные наборы аргументов,
    # поэтому ключ проверяем только для основного сценария.
    if not args.list_currencies and not (args.base and args.quote and args.date):
        LOGGER.error(
            "Указаны не все аргументы. Запуск: %s <валюта> <валюта> <YYYY-MM-DD> "
            "или %s --list-currencies",
            Path(sys.argv[0]).name,
            Path(sys.argv[0]).name,
        )
        return 2

    LOGGER.debug("Журнал ошибок: %s", log_path)

    try:
        # Параметры подключения проверяем до любого сетевого запроса,
        # а параметры запроса — только для сценария получения курса.
        config = validate_connection(args)

        LOGGER.info("Курс валюты, источник: %s", config.endpoint)

        with requests.Session() as session:
            session.headers.update(
                {
                    "Accept": "application/json",
                    "User-Agent": "lab02-currency-exchange/1.0",
                }
            )
            if args.list_currencies:
                return run_list_currencies(session, config)
            return run_rate_request(session, config, args, project_root)
    except ValidationError as exc:
        # Ошибки проверки входных данных не логируются в месте Raise,
        # поэтому записываем их здесь (код возврата — как у argparse).
        LOGGER.error("Проверка аргументов не пройдена: %s", exc)
        return 2
    except CurrencyExchangeError as exc:
        # Причина уже записана в error.log на уровне ERROR в точке
        # возникновения; добавляем итоговую строку без дублирования.
        LOGGER.error(
            "Скрипт завершён с ошибкой (код возврата 1): %s", exc.__class__.__name__
        )
        return 1
    except KeyboardInterrupt:  # pragma: no cover - прерывание пользователем
        LOGGER.warning("Работа прервана пользователем (Ctrl+C).")
        return 1


if __name__ == "__main__":
    sys.exit(main())
