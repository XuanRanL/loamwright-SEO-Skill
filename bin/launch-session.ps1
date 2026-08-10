<#
.SYNOPSIS
    Launch a Claude Code session pinned to a single Xuanran-SEO project.

.DESCRIPTION
    Sets the XS_ACTIVE_PROJECT environment variable for THIS shell, then starts
    `claude`. The env var is authoritative (env-first resolution in
    scripts/_core/active_project.py), so the session is pinned to <slug> and never
    reads or writes the shared ~/.xuanran-seo/active-project file.

    This is what makes it safe to run multiple sessions in parallel — open one
    terminal per project:

        .\bin\launch-session.ps1 project-charlie
        .\bin\launch-session.ps1 project-juliet
        .\bin\launch-session.ps1 project-kilo

    Concurrent shared-state writes (cost-ledger, tavily round-robin counter) are
    cross-process locked, so the sessions do not corrupt each other.

.PARAMETER Slug
    The project slug to pin (must match a projects/<slug>/ directory).

.EXAMPLE
    .\bin\launch-session.ps1 project-charlie
#>
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Slug
)

if ([string]::IsNullOrWhiteSpace($Slug)) {
    Write-Error "Usage: .\bin\launch-session.ps1 <project-slug>"
    exit 1
}

$env:XS_ACTIVE_PROJECT = $Slug.Trim()
Write-Host "📌 Pinned this session to project: $($env:XS_ACTIVE_PROJECT)" -ForegroundColor Green
Write-Host "   (XS_ACTIVE_PROJECT is authoritative; the shared active-project file is ignored here.)"

claude @args
