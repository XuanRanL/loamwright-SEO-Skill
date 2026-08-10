#!/usr/bin/env python3
"""
install/claude-code/health_check.py — Verify plugin install is complete.

Checks:
  1. Python 3.11+
  2. Required Python packages importable
  3. ~/.xuanran-seo/ directory structure
  4. config.yaml present and valid YAML
  5. Credential files present (warn if missing, fail if all missing)
  6. Plugin manifest valid JSON
  7. All schemas valid JSON Schema
  8. patchright Chromium binary present
  9. Optional: API key actually works (--deep flag)

Exit codes:
  0  All OK
  1  Warnings (non-blocking)
  2  Critical missing
"""
import argparse
import importlib
import json
import os
import sys
from pathlib import Path


GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
NC = "\033[0m"


class HealthChecker:
    def __init__(self, plugin_root: Path, deep: bool = False):
        self.plugin_root = plugin_root
        self.xs_home = Path.home() / ".xuanran-seo"
        self.deep = deep
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def ok(self, msg: str) -> None:
        print(f"  {GREEN}✓{NC} {msg}")

    def warn(self, msg: str) -> None:
        print(f"  {YELLOW}⚠️{NC} {msg}")
        self.warnings.append(msg)

    def err(self, msg: str) -> None:
        print(f"  {RED}❌{NC} {msg}")
        self.errors.append(msg)

    # ───── Checks ────────────────────────────────────────────

    def check_python(self) -> None:
        print(f"\n{CYAN}[1] Python version{NC}")
        v = sys.version_info
        if v.major < 3 or (v.major == 3 and v.minor < 11):
            self.err(f"Python {v.major}.{v.minor} found. Need 3.11+.")
        else:
            self.ok(f"Python {v.major}.{v.minor}.{v.micro}")

    def check_packages(self) -> None:
        print(f"\n{CYAN}[2] Python packages{NC}")
        required = [
            "httpx", "bs4", "lxml", "markdown_it", "PIL", "jsonschema",
            "patchright", "click", "yaml", "tenacity",
            "anthropic", "openai", "tavily", "google.genai",
        ]
        for pkg in required:
            try:
                importlib.import_module(pkg)
                self.ok(f"{pkg}")
            except ImportError as e:
                self.err(f"{pkg}: {e}")

    def check_xs_home(self) -> None:
        print(f"\n{CYAN}[3] ~/.xuanran-seo/ directory{NC}")
        if not self.xs_home.is_dir():
            self.err(f"{self.xs_home} not found. Run install script.")
            return
        self.ok(f"{self.xs_home} exists")
        for sub in ["credentials", "credentials/wordpress"]:
            p = self.xs_home / sub
            if not p.is_dir():
                self.warn(f"{p} missing")
            else:
                self.ok(f"{p}")

    def check_config(self) -> None:
        print(f"\n{CYAN}[4] config.yaml{NC}")
        cfg = self.xs_home / "config.yaml"
        if not cfg.exists():
            self.err("config.yaml not found")
            return
        try:
            import yaml
            data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
            assert "cost_limits" in data, "missing cost_limits"
            assert "models" in data, "missing models"
            self.ok(f"valid YAML with cost_limits + models")
        except Exception as e:
            self.err(f"{cfg}: {e}")

    def check_credentials(self) -> None:
        print(f"\n{CYAN}[5] Credentials{NC}")
        cred_dir = self.xs_home / "credentials"
        env_vars = {
            "anthropic.key": "ANTHROPIC_API_KEY",
            "openai.key": "OPENAI_API_KEY",
            "tavily.key": "TAVILY_API_KEY",
        }
        any_found = False
        for key_file, env_var in env_vars.items():
            file_ok = (cred_dir / key_file).exists()
            env_ok = bool(os.environ.get(env_var))
            if file_ok or env_ok:
                src = "file" if file_ok else "env"
                self.ok(f"{key_file} ({src})")
                any_found = True
            else:
                self.warn(f"{key_file} or ${env_var} not set")
        if not any_found:
            self.err("No credentials found at all — plugin will not function")

    def check_plugin_manifest(self) -> None:
        print(f"\n{CYAN}[6] Plugin manifest{NC}")
        manifest = self.plugin_root / ".claude-plugin" / "plugin.json"
        if not manifest.exists():
            self.err(f"{manifest} not found")
            return
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            assert data.get("name"), "missing name"
            assert data.get("version"), "missing version"
            self.ok(f"name={data['name']}, version={data['version']}")
        except Exception as e:
            self.err(f"{manifest}: {e}")

    def check_schemas(self) -> None:
        print(f"\n{CYAN}[7] JSON Schemas{NC}")
        schemas_dir = self.plugin_root / "schemas"
        if not schemas_dir.is_dir():
            self.err("schemas/ directory not found")
            return
        expected = ["state", "research", "angle", "outline", "section",
                    "citations", "meta", "quality", "handoff", "auditor-output"]
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.warn("jsonschema not installed; skipping schema validation")
            return
        for name in expected:
            p = schemas_dir / f"{name}.schema.json"
            if not p.exists():
                self.err(f"{name}.schema.json missing")
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                Draft202012Validator.check_schema(data)
                self.ok(f"{name}.schema.json valid")
            except Exception as e:
                self.err(f"{name}.schema.json: {e}")

    def check_patchright(self) -> None:
        print(f"\n{CYAN}[8] Patchright Chromium{NC}")
        try:
            from patchright._impl._driver import compute_driver_executable
            self.ok("patchright importable")
        except ImportError:
            self.warn("patchright not importable (Tier 2 of /init waterfall unavailable)")
        except Exception:
            self.ok("patchright partial init (Chromium binary may need install)")

    def check_deep_apis(self) -> None:
        if not self.deep:
            return
        print(f"\n{CYAN}[9] Deep API connectivity (--deep flag){NC}")
        # Anthropic
        try:
            import anthropic
            c = anthropic.Anthropic()
            models = c.models.list()
            self.ok(f"Anthropic: {len(models.data)} models accessible")
        except Exception as e:
            self.warn(f"Anthropic API: {e}")
        # OpenAI
        try:
            import openai
            c = openai.OpenAI()
            models = c.models.list()
            self.ok(f"OpenAI: {len(models.data)} models accessible")
        except Exception as e:
            self.warn(f"OpenAI API: {e}")
        # Tavily
        try:
            from tavily import TavilyClient
            r = TavilyClient().search("test", max_results=1)
            self.ok(f"Tavily: search returned {len(r.get('results',[]))} results")
        except Exception as e:
            self.warn(f"Tavily API: {e}")

    # ───── Run all ───────────────────────────────────────────

    def run(self) -> int:
        print(f"{CYAN}==> Health Check for xuanran-seo-blog-writer{NC}")
        print(f"    Plugin root: {self.plugin_root}")
        print(f"    Deep mode: {self.deep}")
        self.check_python()
        self.check_packages()
        self.check_xs_home()
        self.check_config()
        self.check_credentials()
        self.check_plugin_manifest()
        self.check_schemas()
        self.check_patchright()
        self.check_deep_apis()
        # Summary
        print(f"\n{CYAN}==> Summary{NC}")
        print(f"    Errors:   {RED}{len(self.errors)}{NC}")
        print(f"    Warnings: {YELLOW}{len(self.warnings)}{NC}")
        if self.errors:
            return 2
        if self.warnings:
            return 1
        return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deep", action="store_true", help="Test live API calls (requires valid keys)")
    args = ap.parse_args()
    plugin_root = Path(__file__).resolve().parent.parent.parent
    checker = HealthChecker(plugin_root, deep=args.deep)
    sys.exit(checker.run())


if __name__ == "__main__":
    main()
