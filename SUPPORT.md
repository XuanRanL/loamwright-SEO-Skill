# Support

This project is maintained by [Loamwright（沃匠）](https://loamwrightseo.com/) on a
**best-effort basis** — it is the production engine of a working SEO agency, and
agency work comes first. There is no SLA, and no guarantee that any given issue
will be fixed.

## What is supported

| | |
|:---|:---|
| **Versions** | The latest release only. Older versions get no fixes or backports. |
| **Host** | Claude Code (current version). Other agent hosts are best-effort at most. |
| **Runtime** | Python 3.11+ on Windows / macOS / Linux. |
| **Publishing target** | WordPress via the REST API + Application Passwords. |
| **Providers** | The ones wired in `scripts/` today (OpenAI, Tavily, SerpApi, GSC/GA4, Vertex). |

## What is out of scope

- **Other CMS platforms** (Ghost, Webflow, Shopify blogs, headless setups) — the
  publish layer is WordPress-specific by design. PRs adding a new publisher are
  welcome; requests to build one are not tracked.
- **Older releases**, forks, and heavily modified copies.
- **Your project configuration.** `projects/{slug}/` content — business context,
  brand voice, taxonomy, prompts — is yours to tune. "It didn't write what I
  wanted" is a configuration question, not a bug.
- **Model behavior and API costs.** Output quality varies with the model you run
  and the budget you allow. Model/provider pricing and rate limits are theirs.
- **Hands-on setup, migrations, audits, or content strategy** — that is
  [what the agency does](https://loamwrightseo.com/), not what the issue tracker
  is for.
- **SEO outcome guarantees.** The tool enforces process, not rankings.

## How to get help

- **Bugs** — open an issue with: version (`cat VERSION`), host, the exact command,
  the relevant `memory/workspace/{task}/state.json` stage, and expected vs actual.
  **Issues without a reproduction may be closed without investigation.**
- **Feature requests** — welcome as issues, but they enter a backlog with no
  timeline. A PR that follows the [contribution rules](README.md#contributing)
  (real executors, not markdown-only wiring) is far more likely to land.
- **Security** — use GitHub's *Report a vulnerability* (Security Advisories).
  Please don't open public issues for security reports. Best-effort response
  within 7 days.
- **Usage questions** — read the skill docs first (`skills/`, `subskills/`,
  `references/`). One-on-one usage support is not provided for free.
- **Priority support / done-for-you** — available to
  [Loamwright clients](https://loamwrightseo.com/). If you'd rather have the team
  that built this run it for your site, that's literally our job.

---

## 支持说明（中文）

本项目由[沃匠（Loamwright）](https://loamwrightseo.com/)以**尽力而为**的方式维护——
它是一家在营 SEO 机构的生产引擎，机构业务优先。没有 SLA，也不保证任何问题一定会被修复。

**支持范围**：仅最新 release · Claude Code 宿主 · Python 3.11+ · WordPress 发布 ·
当前已接入的服务商。

**不在支持范围**：其他 CMS（Ghost / Webflow / Shopify / headless）· 旧版本与 fork ·
你的项目配置调优（`projects/{slug}/` 是你自己的领域，"写出来不是我想要的"属于配置问题，
不是 bug）· 模型表现与 API 费用 · 落地实施 / 迁移 / 审计 / 内容策略（这是
[机构服务](https://loamwrightseo.com/)，不是 issue 区的事）· 排名结果承诺
（工具保证流程，不保证排名）。

**如何求助**：
- **Bug** — 提 issue，附版本（`cat VERSION`）、宿主、完整命令、相关的
  `memory/workspace/{task}/state.json` 阶段、期望 vs 实际。**无复现的报告可能直接关闭。**
- **功能请求** — 欢迎，但进 backlog 且无时间表；直接提 PR 更容易落地。
- **安全问题** — 走仓库的 *Report a vulnerability*（Security Advisories），
  不要发公开 issue；尽力 7 天内响应。
- **用法咨询** — 请先读 `skills/`、`subskills/`、`references/` 文档；不提供免费的一对一支持。
- **优先支持 / 代运营** — 面向[沃匠客户](https://loamwrightseo.com/)。
