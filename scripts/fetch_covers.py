"""
viralens · fetch_covers.py
封面图像分析(L1.5)—— 下载每条视频封面,算一组**通用、可解释、零深度学习**的图像指标。
不做人脸/OCR(要 opencv,且不通用);只做任何分区都成立的色彩/明暗/繁简度量。

指标(每个封面一行):
  brightness   平均亮度 0-255      —— 封面是亮还是暗
  saturation   平均饱和度 0-255    —— 鲜艳还是灰
  contrast     亮度标准差          —— 对比强不强
  colorfulness Hasler–Süsstrunk    —— 色彩丰富度(经典单值度量)
  edge         平均梯度            —— 画面繁简/文字密度代理(边越多越"花")
  warm         暖色像素占比 0-1     —— 暖调(红橙黄)还是冷调

缓存到 data/<alias>_covers.json,按 bvid 存;重跑只补新视频,已下过的跳过。
封面是公开 CDN,只需 Referer 头,**不需要 SESSDATA**。

跑: python fetch_covers.py
依赖: Pillow + numpy(见 requirements.txt)
"""
import json
import sys
import io
import time
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from runtime import DATA           # 源码=仓库/data,打包成 app 时=用户数据目录
from creators import CREATORS

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
           "Referer": "https://www.bilibili.com"}


def metrics(im):
    """一张封面 → 一组通用图像指标。先缩到 480 边长(指标对尺度稳健,省内存)。"""
    im = im.convert("RGB")
    im.thumbnail((480, 480))
    arr = np.asarray(im, dtype=np.float32)
    R, G, B = arr[..., 0], arr[..., 1], arr[..., 2]
    luma = 0.299 * R + 0.587 * G + 0.114 * B

    hsv = np.asarray(im.convert("HSV"), dtype=np.float32)
    H, S = hsv[..., 0], hsv[..., 1]                 # H,S ∈ 0-255

    # Hasler–Süsstrunk 色彩丰富度(需带符号运算,用 numpy)
    rg = R - G
    yb = 0.5 * (R + G) - B
    colorful = float(np.sqrt(rg.std() ** 2 + yb.std() ** 2)
                     + 0.3 * np.sqrt(rg.mean() ** 2 + yb.mean() ** 2))

    # 边缘密度:横纵相邻像素亮度差的平均(繁简/文字代理)
    gx = np.abs(np.diff(luma, axis=1)).mean()
    gy = np.abs(np.diff(luma, axis=0)).mean()

    # 暖色占比:H<43(红橙黄)或 H>233(深红/品红)
    warm = float(((H < 43) | (H > 233)).mean())

    return {
        "brightness": round(float(luma.mean()), 1),
        "saturation": round(float(S.mean()), 1),
        "contrast": round(float(luma.std()), 1),
        "colorfulness": round(colorful, 1),
        "edge": round(float((gx + gy) / 2), 2),
        "warm": round(warm, 3),
        "w": im.width, "h": im.height,
    }


def fetch_img(url, retries=2):
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            data = urllib.request.urlopen(req, timeout=15).read()
            return Image.open(io.BytesIO(data))
        except Exception:
            if i == retries:
                raise
            time.sleep(1.5 * (i + 1))


def main():
    for c in CREATORS:
        vp = DATA / f"{c['alias']}_videos.json"
        if not vp.exists():
            print(f"  ✗ 缺 {c['alias']}_videos.json"); continue
        vids = json.loads(vp.read_text(encoding="utf-8"))
        cp = DATA / f"{c['alias']}_covers.json"
        cache = json.loads(cp.read_text(encoding="utf-8")) if cp.exists() else {}

        n_new = n_fail = 0
        for v in vids:
            bvid, url = v.get("bvid"), v.get("cover_url")
            if not bvid or not url or bvid in cache:
                continue
            try:
                cache[bvid] = metrics(fetch_img(url))
                n_new += 1
                time.sleep(0.15)
            except Exception as e:
                n_fail += 1
                print(f"    · 失败 {bvid}: {e}")
            if n_new and n_new % 10 == 0:                  # 边下边存,中断不丢
                cp.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        cp.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  ✓ {c['name']}: 封面 {len(cache)}/{len(vids)} (新增 {n_new}, 失败 {n_fail})")

    print("\n✅ 封面指标已缓存,可重跑 scan_signals.py 看封面与播放的相关性")


if __name__ == "__main__":
    main()
