# bin/preamble.md — Universal Skill Startup

Every skill invocation in this plugin sources this preamble first.

## What it does

1. **Version check** — compare local VERSION vs marketplace
2. **Active project load** — resolve `XS_ACTIVE_PROJECT` env var first (per-session pin for parallel sessions), else `~/.xuanran-seo/active-project` file → load `projects/{slug}/business-context.json`
3. **Credential validation** — warn if `~/.xuanran-seo/credentials/` missing key files
4. **Cost ledger init** — read `~/.xuanran-seo/config.yaml`, check daily total
5. **Health check** — verify required Python packages installed

## Steps

```bash
# Step 1: Version check
LOCAL_VERSION=$(cat "${PLUGIN_DIR}/VERSION" | tr -d '[:space:]')
REMOTE_VERSION=$("${PLUGIN_DIR}/bin/update-check" 2>/dev/null || echo "")

if [ -n "$REMOTE_VERSION" ] && [ "$LOCAL_VERSION" != "$REMOTE_VERSION" ]; then
    echo "⚠️  UPGRADE_AVAILABLE ${LOCAL_VERSION} ${REMOTE_VERSION}"
    # Don't auto-upgrade; let user run /seo-blog --upgrade
fi

# Step 2: Active project — XS_ACTIVE_PROJECT env var WINS (per-session pin).
# This is what lets the user run N parallel Claude Code sessions, each pinned to
# a different project, without fighting over the single shared active-project
# file. Only fall back to the file when the env var is unset (single-session use).
ACTIVE_FILE="$HOME/.xuanran-seo/active-project"
if [ -n "$XS_ACTIVE_PROJECT" ]; then
    ACTIVE_SLUG="$XS_ACTIVE_PROJECT"            # per-session pin; do NOT overwrite from file
elif [ -f "$ACTIVE_FILE" ]; then
    ACTIVE_SLUG=$(cat "$ACTIVE_FILE" | tr -d '[:space:]')
    export XS_ACTIVE_PROJECT="$ACTIVE_SLUG"
fi
if [ -n "$ACTIVE_SLUG" ] && [ -d "${PLUGIN_DIR}/projects/${ACTIVE_SLUG}" ]; then
    # Check freshness
    BC_FILE="${PLUGIN_DIR}/projects/${ACTIVE_SLUG}/business-context.json"
    if [ -f "$BC_FILE" ]; then
        FRESHNESS=$(python -c "import json; bc=json.load(open('$BC_FILE')); print(bc.get('freshness_state','unknown'))")
        if [ "$FRESHNESS" = "expired" ]; then
            echo "⚠️  Active project '${ACTIVE_SLUG}' business-context expired (>90d). Run /init <url> --refresh"
        fi
    fi
fi

# Step 3: Credentials
CRED_DIR="$HOME/.xuanran-seo/credentials"
for key in anthropic.key openai.key tavily.key; do
    if [ ! -f "$CRED_DIR/$key" ] && [ -z "$(env | grep -E "^${key%%.key}_API_KEY=" -i)" ]; then
        echo "⚠️  Missing credential: $key (and no env var)"
    fi
done

# Step 4: Cost ledger
CONFIG="$HOME/.xuanran-seo/config.yaml"
if [ -f "$CONFIG" ]; then
    DAILY_USED=$(python "${PLUGIN_DIR}/scripts/_core/cost_ledger.py" --summary --period=day --json 2>/dev/null | python -c "import sys,json; print(json.load(sys.stdin).get('total_usd', 0))")
    DAILY_LIMIT=$(python -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['cost_limits']['daily_total_usd'])" 2>/dev/null || echo 50)
    REMAINING=$(python -c "print(${DAILY_LIMIT} - ${DAILY_USED})")
    if (( $(echo "$REMAINING < 5" | bc -l 2>/dev/null) )); then
        echo "⚠️  Daily cost budget remaining: \$${REMAINING} of \$${DAILY_LIMIT}"
    fi
fi

# Step 5: Health (quick)
python -c "import anthropic, openai, tavily, jsonschema, httpx" 2>/dev/null || {
    echo "⚠️  Missing Python deps. Run: pip install -r requirements.txt"
}
```

## Output to Claude Code

Any `⚠️` lines from above are passed back to Claude as context. Claude can decide to:
- Warn the user (e.g., expired project context)
- Halt execution (e.g., missing credentials for required call)
- Suggest an upgrade

## Variables exported

- `XS_PLUGIN_DIR` — absolute path to plugin root
- `XS_ACTIVE_PROJECT` — current project slug. If set by the launching shell (e.g. `bin/launch-session.ps1 <slug>`) it is authoritative and per-session; otherwise it is populated from the shared `active-project` file.
- `XS_DAILY_BUDGET_REMAINING_USD` — informational

## When NOT to run

- `--no-preamble` flag (debug only)
- Inside a hook callback (avoid recursion)
