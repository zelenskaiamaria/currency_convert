from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


API_BASE = "https://open.er-api.com/v6/latest/"
DEFAULT_CACHE_TTL_SECONDS = 12 * 60 * 60


@dataclass(frozen=True)
class RatesResponse:
    base_code: str
    rates: dict[str, float]
    time_last_update_unix: int | None


class RatesError(RuntimeError):
    pass


def _http_get_json(url: str, timeout_seconds: float = 10.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "currency-converter/1.0"})
    with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8"))


def _cache_dir() -> Path:
    # Per-user cache; works on Windows/macOS/Linux.
    root = Path.home() / ".currency_converter_cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _cache_path(base: str) -> Path:
    safe = "".join(ch for ch in base.upper() if ch.isalnum() or ch in ("_", "-"))
    return _cache_dir() / f"rates_{safe}.json"


def _load_cache(base: str, ttl_seconds: int) -> RatesResponse | None:
    path = _cache_path(base)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = float(payload.get("fetched_at", 0))
        if time.time() - fetched_at > ttl_seconds:
            return None
        data = payload.get("data") or {}
        if not isinstance(data, dict):
            return None
        base_code = str(data.get("base_code", "")).upper()
        rates = data.get("rates")
        if not base_code or not isinstance(rates, dict):
            return None
        tlu = data.get("time_last_update_unix")
        tlu_int = int(tlu) if isinstance(tlu, (int, float)) else None
        return RatesResponse(base_code=base_code, rates={k: float(v) for k, v in rates.items()}, time_last_update_unix=tlu_int)
    except Exception:
        return None


def _save_cache(base: str, data: dict) -> None:
    path = _cache_path(base)
    payload = {"fetched_at": time.time(), "data": data}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_rates(base: str, cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS, *, force_refresh: bool = False) -> RatesResponse:
    base = base.upper()
    if not force_refresh:
        cached = _load_cache(base, cache_ttl_seconds)
        if cached is not None:
            return cached

    url = API_BASE + urllib.parse.quote(base)
    data = _http_get_json(url)
    if not isinstance(data, dict):
        raise RatesError("Invalid response from rates API.")

    if data.get("result") != "success":
        err = data.get("error-type") or "unknown"
        raise RatesError(f"Rates API error: {err}")

    base_code = str(data.get("base_code", "")).upper()
    if base_code != base:
        raise RatesError(f"Rates API returned base {base_code}, expected {base}.")

    rates = data.get("rates")
    if not isinstance(rates, dict) or not rates:
        raise RatesError("Rates API returned empty rates.")

    _save_cache(base, data)
    tlu = data.get("time_last_update_unix")
    tlu_int = int(tlu) if isinstance(tlu, (int, float)) else None
    return RatesResponse(base_code=base_code, rates={k: float(v) for k, v in rates.items()}, time_last_update_unix=tlu_int)


def convert(amount: float, from_code: str, to_code: str, rates: RatesResponse) -> float:
    from_code = from_code.upper()
    to_code = to_code.upper()

    if from_code == rates.base_code:
        from_rate = 1.0
    else:
        try:
            from_rate = float(rates.rates[from_code])
        except KeyError as e:
            raise RatesError(f"Unknown currency code: {from_code}") from e

    try:
        to_rate = 1.0 if to_code == rates.base_code else float(rates.rates[to_code])
    except KeyError as e:
        raise RatesError(f"Unknown currency code: {to_code}") from e

    # API gives: 1 BASE = rate * CURRENCY
    # So: amount FROM -> BASE -> TO
    amount_in_base = amount / from_rate
    return amount_in_base * to_rate


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Currency converter (rates from open.er-api.com, no API key).")
    p.add_argument("amount", type=float, help="Amount to convert (e.g. 10.5)")
    p.add_argument("from_currency", help="Source currency code (e.g. USD)")
    p.add_argument("to_currency", help="Target currency code (e.g. EUR)")
    p.add_argument("--base", default=None, help="Base currency for fetching rates (defaults to from_currency)")
    p.add_argument("--refresh", action="store_true", help="Ignore cache and fetch fresh rates")
    p.add_argument("--cache-ttl", type=int, default=DEFAULT_CACHE_TTL_SECONDS, help="Cache TTL in seconds")
    p.add_argument("--precision", type=int, default=2, help="Decimal places for output")
    return p


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)

    if args.amount < 0:
        print("Amount must be non-negative.", file=sys.stderr)
        return 2

    from_code = args.from_currency.upper()
    to_code = args.to_currency.upper()
    base = (args.base or from_code).upper()

    try:
        rates = fetch_rates(base, cache_ttl_seconds=args.cache_ttl, force_refresh=bool(args.refresh))
        result = convert(args.amount, from_code, to_code, rates)
    except RatesError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1

    prec = max(0, int(args.precision))
    formatted = f"{result:.{prec}f}"

    suffix = ""
    if rates.time_last_update_unix:
        suffix = f" (rates updated: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(rates.time_last_update_unix))})"

    print(f"{args.amount:g} {from_code} = {formatted} {to_code}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

