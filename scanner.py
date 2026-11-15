#!/usr/bin/env python3
"""
RS Leaders World · escáner de líderes de fuerza relativa por país.

Para cada país:
  1. Descarga el universo de acciones desde el screener público de TradingView.
  2. Descarga cierres diarios (2 años) de Yahoo Finance con yfinance.
  3. RS = cierre de la acción / cierre del benchmark del país.
  4. Una acción "califica" si su RS supera estrictamente el máximo de RS de las
     250 sesiones anteriores (la sesión actual se excluye) en al menos una de
     las últimas 10 sesiones completadas.
  5. Escribe data/<codigo>.json (+ data/index.json) que lee index.html.

Uso:
  python scanner.py                      # todos los países
  python scanner.py --countries es,us    # solo algunos
  python scanner.py --no-live-fx         # usa los tipos de cambio fijos de abajo
"""
import argparse
import datetime as dt
import json
import math
import os
import sys
import time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import yfinance as yf

LOOKBACK = 250   # sesiones previas para el máximo de RS
WINDOW = 10      # ventana de señal (sesiones completadas)
HISTORY = 20     # sesiones del gráfico de rotación sectorial
ADR_PERIOD = 14

# Umbrales por defecto (en USD equivalentes). EEUU = los de la web original.
PRESETS = {
    "us":   {"price_usd": 10.0, "value_usd": 30e6, "vol10": 350_000, "adr": 4.0},
    "intl": {"price_usd": 2.0,  "value_usd": 3e6,  "vol10": 50_000,  "adr": 3.0},
}

