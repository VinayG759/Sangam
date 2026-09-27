"""
The anti-hallucination check. Every number in a generated summary must match
a value in the evidence bundle it was given, or the summary is rejected.
"""

import re

_NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")


def _forms(value: float) -> set[float]:
    """The ways a fact's value may legitimately be written: exact, or rounded."""
    return {round(value, 2), round(value, 1), float(round(value))}


def allowed_numbers(facts: list[dict]) -> set[float]:
    allowed: set[float] = set()
    for fact in facts:
        for field in ("value", "period"):
            raw = fact.get(field)
            if isinstance(raw, (int, float)):
                allowed |= _forms(float(raw))
            elif isinstance(raw, str):
                for match in _NUMBER.findall(raw):
                    allowed |= _forms(float(match.replace(",", "")))
    return allowed


def unsupported_numbers(text: str, facts: list[dict]) -> list[str]:
    """Numbers in text that no fact supports. Empty list = the text passes."""
    allowed = allowed_numbers(facts)
    bad = []
    for match in _NUMBER.findall(text):
        number = float(match.replace(",", ""))
        if not any(abs(number - a) < 1e-9 for a in allowed):
            bad.append(match)
    return bad
