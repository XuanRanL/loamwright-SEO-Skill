---
name: chart-generator
description: Generate markdown tables OR XSS-safe SVG charts for sections with needs_table=true. Ensures ≥2 tables per article with ≥1 in front 50%. Uses scripts/build/chart_svg_builder.py.
allowed-tools: [Read, Write, Bash]
---

# Chart Generator

Fills in tables/charts where outline-architect marked needs_table=true.

## Workflow
```
1. For each section with needs_table=true:
   - LLM designs table structure (columns + 4-10 rows)
   - python -m scripts.build.chart_svg_builder --input table.json --type table
2. Verify final article has ≥2 tables
3. Verify ≥1 table in first 50% of article
4. Inject tables at the outline-architect specified positions
```

## Default: markdown tables (safe)
Always generates GFM markdown tables unless `chart_type` is explicit "bar" / "pie" / "line".

## SVG charts (XSS-safe)
Per claude-blog pattern: no inline scripts, no event attributes, CSS-only hover.

## See also
- `scripts/build/chart_svg_builder.py`
