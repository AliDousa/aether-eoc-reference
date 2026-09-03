"""Redaction applied before any text leaves the process for a model.

The fixtures in this repository are synthetic, so in practice there is nothing
here worth protecting. The redactor exists anyway, and runs unconditionally,
because the interesting property of a reference implementation is the *shape*
of the control: an operator reading this repo should be able to see exactly
where the boundary is and what crosses it.

Two rules:

1. Operator display names are replaced with role-shaped tokens
   (``LOGISTICS-2``), never sent as names.
2. Anything matching a contact-detail or identifier pattern is masked, even
   though the seeded corpus contains none.

``assert_clean`` is used by the tests to prove rule 2 holds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.enums import IcsRole

# Patterns that must never reach an external endpoint. Ordered most specific
# first so an email is not partially eaten by the digit-run rule.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("[EMAIL]", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("[PHONE]", re.compile(r"(?<![\w.])\+?\d[\d\s().-]{7,}\d(?![\w.])")),
    # Long unbroken digit runs: national ID / MRN shaped.
    ("[ID]", re.compile(r"\b\d{9,}\b")),
    ("[IPV4]", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("[URL]", re.compile(r"\bhttps?://\S+", re.IGNORECASE)),
)

_ROLE_TOKENS: dict[IcsRole, str] = {
    IcsRole.INCIDENT_COMMANDER: "IC",
    IcsRole.OPERATIONS_SECTION: "OPERATIONS",
    IcsRole.LOGISTICS_SECTION: "LOGISTICS",
    IcsRole.PLANNING_SECTION: "PLANNING",
}


@dataclass(frozen=True)
class RedactionMap:
    """Display-name to role-token substitutions for one incident."""

    substitutions: dict[str, str]

    def apply(self, text: str) -> str:
        out = text
        # Longest names first, so "Operator North Lead" is not half-replaced by
        # a shorter overlapping name.
        for name in sorted(self.substitutions, key=len, reverse=True):
            if name:
                out = re.sub(re.escape(name), self.substitutions[name], out, flags=re.IGNORECASE)
        return out


def role_token(role: IcsRole, index: int = 1) -> str:
    return f"{_ROLE_TOKENS.get(role, 'OPERATOR')}-{index}"


def build_map(operators: list[tuple[str, IcsRole]]) -> RedactionMap:
    """Build display-name -> role-token substitutions.

    ``operators`` is a list of ``(display_name, ics_role)`` pairs. Indexes are
    assigned per role in the order given, so the mapping is stable for a given
    incident and the same person reads as the same token across a transcript.
    """
    counters: dict[IcsRole, int] = {}
    substitutions: dict[str, str] = {}
    for display_name, role in operators:
        counters[role] = counters.get(role, 0) + 1
        substitutions[display_name] = role_token(role, counters[role])
    return RedactionMap(substitutions=substitutions)


def scrub(text: str) -> str:
    """Mask contact details and identifier-shaped strings."""
    out = text
    for replacement, pattern in _PATTERNS:
        out = pattern.sub(replacement, out)
    return out


def redact(text: str, mapping: RedactionMap | None = None) -> str:
    """Full outbound redaction: names to role tokens, then pattern scrubbing."""
    out = mapping.apply(text) if mapping else text
    return scrub(out)


def find_violations(text: str) -> list[str]:
    """Return the patterns still present. Empty list means clean."""
    return [label for label, pattern in _PATTERNS if pattern.search(text)]


def assert_clean(text: str) -> None:
    """Raise if redaction missed something. Used as a pre-send tripwire."""
    violations = find_violations(text)
    if violations:
        raise ValueError(f"Refusing to send text containing {', '.join(violations)}.")