# usd = USD por 1 unidad de moneda local (aprox.; se refresca en vivo si se puede).
# ex   = bolsas de TradingView admitidas -> sufijo de Yahoo Finance.
COUNTRIES = {
    "us": dict(name="Estados Unidos", flag="🇺🇸", market="america", bench="SPY", bench_name="SPY",
               cur="USD", usd=1.0, tz="America/New_York", close=16.0, preset="us",
               ex={"NASDAQ": "", "NYSE": "", "AMEX": ""}),
    "ca": dict(name="Canadá", flag="🇨🇦", market="canada", bench="^GSPTSE", bench_name="S&P/TSX Composite",
               cur="CAD", usd=0.72, tz="America/Toronto", close=16.0, preset="intl", ex={"TSX": ".TO"}),
    "mx": dict(name="México", flag="🇲🇽", market="mexico", bench="^MXX", bench_name="S&P/BMV IPC",
               cur="MXN", usd=0.055, tz="America/Mexico_City", close=15.0, preset="intl", ex={"BMV": ".MX"}),
    "br": dict(name="Brasil", flag="🇧🇷", market="brazil", bench="^BVSP", bench_name="Ibovespa",
               cur="BRL", usd=0.18, tz="America/Sao_Paulo", close=17.0, preset="intl", ex={"BMFBOVESPA": ".SA"}),
    "es": dict(name="España", flag="🇪🇸", market="spain", bench="^IBEX", bench_name="IBEX 35",
               cur="EUR", usd=1.10, tz="Europe/Madrid", close=17.5, preset="intl", ex={"BME": ".MC"}),
    "de": dict(name="Alemania", flag="🇩🇪", market="germany", bench="^GDAXI", bench_name="DAX",
               cur="EUR", usd=1.10, tz="Europe/Berlin", close=17.5, preset="intl", ex={"XETR": ".DE"}),
    "fr": dict(name="Francia", flag="🇫🇷", market="france", bench="^FCHI", bench_name="CAC 40",
               cur="EUR", usd=1.10, tz="Europe/Paris", close=17.5, preset="intl", ex={"EURONEXT": ".PA"}),
    "it": dict(name="Italia", flag="🇮🇹", market="italy", bench="FTSEMIB.MI", bench_name="FTSE MIB",
               cur="EUR", usd=1.10, tz="Europe/Rome", close=17.5, preset="intl", ex={"MIL": ".MI"}),
    "uk": dict(name="Reino Unido", flag="🇬🇧", market="uk", bench="^FTSE", bench_name="FTSE 100",
               cur="GBX", usd=0.0130, tz="Europe/London", close=16.5, preset="intl", ex={"LSE": ".L"}),
    "nl": dict(name="Países Bajos", flag="🇳🇱", market="netherlands", bench="^AEX", bench_name="AEX",
               cur="EUR", usd=1.10, tz="Europe/Amsterdam", close=17.5, preset="intl", ex={"EURONEXT": ".AS"}),
    "be": dict(name="Bélgica", flag="🇧🇪", market="belgium", bench="^BFX", bench_name="BEL 20",
               cur="EUR", usd=1.10, tz="Europe/Brussels", close=17.5, preset="intl", ex={"EURONEXT": ".BR"}),
    "pt": dict(name="Portugal", flag="🇵🇹", market="portugal", bench="PSI20.LS", bench_name="PSI",
               cur="EUR", usd=1.10, tz="Europe/Lisbon", close=16.5, preset="intl", ex={"EURONEXT": ".LS"}),
    "ch": dict(name="Suiza", flag="🇨🇭", market="switzerland", bench="^SSMI", bench_name="SMI",
               cur="CHF", usd=1.15, tz="Europe/Zurich", close=17.5, preset="intl", ex={"SIX": ".SW"}),
    "se": dict(name="Suecia", flag="🇸🇪", market="sweden", bench="^OMX", bench_name="OMX Stockholm 30",
               cur="SEK", usd=0.095, tz="Europe/Stockholm", close=17.5, preset="intl", ex={"OMXSTO": ".ST"}),
    "dk": dict(name="Dinamarca", flag="🇩🇰", market="denmark", bench="^OMXC25", bench_name="OMX Copenhagen 25",
               cur="DKK", usd=0.147, tz="Europe/Copenhagen", close=17.0, preset="intl", ex={"OMXCOP": ".CO"}),
    "no": dict(name="Noruega", flag="🇳🇴", market="norway", bench="OSEBX.OL", bench_name="Oslo Børs Benchmark",
               cur="NOK", usd=0.092, tz="Europe/Oslo", close=16.5, preset="intl", ex={"OSL": ".OL"}),
    "fi": dict(name="Finlandia", flag="🇫🇮", market="finland", bench="^OMXH25", bench_name="OMX Helsinki 25",
               cur="EUR", usd=1.10, tz="Europe/Helsinki", close=18.5, preset="intl", ex={"OMXHEX": ".HE"}),
    "jp": dict(name="Japón", flag="🇯🇵", market="japan", bench="^N225", bench_name="Nikkei 225",
               cur="JPY", usd=0.0066, tz="Asia/Tokyo", close=15.5, preset="intl", ex={"TSE": ".T"}),
    "hk": dict(name="Hong Kong", flag="🇭🇰", market="hongkong", bench="^HSI", bench_name="Hang Seng",
               cur="HKD", usd=0.128, tz="Asia/Hong_Kong", close=16.5, preset="intl", ex={"HKEX": ".HK"}),
    "cn": dict(name="China", flag="🇨🇳", market="china", bench="000001.SS", bench_name="SSE Composite",
               cur="CNY", usd=0.14, tz="Asia/Shanghai", close=15.5, preset="intl", ex={"SSE": ".SS", "SZSE": ".SZ"}),
    "kr": dict(name="Corea del Sur", flag="🇰🇷", market="korea", bench="^KS11", bench_name="KOSPI",
               cur="KRW", usd=0.00072, tz="Asia/Seoul", close=15.5, preset="intl", ex={"KRX": ".KS", "KOSDAQ": ".KQ"}),
    "tw": dict(name="Taiwán", flag="🇹🇼", market="taiwan", bench="^TWII", bench_name="TAIEX",
               cur="TWD", usd=0.031, tz="Asia/Taipei", close=14.0, preset="intl", ex={"TWSE": ".TW", "TPEX": ".TWO"}),
    "in": dict(name="India", flag="🇮🇳", market="india", bench="^NSEI", bench_name="Nifty 50",
               cur="INR", usd=0.012, tz="Asia/Kolkata", close=15.75, preset="intl", ex={"NSE": ".NS"}),
    "au": dict(name="Australia", flag="🇦🇺", market="australia", bench="^AXJO", bench_name="S&P/ASX 200",
               cur="AUD", usd=0.66, tz="Australia/Sydney", close=16.5, preset="intl", ex={"ASX": ".AX"}),
    "sg": dict(name="Singapur", flag="🇸🇬", market="singapore", bench="^STI", bench_name="Straits Times",
               cur="SGD", usd=0.75, tz="Asia/Singapore", close=17.25, preset="intl", ex={"SGX": ".SI"}),
}

