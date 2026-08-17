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
of this stage records `skipped_draft`. **The post-flip submitting run is owned by
`python -m scripts.wordpress.flip_post_live {slug} --workspace {task_id} --json`**
(v3.42.16) — it PATCHes the status, re-verifies the live URL, and re-runs this
stage's executor in one sequence, exiting 2 if the indexing re-run did not
submit. Do not re-run the executor by hand as a substitute for the flip
executor: the hand-run path is what left flips unverified. The
publish-confirmation flows in `skills/weekly-digest/SKILL.md`,
`skills/phase-publish/SKILL.md`, and `skills/seo-blog/SKILL.md` all invoke
flip_post_live.

## Credentials

**Per-project first (2026-08-17 — the credential binds to ONE host and this is a
~13-site fleet):** `~/.xuanran-seo/credentials/bing-indexnow/{slug}.json`, one per
site, same shape as below. The global `bing-indexnow.json` remains as a
single-site fallback only — with just the global file, 12 of 13 sites would 422
(URL host ≠ credential host); `indexnow_submit` now refuses a host-mismatched
payload loudly before the network call.

Shape (both levels):
`{ "key": "<32-hex>", "key_location": "https://{host}/{key}.txt", "host": "example.com" }`
(or `BING_INDEXNOW_KEY` / `BING_INDEXNOW_KEY_LOCATION` / `BING_INDEXNOW_HOST`).
The key file must be hosted on each domain (the same key VALUE may be reused
across hosts — each host serves its own `{key}.txt`). Missing credentials record
`no_credentials` — visible, non-blocking. **As of 2026-08-17 no key is
configured on this machine**; every run records `no_credentials` until one is
minted (https://www.bing.com/indexnow), the key file uploaded per site, and the
per-slug credential files written.

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
