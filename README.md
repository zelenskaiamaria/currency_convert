# Currency Converter (Python)

Консольный конвертер валют на Python. Курсы берутся с `open.er-api.com` (без API-ключа) и кэшируются локально.

## Установка

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Примеры

```bash
py main.py 100 USD EUR
py main.py 250 EUR UAH
py main.py 10 GBP JPY --refresh
py main.py 10 EUR USD --precision 4
```

## Опции

- `--base XXX` — валюта базы, относительно которой запрашиваются курсы (по умолчанию равна `from_currency`)
- `--cache-ttl SECONDS` — время жизни кэша (по умолчанию 12 часов)
- `--refresh` — игнорировать кэш и обновить курсы
- `--precision N` — количество знаков после запятой

## Оконный интерфейс (GUI)

Запуск:

```bash
py gui.py
```

Кнопки:

- **Convert** — посчитать и показать результат
- **New convert** — полностью сбросить сумму, пары валют и результат

