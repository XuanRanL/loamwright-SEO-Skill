#!/usr/bin/env python3
"""scripts/build/data_chart_png.py — render clean, BRAND-COLORED data charts as PNG
with REAL text labels (no AI-image garbled text). Addresses the gap where data/diagram
image slots were routed to the AI photo generator and came back text-free + dull.

Chart types:
  - vbar         : vertical bar chart (value labels on bars, category labels, unit)
  - grouped_vbar : vertical bars with TWO+ series per category + a legend
  - rangebar     : horizontal range-band chart (min..max band per row + annotation)
  - table        : multi-column comparison / verdict matrix

Resolution (2026-06-15): charts render at 2x supersample — a logical 1024 layout
drawn at SCALE=2 → 2048x2048 device px — so text is retina-crisp and many-bar charts
stop colliding labels (the 2026-06-14 QA found "9 bars in a 1024px canvas ≈ 90px/slot
→ labels overlap"; at 2048 each slot is ~180px). ALL geometry/font literals go through
px()/_f() so a single SCALE change rescales the whole chart proportionally.

Usage:
  python -m scripts.build.data_chart_png --spec spec.json --out out.png
Spec JSON shape: see CHART specs created by the caller.
"""
from __future__ import annotations
import argparse, json, math, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# ── Supersample scale ────────────────────────────────────────────────────────
# Logical layout is authored in 1024-space; everything is drawn at SCALE× so the
# output is crisp on 2x displays. Bump SCALE to change density everywhere at once.
SCALE = 2
BASE = 1024
CANVAS = BASE * SCALE   # 2048 default square canvas


def px(n: float) -> int:
    """Scale a logical (1024-space) pixel value to device pixels."""
    return int(round(n * SCALE))


# NEUTRAL, project-AGNOSTIC defaults — deliberately NOT any one brand's colors.
# Each project's real palette + footer is applied at render time via set_brand()
# (render_data_charts.py reads it from projects/{slug}/brand-config + site_url).
# A project that has no brand-config gets these neutral slate charts and NO footer
# — never another project's brand. (Fixes the project-charlie-green/footer leak.)
PRIMARY = (45, 55, 68)       # neutral deep slate
SECONDARY = (150, 120, 90)   # neutral warm grey
ACCENT = (180, 170, 155)     # neutral sand
GREEN_MID = (95, 112, 128)   # neutral mid slate
GREY = (120, 120, 116)
LIGHTGREY = (210, 210, 204)
BG = (251, 251, 248)         # off-white
INK = (34, 40, 38)
FOOTER_DOMAIN = ""           # empty = no watermark unless a project sets one


def _ink_on(bg) -> tuple:
    """Return a readable text color (white or near-black) for text drawn ON `bg`.
    Fixes invisible white-on-light-brand text for projects with a light primary."""
    r, g, b = (bg or (0, 0, 0))[:3]
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return (255, 255, 255) if lum < 140 else (28, 34, 38)