# Tipos de cambio en vivo: moneda -> (ticker Yahoo, invertir, escala)
FX_LIVE = {
    "CAD": ("CAD=X", True, 1), "MXN": ("MXN=X", True, 1), "BRL": ("BRL=X", True, 1),
    "EUR": ("EURUSD=X", False, 1), "GBX": ("GBPUSD=X", False, 0.01), "CHF": ("CHF=X", True, 1),
    "SEK": ("SEK=X", True, 1), "DKK": ("DKK=X", True, 1), "NOK": ("NOK=X", True, 1),
    "JPY": ("JPY=X", True, 1), "HKD": ("HKD=X", True, 1), "CNY": ("CNY=X", True, 1),
    "KRW": ("KRW=X", True, 1), "TWD": ("TWD=X", True, 1), "INR": ("INR=X", True, 1),
    "AUD": ("AUDUSD=X", False, 1), "SGD": ("SGD=X", True, 1),
}

TV_URL = "https://scanner.tradingview.com/{market}/scan"
TV_COLUMN_SETS = [
    ["name", "description", "sector", "close", "average_volume_10d_calc",
     "average_volume_30d_calc", "float_shares_outstanding_current", "type", "subtype"],
    ["name", "description", "sector", "close", "average_volume_10d_calc",
     "average_volume_30d_calc", "type", "subtype"],
    ["name", "description", "close", "average_volume_10d_calc",
     "average_volume_30d_calc", "type", "subtype"],
]
BAD_SUBTYPES = {"preferred", "unit", "right", "warrant", "trust", "structured", "closedend"}
HEADERS = {"User-Agent": "Mozilla/5.0 (RS-Leaders-World)", "Content-Type": "application/json"}


def log(*a):
    print(*a, flush=True)


# ----------------------------------------------------------------------------
# Configuración derivada
# ----------------------------------------------------------------------------
def nice(x):
    return float(f"{x:.2g}")


def thresholds(cfg, usd):
    p = PRESETS[cfg["preset"]]
    defaults = {
        "price": nice(p["price_usd"] / usd),
        "value_usd": p["value_usd"],
        "vol10": p["vol10"],
        "adr": p["adr"],
    }
    floor = {
        "price": nice(defaults["price"] * 0.5),
        "value_usd": defaults["value_usd"] * 0.5,
        "vol10": defaults["vol10"] * 0.5,
        "adr": max(defaults["adr"] - 1.0, 1.5),
    }
    return defaults, floor


def refresh_fx():
    fx = {}
    for cur, (tk, inv, scale) in FX_LIVE.items():
        try:
            s = yf.Ticker(tk).history(period="5d")["Close"].dropna()
            if len(s):
                v = float(s.iloc[-1])
                fx[cur] = (1.0 / v if inv else v) * scale
        except Exception as e:  # noqa: BLE001
            log(f"  [fx] {cur}: {e}")
    return fx


# ----------------------------------------------------------------------------
# Universo (TradingView)
# ----------------------------------------------------------------------------
def tv_universe(cfg, floor):
    url = TV_URL.format(market=cfg["market"])
    for cols in TV_COLUMN_SETS:
        out, start, page = [], 0, 1000
        try:
            while True:
                payload = {
                    "filter": [
                        {"left": "type", "operation": "in_range", "right": ["stock", "dr"]},
                        {"left": "close", "operation": "greater", "right": floor["price"]},
                        {"left": "average_volume_10d_calc", "operation": "greater", "right": floor["vol10"]},
                    ],
                    "options": {"lang": "en"},
                    "markets": [cfg["market"]],
                    "symbols": {"query": {"types": []}, "tickers": []},
                    "columns": cols,
                    "sort": {"sortBy": "average_volume_10d_calc", "sortOrder": "desc"},
                    "range": [start, start + page],
                }
                r = requests.post(url, json=payload, headers=HEADERS, timeout=60)
                r.raise_for_status()
                j = r.json()
                data = j.get("data") or []
                for item in data:
                    d = dict(zip(cols, item["d"]))
                    exch, _, _tk = item["s"].partition(":")
                    d["exchange"] = exch
                    out.append(d)
                total = j.get("totalCount", 0)
                if not data or start + page >= total:
                    break
                start += page
                time.sleep(0.5)
            return out
        except requests.HTTPError as e:
            log(f"  [tv] columnas {len(cols)} rechazadas ({e}); probando set más pequeño")
            continue
    return []


def yahoo_symbol(cfg, exch, ticker):
    t = str(ticker).strip().upper().rstrip(".").replace("/", "-").replace("_", "-").replace(".", "-")
    if cfg["market"] == "hongkong" and t.isdigit():
        t = t.zfill(4)
    if cfg["market"] in ("korea", "china") and t.isdigit():
        t = t.zfill(6)
    return t + cfg["ex"][exch]


