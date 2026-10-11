#!/usr/bin/env python3
"""Check the configured generation route using a small actual screening sample."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def verify(screening_report: Path, output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    screening = json.loads(screening_report.read_text(encoding="utf-8"))
    summary = {"status": "failed", "screening_date": screening.get("date"),
               "purpose": "sample report generation, not a full-stock analysis",
               "notifications_sent": False}
    try:
        samples = screening.get("sample_evaluations", [])
        if screening.get("status") != "complete" or not samples:
            raise ValueError("screening must have a completed sample with actual evaluations")
        from src.config import get_config
        from src.analyzer import GeminiAnalyzer

        config = get_config()
        requested = config.litellm_model
        if not requested:
            raise ValueError("no explicit analysis model configured")
        summary["requested_model"] = requested
        analyzer = GeminiAnalyzer(config=config)
        if not analyzer.is_available():
            raise ValueError("configured generation backend unavailable")
        prompt = (
            "这是一项软件通路验证。请用中文写一份简短验证报告，依据下面实际样本的 J、DIF、"
            "avg_high、avg_low 核对 J<18 且 DIF>0 且 avg_high>4*avg_low。"
            "说明样本中是否有命中，不推断全市场结果，不编造新闻，也不提出买卖建议。\n"
            + json.dumps({"date": screening["date"], "samples": samples[:3]}, ensure_ascii=False)
        )
        result = analyzer.generate_text_with_metadata(prompt, max_tokens=2048, temperature=0.7)
        if result is None or not result.text.strip():
            raise RuntimeError("model returned no usable report")
        summary.update({"actual_model": result.model, "backend": result.backend,
                        "provider": result.provider, "report": result.text})
        if str(result.model).split("/", 1)[-1] != str(requested).split("/", 1)[-1]:
            raise RuntimeError("actual model differs from configured model")
        summary["status"] = "passed"
        print(f"Model verification passed: {result.model}")
        return 0
    except Exception as exc:
        # Keep credentials, provider request bodies and arbitrary error text out
        # of the public artifact. Existing application logs diagnose the route.
        summary["error_type"] = type(exc).__name__
        print(f"Model verification failed ({type(exc).__name__}); inspect application logs", file=sys.stderr)
        return 1
    finally:
        output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screening-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    return verify(args.screening_report, args.output)


if __name__ == "__main__":
    sys.exit(main())
