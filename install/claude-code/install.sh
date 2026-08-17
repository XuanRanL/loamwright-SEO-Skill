#!/usr/bin/env bash
# install/claude-code/install.sh
# Linux / macOS installer for Xuanran SEO Blog Writer plugin
#
# Plugin version: 3.7.0
#
# Usage:
#   bash install/claude-code/install.sh
#   bash install/claude-code/install.sh --dev      # editable mode (symlink)
#   bash install/claude-code/install.sh --check    # verify install only

set -euo pipefail

PLUGIN_VERSION="3.42.18"
PLUGIN_NAME="xuanran-seo-blog-writer"

# Resolve plugin root (2 levels up from this script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

XS_HOME="$HOME/.xuanran-seo"
CRED_DIR="$XS_HOME/credentials"
CONFIG_FILE="$XS_HOME/config.yaml"

MODE="install"
for arg in "$@"; do
    case "$arg" in
        --dev) MODE="dev" ;;
        --check) MODE="check" ;;
        *) echo "Unknown arg: $arg"; exit 1 ;;
    esac
done

echo "==> Xuanran SEO Blog Writer installer (v${PLUGIN_VERSION})"
echo "    Plugin root: ${PLUGIN_ROOT}"
echo "    Mode: ${MODE}"
echo ""

# ─── Step 1: Python ─────────────────────────────────────────────
echo "[1/7] Checking Python..."
if ! command -v python3 &>/dev/null; then
    echo "    ❌ python3 not found. Install Python 3.11+."
    exit 1
fi
PY_VERSION=$(python3 -c "import sys; print('.'.join(map(str, sys.version_info[:2])))")
PY_MAJOR=$(python3 -c "import sys; print(sys.version_info[0])")
PY_MINOR=$(python3 -c "import sys; print(sys.version_info[1])")
if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]); then
    echo "    ❌ Python ${PY_VERSION} found. Need 3.11+."
    exit 1
fi
echo "    ✓ Python ${PY_VERSION}"

# ─── Step 2: ~/.xuanran-seo ──────────────────────────────────────
echo "[2/7] Setting up ~/.xuanran-seo/..."
mkdir -p "$CRED_DIR/wordpress"
chmod 700 "$XS_HOME"
chmod 700 "$CRED_DIR"
chmod 700 "$CRED_DIR/wordpress"
echo "    ✓ Created $XS_HOME (chmod 700)"

# ─── Step 3: config.yaml ────────────────────────────────────────
echo "[3/7] Initializing config.yaml..."
if [ ! -f "$CONFIG_FILE" ]; then
    cat > "$CONFIG_FILE" <<'EOF'
# ~/.xuanran-seo/config.yaml
# Plugin runtime configuration

cost_limits:
  daily_total_usd: 50            # daily total spend cap
  per_init_usd: 1.5              # single /init upper bound
  per_article_usd: 3.0           # single /article upper bound
  per_image_batch_usd: 2.0       # single image batch upper bound

api_keys:
  # Set to true to ONLY use ~/.xuanran-seo/credentials/ (skip env vars)
  fallback_only: false

defaults:
  reading_level_per_persona: true
  image_quality: high            # low / medium / high
  image_mode: batch              # batch / realtime
  visual_consistency: strategy_a # strategy_a / strategy_b
  voice_search_targets:
    - google-assistant
    - chatgpt-voice

models:
  # Override default model IDs here if needed
  anthropic_main: claude-opus-4-7
  anthropic_judge: claude-haiku-4-5
  openai_image: gpt-image-2
  gemini_second_opinion: gemini-3.1-pro
EOF
    chmod 600 "$CONFIG_FILE"
    echo "    ✓ Created $CONFIG_FILE (chmod 600)"
else
    echo "    ✓ $CONFIG_FILE already exists, preserving"
fi

# ─── Step 4: Python dependencies ────────────────────────────────
echo "[4/7] Installing Python dependencies..."
if ! python3 -c "import uv" &>/dev/null && ! command -v uv &>/dev/null; then
    echo "    Installing uv for fast package management..."
    pip install --user uv || python3 -m pip install --user uv
fi
cd "$PLUGIN_ROOT"
if command -v uv &>/dev/null; then
    uv pip install -r requirements.txt
else
    pip install -r requirements.txt
fi
echo "    ✓ Dependencies installed"

# ─── Step 5: patchright Chromium ───────────────────────────────
echo "[5/7] Installing patchright Chromium..."
python3 -m patchright install chromium 2>&1 | head -20 || {
    echo "    ⚠️ patchright Chromium install failed (non-fatal; /init Tier 2 fallback may not work)"
}
echo "    ✓ Patchright ready"

# ─── Step 6: Plugin registration with Claude Code ───────────────
echo "[6/7] Registering plugin with Claude Code..."
if command -v claude &>/dev/null; then
    if [ "$MODE" = "dev" ]; then
        echo "    Installing in dev mode (symlink)..."
        # Claude Code's --dev / symlink syntax varies; using generic approach
        claude plugin install "$PLUGIN_ROOT" --dev || claude plugin install "$PLUGIN_ROOT"
    else
        claude plugin install "$PLUGIN_ROOT"
    fi
    echo "    ✓ Registered with claude plugin install"
else
    echo "    ⚠️ Claude Code CLI not in PATH. Install manually:"
    echo "         /plugin install ${PLUGIN_ROOT}"
fi

# ─── Step 7: Health check ──────────────────────────────────────
echo "[7/7] Running health check..."
python3 "$PLUGIN_ROOT/install/claude-code/health_check.py" || {
    echo "    ⚠️ Health check reported issues (see above)"
}

echo ""
echo "==> Install complete!"
echo ""
echo "Next steps:"
echo "  1. Add API keys to $CRED_DIR/  (anthropic.key, openai.key, tavily.key)"
echo "     Or set environment variables: ANTHROPIC_API_KEY, OPENAI_API_KEY, TAVILY_API_KEY"
echo "  2. Add WordPress credentials: $CRED_DIR/wordpress/<site-slug>.json"
echo "     Format: {\"url\":\"https://example.com\",\"username\":\"...\",\"app_password\":\"24-char-key\"}"
echo "  3. (Optional) Install WordPress MU-plugin for Yoast REST endpoint:"
echo "     Copy $PLUGIN_ROOT/install/wordpress-mu-plugin/*.php to wp-content/mu-plugins/"
echo "  4. In Claude Code, try:  /init https://your-site.com"
echo ""
