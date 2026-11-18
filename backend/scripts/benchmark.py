"""Deterministic evaluation harness for the Zorvy risk pipeline.

The harness runs the same in-process pipeline the API uses for text input
(evidence extraction -> URL intelligence -> risk engine), scores every
labelled case in ``data/test_cases/zorvy_test_cases.json`` and reports
accuracy, confusion, per-signal detection and latency.

It deliberately does not touch the network, an LLM or a database, so a
result is reproducible and can be quoted to an investor or auditor.

Usage::

    cd backend
    uv run python -m scripts.benchmark
    uv run python -m scripts.benchmark --json out.json --markdown report.md
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.evidence_extractor import EvidenceExtractor
from app.services.risk_engine import assess_risk
from app.services.url_intelligence import URLIntelligence

ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = ROOT / "data" / "test_cases" / "zorvy_test_cases.json"
DEFAULT_JSON = ROOT / "docs" / "zorvy" / "benchmark-results.json"
DEFAULT_MARKDOWN = ROOT / "docs" / "zorvy" / "BENCHMARK-REPORT.md"

LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
ORDINAL = {level: index for index, level in enumerate(LEVELS)}
HIGH_RISK = {"HIGH", "CRITICAL"}
LOW_RISK = {"LOW", "MEDIUM"}


@dataclass
class CaseResult:
    id: str
    name: str
    category: str
    expected_level: str
    actual_level: str
    score: int
    expected_signals: list[str]
    detected_signals: list[str]
    missing_signals: list[str]
    unexpected_signals: list[str]
    url_count: int
    latency_ms: float

    @property
    def level_correct(self) -> bool:
        return self.expected_level == self.actual_level

    @property
    def ordinal_distance(self) -> int:
        return abs(ORDINAL[self.expected_level] - ORDINAL[self.actual_level])

    @property
    def dangerous_miss(self) -> bool:
        """A harmful case rated LOW or MEDIUM."""

        return self.expected_level in HIGH_RISK and self.actual_level in LOW_RISK

    @property
    def false_alarm(self) -> bool:
        """A benign case rated HIGH or CRITICAL."""

        return self.expected_level == "LOW" and self.actual_level in HIGH_RISK


@dataclass
class Metrics:
    cases: int
    level_accuracy: float
    ordinal_accuracy: float
    macrolevel_f1: float
    signal_precision: float
    signal_recall: float
    signal_f1: float
    signal_expected: int
    signal_found: int
    signal_predicted: int
    dangerous_misses: int
    false_alarms: int
    latency_mean_ms: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_max_ms: float
    confusion: dict[str, dict[str, int]] = field(default_factory=dict)
    per_level: dict[str, dict[str, float]] = field(default_factory=dict)
    per_category: dict[str, dict[str, float]] = field(default_factory=dict)


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise SystemExit(f"No cases found in {path}")
    return cases


def run_case(case: dict[str, Any]) -> CaseResult:
    started = time.perf_counter()

    extracted = EvidenceExtractor.extract(case["message"])
    urls = [URLIntelligence.analyze(url) for url in extracted["urls"]]

    signals = [*extracted["risk_indicators"], *extracted["categories"]]
    if any(result["risk_indicators"] for result in urls):
        signals.append("suspicious_url")

    risk = assess_risk(signals, extracted)

    latency_ms = (time.perf_counter() - started) * 1000

    detected = sorted({signal.lower() for signal in signals})
    expected = sorted({signal.lower() for signal in case["expected_signals"]})

    return CaseResult(
        id=case["id"],
        name=case["name"],
        category=case["category"],
        expected_level=case["expected_risk"],
        actual_level=risk.level,
        score=risk.score,
        expected_signals=expected,
        detected_signals=detected,
        missing_signals=sorted(set(expected) - set(detected)),
        unexpected_signals=sorted(set(detected) - set(expected)),
        url_count=len(urls),
        latency_ms=round(latency_ms, 3),
    )


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _f1(precision: float, recall: float) -> float:
    return _ratio(2 * precision * recall, precision + recall)


def compute_metrics(results: list[CaseResult]) -> Metrics:
    confusion = {
        expected: {actual: 0 for actual in LEVELS} for expected in LEVELS
    }

    true_positives = {level: 0 for level in LEVELS}
    predicted = {level: 0 for level in LEVELS}
    actual = {level: 0 for level in LEVELS}

    for result in results:
        confusion[result.expected_level][result.actual_level] += 1
        actual[result.expected_level] += 1
        predicted[result.actual_level] += 1
        if result.expected_level == result.actual_level:
            true_positives[result.expected_level] += 1

    per_level: dict[str, dict[str, float]] = {}
    for level in LEVELS:
        precision = _ratio(true_positives[level], predicted[level])
        recall = _ratio(true_positives[level], actual[level])
        per_level[level] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(_f1(precision, recall), 4),
            "support": actual[level],
        }

    categories: dict[str, dict[str, float]] = {}
    for result in results:
        bucket = categories.setdefault(
            result.category, {"cases": 0, "level_correct": 0, "signal_expected": 0, "signal_found": 0}
        )
        bucket["cases"] += 1
        bucket["level_correct"] += int(result.level_correct)
        bucket["signal_expected"] += len(result.expected_signals)
        bucket["signal_found"] += len(result.expected_signals) - len(result.missing_signals)

    per_category: dict[str, dict[str, float]] = {}
    for category, bucket in sorted(categories.items()):
        cases = bucket["cases"]
        per_category[category] = {
            "cases": cases,
            "level_accuracy": round(_ratio(bucket["level_correct"], cases), 4),
            "signal_expected": bucket["signal_expected"],
            "signal_recall": round(
                _ratio(bucket["signal_found"], bucket["signal_expected"]), 4
            )
            if bucket["signal_expected"]
            else 0.0,
        }

    signal_expected = sum(len(result.expected_signals) for result in results)
    signal_found = sum(
        len(result.expected_signals) - len(result.missing_signals) for result in results
    )
    signal_predicted = sum(len(result.detected_signals) for result in results)
    signal_precision = _ratio(signal_found, signal_predicted)
    signal_recall = _ratio(signal_found, signal_expected)

    latencies = [result.latency_ms for result in results]
    ordered = sorted(latencies)
    p95_index = min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))

    return Metrics(
        cases=len(results),
        level_accuracy=round(_ratio(sum(r.level_correct for r in results), len(results)), 4),
        ordinal_accuracy=round(
            _ratio(sum(r.ordinal_distance <= 1 for r in results), len(results)), 4
        ),
        macrolevel_f1=round(
            sum(per_level[level]["f1"] for level in LEVELS) / len(LEVELS), 4
        ),
        signal_precision=round(signal_precision, 4),
        signal_recall=round(signal_recall, 4),
        signal_f1=round(_f1(signal_precision, signal_recall), 4),
        signal_expected=signal_expected,
        signal_found=signal_found,
        signal_predicted=signal_predicted,
        dangerous_misses=sum(result.dangerous_miss for result in results),
        false_alarms=sum(result.false_alarm for result in results),
        latency_mean_ms=round(statistics.fmean(latencies), 3),
        latency_p50_ms=round(statistics.median(latencies), 3),
        latency_p95_ms=round(ordered[p95_index], 3),
        latency_max_ms=round(ordered[-1], 3),
        confusion=confusion,
        per_level=per_level,
        per_category=per_category,
    )


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def render_markdown(
    results: list[CaseResult],
    metrics: Metrics,
    dataset_name: str,
) -> str:
    lines: list[str] = []

    lines.append("# Zorvy Benchmark Report")
    lines.append("")
    lines.append(
        "Generated by `backend/scripts/benchmark.py`. Deterministic, offline and "
        "LLM-free: the same command on the same commit produces the same verdicts."
    )
    lines.append("")
    lines.append(f"- Dataset: `{dataset_name}`")
    lines.append(f"- Cases: **{metrics.cases}**")
    lines.append(f"- Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")

    lines.append("## Headline")
    lines.append("")
    lines.append("| Metric | Value | What it means |")
    lines.append("| --- | --- | --- |")
    lines.append(
        f"| Risk-level accuracy | **{_percent(metrics.level_accuracy)}** | "
        "Verdict band matches the label exactly. |"
    )
    lines.append(
        f"| Within-one-band accuracy | {_percent(metrics.ordinal_accuracy)} | "
        "Verdict is at most one band away from the label. |"
    )
    lines.append(
        f"| Macro F1 (4 bands) | {metrics.macrolevel_f1:.4f} | "
        "Balances performance across LOW/MEDIUM/HIGH/CRITICAL. |"
    )
    lines.append(
        f"| Signal F1 | {metrics.signal_f1:.4f} | "
        "Precision/recall over expected evidence signals. |"
    )
    lines.append(
        f"| Dangerous misses | **{metrics.dangerous_misses}** | "
        "Harmful case rated LOW or MEDIUM. Target: 0. |"
    )
    lines.append(
        f"| False alarms | **{metrics.false_alarms}** | "
        "Benign case rated HIGH or CRITICAL. Target: 0. |"
    )
    lines.append(
        f"| Latency p50 / p95 | {metrics.latency_p50_ms:.2f} / "
        f"{metrics.latency_p95_ms:.2f} ms | In-process engine, no network or LLM. |"
    )
    lines.append("")

    lines.append("## Confusion matrix")
    lines.append("")
    header = "| expected / actual | " + " | ".join(LEVELS) + " |"
    divider = "| --- | " + " | ".join("---:" for _ in LEVELS) + " |"
    lines.append(header)
    lines.append(divider)
    for expected in LEVELS:
        row = " | ".join(str(metrics.confusion[expected][actual]) for actual in LEVELS)
        lines.append(f"| **{expected}** | {row} |")
    lines.append("")

    lines.append("## Per-band performance")
    lines.append("")
    lines.append("| Band | Support | Precision | Recall | F1 |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for level in LEVELS:
        stats = metrics.per_level[level]
        lines.append(
            f"| {level} | {int(stats['support'])} | {stats['precision']:.3f} | "
            f"{stats['recall']:.3f} | {stats['f1']:.3f} |"
        )
    lines.append("")

    lines.append("## Signal detection")
    lines.append("")
    lines.append(
        f"Across all cases the pipeline found {metrics.signal_found} of "
        f"{metrics.signal_expected} expected signals "
        f"({metrics.signal_recall:.1%} recall) and emitted "
        f"{metrics.signal_predicted} signals in total "
        f"({metrics.signal_precision:.1%} precision, F1 {metrics.signal_f1:.3f}). "
        "Unexpected signals are not automatically wrong - the extractor may surface real "
        "evidence the label did not enumerate - so precision is reported as a lower bound."
    )
    lines.append("")
    lines.append("| Category | Cases | Level accuracy | Signal recall |")
    lines.append("| --- | ---: | ---: | ---: |")
    for category, stats in metrics.per_category.items():
        signal_recall = (
            _percent(stats["signal_recall"])
            if stats["signal_expected"]
            else "n/a (no expected signals)"
        )
        lines.append(
            f"| {category} | {int(stats['cases'])} | "
            f"{_percent(stats['level_accuracy'])} | {signal_recall} |"
        )
    lines.append("")

    lines.append("## Per-case results")
    lines.append("")
    lines.append("| ID | Case | Expected | Actual | Score | Missing signals |")
    lines.append("| --- | --- | --- | --- | ---: | --- |")
    for result in results:
        missing = ", ".join(result.missing_signals) or "—"
        flag = ""
        if result.dangerous_miss:
            flag = " **DANGEROUS MISS**"
        elif result.false_alarm:
            flag = " **FALSE ALARM**"
        lines.append(
            f"| {result.id} | {result.name} | {result.expected_level} | "
            f"{result.actual_level}{flag} | {result.score} | {missing} |"
        )
    lines.append("")

    lines.append("## Method")
    lines.append("")
    lines.append(
        "Each case runs the production text pipeline in-process: "
        "`EvidenceExtractor.extract` -> `URLIntelligence.analyze` per URL -> "
        "`RiskEngine.calculate_risk`. No LLM, no network, no database, no "
        "randomness. The risk engine is deterministic and the URL analysis is "
        "pure Python, so repeated runs are stable."
    )
    lines.append("")
    lines.append("## Honest limits")
    lines.append("")
    lines.append(
        f"- The dataset is **{metrics.cases} hand-written cases**, not a sample of "
        "real traffic. It proves the engine behaves as specified; it does not "
        "estimate field accuracy."
    )
    lines.append(
        "- Labels were written by the project author. There is no inter-annotator "
        "agreement study and no held-out test set yet."
    )
    lines.append(
        "- The corpus is mixed: 20 Pakistan-flavoured cases plus 8 India-focused cases. "
        "There are no Indian-language (Hindi, Tamil, Bengali) cases yet, and the sample is "
        "far too small for per-market claims."
    )
    lines.append(
        "- Latency is a single-process measurement on the machine that generated "
        "this report. It excludes HTTP, database and upload time, and it is not a "
        "capacity or throughput claim."
    )
    lines.append(
        "- A high score means a communication warrants verification. It is not "
        "proof of fraud, and a low score is not proof of safety."
    )
    lines.append("")
    lines.append("## Reproduce")
    lines.append("")
    lines.append("```bash")
    lines.append("cd backend")
    lines.append("uv run python -m scripts.benchmark")
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def _summary(
    results: list[CaseResult],
    metrics: Metrics,
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "metrics": asdict(metrics),
        "cases": [
            {**asdict(result), "level_correct": result.level_correct} for result in results
        ],
    }


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=CASES_PATH)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown", type=Path, default=None)
    args = parser.parse_args(argv)

    cases = load_cases(args.cases)
    results = [run_case(case) for case in cases]
    metrics = compute_metrics(results)

    payload = _summary(results, metrics)

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    markdown = render_markdown(
        results,
        metrics,
        args.cases.relative_to(ROOT).as_posix()
        if args.cases.is_relative_to(ROOT)
        else str(args.cases),
    )

    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(markdown, encoding="utf-8")

    print(markdown)
    print(f"JSON written to {args.json}")
    if args.markdown:
        print(f"Markdown written to {args.markdown}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
