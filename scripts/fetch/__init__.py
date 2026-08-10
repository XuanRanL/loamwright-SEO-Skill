"""scripts/fetch — external data acquisition modules.

All web fetches go through scripts/_core/ssrf_guard.validate_url() first.
All API calls log to scripts/_core/cost_ledger.

Modules:
    tavily_search      — Web search via Tavily (1000 free credits/mo)
    tavily_extract     — URL content extraction via Tavily
    crossref_lookup    — DOI / academic citation lookup (free, no key)
    fetch_page         — Direct HTTP GET with UA rotation + redirect tracking
    parse_html         — Extract meta / OG / schema / content from HTML
    ai_search_probe    — Active probe of ChatGPT/PPLX/Claude/Gemini (TODO M1.5)
    youtube_search     — YouTube Data API v3 (TODO addon)
"""
