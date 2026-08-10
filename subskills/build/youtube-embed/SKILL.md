---
name: youtube-embed
description: PARKED (2026-07-17 wiring audit) — its trigger `brief.embed_youtube=true` is set and read by NOTHING in the repo, so this add-on can never fire. Searches YouTube Data API for primary keyword, picks 1-2 high-relevance videos (viewCount/duration/channel auth filtered), embeds into article.
allowed-tools: [Read, Write, Bash]
disable-model-invocation: true
user-invocable: false
---

# YouTube Embed (Add-on)

> ⚠️ **PARKED — NOT WIRED (2026-07-17 wiring audit).** The trigger condition
> `brief.embed_youtube=true` appears nowhere else in the repo — no setter, no reader,
> no stage. Documented behavior with zero executor path (Rule 6). Wiring it (schema
> field + orchestrator conditional stage) or deleting it is a product decision — see
> CHANGELOG [3.40.0].

Optional Stage. Triggers only when `state.brief.embed_youtube == true`.

## Workflow
```
1. python -m scripts.fetch.youtube_search "{primary_keyword}" --max 10
2. Filter:
   - duration 4-15 min
   - viewCount > 10,000 (signal of quality)
   - publishedAt within last 18 months
   - channel subscriberCount > 1,000
3. Pick 1-2 best
4. Insert iframe embed at outline.youtube_slot position
5. Add VideoObject schema entry
```

## Cost
- YouTube search.list = 100 units (vs daily quota 10,000)

## Output
HTML embed appended to draft.md at youtube_slot location.

## See also
- `scripts/fetch/youtube_search.py` (TODO; uses google-api-python-client)
