"""
viralens · build_report.py —— 把 --report 跑出来的分析数据汇总成**一个自包含的 HTML 报告**。

读 data/ 里各步骤产物(cross_creator_form / creator_profile / signal_scan / all_videos)
+ 把 reports/img/*.png 以 base64 内联进来 → 写出单个 reports/index.html。
这个文件不依赖本地服务器、不依赖网络:双击就能开,也能直接发给任何创作者看。

被 viralens.py 的 --report 模式调用,也能单独跑:
    python build_report.py
纯标准库(仅可选 import features 取人类可读的维度名)。
"""
import base64
import html
import json
import sys
import time
from runtime import DATA, REPORTS, IMG
from schema import fmt_play, video_url    # 单一数据源:链接拼法/播放量格式只在 schema.py 维护

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ACCENT = "#61C4E3"   # 项目主色(与 charts.py 一致)
HIT = "#E5484D"      # 爆款红


# ————————————————————————— 小工具 —————————————————————————
def load(name):
    p = DATA / name
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def esc(s):
    return html.escape(str(s if s is not None else ""))


def fmt_dur(sec):
    try:
        sec = int(sec)
    except (TypeError, ValueError):
        return "-"
    m, s = divmod(sec, 60)
    return f"{m}:{s:02d}"


def img_data_uri(path):
    try:
        b = path.read_bytes()
    except Exception:
        return None
    return "data:image/png;base64," + base64.b64encode(b).decode("ascii")


# ————————————————————————— 各板块 —————————————————————————
def section_headline(form):
    """顶部三句话结论卡:形式决定天花板(头尾播放差)。"""
    if not form:
        return ""
    ratios = [r["ratio"] for r in form if isinstance(r.get("ratio"), (int, float))]
    if not ratios:
        return ""
    lo, hi = min(ratios), max(ratios)
    chips = "".join(
        f'<span class="chip"><b>{esc(r["creator"])}</b> {r["ratio"]:.0f}×</span>'
        for r in sorted(form, key=lambda x: -(x.get("ratio") or 0))
    )
    return f"""
<section class="card hero">
  <div class="kicker">站得住的结论</div>
  <h2>同一个创作者,头部 5 条 vs 尾部 5 条播放差 <span class="big">{lo:.0f}×–{hi:.0f}×</span></h2>
  <p>差距不来自选题或运气,而来自<b>视频是否在 TA 的招牌形式里</b>。偏离核心形式(商单 / vlog / 访谈 / 直播回放)就容易翻车。</p>
  <div class="chips">{chips}</div>
</section>"""


def section_charts():
    """内联 reports/img 下生成的图表 PNG。"""
    candidates = [
        ("form_spread.png", "形式决定天花板 —— 各创作者头尾播放差"),
        ("second_person_falsified.png", "被我们自己证伪的「通用杠杆」"),
        ("meme_falsified.png", "玩梗 / 社群参与度 跨创作者检验"),
    ]
    blocks = []
    for fn, cap in candidates:
        uri = img_data_uri(IMG / fn)
        if uri:
            blocks.append(
                f'<figure><img alt="{esc(cap)}" src="{uri}"><figcaption>{esc(cap)}</figcaption></figure>'
            )
    if not blocks:
        return ""
    return f'<section class="card"><h3>图表</h3><div class="charts">{"".join(blocks)}</div></section>'


def _pct(x):
    try:
        return f"{float(x)*100:.0f}%"
    except (TypeError, ValueError):
        return "-"


