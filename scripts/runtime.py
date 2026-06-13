"""
viralens · runtime.py —— 一处搞定「从源码跑」和「打包成 app 跑」的差异。

为什么需要它:整个工具是一串脚本互相用 subprocess 调起来的(app.py → viralens.py →
fetch_multi.py …),每个脚本都靠 `Path(__file__).parent.parent / "data"` 找数据目录、
靠 `sys.executable` 找 Python。打包成单个可执行 app 后这两件事都变了:
  · sys.executable 变成 app 自己,不再是 Python —— 不能再 `[sys.executable, "xxx.py"]`;
  · 程序目录是只读的(尤其 macOS/.app、Linux/AppImage)—— data/ reports/ 不能写在里面。

这个模块把这两件事各收口到一个地方:

  · 路径:DATA / REPORTS / IMG / CLIPS / CONFIG —— 源码模式 = 仓库目录(行为和以前一字不差);
    打包模式 = 用户可写目录(Win: %LOCALAPPDATA%\viralens,mac: ~/Library/Application Support/
    viralens,Linux: ~/.local/share/viralens)。
  · 调子脚本:worker_cmd("fetch_multi.py", [...]) 给出正确的命令行;打包模式下子脚本通过
    app 自己用 `--vl-exec <模块名>` 重新拉起(见 dispatch_if_worker)。

只用标准库,绝不 import 项目里其它脚本(避免循环依赖)。
"""
import os
import sys
from pathlib import Path

# —— 是不是被 PyInstaller 冻结成 app 了 ——
FROZEN = bool(getattr(sys, "frozen", False))

# —— 只读资源目录(gui.html / diagnose.html / config 模板就在这)——
if FROZEN:
    ASSET_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)).resolve()
else:
    ASSET_DIR = Path(__file__).resolve().parent          # scripts/
REPO_ROOT = ASSET_DIR.parent                              # 源码模式下 = 仓库根


def _user_dir() -> Path:
    """打包模式下,可写数据放系统约定的「应用数据」目录。"""
    name = "viralens"
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return Path(base) / name


# —— 可写状态目录 ——
#   源码模式:仓库根(data/、reports/ 还在仓库里,和以前完全一样)
#   打包模式:用户应用数据目录(程序目录只读,不能写这里)
USER_DIR = _user_dir() if FROZEN else REPO_ROOT

DATA = USER_DIR / "data"
REPORTS = USER_DIR / "reports"
IMG = REPORTS / "img"
CLIPS = DATA / "clips"
# 密钥文件:源码模式放 scripts/(和历史一致、能被 import);打包模式放用户目录(可写 + 在 sys.path 上)
CONFIG = (ASSET_DIR / "config_local.py") if not FROZEN else (USER_DIR / "config_local.py")
CONFIG_EXAMPLE = ASSET_DIR / "config_local.example.py"

_BOOTSTRAPPED = False


def bootstrap() -> None:
    """建好可写目录;把 ASSET_DIR 和 USER_DIR 放进 sys.path,
    让 `import config_local` / `import creators` / `import creators_local`
    在源码和打包两种模式下都找得到。可重复调用,幂等。"""
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    for d in (DATA, REPORTS, IMG):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
    # USER_DIR 在前:用户的 config_local.py / creators_local.py 覆盖打包内的默认值
    for p in (str(USER_DIR), str(ASSET_DIR)):
        if p not in sys.path:
            sys.path.insert(0, p)
    _BOOTSTRAPPED = True


def atomic_write_text(path, text: str, encoding: str = "utf-8") -> None:
    """原子写文本:先写同目录临时文件,再 os.replace 覆盖目标。
    中断(断电/Ctrl+C)时目标文件要么是旧内容、要么是新内容,绝不会是写了一半的残缺数据。
    用于不可再生的主数据(<alias>_videos.json / 封面缓存等)。"""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding=encoding)
    os.replace(tmp, path)


def worker_cmd(script: str, args=None):
    """拼出「用本工具自己的解释器跑某个子脚本」的命令行。
      源码模式: [python, scripts/<script>, *args]            (和历史行为一致)
      打包模式: [app 自己, "--vl-exec", <模块名>, *args]      (见 dispatch_if_worker)
    """
    args = list(args or [])
    if FROZEN:
        mod = script[:-3] if script.endswith(".py") else script
        return [sys.executable, "--vl-exec", mod, *args]
    return [sys.executable, str(ASSET_DIR / script), *args]


def dispatch_if_worker() -> None:
    """打包模式专用:若本进程是被 `--vl-exec <模块> [args...]` 拉起的,
    就把那个子脚本当成 __main__ 跑掉再退出 —— 等价于源码模式下
    `python <子脚本>.py args...`。必须在 app 正常启动之前调用。"""
    if not (FROZEN and len(sys.argv) >= 3 and sys.argv[1] == "--vl-exec"):
        return
    bootstrap()
    mod = sys.argv[2]
    # 让子脚本看到的 sys.argv 和「直接跑这个文件」时一模一样
    sys.argv = [mod + ".py", *sys.argv[3:]]
    import runpy
    runpy.run_module(mod, run_name="__main__", alter_sys=True)
    raise SystemExit(0)


# 一旦被 import,就把可写目录和 sys.path 准备好(子脚本 `from runtime import DATA` 即生效)。
bootstrap()
