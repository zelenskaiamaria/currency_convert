# Currency Converter (Python)

Konsolowy konwerter walut w języku Python. Kursy walut są pobierane z open.er-api.com (bez klucza API) i przechowywane lokalnie w pamięci podręcznej (cache).

## Przykłady

```bash
py main.py 100 USD EUR
py main.py 250 EUR UAH
py main.py 10 GBP JPY --refresh
py main.py 10 EUR USD --precision 4
```

## Opcje

--base XXX — waluta bazowa, względem której pobierane są kursy (domyślnie równa from_currency)

--cache-ttl SECONDS — czas życia pamięci podręcznej (domyślnie 12 godzin)

--refresh — ignoruj pamięć podręczną i zaktualizuj kursy

--precision N — liczba miejsc po przecinku


## Interfejs graficzny (GUI)

Uruchomienie:

```bash
py gui.py
```

- **Convert** — obliczyć i wyswietlić wynik
- **New convert** — wyczyszcza interfejs