def section_creators(profile, form):
    """每位创作者一张卡:同区基准对位 + 趋势 + 头/尾代表作。"""
    form_by = {r["creator"]: r for r in (form or [])}
    cards = []
    zones = (profile or {}).get("zones", {}) if isinstance(profile, dict) else {}
    seen = set()
    for zone, zd in zones.items():
        bench = zd.get("benchmark", {}) or {}
        for pr in zd.get("creators", []):
            name = pr.get("name", "?")
            seen.add(name)
            s = pr.get("stat", {}) or {}
            t = pr.get("trend", {}) or {}
            fr = form_by.get(name)
            bench_line = (
                f'<div class="kv"><span>体量(播放中位)</span><b>{fmt_play(s.get("play_med"))}</b>'
                f'<span class="ref">区典型 {fmt_play(bench.get("play_med"))}</span></div>'
                f'<div class="kv"><span>招牌形式命中率</span><b>{_pct(s.get("in_format_rate"))}</b>'
                f'<span class="ref">区典型 {_pct(bench.get("in_format_rate"))}</span></div>'
                f'<div class="kv"><span>典型时长</span><b>{fmt_dur(s.get("dur_med"))}</b>'
                f'<span class="ref">区典型 {fmt_dur(bench.get("dur_med"))}</span></div>'
                f'<div class="kv"><span>每万播放评论</span><b>{esc(s.get("comment_per_10k"))}</b>'
                f'<span class="ref">区典型 {esc(bench.get("comment_per_10k"))}</span></div>'
            )
            if t.get("verdict") and t.get("verdict") != "样本不足":
                trend_line = (f'<div class="trend">趋势:<b>{esc(t.get("verdict"))}</b> · '
                              f'近/早 {esc(t.get("ratio"))}×（{fmt_play(t.get("early_med"))} → {fmt_play(t.get("recent_med"))},'
                              f' {esc(t.get("n_mature"))} 条成熟视频)</div>')
            else:
                trend_line = f'<div class="trend dim">趋势:{esc(t.get("note") or "样本不足")}</div>'
            reps = ""
            if fr:
                def li(v, kind):
                    tag = f'<span class="off">[{esc(v["off"])}]</span> ' if v.get("off") else ""
                    return f'<li><span class="p {kind}">{fmt_play(v.get("play"))}</span> {tag}{esc(v.get("title"))[:40]}</li>'
                tops = "".join(li(v, "hit") for v in (fr.get("top5") or [])[:3])
                bots = "".join(li(v, "flop") for v in (fr.get("bot5") or [])[:3])
                reps = (f'<div class="reps"><div><div class="rep-h">🔴 头部代表作</div><ul>{tops}</ul></div>'
                        f'<div><div class="rep-h">🔵 尾部代表作</div><ul>{bots}</ul></div></div>')
            ratio_badge = f'<span class="ratio">头尾 {fr["ratio"]:.0f}×</span>' if fr and fr.get("ratio") else ""
            cards.append(f"""
  <div class="creator">
    <div class="ch"><h4>{esc(name)}</h4><span class="zone">{esc(zone)}</span>{ratio_badge}</div>
    <div class="kvs">{bench_line}</div>
    {trend_line}
    {reps}
  </div>""")
    # creator_profile 没覆盖、但 form 里有的,也补一张精简卡
    for name, fr in form_by.items():
        if name in seen:
            continue
        ratio_badge = f'<span class="ratio">头尾 {fr["ratio"]:.0f}×</span>' if fr.get("ratio") else ""
        cards.append(f'<div class="creator"><div class="ch"><h4>{esc(name)}</h4>{ratio_badge}</div></div>')
    if not cards:
        return ""
    return f'<section class="card"><h3>各创作者画像</h3><div class="creators">{"".join(cards)}</div></section>'


def section_signals(scan, binlab, numlab):
    if not isinstance(scan, dict):
        return ""
    metric = scan.get("metric", "")
    rows = []
    for g in scan.get("generalization", []):
        label = binlab.get(g["key"], g["key"])
        same = f'{g.get("pos",0)}↑ / {g.get("neg",0)}↓ / 共{g.get("n",0)}'
        rows.append(f'<tr><td>{esc(label)}</td><td>{esc(same)}</td>'
                    f'<td>{esc(g.get("geo_ratio"))}×</td><td>{esc(g.get("verdict"))}</td></tr>')
    for g in scan.get("generalization_numeric", []):
        label = numlab.get(g["key"], g["key"])
        same = f'{g.get("pos",0)}+ / {g.get("neg",0)}- / 共{g.get("n",0)}'
        rows.append(f'<tr><td>{esc(label)}</td><td>{esc(same)}</td>'
                    f'<td>ρ {g.get("mean_rho"):+.2f}</td><td>{esc(g.get("verdict"))}</td></tr>')
    if not rows:
        return ""
    return f"""
<section class="card">
  <h3>哪些杠杆通用,哪些因人而异 <span class="dim">(指标:{esc(metric)})</span></h3>
  <table class="grid"><thead><tr><th>维度</th><th>同向</th><th>平均倍数 / ρ</th><th>判决</th></tr></thead>
  <tbody>{"".join(rows)}</tbody></table>
</section>"""


