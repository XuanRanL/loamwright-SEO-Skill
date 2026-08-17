---
name: indexing-notifier
description: After publish, ping Bing IndexNow (Bing + ChatGPT-via-Bing + Yandex). Wired as the `indexing-notifier` pipeline stage after verify-post (v3.42.12). Drafts are never submitted; re-run after the operator flips the post live.
allowed-tools: [Read, Bash]
---

# Indexing Notifier

**Wiring status (v3.42.12, 2026-08-12): this IS a runner stage.** For months this
file claimed "Triggered as final step of phase-publish" while the orchestrator's
STAGES table ended at `verify-post` and the only caller of `indexnow_submit.py`
was the dead `agents/publisher.md` — a Rule 6 doc-only wiring. No article this
pipeline published was ever submitted. The stage now exists in
`scripts/pipeline/orchestrator.py` and runs automatically after `verify-post`.

## Executor (the ONLY correct invocation — do not hand-roll the curl)

```bash
python -m scripts.publish.indexing_notify {project_slug} --workspace {task_id} --json
```

Reads `publish-result.json :: post_id`, resolves the post's LIVE status from the
WordPress REST object (never from workspace state — the operator may have
flipped or trashed it since), and:

| Live status | Outcome written to `indexing-result.json` |
|---|---|
| `publish` | `submitted` (IndexNow ping) / `submit_failed` / `no_credentials` |
| anything else | `skipped_draft` — a draft URL is NEVER submitted (Rule 5a) |
| unreachable | `transport_error` — distinct from every verdict above (Rule 13) |

## Contract: notifier, not gate

Submission is a best-effort accelerator. Failures are recorded honestly in
`indexing-result.json :: outcome` but exit 0 — the same never-blocks contract as
image-visual-qa. A pipeline whose article already published and verified must
not go red on a Bing hiccup. Exit 2 only on invocation errors (no workspace /
no publish-result.json).

## The draft→publish flip (the case the operator actually hits)

Rule 5a means the pipeline's terminal state is a DRAFT, so the in-pipeline run
of this stage records `skipped_draft`. **After the operator confirms and the
post is PATCHed live, re-run the executor above by hand** — it is idempotent and
this re-run is the one that actually submits. The publish-confirmation flows in
`skills/weekly-digest/SKILL.md` (Step 9) and `skills/phase-publish/SKILL.md`
include this step.

## Credentials

`~/.xuanran-seo/credentials/bing-indexnow.json`:
`{ "key": "<32-hex>", "key_location": "https://{host}/{key}.txt", "host": "example.com" }`
(or `BING_INDEXNOW_KEY` / `BING_INDEXNOW_KEY_LOCATION` / `BING_INDEXNOW_HOST`).
The key file must be hosted on the domain. Missing credentials record
`no_credentials` — visible, non-blocking. **As of 2026-08-12 no key is
configured on this machine**; every run records `no_credentials` until one is
minted (https://www.bing.com/indexnow) and the key file uploaded per site.

One IndexNow ping reaches: Microsoft Bing, ChatGPT-via-Bing, Yandex, Naver,
Seznam, Yep.

## GSC URL Inspection — deliberately NOT in the stage

`scripts/publish/gsc_submit.py` is implemented but stays a documented MANUAL
step: it needs per-site OAuth and carries strict daily quotas, so pinging it
unconditionally from every pipeline run would burn quota across the 13-site
fleet. Run it by hand for high-priority URLs:

```bash
python -m scripts.publish.gsc_submit --site {slug} --url {post_url} --json
```

## See also
- `scripts/publish/indexing_notify.py` — the stage executor
- `scripts/publish/indexnow_submit.py` — the IndexNow HTTP client it calls
- `tests/test_indexing_notifier_wiring.py` — pins the stage's existence + every outcome
- IndexNow docs: https://www.indexnow.org/documentation
