# Project Folder Layout · Canonical Spec

Every project (per site / per client) lives in `projects/{slug}/` with this exact structure. All scripts, agents, and skills resolve paths via `scripts/_core/project_paths.py` — never hardcode paths anywhere else.

## Layout

```
projects/{slug}/
├── project.yaml                       Root — metadata (site_url, client, vertical)
├── internal-links-map.md              Root — frequently consulted, auto-updated on publish
├── KNOWN_ISSUES.md                    Root — project-specific known issues (optional)
├── .gitignore                         Root — auto-generated; excludes secrets + volatile state
│
├── .seo/                              HIDDEN — runtime state + cache
│   ├── state.json                     Active pipeline state for this project
│   ├── change-log.json                7-day undo log (publish actions)
│   ├── wp-taxonomy-cache.json         WP category/tag ID cache (24h TTL)
│   ├── baselines/
│   │   └── drift.sqlite               drift_baseline SHA-256 snapshots
│   ├── archive/                       gitignored — old artifacts
│   ├── backups/                       gitignored — pre-mutation snapshots
│   ├── summaries/                     auto-generated rolling summaries
│   └── observability/                 gitignored — debug + trace logs
│
├── brand/                             Brand assets (one-time + slow evolution)
│   ├── brand-guideline.yaml           7-Block + AI visibility profile
│   ├── brand-config.json              setup_wizard output (voice_pair, banned_words)
│   ├── personas/
│   │   └── {persona-id}.json          Multi-audience variants
│   └── voice-samples/                 URL-extracted brand voice samples
│
├── research/                          Research outputs
│   ├── business-context.md            /init Stage 2-3 business scan
│   ├── competitors.json               /init Stage 9 competitor analysis
│   ├── seo-baseline.json              /init Stage 6-7 SEO baseline
│   ├── target-keywords.md             /init Stage 6 prioritized targets
│   ├── keyword-universe.md            /init Stage 6 full keyword universe
│   ├── content-gaps.json              /init Stage 10 content gap analysis
│   └── ai-probes/
│       └── {date}.json                AI engine recognition probes
│
├── articles/                          Published articles archive
│   └── {article-slug}/
│       ├── final.md                   Source markdown
│       ├── final.html                 WordPress-ready HTML
│       ├── meta.json                  Title / slug / excerpt / tags
│       ├── schema.json          JSON-LD @graph
│       ├── citations.json             Verified citations + APA
│       ├── features.json              Extracted features (for outcome_tagger)
│       ├── publish-log.json           Publish action record
│       └── review.json                Independent reviewer verdict
│
├── clusters/                          Topic cluster plans + scorecards
│   └── {seed-keyword-slug}/
│       ├── cluster-plan.json
│       ├── cluster-map.html           XSS-safe SVG visualization
│       └── cluster-scorecard.md       Post-execution audit
│
├── metrics/                           External API data pulls
│   ├── gsc-api-daily-{date}.json
│   ├── gsc-api-weekly-{date}.json
│   ├── gsc-api-last-28-{date}.json
│   ├── gsc-csv-{date}.json            Manual GSC CSV imports
│   └── bing-{period}-{date}.json
│
├── audits/                            All reports + monitor outputs
│   ├── outcomes.json                  winner/mid/loser tagging
│   ├── rank-history/
│   │   └── {date}.json                T+7/14/30/90 tracking
│   ├── drift-reports/
│   │   └── {url-slug}-{date}.json     17-rule diff per URL
│   ├── ai-citations/
│   │   └── {date}.json                Cross-portfolio AI citation snapshots
│   ├── refresh-queue.json             Articles flagged for /rewrite
│   ├── cross-link-suggestions-{date}.json
│   ├── perf-{period}-{date}.md        Period performance report
│   ├── brand-tuner-report-{date}.json brand_auto_tuner output
│   └── brand-guideline.diff.{date}.yaml Suggested brand-guideline updates
│
├── assets/                            Media assets
│   └── images/
│       └── {article-slug}/
│           ├── cover.webp
│           ├── section_1.webp
│           ├── section_2.webp
│           ├── section_3.webp
│           ├── *.meta.json            Per-image metadata (alt, caption, filename)
│           └── tmp/                   gitignored — pre-processing originals
│
└── credentials/                       GITIGNORED — API keys + WP App passwords
    ├── wordpress.json                 { url, username, app_password }
    ├── gsc-oauth.json                 Per-site GSC OAuth refresh token
    ├── bing-webmaster.json            Bing Webmaster API key
    └── dataforseo.json                DataForSEO API credentials
```

## Root-level files (visible)

| File | Purpose | Created by |
|---|---|---|
| `project.yaml` | Site metadata (URL, client, vertical, etc.) | `/init` Stage 1 |
| `internal-links-map.md` | Internal link map | `/init` Stage 11; auto-updated on publish |
| `KNOWN_ISSUES.md` | Project-specific known issues | Optional, manual |
| `.gitignore` | Per-project gitignore for secrets + volatile state | Auto-generated by `ensure_project_tree` |