def section_table(videos):
    if not videos:
        return ""
    rows = []
    shown = videos[:500]
    for v in shown:
        u = video_url(v)
        title = esc(v.get("title"))[:60]
        title_html = f'<a href="{u}" target="_blank" rel="noopener">{title}</a>' if u else title
        rows.append(
            f'<tr>'
            f'<td>{esc(v.get("creator"))}</td>'
            f'<td>{esc(v.get("platform"))}</td>'
            f'<td>{esc(v.get("zone"))}</td>'
            f'<td class="t">{title_html}</td>'
            f'<td data-v="{v.get("play") or 0}">{fmt_play(v.get("play"))}</td>'
            f'<td data-v="{v.get("comment") or 0}">{esc(v.get("comment"))}</td>'
            f'<td data-v="{v.get("danmaku") or v.get("like") or 0}">{esc(v.get("danmaku") if v.get("danmaku") is not None else v.get("like"))}</td>'
            f'<td data-v="{v.get("duration_sec") or 0}">{fmt_dur(v.get("duration_sec"))}</td>'
            f'<td>{esc((v.get("created_iso") or "")[:10])}</td>'
            f'</tr>'
        )
    note = f'<p class="dim">共 {len(videos)} 条,显示前 {len(shown)} 条。点表头排序。</p>' if len(videos) > len(shown) else '<p class="dim">点表头排序。</p>'
    return f"""
<section class="card">
  <h3>视频明细</h3>
  {note}
  <table class="grid sortable" id="vtab"><thead><tr>
    <th>创作者</th><th>平台</th><th>赛道</th><th>标题</th>
    <th data-num>播放</th><th data-num>评论</th><th data-num>弹幕/赞</th><th data-num>时长</th><th>发布</th>
  </tr></thead><tbody>{"".join(rows)}</tbody></table>
</section>"""


