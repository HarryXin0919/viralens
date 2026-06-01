"""
viralens · 打包成桌面 app 时的入口(被 PyInstaller 冻结,见 viralens.spec)。

目标:双击直接弹出一个**原生应用窗口**(pywebview)——没有终端、没有浏览器标签页。
缺原生 webview 运行时(如部分 Linux 没装 WebKitGTK)时,自动回退到「开浏览器」。

两种角色,靠命令行第一个参数区分:
  · 正常双击启动  → 起本地服务器 + 开原生窗口(或回退浏览器)。
  · 自己重新拉起  → 形如 `viralens --vl-exec fetch_multi --force`:流水线某一步,
                    由 runtime.dispatch_if_worker() 接管、当成 __main__ 跑掉再退出(不开窗口)。

注意:本 app 以「窗口模式」(console=False)打包,没有控制台。下面 _ensure_std() 负责:
  · 子步骤进程(被父进程用管道收 stdout 显示进度)→ 把标准输出接回那条管道;
  · 主窗口进程(双击,没有任何 std 句柄)→ 接到 devnull,避免 print 崩溃。
"""
import io
import os
import sys


def _ensure_std():
    """窗口模式下 sys.stdout/stderr 可能是 None。子进程的句柄是父进程给的管道(有效)→
    接回去让进度能被收集;主窗口进程没有有效句柄 → dup 失败,退到 devnull。"""
    for name, fd in (("stdout", 1), ("stderr", 2)):
        if getattr(sys, name, None) is None:
            try:
                stream = io.TextIOWrapper(os.fdopen(os.dup(fd), "wb"),
                                          encoding="utf-8", errors="replace", line_buffering=True)
            except Exception:
                stream = open(os.devnull, "w", encoding="utf-8", errors="replace")
            setattr(sys, name, stream)


_ensure_std()

import runtime

runtime.bootstrap()
runtime.dispatch_if_worker()   # 若是 --vl-exec 子步骤:跑完即退出,绝不往下走(不开窗口)

import app

# —— 主进程:起服务器,开原生窗口;开不出来就回退浏览器 ——
srv, url = app.start_server()

_opened = False
try:
    import webview
    webview.create_window("viralens", url, width=1180, height=820, min_size=(900, 600))
    webview.start()            # 阻塞,直到用户关掉窗口
    _opened = True
except Exception:
    _opened = False

if not _opened:
    # 没有可用的原生 webview(如 Linux 缺 WebKitGTK)→ 开浏览器并挂住进程
    import threading
    import webbrowser
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
