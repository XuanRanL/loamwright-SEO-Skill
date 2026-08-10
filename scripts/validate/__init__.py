"""scripts/validate — quality gates and content scoring.

Modules:
    title_validator       — SEO title hard checks (keyword + power word + digit + length)
    link_resolver         — HEAD-check URLs; detect 404 / grounding-redirect / 302 chains
    apa_format_validator  — APA 7 reference entry format validation
    schema_validator      — JSON-LD validity + deprecated type detection
    word_count            — accurate word count excluding markdown
    core_eeat_scorer      — 80-item CORE-EEAT gate
    cite_scorer           — 40-item CITE gate
    ai_slop_score         — AI-Slop formula (4×P + 25×(1-B) + 15×V)
"""
