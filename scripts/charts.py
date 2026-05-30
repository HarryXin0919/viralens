"""
viralens · charts.py
生成 README 静态图(matplotlib → PNG)。第一张:形式决定成败(头尾播放差)。
读 data/cross_creator_form.json → reports/img/*.png

依赖: matplotlib  /  中文字体自动适配 Windows·macOS·Linux(见下方 font.sans-serif)
跑: python charts.py   (Windows 可用 py,macOS/Linux 用 python3,详见 README)
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from creators import CREATORS

# 中文字体:按 Windows → macOS → Linux 顺序取第一个装了的,都没有才显示 □□□
plt.rcParams["font.sans-serif"] = [
    "Microsoft YaHei", "SimHei",                                        # Windows
    "PingFang SC", "Hiragino Sans GB", "Heiti SC", "Arial Unicode MS",  # macOS
    "Noto Sans CJK SC", "Noto Sans SC", "Source Han Sans SC",           # Linux: fonts-noto-cjk
    "WenQuanYi Micro Hei", "WenQuanYi Zen Hei", "Droid Sans Fallback",  # Linux 备选
    "sans-serif",
]
plt.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
IMG = ROOT / "reports" / "img"
IMG.mkdir(parents=True, exist_ok=True)

ACCENT = "#61C4E3"   # 项目主色
HIT = "#E5484D"      # 爆款红
FLOP = "#4C93FF"     # 翻车蓝
GREY = "#D9D9D9"
ZCOL = {"知识": ACCENT, "数码": "#8B7CF6", "生活": "#43B581", "美食": "#F2A33C", "游戏": "#EC6B9D"}
# 长名 → 图上简称
SHORT = {"妈咪说MommyTalk": "妈咪说", "李永乐老师官方": "李永乐", "无穷小亮的科普日常": "无穷小亮",
         "老师好我叫何同学": "何同学", "极客湾Geekerwan": "极客湾", "房琪kiki": "房琪",
         "美食作家王刚R": "王刚", "盗月社食遇记": "盗月社", "中国boy超级大猩猩": "中国boy"}


def fmt_play(n):
    if n >= 1e8:
        return f"{n/1e8:.1f}亿"
    if n >= 1e4:
        return f"{n/1e4:.0f}万"
    return f"{n:,.0f}"


def chart_form_spread():
    rows = json.loads((DATA / "cross_creator_form.json").read_text(encoding="utf-8"))
    rows.sort(key=lambda r: r["top5_med"])   # 从下往上递增,天花板最高的在顶部
    zone_of = {c["name"]: c.get("zone", "?") for c in CREATORS}

    fig, ax = plt.subplots(figsize=(11, 9.2))
    for i, r in enumerate(rows):
        lo, hi = r["bot5_med"], r["top5_med"]
        ax.plot([lo, hi], [i, i], color=GREY, lw=4, zorder=1, solid_capstyle="round")
        ax.scatter(lo, i, color=FLOP, s=110, zorder=3, edgecolors="white", linewidths=1.2)
        ax.scatter(hi, i, color=HIT, s=110, zorder=3, edgecolors="white", linewidths=1.2)
        ax.text(hi * 1.3, i, f"{r['ratio']:.0f}×" if r["ratio"] >= 10 else f"{r['ratio']:.1f}×",
                va="center", ha="left", fontsize=11, color="#333", fontweight="bold")
        ax.text(lo * 0.72, i, fmt_play(lo), va="center", ha="right", fontsize=8.5, color="#888")

    ax.set_xscale("log")
    ax.set_yticks(range(len(rows)))
    labels = ax.set_yticklabels([SHORT.get(r["creator"], r["creator"]) for r in rows], fontsize=11)
    for lab, r in zip(labels, rows):              # 名字按分区上色,凸显"各区都成立"
        lab.set_color(ZCOL.get(zone_of.get(r["creator"], "?"), "#333"))
    ax.set_xlabel("单条视频播放量(对数轴)", fontsize=10.5)
    ax.set_title("形式决定成败 · 14 位 UP 主跨 5 大分区全部复现 · 头部5条 vs 尾部5条(3.7–109×)",
                 fontsize=13, fontweight="bold", pad=16)
    ax.set_xlim(min(r["bot5_med"] for r in rows) * 0.4, max(r["top5_med"] for r in rows) * 3.4)

    # 图例:红蓝点 + 分区色
    from matplotlib.lines import Line2D
    handles = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=HIT, markersize=11,
               label="招牌形式(爆款·头部5条中位)"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=FLOP, markersize=11,
               label="偏离招牌(翻车·尾部5条中位)"),
    ]
    handles += [Line2D([0], [0], marker="s", color="w", markerfacecolor=ZCOL[z], markersize=10,
                       label=z) for z in ["知识", "数码", "生活", "美食", "游戏"]]
    ax.legend(handles=handles, loc="lower right", frameon=False, fontsize=9.5, ncol=2)

    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(left=False)
    ax.grid(axis="x", color="#EEE", lw=0.8)
    ax.set_axisbelow(True)

    fig.text(0.012, 0.012,
             "viralens · 数据:B站各 UP 主最近 40 条视频  |  招牌=该 UP 主标志性形式,偏题=商单/vlog/访谈/卖书  |  名字颜色=分区",
             fontsize=8, color="#999")
    plt.tight_layout(rect=[0, 0.03, 1, 1])
    out = IMG / "form_spread.png"
    plt.savefig(out, dpi=145, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {out.relative_to(ROOT)}")


def chart_meme_falsified():
    """第二张:展示方法论严谨——我们杀死了自己的假设。
    '评论玩梗多 → 更容易爆款'?  实测高/低播放组的玩梗评论占比,假设预测红(高)>蓝(低)。"""
    data = json.loads((DATA / "cross_creator_meme.json").read_text(encoding="utf-8"))
    names = [d["creator"].replace("MommyTalk", "").replace("官方", "") for d in data]
    hi = [d["groups"]["高"]["meme_pct"] for d in data]
    lo = [d["groups"]["低"]["meme_pct"] for d in data]

    fig, ax = plt.subplots(figsize=(9.6, 5.8))
    x = list(range(len(names)))
    w = 0.36
    ax.bar([i - w / 2 for i in x], hi, w, color=HIT, zorder=3, label="爆款组(高播放)")
    ax.bar([i + w / 2 for i in x], lo, w, color=FLOP, zorder=3, label="翻车组(低播放)")

    for i, (h, l) in enumerate(zip(hi, lo)):
        ax.text(i - w / 2, h + 0.7, f"{h:.0f}%", ha="center", fontsize=10, color=HIT, fontweight="bold")
        ax.text(i + w / 2, l + 0.7, f"{l:.0f}%", ha="center", fontsize=10, color=FLOP, fontweight="bold")
        ok = h > l                       # 假设预测:高播放组玩梗更多
        mark = "假设成立" if ok else "× 反例"
        col = "#2B9348" if ok else HIT
        ax.text(i, max(h, l) + 4.2, mark, ha="center", fontsize=11, color=col, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(names, fontsize=11.5)
    ax.set_ylabel("评论里含玩梗词的占比 %", fontsize=10.5)
    ax.set_ylim(0, max(max(hi), max(lo)) + 12)
    fig.suptitle("viralens 杀死了自己的假设 ·「评论玩梗多 → 更容易爆款」?",
                 fontsize=14, fontweight="bold", y=0.98)
    ax.set_title("假设预测红 > 蓝。实测 3 个 UP 主里 2 个反过来 —— 假设证伪。",
                 fontsize=10.5, color="#444", pad=12)
    ax.legend(loc="upper right", frameon=False, fontsize=10)

    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", color="#EEE", lw=0.8)
    ax.set_axisbelow(True)

    fig.text(0.012, 0.012,
             "viralens · doge 出现在每个 UP 主评论高频词第 1~5 位 —— 它是全站口头禅,不是爆款的原因。"
             "敢证伪,才信得过结论。",
             fontsize=8, color="#999")
    plt.tight_layout(rect=[0, 0.03, 1, 0.94])
    out = IMG / "meme_falsified.png"
    plt.savefig(out, dpi=145, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {out.relative_to(ROOT)}")


def chart_2nd_person_falsified():
    """第三张:跨区证伪——'标题带「你」→ 更容易火'在知识区成立,出区翻车。
    读 signal_scan.json 里每位 UP 主的 has_2nd_person 倍数(两组各≥4条才有),围绕 1.0× 画发散柱。"""
    scan = json.loads((DATA / "signal_scan.json").read_text(encoding="utf-8"))
    zone_of = {c["name"]: c.get("zone", "?") for c in CREATORS}
    rows = []
    for cr in scan["creators"]:
        e = cr.get("binary", {}).get("has_2nd_person")
        if e:
            nm = cr["creator"]
            rows.append((SHORT.get(nm, nm), zone_of.get(nm, "?"), e["ratio"]))
    rows.sort(key=lambda r: -r[2])               # 倍数从高到低,跨过 1.0 基准线
    if not rows:
        print("  ✗ signal_scan.json 无 has_2nd_person 数据,跳过第三张")
        return

    fig, ax = plt.subplots(figsize=(9.8, 5.8))
    for i, (nm, z, r) in enumerate(rows):
        col = HIT if r >= 1 else FLOP
        ax.bar(i, r - 1, bottom=1, width=0.62, color=col, zorder=3)
        ax.text(i, r + 0.09 if r >= 1 else r - 0.17, f"{r:.2f}×",
                ha="center", fontsize=10.5, color=col, fontweight="bold")

    ax.axhline(1, color="#1A1F24", lw=1.3, ls=(0, (5, 4)), alpha=0.5, zorder=2)
    ax.text(len(rows) - 0.45, 1.07, "1.0× 基准:带不带「你」一样", ha="right", fontsize=9.5, color="#555")
    ax.set_xticks(range(len(rows)))
    xlabs = ax.set_xticklabels([f"{nm}\n{z}" for nm, z, _ in rows], fontsize=10.5)
    for lab, (_, z, _) in zip(xlabs, rows):
        lab.set_color(ZCOL.get(z, "#333"))
    ax.set_ylim(0, 4)
    ax.set_ylabel("标题带「你」 ÷ 不带 的播放倍数", fontsize=10.5)
    fig.suptitle("viralens 推翻了自己的结论 ·「标题带『你』→ 更容易火」?",
                 fontsize=14, fontweight="bold", y=0.99)
    ax.set_title("知识区 4 人全部↑(成立);出了知识区 4 人全部↓(翻车)。几何平均 0.91× —— 假设证伪。",
                 fontsize=10, color="#444", pad=10)

    from matplotlib.lines import Line2D
    ax.legend(handles=[
        Line2D([0], [0], marker="s", color="w", markerfacecolor=HIT, markersize=11, label="带「你」更高(↑)"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor=FLOP, markersize=11, label="带「你」更低(↓)"),
    ], loc="upper right", frameon=False, fontsize=10)

    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", color="#EEE", lw=0.8)
    ax.set_axisbelow(True)

    fig.text(0.012, 0.012,
             "viralens · 同一个测试,只换创作者就翻面 —— 通用涨粉套路经不起跨区检验。敢证伪,才信得过结论。",
             fontsize=8, color="#999")
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    out = IMG / "second_person_falsified.png"
    plt.savefig(out, dpi=145, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {out.relative_to(ROOT)}")


def main():
    chart_form_spread()
    chart_2nd_person_falsified()
    chart_meme_falsified()
    print("\n✅ 图已生成到 reports/img/")


if __name__ == "__main__":
    main()