# Cross-platform font resolution: Windows Arial → common Linux DejaVu fallbacks.
def _resolve_font(bold: bool) -> str:
    import os
    candidates = (
        ["C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/Library/Fonts/Arial Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
        if bold else
        ["C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/Library/Fonts/Arial.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]
    )
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[0]

FONT = _resolve_font(False)
FONTB = _resolve_font(True)


def _hex_to_rgb(h):
    if isinstance(h, (list, tuple)):
        return tuple(h)[:3]
    h = str(h).lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def set_brand(primary=None, secondary=None, accent=None, footer=None,
              font=None, font_bold=None):
    """Override the default palette/footer/font for a project. Accepts hex strings
    or RGB tuples. Called by render_data_charts.py from brand-config so charts
    match each project's brand without hardcoding."""
    global PRIMARY, SECONDARY, ACCENT, GREEN_MID, FOOTER_DOMAIN, FONT, FONTB
    if primary:
        PRIMARY = _hex_to_rgb(primary)
        # derive a readable mid-tone from primary for secondary bars
        GREEN_MID = tuple(min(255, int(c + (255 - c) * 0.32)) for c in PRIMARY)
    if secondary:
        SECONDARY = _hex_to_rgb(secondary)
    if accent:
        ACCENT = _hex_to_rgb(accent)
    if footer:
        FOOTER_DOMAIN = str(footer)
    if font:
        FONT = font
    if font_bold:
        FONTB = font_bold

def _f(sz, bold=False):
    """A logical font size, scaled to device px so text matches the supersample."""
    return ImageFont.truetype(FONTB if bold else FONT, max(1, px(sz)))

def _center(d, x, y, text, font, fill, anchor="mm"):
    d.text((x, y), text, font=font, fill=fill, anchor=anchor)

def _wrap(text, font, max_w, d, max_lines=None):
    """Greedy word wrap; optional ``max_lines`` clamp with an ellipsized last line.

    The clamp exists because unclamped x-axis labels that wrap to 3-4 lines walk
    down into the source-citation footer (2026-07-07 batch: a vbar's 4-line labels
    collided with a 2-line footer → image-QA C1 defect + a regen round). Geometry:
    label line 3 sits at H-72px, a 2-line footer starts at H-84px — collision is
    guaranteed at ≥3 lines, so vbar/grouped_vbar clamp to 2 (rangebar already did).
    """
    words = text.split(); lines=[]; cur=""
    for w in words:
        t=(cur+" "+w).strip()
        if d.textlength(t, font=font) <= max_w: cur=t
        else:
            if cur: lines.append(cur)
            cur=w
    if cur: lines.append(cur)
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and d.textlength(last + "…", font=font) > max_w:
            last = last[:-1]
        lines[-1] = last + "…"
    return lines


def _fmt_num(v, span):
    """Format an axis tick / value label with precision driven by the data span,
    then drop a needless trailing '.0' on whole numbers.

    Fixes the 2026-06-14 'Y-axis ticks degrade to 0,1,1,1,2' defect: a chart whose
    values live below 2 (e.g. density 0.97/1.13/1.32) needs 2 decimals, not the old
    hardcoded {:.0f}. A wide integer chart ($13..$35) still reads as clean integers."""
    a = abs(span)
    dec = 2 if a < 2 else (1 if a < 20 else 0)
    s = f"{v:.{dec}f}"
    if dec:
        try:
            if float(s) == int(float(s)):
                s = f"{int(float(s))}"
        except (ValueError, OverflowError):
            pass
    return s

def _header(d, W, title, subtitle):
    tf=_f(46, True); sf=_f(26)
    y=px(64)
    for ln in _wrap(title, tf, W-px(130), d):
        _center(d, W//2, y, ln, tf, PRIMARY); y+=px(58)
    if subtitle:
        y+=px(6)
        for ln in _wrap(subtitle, sf, W-px(160), d):
            _center(d, W//2, y, ln, sf, GREY); y+=px(34)
    return y+px(18)

def _footer(d, W, H, source):
    if source:
        sf=_f(20)
        lines=_wrap(str(source), sf, W-px(120), d, max_lines=2)
        y=H-px(58)-(len(lines)-1)*px(26)
        for ln in lines:
            _center(d, W//2, y, ln, sf, GREY); y+=px(26)
    if FOOTER_DOMAIN:   # only watermark when a project actually set its domain
        _center(d, W-px(14), H-px(22), FOOTER_DOMAIN, _f(19, True), LIGHTGREY, anchor="rm")

def _readable_on_bg(col):
    """Bar color is fine on the off-white BG unless it's very light, then use INK."""
    lum = 0.299 * col[0] + 0.587 * col[1] + 0.114 * col[2]
    return col if lum < 205 else INK


def render_vbar(spec, W=CANVAS, H=CANVAS):
    bars = spec.get("bars") or []
    if not bars:
        raise ValueError("vbar chart_spec has no non-empty 'bars'")
    img=Image.new("RGB",(W,H),BG); d=ImageDraw.Draw(img)
    top=_header(d, W, spec["title"], spec.get("subtitle",""))
    unit=spec.get("unit","")
    plot_top=top+px(30); plot_bottom=H-px(150); plot_h=plot_bottom-plot_top
    left=px(130); right=W-px(80); plot_w=right-left
    vals=[float(b["value"]) for b in bars]
    # Zero-anchored scale that includes negatives (e.g. a -4.2 ranking change).
    hi=max(max(vals), float(spec.get("y_max", 0)), 0.0)
    lo=min(min(vals), 0.0)
    span=(hi-lo) or 1.0
    pad=span*0.15
    hi+=pad
    if lo < 0: lo-=pad
    span=(hi-lo) or 1.0
    def y_of(v): return plot_bottom-((v-lo)/span)*plot_h
    base_y=y_of(0.0)
    d.text((px(40), plot_top-px(34)), unit, font=_f(22, True), fill=GREY)
    for i in range(5):                              # gridlines + axis values
        v=lo+span*i/4; gy=y_of(v)
        d.line([(left,gy),(right,gy)], fill=LIGHTGREY, width=px(1))
        _center(d, left-px(16), gy, _fmt_num(v, span), _f(19), GREY, anchor="rm")
    n=len(bars); slot=plot_w/n; bw=min(slot*0.5, px(150))
    palette=[GREY, PRIMARY, SECONDARY, ACCENT, GREEN_MID]
    for i,b in enumerate(bars):
        v=float(b["value"]); cx=left+slot*(i+0.5); x0=cx-bw/2
        col=_hex_to_rgb(b["color"]) if b.get("color") else palette[i%len(palette)]
        yv=y_of(v); ytop=min(yv,base_y); ybot=max(yv,base_y)
        if ybot-ytop < 1: ybot=ytop+1               # value 0 → 1px sliver
        d.rectangle([x0,ytop,x0+bw,ybot], fill=col)
        if spec.get("plus"):
            vlab=b.get("value_label", (f"+{v:.1f}%" if v>=0 else f"{v:.1f}%"))
        else:
            vlab=b.get("value_label", _fmt_num(v, span))
        lbl_y=ytop-px(26) if v>=0 else ybot+px(22)  # label above pos / below neg bars
        _center(d, cx, lbl_y, vlab, _f(30, True), _readable_on_bg(col))
        ly=plot_bottom+px(18)
        for ln in _wrap(str(b["label"]), _f(23, True), slot-px(12), d, max_lines=2):
            _center(d, cx, ly, ln, _f(23, True), INK); ly+=px(30)
    d.line([(left,base_y),(right,base_y)], fill=INK, width=px(2))   # zero baseline
    _footer(d, W, H, spec.get("source",""))
    return img


def _draw_legend(d, x, y, series, palette):
    """Draw a single-row swatch+name legend starting at (x, y device px)."""
    legf=_f(22, True)
    lx=x
    for si, name in enumerate(series):
        col=palette[si % len(palette)]
        d.rectangle([lx, y, lx+px(26), y+px(22)], fill=col)
        d.text((lx+px(34), y+px(11)), str(name), font=legf, fill=INK, anchor="lm")
        lx += px(34) + px(26) + int(d.textlength(str(name), font=legf)) + px(40)


def render_grouped_vbar(spec, W=CANVAS, H=CANVAS):
    """Vertical bars with TWO+ series per category + a legend. Use when one category
    carries multiple metrics (e.g. density AND 24h-moisture per material) — closes the
    'renderer has no grouped bar' gap the 2026-06-14 QA flagged on the PA-CF chart."""
    groups=spec.get("groups") or []
    series=spec.get("series") or []
    if not groups or not series:
        raise ValueError("grouped_vbar chart_spec needs non-empty 'groups' and 'series'")
    img=Image.new("RGB",(W,H),BG); d=ImageDraw.Draw(img)
    top=_header(d, W, spec["title"], spec.get("subtitle",""))
    unit=spec.get("unit","")
    # legend sits in a band between header and plot
    _draw_legend(d, px(130), top+px(14), series, [PRIMARY, SECONDARY, ACCENT, GREEN_MID, GREY])
    plot_top=top+px(58); plot_bottom=H-px(150); plot_h=plot_bottom-plot_top
    left=px(130); right=W-px(80); plot_w=right-left
    allvals=[float(v) for g in groups for v in (g.get("values") or [])]
    if not allvals:
        raise ValueError("grouped_vbar groups carry no 'values'")
    hi=max(max(allvals), float(spec.get("y_max", 0)), 0.0)
    lo=min(min(allvals), 0.0)
    span=(hi-lo) or 1.0; pad=span*0.15; hi+=pad
    if lo < 0: lo-=pad
    span=(hi-lo) or 1.0
    def y_of(v): return plot_bottom-((v-lo)/span)*plot_h
    base_y=y_of(0.0)
    d.text((px(40), plot_top-px(34)), unit, font=_f(22, True), fill=GREY)
    for i in range(5):
        v=lo+span*i/4; gy=y_of(v)
        d.line([(left,gy),(right,gy)], fill=LIGHTGREY, width=px(1))
        _center(d, left-px(16), gy, _fmt_num(v, span), _f(19), GREY, anchor="rm")
    palette=[PRIMARY, SECONDARY, ACCENT, GREEN_MID, GREY]
    ns=len(series); gslot=plot_w/len(groups)
    gbw=min(gslot*0.72, px(120)*ns)                 # total width of a group's bars
    bw=gbw/ns
    for gi,g in enumerate(groups):
        gx=left+gslot*(gi+0.5); x_start=gx-gbw/2
        vals=g.get("values") or []
        for si in range(ns):
            v=float(vals[si]) if si < len(vals) else 0.0
            col=palette[si % len(palette)]
            x0=x_start+bw*si
            yv=y_of(v); ytop=min(yv,base_y); ybot=max(yv,base_y)
            if ybot-ytop < 1: ybot=ytop+1
            d.rectangle([x0, ytop, x0+bw*0.9, ybot], fill=col)
            if spec.get("plus"):
                vlab=(f"+{v:.1f}%" if v>=0 else f"{v:.1f}%")
            else:
                vlab=_fmt_num(v, span)
            _center(d, x0+bw*0.45, ytop-px(20), vlab, _f(20, True), _readable_on_bg(col))
        ly=plot_bottom+px(18)
        for ln in _wrap(str(g.get("label","")), _f(23, True), gslot-px(12), d, max_lines=2):
            _center(d, gx, ly, ln, _f(23, True), INK); ly+=px(30)
    d.line([(left,base_y),(right,base_y)], fill=INK, width=px(2))
    _footer(d, W, H, spec.get("source",""))
    return img


def render_rangebar(spec, W=CANVAS, H=CANVAS):
    img=Image.new("RGB",(W,H),BG); d=ImageDraw.Draw(img)
    top=_header(d, W, spec["title"], spec.get("subtitle",""))
    rows=spec.get("rows") or []
    if not rows:
        raise ValueError("rangebar chart_spec has no non-empty 'rows'")
    unit=spec.get("x_unit","")

    # geometry: wide left gutter for wrapped row labels; reserve bottom for axis+footer
    gutter=px(290); left=gutter; right=W-px(80); plot_w=right-left
    plot_top=top+px(30); plot_bottom=H-px(172)
    row_gap=(plot_bottom-plot_top)/len(rows)
    barh=min(row_gap*0.40, px(60))

    mins=[float(r.get("min", 0)) for r in rows]
    maxs=[float(r.get("max", r.get("min", 0))) for r in rows]
    pos_mins=[m for m in mins if m > 0]
    dmin=min(pos_mins) if pos_mins else 1.0
    dmax=max(maxs + [float(spec.get("x_max") or 0), dmin*1.1])
    if dmax <= 0: dmax=1.0
    # Honor an explicit x_scale; otherwise auto log-scale wide dynamic ranges
    # (e.g. $15..$700) so cheap rows stay visible. x_scale='linear' force-disables
    # the auto-log (2026-06-14 QA: DLI 1..30 wrongly auto-logged despite linear ask).
    xs=str(spec.get("x_scale","")).lower()
    if xs == "linear":
        use_log=False
    elif xs == "log":
        use_log=True
    else:
        use_log=(dmin > 0 and dmax/dmin > 15)
    if use_log:
        lo=dmin*0.8; hi=dmax*1.15
        L=math.log10(lo); Rr=math.log10(hi); spanL=(Rr-L) or 1.0
        def xpos(v): return left+plot_w*((math.log10(max(float(v), lo))-L)/spanL)
        ticks=[]; e=int(math.floor(L)); done=False
        while not done and e <= 9:
            for m in (1, 2, 5):
                v=m*(10**e)
                if v > hi*1.02: done=True; break
                if v >= lo*0.98: ticks.append(v)
            e+=1
    else:
        lo=0.0; hi=dmax*1.08; span=(hi-lo) or 1.0
        def xpos(v): return left+plot_w*((float(v)-lo)/span)
        ticks=[hi*i/5 for i in range(6)]

    # x axis ticks + unit
    ax_y=plot_bottom+px(12)
    for v in ticks:
        gx=xpos(v)
        d.line([(gx, plot_top-px(10)), (gx, ax_y)], fill=LIGHTGREY, width=px(1))
        _center(d, gx, ax_y+px(18), (f"{v:.0f}" if v >= 1 else f"{v:g}"), _f(19), GREY)
    if unit:
        _center(d, (left+right)//2, ax_y+px(48), unit, _f(22, True), GREY)

    palette=[GREEN_MID, PRIMARY, SECONDARY]
    rlf=_f(22, True); vf=_f(23, True); af=_f(19)
    for i,r in enumerate(rows):
        cy=plot_top+row_gap*(i+0.5)
        x0=xpos(float(r["min"])); x1=xpos(float(r.get("max", r["min"])))
        if x1-x0 < px(6): x1=x0+px(6)                # keep a visible sliver
        col=_hex_to_rgb(r["color"]) if r.get("color") else palette[i%len(palette)]
        d.rounded_rectangle([x0, cy-barh/2, x1, cy+barh/2], radius=px(8), fill=col)
        # row label in the left gutter (wrapped, max 2 lines, vertically centered)
        lines=_wrap(str(r["label"]), rlf, gutter-px(52), d)[:2]
        ry=cy-(len(lines)-1)*px(14)
        for ln in lines:
            d.text((px(30), ry), ln, font=rlf, fill=INK, anchor="lm"); ry+=px(28)
        # range value: inside the bar if it fits, else to the right (or left) in dark ink
        rng=str(r.get("range_label", f"{r['min']:.0f}-{r['max']:.0f}"))
        lw=d.textlength(rng, font=vf)
        if lw+px(18) <= (x1-x0):
            _center(d, (x0+x1)/2, cy, rng, vf, _ink_on(col))
        elif x1+px(12)+lw <= right:
            d.text((x1+px(12), cy), rng, font=vf, fill=INK, anchor="lm")
        elif x0-px(12)-lw >= left:
            d.text((x0-px(12), cy), rng, font=vf, fill=INK, anchor="rm")
        else:
            _center(d, (x0+x1)/2, cy, rng, vf, _ink_on(col))
        # annotation: small grey, left-aligned under the bar at the plot start
        if r.get("annot"):
            d.text((left, cy+barh/2+px(15)), str(r["annot"]), font=af, fill=GREY, anchor="lm")
    _footer(d, W, H, spec.get("source",""))
    return img

STATUS_COLORS={
 # green = yes/affirmative/safe, rose = no/negative/risk, amber = marginal.
 # (yes/no were swapped before 2026-06-18 — a "Yes" rendered rose and a "No" green,
 #  which inverts the semantic cue on status columns like "Hypoallergenic? Yes/No".)
 "no":(247,219,231),"marginal":(245,231,212),"yes":(225,238,228),
 "no_ink":(150,30,80),"marginal_ink":(140,95,30),"yes_ink":(20,80,52),
}

def _destar(s):
    """Transliterate runs of ★/☆ rating glyphs to 'k/total' text.

    The bundled font stack has no glyph for U+2605/U+2606, so a star-rating cell
    renders as empty tofu boxes (2026-06-18 image QA finding). A cell that is
    purely stars becomes e.g. '4/5'; mixed text is left untouched.
    """
    t=str(s).strip()
    if t and all(c in "★☆" for c in t):
        return f"{t.count(chr(0x2605))}/{len(t)}"
    return str(s)

def _fit_table_layout(d, cols, rows, xb, avail):
    """Choose a font size + per-row heights so every wrapped cell FITS its row.

    v3.38.3 root cure for the recurring image-QA C1 class: the old renderer used
    a FIXED row height (min(avail/nrow, 74px)) and wrapped cells with NO line
    clamp, so a 150-200 char cell wrapped to 5-6 lines and simply drew past its
    row box into the neighbours (2026-07-09 batch: roadmap 'Key deliverables'
    cells + architecture column headers, one regen round each; same class on
    2026-07-06). Now the layout is computed BEFORE drawing:

      1. try font sizes 19 -> 17 -> 15 -> 13; at each size wrap every cell (and
         every column HEADER, clamped to 2 lines) and give each row the height
         its tallest cell needs;
      2. first size where header + all rows fit the available band wins;
      3. if even 13 cannot fit, clamp each cell's line count to what its row can
         hold (ellipsized by _wrap) so text can NEVER escape its row.

    Returns dict: fonts, per-line advance, wrapped header/cell lines, header
    height, per-row heights, and whether ellipsis-clamping was applied
    (surfaced so callers/tests can assert overflow is impossible).
    """
    nrow = max(len(rows), 1)
    col_w = [xb[j + 1] - xb[j] - px(16) for j in range(len(cols))]

    def _layout_at(size, cell_max_lines=None):
        hf = _f(size + 1, True)
        cf = _f(size)
        line_h = px(size + 5)
        pad = px(14)
        hdr_lines = [_wrap(str(c), hf, col_w[j], d, max_lines=2)
                     for j, c in enumerate(cols)]
        hh = max(1, max((len(ls) for ls in hdr_lines), default=1)) * line_h + pad
        row_wrapped, row_heights = [], []
        for row in rows:
            wrapped = [_wrap(_destar(str(v)), cf, col_w[j], d,
                             max_lines=cell_max_lines)
                       for j, v in enumerate(row)]
            n = max(1, max((len(ls) for ls in wrapped), default=1))
            row_wrapped.append(wrapped)
            row_heights.append(n * line_h + pad)
        return {"size": size, "hf": hf, "cf": cf, "cfb": _f(size, True),
                "line_h": line_h, "hdr_lines": hdr_lines, "hh": hh,
                "row_wrapped": row_wrapped, "row_heights": row_heights,
                "clamped": cell_max_lines is not None}

    for size in (19, 17, 15, 13):
        lay = _layout_at(size)
        if lay["hh"] + sum(lay["row_heights"]) <= avail:
            return lay
    # Even the smallest size overflows: clamp lines so text stays inside rows.
    lay = _layout_at(13)
    line_h, pad = lay["line_h"], px(14)
    per_row = max((avail - lay["hh"]) / nrow, line_h + pad)
    max_lines = max(1, int((per_row - pad) // line_h))
    return _layout_at(13, cell_max_lines=max_lines)


def render_table(spec, W=CANVAS, H=CANVAS):
    img=Image.new("RGB",(W,H),BG); d=ImageDraw.Draw(img)
    top=_header(d, W, spec["title"], spec.get("subtitle",""))
    cols=spec["columns"]; rows=spec["rows"]  # rows: list of lists; optional status per row via spec["status_col"]
    widths=spec.get("col_frac",[1/len(cols)]*len(cols))
    status_col=spec.get("status_col", -1)
    left=px(46); right=W-px(46); tw=right-left
    xb=[left]
    for f in widths: xb.append(xb[-1]+tw*f)
    y0=top+px(18)
    bottom=H-px(120)
    lay=_fit_table_layout(d, cols, rows, xb, bottom-y0)
    hf, cf, cfb=lay["hf"], lay["cf"], lay["cfb"]
    line_h, hh=lay["line_h"], lay["hh"]
    # header (text color adapts to the brand primary's luminance; wraps to <=2 lines)
    d.rectangle([left,y0,right,y0+hh], fill=PRIMARY)
    _hdr_ink=_ink_on(PRIMARY)
    for j in range(len(cols)):
        cx=(xb[j]+xb[j+1])/2
        lines=lay["hdr_lines"][j]
        ly=y0+hh/2-(len(lines)-1)*(line_h/2)
        for ln in lines:
            _center(d, cx, ly, ln, hf, _hdr_ink); ly+=line_h
    # rows (variable heights: each row is exactly as tall as its tallest cell)
    yy=y0+hh
    for i,row in enumerate(rows):
        rb=yy; re_=yy+lay["row_heights"][i]
        if i%2==1:
            d.rectangle([left,rb,right,re_], fill=(244,244,240))
        for j,val in enumerate(row):
            cx=(xb[j]+xb[j+1])/2
            # status coloring
            if j==status_col:
                key=str(val).strip().lower().split()[0]
                key="no" if key.startswith("no") else ("yes" if key.startswith("yes") else ("marginal" if key.startswith(("marg","limit","some")) else ""))
                if key:
                    d.rounded_rectangle([xb[j]+px(10),rb+px(8),xb[j+1]-px(10),re_-px(8)], radius=px(8), fill=STATUS_COLORS[key])
                    _center(d, cx,(rb+re_)/2, str(val), cfb, STATUS_COLORS[key+"_ink"])
                    continue
            lines=lay["row_wrapped"][i][j]
            ly=(rb+re_)/2-(len(lines)-1)*(line_h/2)
            for ln in lines:
                _center(d, cx, ly, ln, cf, INK); ly+=line_h
        d.line([(left,re_),(right,re_)], fill=LIGHTGREY, width=px(1))
        yy=re_
    d.rectangle([left,y0,right,yy], outline=LIGHTGREY, width=px(1))
    _footer(d, W, H, spec.get("source",""))
    return img

_RENDERERS = {
    "vbar": render_vbar,
    "grouped_vbar": render_grouped_vbar,
    "rangebar": render_rangebar,
    "table": render_table,
}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--spec", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a=ap.parse_args()
    spec=json.loads(a.spec.read_text(encoding="utf-8"))
    t=str(spec.get("type","vbar")).lower()
    renderer=_RENDERERS.get(t, render_vbar)
    img = renderer(spec)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    img.save(a.out, "PNG")
    print(f"wrote {a.out} ({a.out.stat().st_size} bytes)")
    return 0

if __name__=="__main__":
    sys.exit(main())
