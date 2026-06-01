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

import runtime                        # 收口「源码跑 vs 打包成 app 跑」的路径/子进程差异

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = runtime.ASSET_DIR              # scripts/(源码)或打包资源目录(app)
DATA = runtime.DATA                   # 可写:源码=仓库/data,app=用户数据目录
REPORT = runtime.REPORTS / "index.html"

# 让同目录的 creators.py / config_local.py 等无论以何种方式启动(直接跑文件 or
# 安装为 `viralens` 命令)都能被 import 到。
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

HELP = __doc__


def run(script, args=None, optional=False):
    """跑一个同目录脚本(用同一个 Python)。optional=True 时失败只警告、不中断整条流水线。"""
    args = args or []
    label = script.replace(".py", "")
    print(f"\n──▶ {label} {' '.join(args)}".rstrip())
    r = subprocess.run(runtime.worker_cmd(script, args))   # 源码:[py, 脚本];app:[自己, --vl-exec, 模块]
    if r.returncode != 0:
        if optional:
            print(f"    ⚠ {label} 没跑成(returncode={r.returncode})—— 跳过,不影响前面的结果")
            return False
        print(f"    ✗ {label} 失败(returncode={r.returncode})—— 停在这里")
        sys.exit(r.returncode)
    return True


def preflight():
    """抓取前的友好自检:缺密钥 / 还没改创作者清单时,直接给出下一步,
    而不是让后面的抓取逐条静默失败、最后拿空数据去分析。"""
    problems = []

    # 1) API 密钥:config_local.py 存在且至少填了一个
    has_key = False
    try:
        import config_local
        if getattr(config_local, "SESSDATA", "") or getattr(config_local, "YOUTUBE_API_KEY", ""):
            has_key = True
    except ImportError:
        pass
    if not has_key:
        problems.append(
            "还没配置 API 密钥。\n"
            "       1) 复制 scripts/config_local.example.py 为 scripts/config_local.py\n"
            "       2) 填入 SESSDATA(B站)或 YOUTUBE_API_KEY(YouTube),至少一个\n"
            "       config_local.py 已被 .gitignore 排除,不会上传。"
        )

    # 2) 创作者清单:是否还停在示例占位
    try:
        from creators import CREATORS
        real = [
            c for c in CREATORS
            if "示例" not in c.get("name", "")
            and not str(c.get("alias", "")).startswith("demo_")
            and c.get("name") != "Example Channel"
        ]
        if not real:
            problems.append(
                "创作者清单还是示例占位。\n"
                "       编辑 scripts/creators.py,换成你想分析的 B站 / YouTube 创作者;\n"
                "       想保留私有清单又不进 git,就放进 scripts/creators_local.py(自动覆盖)。"
            )
    except Exception:
        pass

    if problems:
        print("\n" + "─" * 60)
        print("⚠ 还差一步(viralens 启动自检):")
        for i, p in enumerate(problems, 1):
            print(f"\n  {i}. {p}")
        print("\n" + "─" * 60)
        print("把上面配好,再跑一次就行。")
        print("已经有 data/ 数据、只想看分析?加 --no-fetch 跳过抓取。")
        sys.exit(1)


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
        preflight()
        run("fetch_multi.py", ["--force"] if force else [])

    if report_mode:
        # —— 完整分析流水线 ——
        run("compare_form.py")        # 招牌形式:头部 vs 尾部播放差
        run("creator_profile.py")     # 分区基准 + 疲态/趋势
        run("scan_signals.py")        # 多维信号扫描(哪些杠杆通用、哪些因人而异)
        run("charts.py", optional=True)  # README 配图(要 matplotlib;缺了不致命)
        run("export_data.py")         # 顺手也整理一份干净数据出来
        run("build_report.py")        # 汇总成单个自包含 reports/index.html(可离线打开/转发)
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
