# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配方:把 viralens 连同一个真正的 Python 解释器冻进一个文件夹,
用户无需自己装 Python / pip 依赖,双击即用。三平台(Win/Mac/Linux)同一份 spec。

  本地构建(Windows):  py -m PyInstaller --noconfirm --clean packaging/viralens.spec
  产物:               dist/viralens/viralens(.exe)        ← onedir,整个文件夹打包分发

为什么用 onedir 而不是 onefile:流水线一次运行会让 app 自己重新拉起 ~6 次
(fetch → 各分析步骤)。onefile 每次启动都要把上百 MB 解压到临时目录,会非常慢;
onedir 直接就地运行,子步骤秒起。
"""
import os
import sys
from PyInstaller.utils.hooks import collect_all

REPO = os.path.dirname(SPECPATH)            # SPECPATH 由 PyInstaller 注入 = packaging/
SCRIPTS = os.path.join(REPO, "scripts")
ENTRY = os.path.join(SPECPATH, "viralens_app.py")
ICON = os.path.join(SPECPATH, "icon.ico")   # 可选;不存在就不用

datas, binaries, hiddenimports = [], [], []

# —— 重依赖:连子模块 + 数据文件(jieba 词典、bilibili_api 资源等)一起收 ——
for pkg in ("bilibili_api", "aiohttp", "jieba"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# matplotlib / numpy / Pillow 自带 PyInstaller hook,会自动带数据;这里补 Agg 后端保险
hiddenimports += ["matplotlib.backends.backend_agg", "numpy", "PIL"]

# —— 项目自己的脚本 ——
# app 懒加载它们、viralens 通过 `--vl-exec <模块名>` 用 runpy 跑它们,
# 静态分析有可能看不全,这里全部显式声明,确保都被冻进去。
hiddenimports += [
    "runtime", "app", "viralens",
    "fetch_multi", "fetch_bilibili", "fetch_youtube",
    "compare_form", "creator_profile", "scan_signals", "charts", "export_data",
    "diagnose", "analyze_video", "import_private",
    "creators", "features", "benchmarks",
    "classify_and_stats", "comments", "compare_meme", "fetch_covers",
    "fetch_videos", "resolve_creators", "subtitle",
]

# —— 只读资源:网页界面 + 配置模板 —— 放进打包根目录,app.py 用 runtime.ASSET_DIR 找它们 ——
datas += [
    (os.path.join(SCRIPTS, "gui.html"), "."),
    (os.path.join(SCRIPTS, "diagnose.html"), "."),
    (os.path.join(SCRIPTS, "config_local.example.py"), "."),
]

a = Analysis(
    [ENTRY],
    pathex=[SCRIPTS],                 # 让 import runtime / app / 各脚本 找得到
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # yt_dlp 体积巨大且只服务于「下 YouTube 视频开头」这个可选功能(缺了会优雅降级);
    # tkinter 是 GUI 工具包,我们用 matplotlib 的 Agg 后端、用不到它。
    # 注意:不要排 unittest/test —— matplotlib→pyparsing.testing 会在导入时 import unittest。
    excludes=["yt_dlp", "tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="viralens",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,                     # 保留控制台:子进程 stdout 走管道给界面看进度 + 「关窗即停止」
    icon=(ICON if os.path.exists(ICON) else None),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="viralens",
)

# macOS:在 onedir 外再包一层 .app,双击即用(无终端窗口)。
if sys.platform == "darwin":
    app_bundle = BUNDLE(
        coll,
        name="viralens.app",
        icon=(ICON if os.path.exists(ICON) else None),
        bundle_identifier="dev.harryxin.viralens",
        info_plist={
            "CFBundleName": "viralens",
            "CFBundleDisplayName": "viralens",
            "NSHighResolutionCapable": True,
            "LSBackgroundOnly": False,
        },
    )
