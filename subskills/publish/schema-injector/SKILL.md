---
name: schema-injector
description: Inject final JSON-LD @graph into the published post's <head> (via Yoast MU-plugin OR direct REST). Runs after wp publish.
allowed-tools: [Read, Bash]
---

# Schema Injector

## Workflow
```
1. Read workspace/{task}/schema.json
2. POST /wp-json/yoast/v1/posts/{post_id} with schema fields if MU-plugin supports
3. Or: POST custom_fields to set `_genesis_schema` / similar plugin field
4. Verify by fetching post and inspecting <head> JSON-LD
```

## Validation
Run `scripts.validate.schema_validator` against retrieved post HTML:
- No deprecated types
- All required fields present
- ISO 8601 dates

## Note
For most cases, schema-generator output gets included in post.content (inline `<script>` tag).
Schema-injector is needed when you want it in `<head>` instead of body.
