"""
viralens · comments.py
抓 pilot 10 个视频(2025正经科普 高5+低5)的热评,做三类成分分析:
  共同 = 跨视频高频词(创作者标签性反馈,如"涨知识""哈哈哈")
  典型 = 单视频 TF-IDF top 词(这条视频独有的记忆点)
  差异 = 高播放组 vs 低播放组 词频差(观众"买账/不买账"时各说什么)

依赖: bilibili-api-python jieba
SESSDATA: 从 config_local.py 读(不进 git)
跑: python comments.py
输出: data/comments_raw.json + data/comment_components.json + 终端三类成分
"""
import asyncio
import json
import sys
import re
from pathlib import Path
from collections import Counter

from bilibili_api import comment, Credential
from bilibili_api.comment import CommentResourceType, OrderType
import jieba
import jieba.analyse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")   # Win 控制台默认 GBK,强制 UTF-8

from runtime import DATA           # 源码=仓库/data,打包成 app 时=用户数据目录
try:
    from config_local import SESSDATA
except ImportError:
    SESSDATA = ""

PER_VIDEO = 40   # 每视频抓多少条热评

# 停用词:虚词 + 太通用的口水词(创作者自己的名字建议按需加,否则会在词频里霸榜)
STOP = set((
    "的 了 是 我 你 他 她 它 们 在 也 都 和 与 就 不 没 有 这 那 个 啊 吧 吗 呢 嘛 哦 噢 "
    "把 被 给 让 对 跟 还 又 很 太 真 哈 一个 这个 那个 什么 怎么 这样 就是 但是 而且 "
    "所以 因为 如果 视频 一下 知道 觉得 感觉 现在 已经 一直 还是 可能 这种 自己 "
    "然后 其实 真的 这么 那么 一样 时候 看到 出来 起来 一点 不是 没有 这里 那里 我们 "
    "你们 他们 一种 不能 可以 这些 那些 的话 一定 应该 已经"
).split())


def clean_tokens(text):
    text = re.sub(r"[^一-龥a-zA-Z]", " ", text)   # 只留中英文
    return [t for t in jieba.cut(text) if len(t) >= 2 and t.lower() not in STOP]


async def fetch_hot(aid, cred, want):
    """抓按点赞排序的热评,返回 (replies, 错误说明)"""
    reps, err = [], ""
    try:
        page = 1
        while len(reps) < want and page <= 5:
            r = await comment.get_comments(
                oid=aid, type_=CommentResourceType.VIDEO,
                page_index=page, order=OrderType.LIKE, credential=cred)
            batch = r.get("replies") or []
            if not batch:
                break
            reps.extend(batch)
            page += 1
            await asyncio.sleep(0.4)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
    return reps[:want], err


async def main():
    if not SESSDATA:
        print("❌ 没读到 SESSDATA。把 config_local.example.py 复制为 config_local.py 并填入")
        return

    classified = json.loads((DATA / "classified.json").read_text(encoding="utf-8"))
    sci = [v for v in classified if v.get("type") == "正经科普"
           and (v.get("created_iso") or "")[:4] == "2025"]
    sci.sort(key=lambda x: -x["play"])
    pilot = [("高", v) for v in sci[:5]] + [("低", v) for v in sci[-5:]]

    cred = Credential(sessdata=SESSDATA)
    raw = {}
    docs = []
    print("抓评论中(每个约 1-2 秒)...\n")
    for group, v in pilot:
        reps, err = await fetch_hot(v["aid"], cred, PER_VIDEO)
        if not reps:
            print(f"  ✗ [{group}] {v['title'][:20]}: {err or '无评论'}")
            continue
        items = [{
            "msg": r.get("content", {}).get("message", ""),
            "like": r.get("like", 0),
            "uname": r.get("member", {}).get("uname", ""),
        } for r in reps]
        raw[v["bvid"]] = {"title": v["title"], "group": group, "play": v["play"], "comments": items}
        text = " ".join(i["msg"] for i in items)
        docs.append({"group": group, "bvid": v["bvid"], "title": v["title"],
                     "tokens": clean_tokens(text), "text": text})
        print(f"  ✓ [{group}] {v['title'][:20]:<20} 抓到 {len(items):>3} 条热评")

    if not docs:
        print("\n⚠️ 一条评论都没抓到。把上面的 ✗ 报错贴给我,我改接口。")
        return

    (DATA / "comments_raw.json").write_text(
        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    # ① 共同成分:文档频率(出现在多少个视频里)
    df = Counter()
    for d in docs:
        for w in set(d["tokens"]):
            df[w] += 1
    common = [(w, c) for w, c in df.most_common(30) if c >= max(3, len(docs) // 2)]

    # ② 典型成分:每视频 TF-IDF top
    typical = {}
    for d in docs:
        kws = jieba.analyse.extract_tags(d["text"], topK=8)
        typical[d["bvid"]] = {"title": d["title"], "group": d["group"], "keywords": kws}

    # ③ 差异成分:高 vs 低 词频(归一化到每千词),只看出现在≥2视频的词
    def group_counter(g):
        c, total = Counter(), 0
        for d in docs:
            if d["group"] == g:
                c.update(d["tokens"])
                total += len(d["tokens"])
        return c, (total or 1)

    hi_c, hi_n = group_counter("高")
    lo_c, lo_n = group_counter("低")
    diff = []
    for w in set(hi_c) | set(lo_c):
        if df[w] < 2:
            continue
        hf = hi_c[w] / hi_n * 1000
        lf = lo_c[w] / lo_n * 1000
        diff.append((w, hf - lf))
    hi_over = sorted(diff, key=lambda x: -x[1])[:12]
    lo_over = sorted(diff, key=lambda x: x[1])[:12]

    out = {
        "common": [{"w": w, "videos": c} for w, c in common],
        "typical": typical,
        "high_over": [{"w": w, "delta_per_1k": round(d, 2)} for w, d in hi_over],
        "low_over": [{"w": w, "delta_per_1k": round(d, 2)} for w, d in lo_over],
    }
    (DATA / "comment_components.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print("① 共同成分 — 创作者标签性反馈(出现在 ≥半数 视频)")
    print("=" * 60)
    print("  " + "   ".join(f"{w}×{c}" for w, c in common[:18]))

    print("\n" + "=" * 60)
    print("③ 差异成分 — 高 vs 低播放组 观众语言(差值/千词)")
    print("=" * 60)
    print("  🔴 高组更爱说: " + "  ".join(f"{w}(+{d:.1f})" for w, d in hi_over))
    print("  🔵 低组更爱说: " + "  ".join(f"{w}({d:.1f})" for w, d in lo_over))

    print("\n" + "=" * 60)
    print("② 典型成分 — 每条视频的记忆点(TF-IDF)")
    print("=" * 60)
    for t in typical.values():
        print(f"  [{t['group']}] {t['title'][:22]:<22} {'  '.join(t['keywords'])}")

    print("\n✅ 已写 data/comments_raw.json + comment_components.json — 把整段贴给我解读")


if __name__ == "__main__":
    asyncio.run(main())
