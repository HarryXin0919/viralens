"""
viralens · viralens.py —— 一个入口,两种模式。

这是整个工具的「正门」:在 creators.py 里列好你想看的 B站 / YouTube 创作者,然后跑这一句。

  python viralens.py                只要数据。自动调 API 抓取 → 整理成干净的
                                    data/all_videos.csv(Excel 直接开)+ all_videos.json。
  python viralens.py --report       要洞察。抓取后再跑完整分析(招牌形式对比 / 分区基准 /
                                    疲态 / 信号扫描 / 画图)→ 出交互报告 reports/index.html。

常用开关(可叠加):
  --no-fetch    不抓取,直接用 data/ 里已有的数据(不碰网络、不耗 API 配额)
  --force       强制重抓(默认会跳过已抓过的创作者,保护已验证数据集)
  -h / --help   看这段说明

跨平台:Windows / macOS / Linux 都能跑。python 找不到就换 py(Windows)或 python3。
"""
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).parent          # scripts/
ROOT = HERE.parent                    # 仓库根
DATA = ROOT / "data"
REPORT = ROOT / "reports" / "index.html"

HELP = __doc__


def run(script, args=None, optional=False):
    """跑一个同目录脚本(用同一个 Python)。optional=True 时失败只警告、不中断整条流水线。"""
    args = args or []
    label = script.replace(".py", "")
    print(f"\n──▶ {label} {' '.join(args)}".rstrip())
    r = subprocess.run([sys.executable, str(HERE / script), *args])
    if r.returncode != 0:
        if optional:
            print(f"    ⚠ {label} 没跑成(returncode={r.returncode})—— 跳过,不影响前面的结果")
            return False
        print(f"    ✗ {label} 失败(returncode={r.returncode})—— 停在这里")
        sys.exit(r.returncode)
    return True


def main():
    argv = sys.argv[1:]
    if "-h" in argv or "--help" in argv:
        print(HELP)
        return

    report_mode = "--report" in argv or "--full" in argv
    no_fetch = "--no-fetch" in argv
    force = "--force" in argv

    print("=" * 60)
    print(f"viralens · {'抓取 + 完整分析报告' if report_mode else '只要数据(抓取 + 整理成 CSV/JSON)'}")
    print("=" * 60)

    # —— 第 1 步:抓取(两种模式都要,除非 --no-fetch)——
    if no_fetch:
        print("\n(--no-fetch:跳过抓取,直接用 data/ 里已有的数据)")
    else:
        run("fetch_multi.py", ["--force"] if force else [])

    if report_mode:
        # —— 完整分析流水线 ——
        run("compare_form.py")        # 招牌形式:头部 vs 尾部播放差
        run("creator_profile.py")     # 分区基准 + 疲态/趋势
        run("scan_signals.py")        # 多维信号扫描(哪些杠杆通用、哪些因人而异)
        run("charts.py", optional=True)  # README 配图(要 matplotlib;缺了不致命)
        run("export_data.py")         # 顺手也整理一份干净数据出来
        print("\n" + "=" * 60)
        print("✅ 全跑完了。")
        print(f"   交互报告 → {REPORT}")
        print(f"   干净数据 → {DATA / 'all_videos.csv'}")
        print("=" * 60)
    else:
        # —— 只要数据 ——
        run("export_data.py")
        print("\n" + "=" * 60)
        print("✅ 数据取好了。")
        print(f"   Excel 直接开 → {DATA / 'all_videos.csv'}")
        print(f"   完整字段(程序用)→ {DATA / 'all_videos.json'}")
        print("   想顺便看分析报告?加一句:python viralens.py --report")
        print("=" * 60)


if __name__ == "__main__":
    main()
