---
name: indexing-notifier
description: After publish, ping Bing IndexNow + GSC URL Inspection. Instant indexing for Bing + ChatGPT-via-Bing. Triggered as final step of phase-publish.
allowed-tools: [Read, Bash]
---

# Indexing Notifier

## Inputs
- Newly published post URL (from wp-publisher result)
- `~/.xuanran-seo/credentials/bing-indexnow.json` (key + host)

## Workflow

### Bing IndexNow
```bash
curl -X POST https://api.indexnow.org/indexnow \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{
    "host": "{host}",
    "key": "{key}",
    "keyLocation": "{key_location}",
    "urlList": ["{post_url}"]
  }'
```

Expected: 200 OK or 202 Accepted.

Supported engines (one ping → multiple):
- Microsoft Bing
- ChatGPT via Bing
- Yandex
- Naver
- Seznam
- Yep

### Google Search Console (if creds available)
```bash
python -m scripts.publish.gsc_submit --url {post_url}  # TODO
```

Submits URL for inspection / indexing request.

## Output
Append to `projects/{slug}/change-log.json`:
```json
{
  "action": "indexed",
  "url": "...",
  "indexnow_status": 200,
  "gsc_status": "submitted",
  "timestamp": "..."
}
```

## See also
- `scripts/publish/indexnow_submit.py` (TODO)
- IndexNow docs: https://www.indexnow.org/documentation
