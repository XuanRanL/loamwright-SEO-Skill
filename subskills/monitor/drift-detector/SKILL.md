---
name: drift-detector
description: 17-rule diff vs SQLite baseline. Detects: title/meta changed, schema removed, H1 changed, AI bots policy changed, broken internal links emerged, AIO citation lost, etc. Triggered by /drift command or scheduled weekly.
allowed-tools: [Read, Write, Bash]
---

# Drift Detector

Per claude-seo 17-rule diff pattern.

## Workflow

```
1. python -m scripts.monitor.drift_baseline --site {slug} --url {url}  # snapshot
2. python -m scripts.monitor.drift_compare --site {slug} --baseline {sha}  # 17 rules

Output: drift-report-{date}.json with 3 severity levels
```

## 17 rules (per claude-seo)

| Rule | Severity |
|---|---|
| 1. Title tag changed | high |
| 2. Meta description changed | medium |
| 3. H1 changed | high |
| 4. Canonical URL changed | high |
| 5. Robots meta changed (noindex added) | critical |
| 6. JSON-LD schema removed | high |
| 7. JSON-LD schema type changed | medium |
| 8. Featured image removed | medium |
| 9. Internal links count -20%+ | medium |
| 10. External Tier-1 link removed | high |
| 11. Word count dropped >30% | high |
| 12. H2 count changed by ±2 | medium |
| 13. AIO citation lost | critical |
| 14. Broken outbound link emerged | medium |
| 15. AI bots robots.txt policy changed | high |
| 16. SSL/HTTPS broken | critical |
| 17. dateModified missing | low |

## Cross-skill recommendations

Per rule, suggest:
- 5/13 → trigger ai-overview-recovery
- 9/14 → trigger internal-linker / link verification
- 6/7 → trigger schema-generator
- 1/3/11 → likely manual review needed
- 16 → halt all operations; site emergency

## See also
- `scripts/monitor/drift_baseline.py` (TODO)
- `scripts/monitor/drift_compare.py` (TODO)
