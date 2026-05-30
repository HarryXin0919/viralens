"""
viralens · security_check.py —— 上传 / 分享前的一键安全自检。

跑一遍整个项目,确认你的密钥(B 站 SESSDATA、YouTube API Key、代理、CSRF token 等)
不会跟着代码泄露出去。**绝不打印密钥明文** —— 命中时只显示打码片段 + 所在文件行号。

查四件事:
  [1] .gitignore 有没有把 config_local.py / data/ 排除掉
  [2] 除了密钥保险箱(config_local.py),有没有别的文件硬编码了密钥指纹(AIza… / SESSDATA…)
  [3] 保险箱里的「真实值」有没有被复制到了别的文件(最强检查:防手滑粘贴泄漏)
  [4] 如果是 git 仓库,git 有没有在偷偷跟踪 config_local.py

跑法:
    python security_check.py
退出码:0 = 安全,1 = 有风险(可挂到 git pre-commit 钩子 / CI)。
"""
import os
import re
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):                 # Windows 控制台默认 GBK,强制 UTF-8 才能打 ✅/中文
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent          # viralens/
VAULT = "config_local.py"                              # 唯一允许存明文密钥的文件

SCAN_EXT = {".py", ".html", ".js", ".json", ".md", ".txt", ".css",
            ".csv", ".yml", ".yaml", ".toml", ".cfg", ".ini", ".env"}
SKIP_DIR = {".git", "__pycache__", ".venv", "venv", "node_modules",
            ".idea", ".vscode", ".mypy_cache", ".pytest_cache"}

# 密钥指纹:命中即风险(在 vault 之外出现就是泄漏)
PATTERNS = [
    ("Google / YouTube API key", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("Google OAuth client secret", re.compile(r"GOCSPX-[0-9A-Za-z_\-]{20,}")),
    ("B 站 SESSDATA cookie", re.compile(r"[0-9a-fA-F]{8}%2C\d{10}%2C[0-9A-Za-z%]{20,}")),
    ("B 站 bili_jct CSRF", re.compile(r"bili_jct['\"\s=:]{0,4}[0-9a-f]{32}")),
    ("OAuth refresh token", re.compile(r"1//0[0-9A-Za-z_\-]{30,}")),
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
]
# 第 3 项检查:只把这些「名字像密钥」的变量值拿来做扩散比对(PROXY/URL 之类不算)
SECRET_NAME_HINT = ("SESSDATA", "KEY", "TOKEN", "SECRET", "COOKIE", "PASSWORD", "JCT")


def mask(s):
    s = s.strip()
    if len(s) <= 8:
        return "*" * len(s)
    return s[:4] + "…" + "*" * 6 + "…" + s[-2:]


def rel(p):
    try:
        return str(p.relative_to(ROOT))
    except Exception:
        return str(p)


def iter_files():
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if d not in SKIP_DIR]
        for fn in fns:
            p = Path(dp) / fn
            if p.suffix.lower() in SCAN_EXT:
                yield p


def _read(p):
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


# ———————————————————— [1] .gitignore ————————————————————
def check_gitignore():
    gi = ROOT / ".gitignore"
    if not gi.exists():
        return False, ["没有 .gitignore —— 一旦 git push,config_local.py(含密钥)会被上传!"]
    ignored = {ln.strip().rstrip("/") for ln in _read(gi).splitlines()
               if ln.strip() and not ln.lstrip().startswith("#")}
    issues, ok = [], True
    if "config_local.py" not in ignored:
        issues.append("config_local.py 不在 .gitignore —— 密钥会进 git!(致命)")
        ok = False
    if "data" not in ignored:
        issues.append("data/ 不在 .gitignore(建议忽略:体积大、含抓取来的他人内容)")
    return ok, issues


# ———————————————————— [2] 硬编码指纹 ————————————————————
def check_hardcoded():
    hits = []
    for p in iter_files():
        if p.name == VAULT:                # 保险箱允许存明文,跳过
            continue
        for i, line in enumerate(_read(p).splitlines(), 1):
            for label, rx in PATTERNS:
                m = rx.search(line)
                if m:
                    hits.append((rel(p), i, label, mask(m.group(0))))
    return (not hits), hits


# ———————————————————— [3] 真实值扩散 ————————————————————
def _vault_secrets():
    """从 config_local.py 读出「名字像密钥」的值。只在内存里用,只返回值列表。"""
    cands = list(ROOT.rglob(VAULT))
    if not cands:
        return None
    out = []
    for line in _read(cands[0]).splitlines():
        m = re.match(r'\s*(\w+)\s*=\s*["\'](.+?)["\']\s*$', line)
        if m and len(m.group(2)) >= 12 and any(h in m.group(1).upper() for h in SECRET_NAME_HINT):
            out.append(m.group(2))
    return out


def check_spread():
    secrets = _vault_secrets()
    if secrets is None:
        return None, []                    # 还没建 config_local.py
    hits = []
    for p in iter_files():
        if p.name == VAULT:
            continue
        text = _read(p)
        for s in secrets:
            if s and s in text:
                for i, line in enumerate(text.splitlines(), 1):
                    if s in line:
                        hits.append((rel(p), i, mask(s)))
                        break
    return (not hits), hits


# ———————————————————— [4] git 跟踪 ————————————————————
def check_git():
    if not (ROOT / ".git").exists():
        return True, "不是 git 仓库(还没上传,暂无 git 泄漏风险)"
    try:
        r = subprocess.run(["git", "ls-files", VAULT], cwd=str(ROOT),
                           capture_output=True, text=True)
        if r.stdout.strip():
            return False, f"git 正在跟踪 {VAULT}!立刻跑:git rm --cached {VAULT}"
        return True, f"git 未跟踪 {VAULT}"
    except Exception as e:
        return True, f"(跳过:无法运行 git —— {e})"


def main():
    print("=" * 58)
    print("  viralens 安全自检  /  pre-share security check")
    print("=" * 58)
    ok_all = True

    ok, issues = check_gitignore()
    print(f"\n[1] .gitignore 保护      {'✅ 通过' if ok else '❌ 有风险'}")
    for s in issues:
        print(f"      · {s}")
    ok_all &= ok

    ok, hits = check_hardcoded()
    print(f"\n[2] 硬编码密钥扫描        {'✅ 干净' if ok else '❌ 发现密钥'}")
    for f, ln, lab, mk in hits:
        print(f"      · {f}:{ln}  [{lab}]  {mk}")
    ok_all &= ok

    ok, hits = check_spread()
    if ok is None:
        print("\n[3] 真实密钥扩散检查      ⚠️  没找到 config_local.py(还没设密钥?跳过)")
    else:
        print(f"\n[3] 真实密钥扩散检查      {'✅ 没外泄' if ok else '❌ 密钥出现在别的文件里!'}")
        for f, ln, mk in hits:
            print(f"      · {f}:{ln}  {mk}")
        ok_all &= ok

    ok, msg = check_git()
    print(f"\n[4] git 跟踪状态          {'✅' if ok else '❌'}  {msg}")
    ok_all &= ok

    print("\n" + "=" * 58)
    print("  结论:" + ("✅ 可以安全分享 / 上传 GitHub"
                       if ok_all else "❌ 先把上面标 ❌ 的修掉再上传"))
    print("=" * 58)
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