HEAD = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>viralens 报告</title>
<style>
  :root{ --accent:#61C4E3; --hit:#E5484D; --ink:#1d1d1f; --sub:#6e6e73; --line:#e6e6e9; --bg:#f5f5f7; --card:#fff; }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
       font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
  .wrap{max-width:980px;margin:0 auto;padding:32px 20px 80px}
  header.top{text-align:center;margin:18px 0 26px}
  header.top h1{font-size:34px;margin:0;letter-spacing:-.5px}
  header.top .meta{color:var(--sub);margin-top:6px;font-size:13px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:22px 24px;margin:16px 0;
        box-shadow:0 1px 2px rgba(0,0,0,.03)}
  .card h2{font-size:22px;margin:.2em 0 .4em;letter-spacing:-.3px}
  .card h3{font-size:18px;margin:0 0 14px}
  .hero{background:linear-gradient(180deg,#fff, #fbfdff);border-color:#dCEFF6}
  .kicker{color:var(--accent);font-weight:700;font-size:13px;letter-spacing:.04em;text-transform:uppercase}
  .big{color:var(--hit);white-space:nowrap}
  .chips{margin-top:14px;display:flex;flex-wrap:wrap;gap:8px}
  .chip{background:#eef7fb;border:1px solid #d6ecf4;border-radius:999px;padding:4px 11px;font-size:13px}
  .chip b{font-weight:600}
  .charts{display:grid;grid-template-columns:1fr;gap:18px}
  figure{margin:0}
  figure img{width:100%;border:1px solid var(--line);border-radius:12px;display:block}
  figcaption{color:var(--sub);font-size:13px;margin-top:6px;text-align:center}
  .creators{display:grid;grid-template-columns:1fr 1fr;gap:16px}
  @media(max-width:720px){.creators{grid-template-columns:1fr}}
  .creator{border:1px solid var(--line);border-radius:12px;padding:14px 16px}
  .ch{display:flex;align-items:center;gap:8px;margin-bottom:8px}
  .ch h4{margin:0;font-size:16px}
  .zone{font-size:12px;color:var(--sub);background:#f0f0f3;border-radius:6px;padding:1px 7px}
  .ratio{margin-left:auto;font-size:12px;color:#fff;background:var(--hit);border-radius:6px;padding:2px 8px}
  .kvs{display:flex;flex-direction:column;gap:3px;margin:8px 0}
  .kv{display:flex;align-items:baseline;gap:8px;font-size:13px}
  .kv span:first-child{color:var(--sub);min-width:108px}
  .kv b{font-weight:600}
  .kv .ref{color:#9a9aa0;font-size:12px;margin-left:auto}
  .trend{font-size:13px;margin-top:6px}
  .trend.dim,.dim{color:var(--sub)}
  .reps{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px}
  .rep-h{font-size:12px;color:var(--sub);margin-bottom:3px}
  .reps ul{margin:0;padding-left:2px;list-style:none;font-size:12.5px}
  .reps li{margin:2px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .p{font-variant-numeric:tabular-nums;font-weight:600;margin-right:5px}
  .p.hit{color:var(--hit)} .p.flop{color:#8a8a8f}
  .off{color:var(--accent);font-size:11px}
  table.grid{width:100%;border-collapse:collapse;font-size:13px}
  table.grid th,table.grid td{padding:7px 9px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
  table.grid th{color:var(--sub);font-weight:600;position:sticky;top:0;background:var(--card)}
  table.sortable th{cursor:pointer;user-select:none}
  table.sortable th[data-num]{text-align:right}
  table.grid td[data-v]{text-align:right;font-variant-numeric:tabular-nums}
  td.t{max-width:360px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  td.t a{color:inherit;text-decoration:none;border-bottom:1px solid var(--line)}
  footer{text-align:center;color:var(--sub);font-size:12px;margin-top:30px}
  a.gh{color:var(--accent);text-decoration:none}
</style></head><body><div class="wrap">"""

FOOT_TMPL = """<footer>由 <a class="gh" href="https://github.com/HarryXin0919/viralens">viralens</a> 生成 · 数据与分析全部在本机完成,未上传 · __TS__</footer>
<script>
document.querySelectorAll('table.sortable').forEach(function(tb){
  tb.querySelectorAll('th').forEach(function(th,ci){
    th.addEventListener('click',function(){
      var body=tb.tBodies[0], rows=[].slice.call(body.rows);
      var num=th.hasAttribute('data-num');
      var dir=th.dataset.dir==='asc'?-1:1; th.dataset.dir=dir===1?'asc':'desc';
      rows.sort(function(a,b){
        var x=a.cells[ci], y=b.cells[ci];
        if(num){return (parseFloat(x.dataset.v||x.textContent)-parseFloat(y.dataset.v||y.textContent))*dir;}
        return x.textContent.localeCompare(y.textContent,'zh')*dir;
      });
      rows.forEach(function(r){body.appendChild(r);});
    });
  });
});
</script></div></body></html>"""


def main():
    form = load("cross_creator_form.json")
    profile = load("creator_profile.json")
    scan = load("signal_scan.json")
    videos = load("all_videos.json") or []
    try:
        from features import BINARY_LABELS, NUMERIC_LABELS
    except Exception:
        BINARY_LABELS, NUMERIC_LABELS = {}, {}

    n_creators = len({v.get("creator") for v in videos}) if videos else len(form or [])
    parts = [HEAD]
    parts.append(
        f'<header class="top"><h1>viralens 报告</h1>'
        f'<div class="meta">{n_creators} 位创作者 · {len(videos)} 条视频 · '
        f'{time.strftime("%Y-%m-%d %H:%M")}</div></header>'
    )
    body = [section_headline(form), section_charts(),
            section_creators(profile, form), section_signals(scan, BINARY_LABELS, NUMERIC_LABELS),
            section_table(videos)]
    body = [b for b in body if b]
    if not body:
        body = ['<section class="card"><h3>还没有数据</h3>'
                '<p class="dim">先在界面里「抓取并分析」,或命令行跑 <code>python viralens.py --report</code>,再生成报告。</p></section>']
    parts.extend(body)
    parts.append(FOOT_TMPL.replace("__TS__", time.strftime("%Y-%m-%d %H:%M")))

    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / "index.html"
    out.write_text("\n".join(parts), encoding="utf-8")
    print(f"✅ 已写交互报告 → {out}")


if __name__ == "__main__":
    main()
