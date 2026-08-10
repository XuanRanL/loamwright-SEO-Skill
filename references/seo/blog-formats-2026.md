# Blog Formats 2026 · 三维分类完整目录

> **来源**：用户提供 24 形式分类 + Wix 2026.3 / Yext 680 万引用研究 / AirOps 2026.4 / HubSpot / Rebeccavandenberg / Sandstormdigital / ALM Corp 等公开研究数据
>
> **用途**：插件内引用为 `references/seo/blog-formats-2026.md`，供以下 skills 决策时调用：
> - `topic-angle-selector` — 选哪一种形式
> - `format-selector`（**新增**）— 按 brief intent × funnel × AI target 自动推荐
> - `outline-architect` — 按形式选骨架
> - `templates/` — 24 个模板对应
> - `geo-content-optimizer` — 知道哪个形式被哪个 AI 引擎偏爱
> - `quality-gate-cite` — 评估形式与目标的匹配度
>
> **核心原则**：形式不是"按文章长度选"或"看心情选"——是按三维硬指标决定：**搜索意图 + 转化漏斗 + 目标 AI 引擎**。

---

## 目录

1. 三维分类总表（速查矩阵）
2. AI 引擎引用率统计（按形式）
3. 核心十大形式（#1–10）
4. 进阶形式（#11–20）
5. 2026 AI 搜索时代新兴形式（#21–24）
6. 形式选择决策树
7. 每形式的模板骨架（Outline skeleton）
8. 与 v3.0 skills 的接线
9. 形式匹配 brief 时的"硬约束"映射
10. 反例：什么形式**不该**用

---

## 1 · 三维分类总表

> 这张表是 `format-selector` skill 的核心查询表。给定 (intent, funnel_stage, ai_target) 三元组，直接查到推荐形式。

### 1.1 三轴定义

**搜索意图（Search Intent）**：
- `info` — Informational（"what is..."、"how to..."、"why..."）
- `comm` — Commercial Investigation（"best X"、"X vs Y"、"X review"）
- `trans` — Transactional（"buy X"、"X coupon"、"X discount"）
- `nav` — Navigational（"X login"、"X documentation"）

**转化漏斗（Funnel Stage）**：
- `TOFU` — Top of Funnel（认知阶段，受众面广）
- `MOFU` — Middle of Funnel（评估阶段，开始对比）
- `BOFU` — Bottom of Funnel（决策阶段，即将下单）
- `RETN` — Retention/Loyalty（已有客户复购/留存）

**AI 引擎偏好（AI Citation Preference）**：
- `chatgpt` — ChatGPT / OpenAI Search
- `pplx` — Perplexity
- `claude` — Claude
- `gemini` — Gemini / Google AIO (AI Overviews)
- `multi` — 多引擎通吃（GEO 安全牌）

### 1.2 速查矩阵

| 形式 | 编号 | Intent | Funnel | AI 偏好 | 一句话定位 |
|---|---|---|---|---|---|
| Listicle | #1 | comm | MOFU | multi（chatgpt 强） | 商业调查阶段 AI 引用率 21.9% 王者 |
| How-to Guide | #2 | info | TOFU/MOFU | gemini, multi | 抢 Featured Snippet + Google AIO |
| Ultimate Guide / Pillar | #3 | info | TOFU | multi（Yext: 3.2× AI 引用） | GEO/AEO 2026 第一形式 |
| Comparison Post | #4 | comm | BOFU | chatgpt（+25.7%） | "X vs Y" 商业决策杀器 |
| Review | #5 | comm | BOFU | claude（E-E-A-T 强） | 联盟营销 / SaaS 引流 |
| Case Study | #6 | comm | MOFU/BOFU | claude, pplx | 原始数据 = AI 引擎特别青睐 |
| Definition / Glossary | #7 | info | TOFU | chatgpt（Wikipedia 风偏好） | "what is X" + 中立结构化 |
| Checklist | #8 | info | TOFU | gemini, multi | 用户收藏 + 复访率 |
| News / Trend | #9 | info | TOFU | gemini（freshness 权重） | 时效流量 + 刷新度信号 |
| Pros and Cons / Problem-Solution | #10 | info | MOFU | multi | "problem-aware" 阶段 |
| Roundup (专家观点) | #11 | info | TOFU/MOFU | multi | 自带传播链 + 外链 |
| Original Research / Data Study | #12 | info | TOFU | multi（+30-40% 引用） | 原创数据 = 不可被 AI 凭空生成 |
| FAQ Page / Hub | #13 | info | 全阶段 | gemini, multi | Q&A 天然契合 AI 答案引擎 |
| Glossary Hub | #14 | info | TOFU | chatgpt, pplx | SaaS / B2B 长尾流量 |
| Template / Resource / Tool | #15 | info | TOFU/MOFU | multi | 可下载 = 邮件订阅 |
| Opinion / Thought Leadership | #16 | info | TOFU | claude（E-E-A-T） | 个人品牌 + 独家观点 |
| Personal Story / Behind-the-Scenes | #17 | info | TOFU | claude | 品牌信任 |
| Interview Post | #18 | info | TOFU | multi | 权威背书 + 自带外链 |
| Curated Roundup（内容策展） | #19 | info | TOFU | gemini | Newsletter 内容回收 |
| Beginner's Guide vs Advanced Guide | #20 | info | TOFU/MOFU | multi | 同主题分级抢长尾 |
| TL;DR-First Structure | #21 | info | TOFU/MOFU | multi（grounding 540 字饱和） | 2026 AI 时代结构标配 |
| Validation / Shortlist Pages | #22 | comm | MOFU/BOFU | chatgpt（+26.9% 引用） | 8 list section + 每句 ≤10 词 |
| Entity-Rich Encyclopedic Post | #23 | info | TOFU | chatgpt, pplx | 模仿 Wikipedia 结构 |
| Multi-Intent Hybrid Post | #24 | info+comm | TOFU→BOFU 全程 | multi | 顶部定义 + 中段对比 + 底部 FAQ |
| Weekly Digest | #25 | info | RETN/TOFU | gemini, multi（freshness + authority） | 行业周报；固定周期聚合；`/weekly` 专属入口 |

