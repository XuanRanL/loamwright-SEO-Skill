# install/claude-code/install.ps1
# Windows installer for Xuanran SEO Blog Writer plugin
#
# Plugin version: 3.7.0
#
# Usage:
#   pwsh install/claude-code/install.ps1
#   pwsh install/claude-code/install.ps1 -Dev
#   pwsh install/claude-code/install.ps1 -Check

[CmdletBinding()]
param(
    [switch]$Dev,
    [switch]$Check
)

$ErrorActionPreference = "Stop"
$PluginVersion = "3.42.17"
$PluginName = "xuanran-seo-blog-writer"

# Resolve plugin root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PluginRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path

$XsHome = Join-Path $env:USERPROFILE ".xuanran-seo"
$CredDir = Join-Path $XsHome "credentials"
$ConfigFile = Join-Path $XsHome "config.yaml"

$Mode = "install"
if ($Dev) { $Mode = "dev" }
if ($Check) { $Mode = "check" }

Write-Host "==> Xuanran SEO Blog Writer installer (v$PluginVersion)" -ForegroundColor Cyan
Write-Host "    Plugin root: $PluginRoot"
Write-Host "    Mode: $Mode"
Write-Host ""

# ─── Step 1: Python ─────────────────────────────────────────────
Write-Host "[1/7] Checking Python..."
try {
    $pyVersion = (python --version 2>&1) -replace "Python ",""
    $pyParts = $pyVersion.Split(".")
    if ([int]$pyParts[0] -lt 3 -or ([int]$pyParts[0] -eq 3 -and [int]$pyParts[1] -lt 11)) {
        Write-Host "    ❌ Python $pyVersion found. Need 3.11+." -ForegroundColor Red
        exit 1
    }
    Write-Host "    ✓ Python $pyVersion" -ForegroundColor Green
}
catch {
    Write-Host "    ❌ Python not found. Install Python 3.11+." -ForegroundColor Red
    exit 1
}

# ─── Step 2: ~/.xuanran-seo ──────────────────────────────────────
Write-Host "[2/7] Setting up $XsHome..."
New-Item -ItemType Directory -Force -Path $XsHome | Out-Null
New-Item -ItemType Directory -Force -Path $CredDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $CredDir "wordpress") | Out-Null

# Windows ACL: Restrict to current user
$acl = Get-Acl $XsHome
$acl.SetAccessRuleProtection($true, $false)
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
    [System.Security.Principal.WindowsIdentity]::GetCurrent().Name,
    "FullControl", "ContainerInherit,ObjectInherit", "None", "Allow"
)
$acl.SetAccessRule($rule)
Set-Acl -Path $XsHome -AclObject $acl
Write-Host "    ✓ Created $XsHome (ACL restricted to current user)" -ForegroundColor Green

# ─── Step 3: config.yaml ────────────────────────────────────────
Write-Host "[3/7] Initializing config.yaml..."
if (-not (Test-Path $ConfigFile)) {
    @"
# ~/.xuanran-seo/config.yaml
# Plugin runtime configuration

cost_limits:
  daily_total_usd: 50
  per_init_usd: 1.5
  per_article_usd: 3.0
  per_image_batch_usd: 2.0

api_keys:
  fallback_only: false

defaults:
  reading_level_per_persona: true
  image_quality: high
  image_mode: batch
  visual_consistency: strategy_a
  voice_search_targets:
    - google-assistant
    - chatgpt-voice

models:
  anthropic_main: claude-opus-4-7
  anthropic_judge: claude-haiku-4-5
  openai_image: gpt-image-2
  gemini_second_opinion: gemini-3.1-pro
"@ | Out-File -FilePath $ConfigFile -Encoding utf8 -NoNewline
    Write-Host "    ✓ Created $ConfigFile" -ForegroundColor Green
}
else {
    Write-Host "    ✓ $ConfigFile already exists, preserving" -ForegroundColor Green
}

# ─── Step 4: Python dependencies ────────────────────────────────
Write-Host "[4/7] Installing Python dependencies..."
Set-Location $PluginRoot
try {
    python -m pip install uv 2>&1 | Out-Null
    & uv pip install -r requirements.txt
}
catch {
    & python -m pip install -r requirements.txt
}
Write-Host "    ✓ Dependencies installed" -ForegroundColor Green

# ─── Step 5: patchright Chromium ───────────────────────────────
Write-Host "[5/7] Installing patchright Chromium..."
try {
    & python -m patchright install chromium 2>&1 | Select-Object -First 20
    Write-Host "    ✓ Patchright ready" -ForegroundColor Green
}
catch {
    Write-Host "    ⚠️ patchright Chromium install failed (non-fatal)" -ForegroundColor Yellow
}

# ─── Step 6: Plugin registration ───────────────────────────────
Write-Host "[6/7] Registering plugin with Claude Code..."
if (Get-Command claude -ErrorAction SilentlyContinue) {
    if ($Mode -eq "dev") {
        & claude plugin install $PluginRoot --dev
    }
    else {
        & claude plugin install $PluginRoot
    }
    Write-Host "    ✓ Registered" -ForegroundColor Green
}
else {
    Write-Host "    ⚠️ Claude Code CLI not in PATH. Install manually:" -ForegroundColor Yellow
    Write-Host "         /plugin install $PluginRoot"
}

# ─── Step 7: Health check ──────────────────────────────────────
Write-Host "[7/7] Running health check..."
try {
    & python (Join-Path $PluginRoot "install\claude-code\health_check.py")
}
catch {
    Write-Host "    ⚠️ Health check reported issues" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==> Install complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Add API keys to $CredDir\  (anthropic.key, openai.key, tavily.key)"
Write-Host "     Or set environment variables: `$env:ANTHROPIC_API_KEY etc."
Write-Host "  2. Add WordPress credentials: $CredDir\wordpress\<site-slug>.json"
Write-Host "     Format: { url, username, app_password }"
Write-Host "  3. (Optional) Install WordPress MU-plugin"
Write-Host "  4. In Claude Code: /init https://your-site.com"
Write-Host ""
