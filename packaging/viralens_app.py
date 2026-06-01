"""
viralens · 打包成桌面 app 时的入口(被 PyInstaller 冻结,见 viralens.spec)。

两种角色,靠命令行第一个参数区分:
  · 正常双击启动  → 起本地网页界面(app.main()),浏览器自动打开。
  · 自己重新拉起  → 形如 `viralens --vl-exec fetch_multi --force`:这是流水线某一步,
                    由 runtime.dispatch_if_worker() 接管、当成 __main__ 跑掉再退出。
                    (源码模式下这一步等价于 `python scripts/fetch_multi.py --force`。)

为什么要这样:整个工具是一串脚本用 subprocess 互相调起来的。打包后 sys.executable
变成 app 自己而不是 Python,所以让 app 自己充当「Python」——带上 --vl-exec 再跑一遍。
"""
import runtime

runtime.bootstrap()
runtime.dispatch_if_worker()   # 若本进程是 --vl-exec 子步骤:跑完即退出,不会往下走

import app
app.main()