Everything else lives in a subdirectory.

## Hidden state (.seo/)

The `.seo/` folder follows the convention from `.git/` or `.vscode/` — dotted-prefix means "tooling artifact, not user content."

**Tracked in git** (so projects can be cloned/shared):
- `state.json` — current pipeline state
- `change-log.json` — publish history (for undo + rollback)
- `wp-taxonomy-cache.json` — WP taxonomy cache (24h TTL)
- `baselines/drift.sqlite-schema` — schema only, not data

**Gitignored** (volatile / large / not portable):
- `observability/` — debug logs from pipeline runs
- `backups/` — pre-mutation snapshots
- `archive/` — historical artifacts past retention period
- `baselines/*.sqlite` — actual baseline DBs are local-only

## Multi-tenant isolation

Cross-project data leakage is a critical risk for agency use. Hard rules:

1. **Never** read from another project's folder during operations on a different project
2. **Never** copy data between project folders without explicit user direction
3. **Credentials** are per-project; never globalize WP app passwords
4. **Personas + voice samples** are per-project; one client's voice doesn't poison another's
5. **Outcomes + brand-tuner data** are per-project; one client's winner patterns don't bleed to another's brand

## File operations conventions

### Atomic writes
For files that scripts mutate (state.json, change-log.json, outcomes.json):
1. Write to temp file in same directory (`outcomes.json.tmp`)
2. fsync
3. Atomic rename to target name

Prevents partial writes on crash.

### Cache TTLs
| File | TTL | Behavior on expiry |
|---|---|---|
| `wp-taxonomy-cache.json` | 24h | Re-query WP REST + rewrite |
| `metrics/gsc-*.json` | 7d | Re-pull via gsc_api_ingest |
| `ai-probes/*.json` | 30d | Re-probe via ai_search_probe |
| `competitors.json` | 90d | Re-run /init Stage 9 |

## Resolving paths in code

Always use `scripts/_core/project_paths.py`:

```python
from scripts._core.project_paths import (
    project_root, brand_dir, research_dir, audits_dir,
    outcomes_path, state_path, brand_guideline_path,
)

# Resolve a directory
out = audits_dir("client-a") / "drift-reports" / "post-1-2026-05-19.json"

# Resolve a specific file
outcomes = outcomes_path("client-a")

# Ensure tree exists (e.g., during /init)
from scripts._core.project_paths import ensure_project_tree
ensure_project_tree("client-a")

# Health check
from scripts._core.project_paths import health_check
print(health_check("client-a"))
```

### CLI usage

```bash
# Create the standard tree for a new project
python -m scripts._core.project_paths init client-a-saas

# List all projects
python -m scripts._core.project_paths list

# Health-check a project
python -m scripts._core.project_paths check client-a-saas

# Resolve a standard path
python -m scripts._core.project_paths path client-a-saas outcomes
# → projects/client-a-saas/audits/outcomes.json
```

## Migration from flat layout (legacy → standard)

For existing projects that had the flat layout (everything in root), run:

```bash
python -m scripts._core.project_paths init {slug}     # Creates missing subdirs
# Then manually move existing files into their new homes:
#   outcomes.json → audits/outcomes.json
#   drift-reports/ → audits/drift-reports/
#   brand-guideline.yaml → brand/brand-guideline.yaml
#   etc.
```

Migration is a manual checklist today — no `/project-migrate` skill exists (a prior version of this doc claimed one; 2026-08-17 wiring audit).

## What this layout enables

1. **`ls projects/client-a/` is scannable** — 8 standard subdirs, 3 root files, .seo hidden by file browsers
2. **Cross-project isolation is enforced by directory tree** — can't accidentally read from wrong project
3. **Export-friendly** — zip a project folder and share/migrate; structure is self-describing
4. **Backup-friendly** — exclude `.seo/observability/` + `.seo/backups/` + `.seo/archive/` to save space
5. **Git-friendly** — `.gitignore` is auto-generated; safe to commit project state without leaking secrets
6. **Multi-vertical** — same structure for B2B SaaS, B2C ecom, publisher, agency sites

## What this layout does NOT do

- ❌ Replace `~/.xuanran-seo/active-project` pointer (lives in user home, not project)
- ❌ Replace `~/.xuanran-seo/credentials/` global creds (those are plugin-wide fallbacks)
- ❌ Replace `~/.xuanran-seo/cost-ledger.jsonl` (cost tracking is global)
- ❌ Replace `~/.xuanran-seo/config.yaml` (cost limits + defaults are global)

Project-local data is in `projects/{slug}/`. User-global data is in `~/.xuanran-seo/`.
