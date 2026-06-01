# viralens · 本地构建 Windows 桌面 app(给开发者验证用;正式三平台包由 GitHub Actions 出)
#
#   用法:  powershell -ExecutionPolicy Bypass -File packaging\build-local.ps1
#   产物:  dist\viralens\viralens.exe   (整个 dist\viralens\ 文件夹即可压缩分发)
#
# 需要本机已装 Python 3.10+(3.12 最稳)。脚本会装好打包所需依赖,再跑 PyInstaller。
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)   # 切到仓库根

# 找 Python:优先 py -3,退而求其次 python
$py = $null
if (Get-Command py -ErrorAction SilentlyContinue) { $py = "py"; $pyArgs = @("-3") }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $py = "python"; $pyArgs = @() }
else { Write-Error "没找到 Python。先装 Python 3.10+ 并勾选 Add to PATH。"; exit 1 }

Write-Host "[*] 用解释器:" -NoNewline; & $py @pyArgs --version

Write-Host "[*] 安装运行依赖(来自 pyproject)+ 原生窗口后端 + PyInstaller ..."
& $py @pyArgs -m pip install --upgrade pip
& $py @pyArgs -m pip install -e ".[gui]"    # [gui] = pywebview,双击弹原生窗口
& $py @pyArgs -m pip install pyinstaller

Write-Host "[*] 打包(onedir)..."
& $py @pyArgs -m PyInstaller --noconfirm --clean packaging/viralens.spec

$exe = Join-Path (Get-Location) "dist\viralens\viralens.exe"
if (Test-Path $exe) {
    Write-Host "[OK] 构建完成 -> $exe"
    Write-Host "     双击 viralens.exe 即可启动;整个 dist\viralens\ 文件夹打包(zip)就能分发。"
} else {
    Write-Error "构建结束但没找到 $exe —— 看上面的 PyInstaller 日志。"
    exit 1
}