---

## 2 · AI 引擎引用率统计（按形式聚合）

### 2.1 Wix 2026.3 三引擎研究

| 形式 | AI Mode | ChatGPT | Perplexity | 商业类查询独立引用率 |
|---|---|---|---|---|
| Listicle (#1) | 19.4% | 24.6% | 21.7% | **40.86%** ⭐ |
| Ultimate Guide (#3) | 18.2% | 19.8% | 22.1% | 11.3% |
| Comparison (#4) | 12.7% | 17.2% | 15.9% | **28.4%** |
| Definition (#7) | 22.1% | 23.4% | 19.6% | 4.2% |
| How-to (#2) | 16.8% | 12.3% | 14.1% | 6.7% |
| FAQ (#13) | 18.6% | 21.8% | 19.4% | 8.5% |
| Other | 23.8% | 15.7% | 19.5% | n/a |

**核心结论**：商业类查询里 **listicle + comparison 合计 69.26%**——这是给 brief 选形式的硬数据依据。

### 2.2 AirOps 2026.4 ChatGPT 子研究

- **带 3 个对比表格的页面**：ChatGPT 引用 +25.7%（#4 强化）
- **8 个 list section 的验证页**：ChatGPT 引用 +26.9%（#22 强化）
- **每句 ≤10 词的精简清单页**：ChatGPT 引用 +18.8%（#22 + Validation 风格）

### 2.3 Yext 680 万 AI 引用研究

- **Topic cluster**（#3 + spokes）比独立文章获得 **3.2× AI 引用**
- HubSpot：pillar-centric cluster 比无连接内容多 **30–43% 自然流量**

### 2.4 LinkedIn 数据（2026 Q1）

- 含**原创数据**的内容（#12）AI 引用率比无数据内容高 **30-40%**

### 2.5 Rebeccavandenberg 结构研究

- AI grounding 在约 **540 字处饱和** → TL;DR 必须置顶（#21）
- 2026 vs 2019 最大结构差异：**摘要从底部 → 顶部**

---

## 3 · 核心十大形式（#1–10）详解

> 每形式 7 字段：定位、何时用、何时**不该**用、AI 引擎适配、字数、骨架、模板 ID

### #1 · Listicle（清单文）

- **定位**：商业调查阶段绝对王者；AI 引用率商业类 40.86%
- **何时用**：用户搜 "best X"、"top X tools"、"10 X for Y"
- **何时不该用**：纯定义类查询（用 #7）；深度教程（用 #2 或 #3）
- **AI 适配**：multi 通吃；ChatGPT 偏好结构化数字开头标题
- **字数**：2,000–4,500（每条 200-400 字 + 引言/结论）
- **骨架**：
  ```
  H1: <数字> Best <Subject> for <Use Case> in 2026 (Data-Backed)
  Abstract
  Key Takeaways
  ## Why these <subject> matter / Selection criteria
  ## #1 <Item Name>
     - Best for: <persona>
     - Why it made the list
     - Pros / Cons
     - Pricing / Specs table
     - Bottom line
  ## #2 ...
  ...
  ## How we tested / Methodology
  ## FAQ
  ## Conclusion
  ## References
  ```
- **模板 ID**：`templates/listicle.md`

### #2 · How-to Guide（步骤指南）

- **定位**：信息查询 + Featured Snippet + Google AIO 抢答
- **何时用**：用户搜 "how to X"、"how do I X"、"X step by step"
- **何时不该用**：决策类查询（用 #4）；概念解释（用 #7）
- **AI 适配**：gemini（步骤型 AIO 卡片）；multi 中等
- **字数**：1,500–3,500
- **骨架**：
  ```
  H1: How to <Action> in <Time Frame> (Beginner's Guide)
  Abstract (50-100 词：what you'll learn + time required)
  Key Takeaways
  ## Before you start (prerequisites/tools)
  ## Step 1: <Action verb>
     ### What this step does
     ### How to do it
     ### Common mistakes
  ## Step 2: ...
  ...
  ## Troubleshooting (top 5 issues)
  ## FAQ
  ## Conclusion
  ## References
  ```
  **配 HowTo schema**（虽部分废弃但 Recipe 类仍支持）
- **模板 ID**：`templates/how-to-guide.md`

### #3 · Ultimate Guide / Pillar Page（终极指南/支柱页）

- **定位**：2026 GEO/AEO **第一形式**；topic cluster 的 hub
- **何时用**：建一个 cluster 的中心页；覆盖宽泛主题
- **何时不该用**：单点问题（用 #2 或 #10）；时效内容（用 #9）
- **AI 适配**：multi 全引擎偏爱；Yext 数据 3.2× AI 引用率
- **字数**：3,000–5,000（不可低于 3,000，否则失去 pillar 资格）
- **骨架**：
  ```
  H1: The Ultimate Guide to <Subject> (2026 Edition)
  Abstract (180-220 词：覆盖范围 + 谁该读)
  Key Takeaways (6-8 条)
  Table of Contents (强制 H2 anchor 链接)
  ## What is <Subject>? (定义 + 历史 + 重要性)
  ## Types/Categories of <Subject>
     ### Subtype A → 链 spoke 1
     ### Subtype B → 链 spoke 2
  ## How <Subject> Works
  ## Benefits and Drawbacks
  ## Choosing the Right <Subject> (决策框架 + 对比表)
  ## How to Get Started (略提步骤，深 → 链 spoke #2 how-to)
  ## Best <Subject> for Different Use Cases (略提推荐，深 → 链 spoke #1 listicle)
  ## Common Mistakes to Avoid
  ## Future Trends (2026 Outlook)
  ## FAQ (10+ 题)
  ## Conclusion
  ## Further Reading (链 spokes 3-7)
  ## References
  ```
- **模板 ID**：`templates/pillar-page.md`

### #4 · Comparison Post（对比文）

- **定位**：BOFU 决策杀器；AirOps 数据 +25.7% AI 引用（3 对比表）
- **何时用**：用户搜 "X vs Y"、"alternatives to X"、"X or Y for Z"
- **何时不该用**：单产品评测（用 #5）；类目概览（用 #1）
- **AI 适配**：chatgpt 极强；3 对比表是触发器
- **字数**：2,500–4,500
- **骨架**：
  ```
  H1: <X> vs <Y>: Which Is Better for <Use Case> in 2026?
  Abstract (含 verdict 一句：80% 读者只看这句)
  Key Takeaways (含 "Choose X if..." / "Choose Y if..." 决策框架)
  ## Quick Comparison Table (⭐ 表 #1，必须前 25% 篇幅)
  ## Pricing Comparison (⭐ 表 #2)
  ## Feature-by-Feature (⭐ 表 #3)
  ## <X>: Strengths & Weaknesses
  ## <Y>: Strengths & Weaknesses
  ## Real-World Use Cases
  ## Performance Comparison (data-backed)
  ## When to Choose <X>
  ## When to Choose <Y>
  ## Migration Path (if applicable)
  ## FAQ
  ## Verdict (⭐ 同 Abstract 的 verdict 但展开)
  ## References
  ```
- **模板 ID**：`templates/comparison.md`

### #5 · Review / Product Review（评测文）

- **定位**：BOFU 联盟营销 / SaaS 引流；强 E-E-A-T
- **何时用**：单产品深度评测（含真实使用经验）
- **何时不该用**：对比多产品（用 #4）；类目概览（用 #1）
- **AI 适配**：claude 偏好（E-E-A-T 强）；ChatGPT 中等
- **字数**：2,000–3,500
- **骨架**：
  ```
  H1: <Product Name> Review (2026): Is It Worth the <Price>?
  Abstract (verdict + rating /10)
  Key Takeaways (Pros / Cons / Best for)
  ## Quick Summary Box (⭐ 含 rating + price + best for + alternatives)
  ## What is <Product>?
  ## Who Should Use This?
  ## Pricing & Plans
  ## Key Features (deep dive, with screenshots)
  ## Performance / Real-World Testing
     ### Setup experience
     ### Daily use
     ### Edge cases
  ## Pros and Cons
  ## How It Compares (mini 对比表 vs 2-3 竞品)
  ## Customer Reviews Summary (avg rating, common praise, common complaints)
  ## Pricing vs Value
  ## My Verdict (含 rating /10)
  ## Alternatives (链 #4)
  ## FAQ
  ## References
  ```
  **配 Review schema** + Organization schema
- **模板 ID**：`templates/product-review.md`

### #6 · Case Study（案例研究）

- **定位**：E-E-A-T 杀器；AI 引擎特别青睐原始数据
- **何时用**：有真实客户成果 + 数据 + 复盘
- **何时不该用**：泛理论介绍（用 #3）；产品宣传（用 #5）
- **AI 适配**：claude / pplx 偏爱；data freshness 强
- **字数**：2,000–4,000
- **骨架**：
  ```
  H1: How <Company> Achieved <Specific Result> with <Method> (Case Study)
  Abstract (含三个数字：起始数值 / 结果数值 / 时间)
  Key Takeaways (5-7 actionable insights)
  ## Company Background
  ## The Challenge (含起始数值的具体数据)
  ## What We Tried (Approach)
  ## The Strategy / Implementation
     ### Step / Phase 1
     ### Step / Phase 2
  ## Results (⭐ 强数据图表区，多个 charts)
     - Metric 1: X → Y (+N%)
     - Metric 2: ...
  ## What Worked
  ## What Didn't Work (诚实加分)
  ## Lessons Learned
  ## Replicating This (For your business)
  ## Tools & Resources Used
  ## FAQ
  ## References (含原始数据来源 / Methodology)
  ```
  必须含 **≥3 个 original data (plain prose) Information Gain Markers**
- **模板 ID**：`templates/case-study.md`

### #7 · Expanded Definition / Glossary Post（深度释义/词条文）

- **定位**："what is X" 类型；Wikipedia 风格 = ChatGPT 训练偏好
- **何时用**：单一概念深度释义
- **何时不该用**：操作教程（用 #2）；产品对比（用 #4）
- **AI 适配**：chatgpt 强；pplx 中等
- **字数**：1,500–3,000
- **骨架**：
  ```
  H1: What Is <Subject>? Definition, Types & Examples (2026)
  Abstract (核心定义一句 + 35-50 词扩展)
  Key Takeaways
  Table of Contents
  ## Definition (⭐ 强制前 100 词，独立段，AI grounding 最佳位)
  ## Etymology / History (Wikipedia 风格加分)
  ## Types of <Subject>
     ### Type A
     ### Type B
     ### Type C
  ## How <Subject> Works (机制)
  ## Examples (5-8 具体例子)
  ## Use Cases / Applications
  ## Advantages
  ## Disadvantages / Limitations
  ## Related Concepts (链 glossary hub 其它词条)
  ## Common Misconceptions
  ## FAQ
  ## References (Wikipedia / 学术源优先)
  ```
- **模板 ID**：`templates/definition.md` / `templates/glossary-entry.md`

### #8 · Checklist / Cheat Sheet（清单/速查表）

- **定位**：用户会收藏复访 → 高复访率 + 邮箱订阅
- **何时用**：操作流程 / 准备清单 / 评估指标
- **何时不该用**：教程（用 #2）；理论（用 #7）
- **AI 适配**：gemini / multi；列表化 + checkbox 易抽
- **字数**：1,200–2,500
- **骨架**：
  ```
  H1: The Complete <Subject> Checklist (Downloadable PDF)
  Abstract (谁该用 + 完成后能做什么)
  Key Takeaways
  ## How to Use This Checklist
  ## Section 1: <Phase Name> Checklist
     - **Item 1** (with 1-line explanation)
     - **Item 2** ...
     (plain bold-led items — NEVER GFM `- [ ]` checkboxes: the publisher's
      markdown-it has no tasklists plugin, "[ ]" leaks literally; render_lint L13)
  ## Section 2: ...
  ## Bonus Tips
  ## Common Mistakes
  ## Download as PDF / Print Version (⭐ CTA)
  ## FAQ
  ## References
  ```
- **模板 ID**：`templates/checklist.md`

### #9 · News / Trend Post（行业新闻/趋势文）

- **定位**：时效流量；freshness 信号
- **何时用**：3-7 天内的行业事件；季度/年度趋势报告
- **何时不该用**：常青主题（用 #3）；评测（用 #5）
- **AI 适配**：gemini 强（freshness 权重高）；其它中等
- **字数**：800–2,000（短而快）
- **骨架**：
  ```
  H1: <Event Name>: What It Means for <Industry> (2026)
  Date Stamp (⭐ 醒目)
  Abstract (新事件 + 影响 + 关键日期)
  ## What Happened
  ## Why It Matters
  ## Industry Reactions
  ## What's Next (Predictions)
  ## What You Should Do
  ## Related Stories
  ## References (含主要新闻源链接)
  ```
  **配 NewsArticle schema** + datePublished + dateModified
- **模板 ID**：`templates/news-analysis.md`

### #10 · Pros and Cons / Problem-Solution（利弊/痛点解决文）

- **定位**："problem-aware" 阶段；用户已知问题想找解法
- **何时用**：用户搜 "why X doesn't work"、"problems with X"、"how to fix X"
- **何时不该用**：决策类（用 #4）；新概念（用 #7）
- **AI 适配**：multi
- **字数**：1,800–3,200
- **骨架**：
  ```
  H1: 7 Common Problems with <Subject> (And How to Solve Them)
  Abstract (问题数 + 总体诊断)
  Key Takeaways (解法摘要)
  ## Problem 1: <Specific Issue>
     ### Why this happens
     ### How to identify it
     ### Solution (with code/steps if applicable)
     ### Prevention
  ## Problem 2: ...
  ## When to Get Professional Help
  ## FAQ
  ## References
  ```
- **模板 ID**：`templates/problem-solution.md`

---

## 4 · 进阶形式（#11–20）详解

> 与核心十大相同的 7 字段格式，简版。

### #11 Roundup Post（专家观点汇总）
- **定位**：20 位专家访谈聚合；自带传播链
- **字数**：3,000–5,000
- **关键设计**：每专家独立 H3 + 头像 + 1-2 句金句 + 公司/职位 + 社交链接
- **AI 适配**：multi；权威性强
- **模板 ID**：`templates/roundup.md`

### #12 Original Research / Data Study（原创研究）
- **定位**：LinkedIn 数据 +30-40% AI 引用率；无可替代壁垒
- **字数**：3,000–6,000
- **关键设计**：含 methodology section + 原始 dataset 下载 + ≥5 charts + 多个 original data points (plain prose)
- **AI 适配**：multi 通吃（最佳武器）
- **模板 ID**：`templates/data-research.md`

### #13 FAQ Page / Hub（FAQ 集合页）
- **定位**：Q&A 天然契合 AI 答案引擎
- **字数**：2,000–4,000（每问 50-200 词答案）
- **关键设计**：每问独立 H2/H3，**配 FAQPage schema 取 rich result**
- **AI 适配**：gemini / multi；rich snippet 触发器
- **模板 ID**：`templates/faq-knowledge.md`

### #14 Glossary Hub（术语库）
- **定位**：SaaS / B2B 长尾流量；hub-and-spoke
- **字数**：hub 1,500-2,500（含 50+ 词条概览） + 每词条独立页 #7 形式
- **关键设计**：字母索引 + 词条互链
- **AI 适配**：chatgpt / pplx 偏爱
- **模板 ID**：`templates/glossary-hub.md`

### #15 Template / Resource / Tool Post（模板/资源文）
- **定位**：可下载资源 = 邮件订阅
- **字数**：1,500–3,000
- **关键设计**：可下载 PDF/Notion/Excel；强 CTA 表单
- **AI 适配**：multi；下载链接被引用率高
- **模板 ID**：`templates/template-resource.md`

### #16 Opinion / Thought Leadership Post（观点文）
- **定位**：建立个人品牌；强 E-E-A-T 中 Experience
- **字数**：1,500–3,500
- **关键设计**：清晰立场 + 论据 + 反方观点公平呈现 + 行动建议
- **AI 适配**：claude 偏爱（E-E-A-T）；其它中等
- **模板 ID**：`templates/opinion.md`

### #17 Personal Story / Behind-the-Scenes（个人故事）
- **定位**：品牌信任建立；情感联结
- **字数**：1,500–3,000
- **关键设计**：时间线叙事 + 真实数据/截图 + lesson learned
- **AI 适配**：claude；情感性强
- **模板 ID**：`templates/personal-story.md`

### #18 Interview Post（访谈文）
- **定位**：1v1 行业人物访谈；权威背书 + 自带外链
- **字数**：2,000–4,000
- **关键设计**：Q&A 格式 + 嘉宾介绍 + 关键金句 pull quote
- **AI 适配**：multi；引用率与嘉宾权威性相关
- **模板 ID**：`templates/interview.md`

### #19 Curated Roundup（内容策展）
- **定位**：Newsletter 内容回收
- **字数**：800–1,800
- **关键设计**：精选 5-15 个外部资源 + 你的一句评注
- **AI 适配**：gemini（freshness）
- **模板 ID**：`templates/curated-roundup.md`

### #20 Beginner's Guide vs Advanced Guide（分级指南）
- **定位**：同主题两篇分级抢长尾
- **字数**：Beginner 2,000–3,000 / Advanced 3,000–5,000
- **关键设计**：明确 prerequisites + 互链 + level 标签
- **AI 适配**：multi
- **模板 ID**：`templates/level-guide.md`（参数化 level=beginner/advanced）

---

## 5 · 2026 AI 搜索时代新兴形式（#21–24）

### #21 TL;DR-First Structure（前置摘要结构）

- **定位**：2026 与 2019 最大结构差异；AI grounding 540 字饱和
- **何时用**：**任何形式都应该叠加**这个结构（不是独立形式，是 modifier）
- **关键设计**：
  - 第 1 屏（前 540 字）必须包含：核心答案 + 关键数字 + verdict
  - Abstract 前置，不放底部
  - 第一个 H2 之前必须有 "TL;DR" / "Quick Answer" / "Verdict" 段
- **AI 适配**：multi；所有引擎 grounding 都在第一段
- **集成方式**：v3.0 的所有 outline-architect 默认开启 TL;DR-first

### #22 Validation / Shortlist Pages（验证清单页）

- **定位**：AirOps 数据 +26.9% ChatGPT 引用
- **何时用**：商业调查 "best X for Y"、"top X under $Z"
- **关键设计**：
  - **必须 8 个 list section**（不多不少最佳）
  - **每句 ≤ 10 词**
  - 每条带 1 行 verdict + 1 行 caveat
  - 极简清单视觉
- **AI 适配**：chatgpt 极强；pplx 中等
- **模板 ID**：`templates/shortlist-validation.md`
- **与 #1 listicle 区别**：listicle 每条 200-400 词深度；validation 每条 ≤50 词浓缩

### #23 Entity-Rich Encyclopedic Post（实体丰富百科式）

- **定位**：模仿 Wikipedia 结构 = AI 信任
- **何时用**：知识型主题；定义类（升级版 #7）
- **关键设计**：
  - 中立语气（无 sales）
  - 强 References 区（10+ 学术/官方源）
  - Table of Contents 强制
  - 每段含 ≥1 实体（人名/公司/地点/产品名 schema markup）
  - Wikipedia 风格 H2：Background / Etymology / Types / Process / Applications / Criticism / See Also / References
- **AI 适配**：chatgpt / pplx 极强（训练数据偏好）
- **模板 ID**：`templates/encyclopedic.md`

### #24 Multi-Intent Hybrid Post（多意图混合文）

- **定位**：2026 核心思路——一篇文章同时服务 discovery + depth intent
- **何时用**：宽泛主题 + 高搜索量 + 多种 intent 重叠
- **关键设计**：
  - **顶部回答定义**（#7 风格，<500 词）
  - **中段对比/教程**（#4 或 #2 风格，1500-2500 词）
  - **底部 FAQ + 延伸**（#13 风格，800-1500 词）
- **AI 适配**：multi；每段服务不同引擎抽取
- **模板 ID**：`templates/multi-intent-hybrid.md`
- **总字数**：3,500–5,500（接近 pillar 但结构不同）

### #25 · Weekly Digest（行业周报）

- **定位**：固定周期行业聚合；freshness 信号 + 权威声音；留存型订阅流量
- **何时用**：每周一期行业新闻汇总；有固定受众群（Newsletter / RSS 订阅者）；品牌希望建立"本领域权威声音"
- **何时不该用**：单篇深度分析（用 #9 news-analysis）；常青主题（用 #3 pillar）；无固定发布节奏时
- **AI 适配**：gemini 强（freshness 权重 + 结构化条目易抽取）；multi（ItemList schema + FAQPage 覆盖多引擎）
- **字数**：2,000–2,800（固定周期；简洁优先）
- **骨架**：
  ```
  H1: {Industry} Weekly: {YYYY-MM-DD} — {Punchy Hook Phrase}

  ## TL;DR (60-90w)
  本周 3-5 条最大新闻 bullet（每条 ≤ 15 词）

  ## The Big Story (~400w)
  本周 #1 事件：事实 + 品牌视角 + 一个引用数字

  ## Also This Week
  N 条 (~150-200w each)：发生了什么（含引用）+ 品牌点评（标注为观点）

  ## By the Numbers (optional, ~150w)
  本周核心数据；第一手数据标 original data (plain prose)

  ## On Our Radar (~150w)
  4-6 条小新闻 bullet，每条 ≤ 25 词 + 来源链接

  ## Follow-ups (optional, ~150w)
  前期故事的本周更新；注明原文日期

  ## FAQ (2-3 问)

  ## References (APA-7, 8-15 条)
  <hr />
  <p class="article-signature">...</p>
  ```
  **配 BlogPosting + ItemList + FAQPage schema**；`datePublished` + `dateModified` 必填
- **模板 ID**：`templates/weekly-digest.md`
- **入口限制**：**仅 `/weekly` 技能可强制选择此形式**；`format-selector` keyword 匹配不会自动路由到此形式

---

## 6 · 形式选择决策树

> 这是 `format-selector` skill 的核心算法。给定 brief，按以下决策树选最优形式。

```
┌─ Step 1: Intent 分类 ─────────────────────────────────────
│ keyword 含 "what is" / "definition" / "meaning" → 走 Info-Define
│ keyword 含 "how to" / "step by step" / "tutorial" → 走 Info-Howto
│ keyword 含 "best X" / "top X" / "X tools" → 走 Comm-Listicle
│ keyword 含 "X vs Y" / "alternatives" / "X or Y" → 走 Comm-Compare
│ keyword 含 "X review" / "is X worth" → 走 Comm-Review
│ keyword 含 "X problems" / "why X" / "fix X" → 走 Info-ProblemSolve
│ keyword 含 "X case study" / "how company achieved" → 走 Comm-CaseStudy
│ keyword 含 "X 2026" / "X trends" → 走 Info-News
│ keyword 含 "X checklist" / "X template" → 走 Info-Checklist/Template
│ keyword 无明确触发词 + 宽泛主题 + word_count >= 4000 → 走 Pillar
│ 否则 → 走 Default-Multi-Intent (#24)
│
┌─ Step 2: Funnel 修正 ────────────────────────────────────
│ 若 brief.surfaces 含 "shopping" / "transactional" → 优先 BOFU 形式
│   → Comparison (#4) / Review (#5) / Validation (#22)
│ 若 brief.surfaces 含 "ai-assistant" 且仅一个 → 走对应引擎偏好
│   chatgpt → Listicle (#1) / Shortlist (#22) / Encyclopedic (#23)
│   perplexity → Case Study (#6) / Original Research (#12)
│   claude → Review (#5) / Opinion (#16) / Personal Story (#17)
│   gemini → How-to (#2) / News (#9) / FAQ Hub (#13)
│ 若 brief.surfaces 含 "ai-assistant" 多个 → 走 multi 通吃形式 (#3/#24)
│
┌─ Step 3: 数据可得性 gate ─────────────────────────────────
│ 若可以拿到原始数据（GA4/客户访谈/调研） → 强烈优先 #12 Original Research
│ 若 brand 有真实客户成果 → 强烈优先 #6 Case Study
│ 若仅有公开信息 → 走 Step 1 默认结果
│
┌─ Step 4: 现有 cluster 检查 ──────────────────────────────
│ 读 projects/{slug}/existing-clusters.json
│ 若该主题已有 pillar → 写 spoke（#2/#4/#5/#7 等具体形式）
│ 若该主题无 pillar → 优先 #3 Pillar 建 hub
│ 若多个 spokes 已存在但无 hub → 强制 #3 Pillar
│
┌─ Step 5: 叠加 modifier ──────────────────────────────────
│ 总是叠加 #21 TL;DR-First Structure（所有形式都用）
│ 若 brief.surfaces 含 "ai-assistant" → 叠加 Citation Capsule per H2
│ 若 word_count >= 3000 → 叠加 ToC + 强制 Information Gain Markers
│ 若 industry = YMYL（health/finance/legal） → 叠加强 E-E-A-T 信号
│
└─ Output: format_id + modifiers + template_path
```

### 6.1 决策树伪代码

```python
def select_format(brief, project_context):
    # Step 1
    intent_format = match_keyword_pattern(brief.primary_keyword)
    
    # Step 2 - Funnel & AI target adjustment
    if "shopping" in brief.target_surfaces:
        format = upgrade_to_bofu(intent_format)  # #1 → #22, #2 → #4 etc
    if len(brief.ai_engine_targets) == 1:
        format = engine_specific_preference(brief.ai_engine_targets[0])
    
    # Step 3 - Data availability
    if project_context.has_original_data:
        format = "data-research" if intent_format == "info" else "case-study"
    
    # Step 4 - Cluster check
    cluster_state = check_cluster(brief.primary_keyword, project_context)
    if cluster_state == "no-pillar-multiple-spokes":
        format = "pillar"
    elif cluster_state == "has-pillar":
        format = downgrade_to_spoke(format)
    
    # Step 5 - Modifiers
    modifiers = ["tldr-first"]
    if "ai-assistant" in brief.target_surfaces:
        modifiers.append("citation-capsules-per-h2")
    if brief.word_count >= 3000:
        modifiers.extend(["mandatory-toc", "info-gain-prose"])
    if project_context.industry in YMYL_INDUSTRIES:
        modifiers.append("strong-eeat-signals")
    
    return FormatDecision(
        format_id=format,
        modifiers=modifiers,
        template_path=f"templates/{format}.md",
        rationale=explain(format, modifiers)
    )
```

---

## 7 · 模板骨架对照（24 形式 × templates/ 目录）

更新 v3.0 的 `templates/` 从 15 → **24** 个文件：

```
templates/
├── listicle.md                    #1
├── how-to-guide.md                #2
├── pillar-page.md                 #3
├── comparison.md                  #4
├── product-review.md              #5
├── case-study.md                  #6
├── definition.md                  #7
├── checklist.md                   #8
├── news-analysis.md               #9
├── problem-solution.md            #10
├── roundup.md                     #11
├── data-research.md               #12
├── faq-knowledge.md               #13
├── glossary-hub.md                #14
├── template-resource.md           #15
├── opinion.md                     #16
├── personal-story.md              #17
├── interview.md                   #18
├── curated-roundup.md             #19
├── level-guide.md                 #20 (参数化 level)
├── shortlist-validation.md        #22 (新增)
├── encyclopedic.md                #23 (新增)
├── multi-intent-hybrid.md         #24 (新增)
├── weekly-digest.md               #25 (/weekly 入口专属；固定周期行业周报)
└── _modifiers/
    ├── tldr-first.md              #21（modifier 而非独立形式）
    ├── citation-capsules.md
    ├── eeat-strong.md
    └── ai-quotable.md
```

---

## 8 · 与 v3.0 skills 的接线

### 8.1 新增 skill：`format-selector`

放 `subskills/plan/format-selector/SKILL.md`：

```markdown
---
name: format-selector
description: Choose the optimal blog format from the evidence-backed templates (source of truth = schemas/angle.schema.json :: format_id enum, currently 27) based on brief intent × funnel × AI target. Use whenever the user asks to write any blog post — this skill runs BEFORE topic-angle-selector to constrain the angle search space to the right format.
---

# Format Selector

Read `references/seo/blog-formats-2026.md` and decide format using the
5-step decision tree.

## Inputs
- brief (from active project + per-article overrides)
- project_context (business-context.json + existing-clusters.json)

## Output
{
  "format_id": "listicle" | "pillar" | ... (one of the schemas/angle.schema.json format_id enum),
  "modifiers": ["tldr-first", "citation-capsules-per-h2", ...],
  "template_path": "templates/<format>.md",
  "rationale": "Chose listicle because: keyword 'best fishing rods 2026' = commercial-investigation intent + brief.surfaces=[google-aio,chatgpt] + projects.existing-clusters has no listicle for this keyword. Cited research: Wix 2026.3 listicle has 40.86% AI citation rate on commercial queries.",
  "evidence_data": {
    "citation_rate_expected": 0.41,
    "research_source": "Wix 2026.3"
  }
}
```

### 8.2 修改 skill：`topic-angle-selector`

变更：**format 选定后再选 angle**（不是先 angle 后 format）：
- format-selector 决定 #1 listicle
- topic-angle-selector 在 listicle 内部 12 angle 子集里选（"10 best..." / "7 ways..." / "21 surprising..."）
- 这样 angle 一定与 format 兼容

### 8.3 修改 skill：`outline-architect`

按 format_id 选 outline 骨架（见 §3 各形式骨架）。从此 outline 不再"凭直觉"。

### 8.4 修改 skill：`section-drafter`

新增字段输入：`format_id` + `modifiers[]`。drafter 知道这是 listicle 第 #3 段（应 200-400 词 + pros/cons + 1 表）vs pillar 第 #3 段（应 800-1200 词 + 链 spoke）。

### 8.5 修改 skill：`quality-gate-cite`

新增维度：**format_fit_score**
- 形式与 intent 匹配 → +10
- 形式与 surface 匹配 → +10
- modifier 全部应用 → +5
- 不匹配 → 触发 repair 建议改 format

### 8.6 修改 skill：`geo-content-optimizer`

按 `evidence_data.research_source` 引用具体数据。例：
> "This listicle format is optimized for ChatGPT citation (Wix 2026.3 study: 40.86% commercial query citation rate)."

---

## 9 · 形式 × Brief 字段的硬约束映射

| Brief 字段 | 影响的形式选择 |
|---|---|
| `keywords[0]` 含 trigger words（如 "best/top"） | 强制 listicle / shortlist |
| `word_count_target < 1500` | 排除 pillar / case-study / data-research |
| `word_count_target > 4000` | 优先 pillar / multi-intent-hybrid / data-research |
| `target_surfaces=["shopping"]` | 优先 BOFU 形式（#4/#5/#22） |
| `target_surfaces=["ai-assistant-chatgpt"]` | 优先 #1/#22/#23 |
| `target_surfaces=["ai-assistant-pplx"]` | 优先 #6/#12 |
| `target_surfaces=["ai-assistant-claude"]` | 优先 #5/#16/#17 |
| `target_surfaces=["ai-assistant-gemini"]` | 优先 #2/#9/#13 |
| `target_surfaces=["reddit"]` | 优先 #17 personal-story 类口语 |
| `industry=YMYL` | 强制叠加 strong-eeat modifier；不允许纯 opinion |
| `cluster_state=no-pillar-multiple-spokes` | 强制 pillar |
| `cluster_state=has-pillar-need-spoke` | 排除 pillar |
| `freshness_required=true` | 优先 #9 news / #19 curated |
| `data_available=true` | 强烈优先 #6/#12 |

---

## 10 · 反例：什么形式**不该**用（避坑）

| 错配 | 真实后果 | 应改用 |
|---|---|---|
| 1500 词写 pillar | 算法判断"thin pillar"，cluster 失效 | 升级到 3000+ 词 或 改 listicle |
| 用 listicle 写 "what is X" | 反人类，跳出率高 | 改 #7 definition |
| 用 case study 写无真实数据的故事 | YMYL 违规 + AI 检测假数据 | 改 #16 opinion / #17 story |
| 用 #5 review 写自家产品 + 满分 | 违 E-E-A-T；ChatGPT 不引 | 改 #16 thought leadership + 诚实 cons |
| 用 #1 listicle 推广联盟链接但隐藏披露 | T03 Veto 触发 → BLOCKED | 加 affiliate disclosure |
| 用 #9 news 写 6 个月前事件 | freshness 信号失效；Gemini 降权 | 改 #3 pillar 或 #16 opinion |
| 单纯 #21 TL;DR（无主体） | TL;DR 是 modifier 不是形式 | 叠加在任一形式上 |
| 多 #4 comparison 写相同对比对 | cannibalization | 合并 或 改 cluster pillar+spokes |
| 用 #12 original research 但样本 N<30 | 数据可信度低 | 增样本 或 改 #16 opinion |
| 用 #23 encyclopedic 写产品广告 | Wikipedia 风格 + sales 冲突 | 改 #5 review |

---

## 附录 A · 形式选择 cheat sheet（贴在桌面）

```
+-------------------+---------------------+----------------------+
| Brief 关键信号     | 选这个形式            | 二选项                |
+-------------------+---------------------+----------------------+
| "best X 2026"     | #1 Listicle         | #22 Shortlist        |
| "how to X"        | #2 How-to           | #3 Pillar (if broad) |
| "X vs Y"          | #4 Comparison       | #22 Shortlist        |
| "X review"        | #5 Review           | #16 Opinion          |
| "what is X"       | #7 Definition       | #23 Encyclopedic     |
| "X for beginners" | #20 Level Guide     | #3 Pillar            |
| "X case study"    | #6 Case Study       | #12 Data Research    |
| "X problems"      | #10 Problem-Solve   | #2 How-to (fix)      |
| "X 2026 trends"   | #9 News/Trend       | #3 Pillar (annual)   |
| "X checklist"     | #8 Checklist        | #15 Template         |
| (broad topic, no  | #3 Pillar           | #24 Multi-Intent     |
|  cluster yet)     |                     |                      |
| (AI ChatGPT goal) | #1 Listicle (+#22)  | #23 Encyclopedic     |
| (AI PPLX goal)    | #6 Case Study       | #12 Data Research    |
| (AI Claude goal)  | #5 Review / #16     | #17 Personal Story   |
| (AI Gemini goal)  | #2 How-to           | #13 FAQ Hub          |
| (Original data    | #12 Data Research   | #6 Case Study        |
|  available)       |                     |                      |
+-------------------+---------------------+----------------------+

Always overlay:
  • #21 TL;DR-First (top 540 words have key answer)
  • Citation Capsules per H2 (if AI-target)
  • original data / real first-hand experience / original analysis — all expressed as plain prose
```

---

## 附录 B · 24 形式 × 5 阶段 pipeline 时间分配

| Phase | 各形式可能不同的处理 |
|---|---|
| Research | listicle 需 SERP 拉竞品列表；pillar 需 cluster scan；case-study 需自家数据；data-research 需调研设计 |
| Plan | format-selector 是 Plan 阶段第一步 |
| Build | section-drafter 按 format_id 选不同 outline；listicle 每条平均 200-400w 并行写；pillar 各 section 800-1200w |
| Optimize | quality-gate-cite 加 format_fit 维度；具体形式触发不同 modifier 检验 |
| Publish | comparison/listicle 需特殊 schema（ItemList）；review 需 Review schema；FAQ hub 需 FAQPage |
| Monitor | listicle 引用率监测 vs Wix 基线；pillar cluster 健康度监测 vs Yext 3.2× 基线 |

---

*版本 1.0 · 2026-05-19 · 24 形式三维分类完整目录 · 将整合到插件 `references/seo/blog-formats-2026.md`*
