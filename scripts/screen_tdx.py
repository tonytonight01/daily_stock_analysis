#!/usr/bin/env python3
"""Screen Shanghai/Shenzhen A shares before the existing daily analysis job."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import date, datetime
import json
import logging
from pathlib import Path
import re
import sys
import time
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.screening.tdx_formula import UndefinedFormulaError, evaluate_formula  # noqa: E402


def eligible(code: str, name: str) -> bool:
    # 沪深主板、创业板、科创板；不含北交所、B股、ETF及指数。
    return bool(re.fullmatch(r"(?:60\d{4}|68\d{4}|00\d{4}|30\d{4})", code)) and "ST" not in name.upper()


def screen_one(code: str, name: str, lookback: int, session_date, historical: bool = False) -> dict:
    from src.services.screening.daily import fetch_daily_history

    # Pin one source: Tencent qfq prices and volume in lots. Do not mix
    # unadjusted fallback sources or share-unit volume into this formula.
    frame = fetch_daily_history(code, lookback_days=lookback, source="tencent", retries=1)
    frame = frame.sort_values("date")
    if historical:
        frame = frame[frame["date"].astype(str).str[:10] <= session_date.isoformat()]
    if len(frame) < 90:
        raise UndefinedFormulaError("history shorter than 90 daily bars")
    if frame.attrs.get("daily_stale") and not historical:
        raise ValueError("stale daily data")
    dates = frame["date"].astype(str).str[:10]
    if dates.duplicated().any() or dates.iloc[-1] != session_date.isoformat():
        raise ValueError("duplicate dates or missing current session close")
    result = evaluate_formula(*[
        frame[column].astype(float).tolist() for column in ("close", "high", "low", "volume")
    ])
    return {"code": code, "name": name, "date": dates.iloc[-1], "selected": result.selected, **asdict(result)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--lookback", type=int, default=250)
    parser.add_argument("--sample-size", type=int, default=0,
                        help="Feasibility sample of 1..100 stocks; 0 scans the full universe")
    parser.add_argument("--as-of", type=date.fromisoformat,
                        help="Historical completed trading date for verification (YYYY-MM-DD)")
    args = parser.parse_args()
    if not 1 <= args.workers <= 8 or not 90 <= args.lookback <= 1000:
        parser.error("workers must be 1..8; lookback must be 90..1000")
    if not 0 <= args.sample_size <= 100:
        parser.error("sample-size must be 0..100")
    if args.as_of and args.sample_size == 0:
        parser.error("as-of is only supported with an explicit verification sample")

    # Clear old outputs before any network work. A failed run cannot reuse
    # yesterday's picks, and an empty result never falls back to default stocks.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.unlink(missing_ok=True)
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write("has_matches=false\nstock_list=\n")

    from src.core.trading_calendar import is_market_open
    from src.services.screening.snapshot import fetch_snapshot_with_fallback

    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    session_date = args.as_of or now.date()
    if session_date > now.date():
        parser.error("as-of cannot be in the future")
    started = time.monotonic()
    report = {"date": session_date.isoformat(), "period": "daily", "adjust": "qfq",
              "universe": "Shanghai/Shenzhen A shares excluding ST", "source": "tencent",
              "lookback": args.lookback, "sample_size": args.sample_size,
              "verification_only": bool(args.sample_size),
              "matches": [], "errors": [], "undefined": []}
    if not is_market_open("cn", session_date):
        report["status"] = "non_trading_day"
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Non-trading day: skip screening and stock analysis")
        return 0
    if session_date == now.date() and (now.hour, now.minute) < (15, 30):
        raise RuntimeError("daily screening requires completed close (after 15:30 Asia/Shanghai)")

    snapshot = fetch_snapshot_with_fallback(["sina", "efinance", "akshare_em"],
                                            required_columns=["code", "name"])
    universe = {}
    for row in snapshot.to_dict("records"):
        code, name = str(row["code"]).zfill(6), str(row["name"]).strip()
        if name and name.lower() != "nan" and eligible(code, name):
            universe[code] = name
    if not universe:
        raise RuntimeError("no eligible stocks in live snapshot")
    report["universe_count"] = len(universe)
    if args.sample_size:
        # Evenly spaced by code, to exercise several exchanges/boards without
        # advertising the validation sample as a full-market selection result.
        items = sorted(universe.items())
        count = min(args.sample_size, len(items))
        indices = [i * (len(items) - 1) // max(count - 1, 1) for i in range(count)]
        universe = dict(items[i] for i in indices)
        report["sample_evaluations"] = []
    report["scanned_count"] = len(universe)
    report["universe_fetch_seconds"] = round(time.monotonic() - started, 3)
    processed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(screen_one, code, name, args.lookback, session_date, bool(args.as_of)): code
                   for code, name in sorted(universe.items())}
        for future in as_completed(futures):
            code = futures[future]
            try:
                row = future.result()
                if args.sample_size:
                    report["sample_evaluations"].append(row)
                if row["selected"]:
                    report["matches"].append(row)
            except UndefinedFormulaError as exc:
                report["undefined"].append({"code": code, "reason": str(exc)})
            except Exception as exc:
                report["errors"].append({"code": code, "error": str(exc)})
            processed += 1
            if processed % 100 == 0:
                print(f"Screened {processed}/{len(universe)}, matches={len(report['matches'])}", flush=True)
    report["matches"].sort(key=lambda row: row["code"])
    report["errors"].sort(key=lambda row: row["code"])
    report["undefined"].sort(key=lambda row: row["code"])
    report["evaluated_count"] = len(universe) - len(report["errors"]) - len(report["undefined"])
    report["status"] = "partial" if report["errors"] else "complete"
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    if args.sample_size:
        report["sample_evaluations"].sort(key=lambda row: row["code"])
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Coverage {report['evaluated_count']}/{len(universe)}; matches={len(report['matches'])}")
    if report["errors"]:
        # A partial scan is an error, not a full-market all-clear or match list.
        print("Incomplete scan: inspect screening report; stock analysis suppressed", file=sys.stderr)
        return 1
    if args.github_output and not args.sample_size:
        codes = ",".join(row["code"] for row in report["matches"])
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write(f"has_matches={'true' if codes else 'false'}\nstock_list={codes}\n")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    try:
        sys.exit(main())
    except Exception:
        logging.exception("Tongdaxin screening failed")
        sys.exit(1)
