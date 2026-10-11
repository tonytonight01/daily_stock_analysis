"""Model verification fails on empty output, partial scans or fallback models."""

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.tdx_model_check import verify


class ModelVerificationTest(unittest.TestCase):
    def check(self, *, actual="example-model", text="验证报告", status="complete", samples=True):
        class Analyzer:
            def __init__(self, **kwargs):
                pass

            def is_available(self):
                return True

            def generate_text_with_metadata(self, *args, **kwargs):
                return SimpleNamespace(text=text, model=actual, backend="litellm", provider="openai")

        modules = {
            "src.config": SimpleNamespace(get_config=lambda: SimpleNamespace(litellm_model="openai/example-model")),
            "src.analyzer": SimpleNamespace(GeminiAnalyzer=Analyzer),
        }
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "screening.json"
            output = Path(directory) / "model.json"
            source.write_text(json.dumps({"date": "2026-10-09", "status": status,
                                         "sample_evaluations": [{"code": "600519"}] if samples else []}))
            with patch.dict("sys.modules", modules):
                code = verify(source, output)
            return code, json.loads(output.read_text(encoding="utf-8"))

    def test_records_actual_model_without_notifications(self):
        code, report = self.check()
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["actual_model"], "example-model")
        self.assertFalse(report["notifications_sent"])

    def test_empty_report_is_not_success(self):
        code, report = self.check(text="")
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "failed")

    def test_fallback_model_does_not_validate_requested_model(self):
        code, report = self.check(actual="different-model")
        self.assertEqual(code, 1)
        self.assertEqual(report["actual_model"], "different-model")

    def test_partial_or_empty_scan_does_not_call_model(self):
        for options in ({"status": "partial"}, {"samples": False}):
            code, report = self.check(**options)
            self.assertEqual(code, 1)
            self.assertNotIn("actual_model", report)
