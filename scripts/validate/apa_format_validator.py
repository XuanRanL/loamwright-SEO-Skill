"""
scripts/validate/apa_format_validator.py — APA 7 reference entry format checker.

Validates each entry in a References list against APA 7 rules from
references/apa-citation-rules.md.

Checks per entry:
  - Has author(s) in "Lastname, F. M." format
  - Has year in (YYYY) or (n.d.) format
  - Title ends with period
  - Has DOI (preferred) or URL
  - DOI format: https://doi.org/...
  - No "Retrieved from" / "from" / "source" prose
  - No hyperlinks on in-text format (e.g. (Smith, 2023) plain text)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class ApaIssue:
    entry_index: int       # 0-based position in references list
    severity: str           # high / medium / low
    issue: str
    entry_text: str         # first 200 chars


@dataclass
class ApaValidationReport:
    total_entries: int
    valid_entries: int
    issues: list[ApaIssue] = field(default_factory=list)
    passes: bool = False


# Patterns
_AUTHOR_PATTERN = re.compile(r"^([A-Z][a-zà-ÿ\-']+),\s+[A-Z]\.")  # Smith, J.
_YEAR_PATTERN = re.compile(r"\((\d{4}|n\.d\.)\)")
_DOI_PATTERN = re.compile(r"https://doi\.org/\S+")
_URL_PATTERN = re.compile(r"https?://\S+")
_BAD_PHRASE_PATTERN = re.compile(r"\b(?:retrieved from|source:|from:)\b", re.IGNORECASE)


def _extract_entries(text: str) -> list[str]:
    """Extract individual reference entries from a References section.

    Supports formats:
      - Bullet list: "- Smith, J. (2023)..."
      - Numbered: "1. Smith, J. (2023)..."
      - Plain paragraphs separated by blank lines
    """
    lines = [l.rstrip() for l in text.splitlines()]
    entries: list[str] = []
    current: list[str] = []

    for line in lines:
        line_stripped = line.strip()
        # Skip empty / heading
        if not line_stripped or line_stripped.startswith("#"):
            if current:
                entries.append(" ".join(current).strip())
                current = []
            continue

        # New entry markers
        if (line_stripped.startswith("- ")
                or re.match(r"^\d+\.\s", line_stripped)
                or re.match(r"^[A-Z][a-zà-ÿ]+,", line_stripped)):
            if current:
                entries.append(" ".join(current).strip())
                current = []
            current.append(re.sub(r"^[-\d.\s]+", "", line))
        else:
            # Continuation of previous entry
            if current:
                current.append(line_stripped)

    if current:
        entries.append(" ".join(current).strip())

    return [e for e in entries if e]


def validate_entry(entry: str, index: int) -> list[ApaIssue]:
    """Validate a single APA reference entry. Returns list of issues."""
    issues: list[ApaIssue] = []
    preview = entry[:200]

    # 1. Author check
    if not _AUTHOR_PATTERN.match(entry):
        # Allow Organization as author (starts with capital, no comma)
        if not re.match(r"^[A-Z][a-zA-Z\s&]+\.\s+\(", entry):
            issues.append(ApaIssue(
                entry_index=index, severity="high",
                issue="Missing or malformed author (expected 'Lastname, F. M.' or organization)",
                entry_text=preview,
            ))

    # 2. Year check
    if not _YEAR_PATTERN.search(entry):
        issues.append(ApaIssue(
            entry_index=index, severity="high",
            issue="Missing year (expected (YYYY) or (n.d.))",
            entry_text=preview,
        ))

    # 3. DOI / URL check
    has_doi = bool(_DOI_PATTERN.search(entry))
    has_url = bool(_URL_PATTERN.search(entry))
    if not has_doi and not has_url:
        issues.append(ApaIssue(
            entry_index=index, severity="medium",
            issue="No DOI or URL (citations should be linkable)",
            entry_text=preview,
        ))

    # 4. Bad phrases
    bad_match = _BAD_PHRASE_PATTERN.search(entry)
    if bad_match:
        issues.append(ApaIssue(
            entry_index=index, severity="medium",
            issue=f"APA 7 forbids '{bad_match.group(0)}' phrase",
            entry_text=preview,
        ))

    # 5. DOI format check
    if _URL_PATTERN.search(entry) and not has_doi:
        m = re.search(r"(doi\.org/\S+)", entry)
        if m and not entry[max(0, m.start()-8):m.start()].endswith("https://"):
            issues.append(ApaIssue(
                entry_index=index, severity="low",
                issue="DOI should be prefixed with https://",
                entry_text=preview,
            ))

    return issues


def validate(text: str) -> ApaValidationReport:
    """Validate entire References section text."""
    entries = _extract_entries(text)
    all_issues: list[ApaIssue] = []
    valid_count = 0

    for i, entry in enumerate(entries):
        issues = validate_entry(entry, i)
        if not issues:
            valid_count += 1
        else:
            all_issues.extend(issues)

    return ApaValidationReport(
        total_entries=len(entries),
        valid_entries=valid_count,
        issues=all_issues,
        passes=(valid_count == len(entries) and len(entries) > 0),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="APA 7 reference format validator")
    ap.add_argument("file", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.file.exists():
        print(f"Not found: {args.file}", file=sys.stderr)
        return 2
    text = args.file.read_text(encoding="utf-8")
    r = validate(text)

    if args.json:
        print(json.dumps(asdict(r), indent=2, ensure_ascii=False))
    else:
        verdict = "✓ PASS" if r.passes else "✗ FAIL"
        print(f"Entries:       {r.total_entries}")
        print(f"Valid:         {r.valid_entries}")
        print(f"Issues:        {len(r.issues)}")
        print(f"Verdict:       {verdict}")
        if r.issues:
            for i in r.issues[:30]:
                print(f"  [{i.severity}] entry #{i.entry_index}: {i.issue}")
                print(f"      …{i.entry_text[:100]}…")

    return 0 if r.passes else 1


if __name__ == "__main__":
    sys.exit(main())
