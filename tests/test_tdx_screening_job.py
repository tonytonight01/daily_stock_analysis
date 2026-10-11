"""Check daily job outputs and failures without live market requests."""

from datetime import datetime
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import screen_tdx


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 12, 18, tzinfo=tz)


class Snapshot:
    def to_dict(self, orient):
        return [{"code": "600519", "name": "茅台"}, {"code": "000001", "name": "银行"},
                {"code": "000002", "name": "*ST测试"}, {"code": "510300", "name": "ETF"}]


class ScreeningJobTest(unittest.TestCase):
    def run_job(self, directory, *, worker, trading=True, snapshot=None):
        report = Path(directory) / "report.json"
        output = Path(directory) / "github-output"
        report.write_text('{"matches":[{"code":"999999"}]}', encoding="utf-8")
        modules = {
            "src.core.trading_calendar": SimpleNamespace(is_market_open=lambda *args: trading),
            "src.services.screening.snapshot": SimpleNamespace(
                fetch_snapshot_with_fallback=lambda *args, **kwargs: snapshot or Snapshot()),
        }
        argv = ["screen_tdx.py", "--output", str(report), "--github-output", str(output)]
        with patch.dict("sys.modules", modules), patch("sys.argv", argv), \
                patch.object(screen_tdx, "datetime", FixedDatetime), \
                patch.object(screen_tdx, "screen_one", side_effect=worker) as mocked:
            status = screen_tdx.main()
        return status, json.loads(report.read_text(encoding="utf-8")), \
            dict(line.split("=", 1) for line in output.read_text().splitlines()), mocked

    def test_only_sorted_daily_matches_are_exported(self):
        with tempfile.TemporaryDirectory() as directory:
            status, report, output, mocked = self.run_job(directory, worker=lambda code, *args: {
                "code": code, "selected": True})
        self.assertEqual(status, 0)
        self.assertEqual(output["stock_list"], "000001,600519")
        self.assertEqual(output["has_matches"], "true")
        self.assertEqual(report["status"], "complete")
        self.assertEqual(mocked.call_count, 2)

    def test_no_matches_does_not_reuse_previous_picks(self):
        with tempfile.TemporaryDirectory() as directory:
            status, report, output, _ = self.run_job(directory, worker=lambda code, *args: {
                "code": code, "selected": False})
        self.assertEqual(status, 0)
        self.assertEqual(report["matches"], [])
        self.assertEqual(output, {"has_matches": "false", "stock_list": ""})

    def test_fetch_failure_blocks_partial_match_export(self):
        def worker(code, *args):
            if code == "000001":
                raise RuntimeError("data source unavailable")
            return {"code": code, "selected": True}
        with tempfile.TemporaryDirectory() as directory:
            status, report, output, _ = self.run_job(directory, worker=worker)
        self.assertEqual(status, 1)
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["errors"][0]["code"], "000001")
        self.assertEqual(output["stock_list"], "")

    def test_short_histories_are_explicitly_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            status, report, output, _ = self.run_job(
                directory, worker=screen_tdx.UndefinedFormulaError("short history"))
        self.assertEqual(status, 0)
        self.assertEqual(len(report["undefined"]), 2)
        self.assertEqual(report["evaluated_count"], 0)
        self.assertEqual(output["has_matches"], "false")

    def test_nontrading_day_does_not_fetch_history(self):
        with tempfile.TemporaryDirectory() as directory:
            status, report, output, mocked = self.run_job(directory, worker=RuntimeError(), trading=False)
        self.assertEqual(status, 0)
        self.assertEqual(report["status"], "non_trading_day")
        self.assertEqual(output["stock_list"], "")
        mocked.assert_not_called()


if __name__ == "__main__":
    unittest.main()