def build_universe(code, cfg, usd, floor):
    raw = tv_universe(cfg, floor)
    uni = {}
    for d in raw:
        exch = d.get("exchange")
        if exch not in cfg["ex"]:
            continue
        if (d.get("subtype") or "").lower() in BAD_SUBTYPES:
            continue
        close, v30 = d.get("close") or 0, d.get("average_volume_30d_calc") or 0
        if close * v30 * usd < floor["value_usd"] * 0.5:   # margen: se reevalúa con datos de Yahoo
            continue
        ysym = yahoo_symbol(cfg, exch, d["name"])
        uni[ysym] = {
            "t": f"{exch}:{d['name']}", "sym": d["name"], "ex": exch,
            "name": d.get("description") or d["name"],
            "sector": d.get("sector") or "Otros",
            "float": d.get("float_shares_outstanding_current"),
        }
    return uni, len(raw)


# ----------------------------------------------------------------------------
# Precios (Yahoo Finance)
# ----------------------------------------------------------------------------
def norm_index(df):
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    df = df.copy()
    df.index = idx.normalize()
    return df[~df.index.duplicated(keep="last")]


def get_benchmark(cfg, now_utc):
    h = yf.Ticker(cfg["bench"]).history(period="2y", auto_adjust=True)
    if h is None or h.empty:
        return None
    s = norm_index(h)["Close"].dropna()
    local = now_utc.astimezone(ZoneInfo(cfg["tz"]))
    # Si la sesión de hoy aún no ha cerrado, la barra es parcial: se descarta.
    if len(s) and s.index[-1].date() == local.date() and local.hour + local.minute / 60 < cfg["close"] + 0.25:
        s = s.iloc[:-1]
    return s


def download(symbols, chunk=100):
    out = {}
    for i in range(0, len(symbols), chunk):
        part = symbols[i:i + chunk]
        df = None
        for attempt in range(3):
            try:
                df = yf.download(part, period="2y", interval="1d", auto_adjust=True,
                                 group_by="ticker", threads=True, progress=False)
                break
            except Exception as e:  # noqa: BLE001
                log(f"    reintento {attempt + 1}: {e}")
                time.sleep(3 * (attempt + 1))
        if df is None or df.empty:
            continue
        if isinstance(df.columns, pd.MultiIndex):
            top = set(df.columns.get_level_values(0))
            for s in part:
                if s in top:
                    sub = df[s].dropna(how="all")
                    if not sub.empty:
                        out[s] = norm_index(sub)
        else:
            out[part[0]] = norm_index(df.dropna(how="all"))
        log(f"    descargados {min(i + chunk, len(symbols))}/{len(symbols)}")
        time.sleep(1.0)
    return out


# ----------------------------------------------------------------------------
# Cálculo
# ----------------------------------------------------------------------------
def analyze(df, bench):
    """Devuelve métricas de RS de una acción frente al benchmark, o None."""
    if not {"Close", "High", "Low", "Volume"}.issubset(df.columns):
        return None
    close = df["Close"].reindex(bench.index).ffill(limit=3)
    if pd.isna(close.iloc[-1]):
        return None
    rs = close / bench
    if rs.notna().sum() < LOOKBACK + WINDOW:
        return None

    prior = rs.shift(1).rolling(LOOKBACK, min_periods=LOOKBACK).max()
    brk = (rs > prior).fillna(False)
    flags = brk.astype(float).rolling(WINDOW, min_periods=1).max().gt(0)

    last = brk.iloc[-WINDOW:].to_numpy()
    qualifies = bool(last.any())
    ago, above = None, None
    if qualifies:
        pos = int(np.where(last)[0][-1])               # última sesión con ruptura dentro de la ventana
        ago = WINDOW - 1 - pos
        d = brk.index[-WINDOW + pos]
        above = float((rs[d] / prior[d] - 1) * 100)

    hi = df["High"].dropna().iloc[-ADR_PERIOD:]
    lo = df["Low"].reindex(hi.index)
    adr = float(((hi / lo).mean() - 1) * 100) if len(hi) == ADR_PERIOD else float("nan")
    vol10 = float(df["Volume"].iloc[-10:].mean())
    value_local = float(df["Close"].iloc[-30:].mean() * df["Volume"].iloc[-30:].mean())
    rs_max = float(rs.iloc[-LOOKBACK:].max())
    return {
        "price": float(close.iloc[-1]), "adr": adr, "vol10": vol10, "value_local": value_local,
        "qualifies": qualifies, "ago": ago, "above": above,
        "rs": float(rs.iloc[-1]), "rs_ratio": float(rs.iloc[-1] / rs_max),
        "hist": flags.iloc[-HISTORY:].to_list(),
    }


