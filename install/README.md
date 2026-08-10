# install/

Per-host install adapters for the Xuanran SEO Blog Writer plugin.

> **Source of truth**: All skill content lives at the plugin root (`skills/`, `subskills/`, `agents/`, etc).
> Each subdirectory here is a **thin adapter** that copies / links / compiles those files into the host's expected location.

## Hosts supported

| Host | Adapter | Status |
|---|---|---|
| **Claude Code** | `claude-code/` | ✅ Primary target |
| Gemini API host | `gemini-api/` | 🚧 v3.2 stub (compiles SKILL.md → system prompt) |
| Codex CLI | `codex/` | 📋 Planned |
| Custom AI host | — | Read `../AGENTS.md` directly |

## Claude Code (primary)

```bash
# Linux / macOS
bash install/claude-code/install.sh

# Windows
pwsh install/claude-code/install.ps1

# Dev mode (editable, symlink)
bash install/claude-code/install.sh --dev

# Verify only
bash install/claude-code/install.sh --check
python install/claude-code/health_check.py --deep   # test live API calls
```

What it does:
1. Verify Python 3.11+
2. Create `~/.xuanran-seo/{credentials,credentials/wordpress}/`
3. Write default `~/.xuanran-seo/config.yaml`
4. Install Python deps (`pip install -r requirements.txt`)
5. Install patchright Chromium (`python -m patchright install chromium`)
6. Register plugin with Claude Code (`claude plugin install <root>`)
7. Run health check

## Gemini API (compile-time adapter)

For users running the plugin's logic on Google Gemini API instead of Claude Code:

```bash
python install/gemini-api/compile_skill.py \
    --plugin-root . \
    --output build/gemini-system-prompt.txt
```

Output: a compiled system prompt that bundles `AGENTS.md` routing rules + relevant SKILL.md contents.

## WordPress MU-plugin (separate install)

The Yoast REST endpoint extension lives at `install/wordpress-mu-plugin/`. Copy the PHP file to your WordPress site's `wp-content/mu-plugins/` directory:

```bash
scp install/wordpress-mu-plugin/seo-machine-yoast-rest.php \
    user@your-wp-site.com:/path/to/wp-content/mu-plugins/
```

MU-plugins auto-load — no activation needed. Verify by:
```bash
curl https://your-wp-site.com/wp-json/yoast/v1/posts/1 -u "username:app_pwd"
# Should return 200 (or 404 if post #1 doesn't exist; what matters is endpoint exists)
```

## Uninstall

```bash
bash install/claude-code/uninstall.sh
# Removes plugin registration; preserves ~/.xuanran-seo/ user data.
```

## Cross-host compatibility notes

- All skill content uses **markdown** (not HTML)
- All scripts support `--json` output (cross-host contract)
- All file paths use `pathlib.Path` (cross-platform)
- All env vars upper-case underscore (`ANTHROPIC_API_KEY` not `anthropic_api_key`)
- No hard-coded Linux-only paths
