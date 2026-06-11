"""
viralens · export_data.py
纯取数出口:把 data/ 里每个创作者的 <alias>_videos.json 合并成两份「干净数据」——

  data/all_videos.csv   一行一条视频,Excel 直接打开(给不写代码的人看)
  data/all_videos.json  全部视频拍平成一个列表(给程序/二次分析用,字段完整)

不做任何分析、不下结论,就是把抓下来的数据整理成方便取用的样子。
被 viralens.py 的「只要数据」模式调用,也能单独跑:
    python export_data.py
纯标准库,零依赖。
"""
import csv
import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from runtime import DATA           # 源码=仓库/data,打包成 app 时=用户数据目录
from schema import video_url       # 单一数据源:链接拼法只在 schema.py 维护

# CSV 里放哪些列、按什么顺序(挑人看得懂、Excel 排序有用的;长描述留在 JSON 里不塞 CSV)
CSV_COLS = ["creator", "platform", "zone", "title", "play", "comment", "like",
            "danmaku", "duration_sec", "length", "published", "url", "cover_url"]


def hhmmss(sec):
    """秒 → 人看的 时长(M:SS 或 H:MM:SS)。"""
    sec = int(sec or 0)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def load_all():
    """读 data/*_videos.json(每个创作者一份),拍平成一个大列表。"""
    # 排除自己的合并输出 all_videos.json(它也匹配 *_videos.json,不排掉会自我翻倍)
    files = sorted(p for p in DATA.glob("*_videos.json") if p.name != "all_videos.json")
    records = []
    for p in files:
        try:
            vids = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  ✗ 跳过 {p.name}: {type(e).__name__}: {e}")
            continue
        records.extend(vids)
    return files, records


def main():
    files, records = load_all()
    if not records:
        print("  ✗ data/ 里没找到任何 <alias>_videos.json —— 先跑 fetch_multi.py 抓数据")
        return 1

    # —— 1) 完整数据 → all_videos.json(字段一个不丢) ——
    (DATA / "all_videos.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    # —— 2) 人看的表 → all_videos.csv(utf-8-sig 带 BOM,Excel 不乱码) ——
    with (DATA / "all_videos.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS, extrasaction="ignore")
        w.writeheader()
        for v in records:
            w.writerow({
                "creator": v.get("creator", ""),
                "platform": v.get("platform", ""),
                "zone": v.get("zone", ""),
                "title": v.get("title", ""),
                "play": v.get("play", "") if v.get("play") is not None else "",
                "comment": v.get("comment", "") if v.get("comment") is not None else "",
                "like": v.get("like", "") if v.get("like") is not None else "",
                "danmaku": v.get("danmaku", "") if v.get("danmaku") is not None else "",
                "duration_sec": v.get("duration_sec", ""),
                "length": hhmmss(v.get("duration_sec")),
                "published": (v.get("created_iso") or "")[:10],
                "url": video_url(v),
                "cover_url": v.get("cover_url", "") or "",
            })

    creators = sorted({v.get("creator", "") for v in records})
    print(f"  ✓ {len(files)} 位创作者 · {len(records)} 条视频")
    print(f"  ✓ data/all_videos.csv   (Excel 直接开)")
    print(f"  ✓ data/all_videos.json  (完整字段,程序用)")
    print(f"    创作者:{'、'.join(creators)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