def clean(v, nd=4):
    if v is None:
        return None
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return round(v, nd)
    return v


def run_country(code, cfg, usd, now_utc):
    defaults, floor = thresholds(cfg, usd)
    log(f"\n== {cfg['flag']} {cfg['name']} ({code}) · benchmark {cfg['bench']} ==")
    uni, raw_n = build_universe(code, cfg, usd, floor)
    log(f"  universo TradingView: {raw_n} · tras prefiltro: {len(uni)}")
    if not uni:
        return None
    bench = get_benchmark(cfg, now_utc)
    if bench is None or len(bench) < LOOKBACK + WINDOW:
        log("  ! benchmark sin datos suficientes")
        return None
    prices = download(list(uni))
    log(f"  series válidas: {len(prices)}")

    rows, sector_days = [], [dict() for _ in range(HISTORY)]
    for ysym, df in prices.items():
        try:
            m = analyze(df, bench)
        except Exception as e:  # noqa: BLE001
            log(f"    {ysym}: {e}")
            continue
        if m is None or math.isnan(m["adr"]):
            continue
        value_usd = m["value_local"] * usd
        if (m["price"] < floor["price"] or m["adr"] < floor["adr"]
                or m["vol10"] < floor["vol10"] or value_usd < floor["value_usd"]):
            continue
        info = uni[ysym]
        for i, ok in enumerate(m["hist"]):
            if ok:
                sd = sector_days[i]
                sd[info["sector"]] = sd.get(info["sector"], 0) + 1
        if m["qualifies"]:
            rows.append({**info, "price": clean(m["price"], 4), "adr": clean(m["adr"], 2),
                         "vol10": clean(m["vol10"], 0), "value_usd": clean(value_usd, 0),
                         "ago": m["ago"], "rs": clean(m["rs"], 6), "rs_ratio": clean(m["rs_ratio"], 4),
                         "above": clean(m["above"], 2)})
    rows.sort(key=lambda r: (r["ago"], -(r["above"] or 0)))

    dates = [d.strftime("%Y-%m-%d") for d in bench.index[-HISTORY:]]
    history = [{"date": d, "total": sum(sd.values()), "sectors": sd}
               for d, sd in zip(dates, sector_days)]
    meta = {
        "code": code, "name": cfg["name"], "benchmark": cfg["bench"], "benchmark_name": cfg["bench_name"],
        "currency": cfg["cur"], "usd_per_unit": usd, "last_date": dates[-1],
        "generated_at": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), "universe": raw_n, "scanned": len(prices),
        "lookback": LOOKBACK, "window": WINDOW, "adr_period": ADR_PERIOD,
        "defaults": defaults, "floor": floor,
    }
    log(f"  -> {len(rows)} acciones califican · último día {dates[-1]}")
    return {"meta": meta, "rows": rows, "history": history}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", default="", help="códigos separados por coma (vacío = todos)")
    ap.add_argument("--out", default="data")
    ap.add_argument("--no-live-fx", action="store_true")
    args = ap.parse_args()

    codes = [c.strip().lower() for c in args.countries.split(",") if c.strip()] or list(COUNTRIES)
    bad = [c for c in codes if c not in COUNTRIES]
    if bad:
        sys.exit(f"Códigos desconocidos: {bad}. Disponibles: {list(COUNTRIES)}")

    os.makedirs(args.out, exist_ok=True)
    now_utc = dt.datetime.now(dt.timezone.utc)
    live = {} if args.no_live_fx else refresh_fx()

    idx_path = os.path.join(args.out, "index.json")
    index = {}
    if os.path.exists(idx_path):
        try:
            index = json.load(open(idx_path, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            index = {}

    ok = 0
    for code in codes:
        cfg = COUNTRIES[code]
        usd = live.get(cfg["cur"], cfg["usd"])
        try:
            res = run_country(code, cfg, usd, now_utc)
        except Exception as e:  # noqa: BLE001
            log(f"  ! {code} falló: {e}")
            continue
        if not res:
            continue
        with open(os.path.join(args.out, f"{code}.json"), "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, separators=(",", ":"))
        index[code] = {"name": cfg["name"], "last_date": res["meta"]["last_date"],
                       "qualifying": len(res["rows"]), "generated_at": res["meta"]["generated_at"]}
        ok += 1

    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    log(f"\nHecho: {ok}/{len(codes)} países actualizados")
    if ok == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
