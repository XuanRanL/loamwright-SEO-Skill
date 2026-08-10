#!/usr/bin/env bash
# Launch a Claude Code session pinned to a single Xuanran-SEO project.
#
# Sets XS_ACTIVE_PROJECT for this shell, then starts `claude`. The env var is
# authoritative (env-first resolution in scripts/_core/active_project.py), so the
# session is pinned to <slug> and never reads/writes the shared
# ~/.xuanran-seo/active-project file. Run one terminal per project to write for
# multiple projects in parallel:
#
#     ./bin/launch-session.sh project-charlie
#     ./bin/launch-session.sh project-juliet
#     ./bin/launch-session.sh project-kilo
#
# Concurrent shared-state writes (cost-ledger, tavily round-robin counter) are
# cross-process locked, so the sessions do not corrupt each other.
set -euo pipefail

if [ "$#" -lt 1 ] || [ -z "${1// }" ]; then
    echo "Usage: ./bin/launch-session.sh <project-slug>" >&2
    exit 1
fi

slug="$1"
shift
export XS_ACTIVE_PROJECT="$slug"
echo "📌 Pinned this session to project: ${XS_ACTIVE_PROJECT}"
echo "   (XS_ACTIVE_PROJECT is authoritative; the shared active-project file is ignored here.)"

exec claude "$@"
