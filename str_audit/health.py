"""Listing Health Score — our composite signal (rule 5).

A property manager shouldn't have to read four dots; they should see
"62/100, Needs work" at a glance. Formula is fully printed on the PDF:

    start at 100
    - each FAIL signal:    -25
    - each WARN signal:    -12
    - UNKNOWN photo count: -5  (absence of evidence is itself a risk)
    clamp to [0, 100]

Transparent on purpose — no weighting magic. Label bands:
  >= 85 Healthy · 70–84 Solid but leaky · 50–69 Needs work · < 50 At risk
"""

from __future__ import annotations

LABELS = [(85, "Healthy"), (70, "Solid but leaky"), (50, "Needs work"), (0, "At risk")]


def health_score(signals: list[dict]) -> dict:
    score = 100
    deductions = []
    for s in signals:
        status = s.get("status")
        key = s.get("key", "signal")
        if status == "fail":
            score -= 25
            deductions.append(f"−25 {key.replace('_', ' ')} (fail)")
        elif status == "warn":
            score -= 12
            deductions.append(f"−12 {key.replace('_', ' ')} (warn)")
        elif status == "unknown":
            score -= 5
            deductions.append(f"−5 {key.replace('_', ' ')} (unknown)")
    score = max(0, min(100, score))
    label = next(lbl for cutoff, lbl in LABELS if score >= cutoff)
    return {
        "score": score,
        "label": label,
        "deductions": deductions,
        "formula": ("Start 100; −25 per failing signal, −12 per warning, "
                    "−5 for unknown photo count; clamped to [0, 100]."),
    }
