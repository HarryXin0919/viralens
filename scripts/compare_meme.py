"""
viralens · compare_meme.py
跨创作者验证核心假设:高播放视频的评论"玩梗/社群参与度"是否 > 低播放视频。
performance 用 play_per_day(播放 / 发布天数)排名,控制累积偏差,三创作者同口径。

对每个创作者:取 play_per_day 前5/后5,各抓 N 条热评,算:
  玩梗参与度 = 含"玩梗/情绪"词的评论占比(doge/哈哈/草/离谱…)
  社群参与度 = 含"社群/元互动"词的评论占比(评论区/三连/催更…)
并打印各创作者评论高频签名词。

依赖: bilibili-api-python jieba  /  SESSDATA 从 config_local.py 读
跑: python compare_meme.py
输出: data/cross_creator_meme.json + 终端对比表
"""
import asyncio
import json
import sys
import re
import time
from pathlib import Path
from collections import Counter

from bilibili_api import comment, Credential
from bilibili_api.comment import CommentResourceType, OrderType
import jieba

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DATA = Path(__file__).parent.parent / "data"
try:
    from config_local import SESSDATA
except ImportError:
    SESSDATA = ""
from creators import CREATORS

PER_VIDEO = 30
TOP_N = 5
NOW = time.time()

# 玩梗/情绪(跨创作者通用的 B站 互动语)
MEME = ["doge", "哈哈", "草", "笑死", "绷", "乐死", "梗", "yyds", "awsl", "离谱",
        "好家伙", "啊这", "妙啊", "泪目", "破防", "笑", "整活", "活久见", "牛逼", "栓q"]
# 社群/元互动
COMMUNITY = ["评论区", "三连", "催更", "关注", "点赞", "粉丝", "弹幕", "脱单",
             "前排", "沙发", "支持", "期待", "更新", "蹲", "在线等"]

STOP = set((
    "的 了 是 我 你 他 她 它 们 在 也 都 和 与 就 不 没 有 这 那 个 啊 吧 吗 呢 嘛 哦 噢 "
    "把 被 给 让 对 跟 还 又 很 太 真 哈 一个 这个 那个 什么 怎么 这样 就是 但是 而且 "
    "所以 因为 如果 视频 一下 知道 觉得 感觉 现在 已经 一直 还是 可能 这种 自己 然后 "
    "其实 真的 这么 那么 一样 时候 看到 出来 起来 一点 不是 没有 这里 那里 我们 你们 "
    "他们 一种 不能 可以 这些 那些 的话 一定 应该 毕导 妈咪 妈咪说 李永乐 永乐 老师"
).split())


def has_any(text, words):
    t = text.lower()
    return any(w in t for w in words)


def clean_tokens(text):
    text = re.sub(r"[^一-龥a-zA-Z]", " ", text)
    return [t for t in jieba.cut(text) if len(t) >= 2 and t.lower() not in STOP]


async def fetch_hot(aid, cred, want, tries=4):
    err = ""
    for attempt in range(tries):
        try:
            reps, page = [], 1
            while len(reps) < want and page <= 5:
                r = await comment.get_comments(
                    oid=aid, type_=CommentResourceType.VIDEO,
                    page_index=page, order=OrderType.LIKE, credential=cred)
                batch = r.get("replies") or []
                if not batch:
                    break
                reps.extend(batch)
                page += 1
                await asyncio.sleep(0.5)
            return reps[:want], ""
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            if attempt < tries - 1:
                await asyncio.sleep(5 * (attempt + 1))   # 412 风控退避
    return [], err


def pick_high_low(videos):
    for v in videos:
        days = max((NOW - (v.get("created_ts") or NOW)) / 86400, 1)
        v["play_per_day"] = (v.get("play") or 0) / days
    ranked = sorted(videos, key=lambda x: -x["play_per_day"])
    return ranked[:TOP_N], ranked[-TOP_N:]


async def analyze_creator(c, cred):
    path = DATA / f"{c['alias']}_videos.json"
    if not path.exists():
        print(f"  ✗ {c['name']}: 缺 {path.name},先跑 fetch_multi.py")
        return None
    videos = json.loads(path.read_text(encoding="utf-8"))
    high, low = pick_high_low(videos)
    result = {"creator": c["name"], "groups": {}}
    sig = Counter()
    for gname, vids in [("高", high), ("低", low)]:
        meme_hits = comm_hits = total = 0
        for v in vids:
            reps, err = await fetch_hot(v["aid"], cred, PER_VIDEO)
            if not reps:
                print(f"     ✗ [{gname}] {v['title'][:16]}: {err}")
                await asyncio.sleep(0.8)
                continue
            for r in reps:
                msg = r.get("content", {}).get("message", "")
                total += 1
                if has_any(msg, MEME):
                    meme_hits += 1
                if has_any(msg, COMMUNITY):
                    comm_hits += 1
                sig.update(clean_tokens(msg))
            print(f"     ✓ [{gname}] {v['title'][:16]:<16} {len(reps)}条")
            await asyncio.sleep(0.8)
        result["groups"][gname] = {
            "videos": len(vids), "comments": total,
            "meme_pct": round(meme_hits / (total or 1) * 100, 1),
            "comm_pct": round(comm_hits / (total or 1) * 100, 1),
        }
    result["signature"] = [w for w, _ in sig.most_common(12)]
    return result


async def main():
    if not SESSDATA:
        print("❌ 没读到 SESSDATA(config_local.py)")
        return
    cred = Credential(sessdata=SESSDATA)
    results = []
    print("跨创作者抓评论中(较慢,带风控退避)...\n")
    for c in CREATORS:
        if (c.get("platform") or "bilibili").lower() != "bilibili":
            continue   # 评论分析依赖 B 站评论 API,跳过其它平台
        print(f"■ {c['name']}")
        r = await analyze_creator(c, cred)
        if r:
            results.append(r)
        await asyncio.sleep(1.5)

    if not results:
        print("\n⚠️ 没结果,把报错贴给我")
        return

    (DATA / "cross_creator_meme.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 74)
    print("跨创作者 · 高 vs 低播放组(play/天)· 评论玩梗 & 社群参与度")
    print("=" * 74)
    print(f"{'创作者':<13}{'玩梗高':>7}{'玩梗低':>7}{'差':>7}  {'社群高':>7}{'社群低':>7}{'差':>7}   假设")
    for r in results:
        hi, lo = r["groups"].get("高", {}), r["groups"].get("低", {})
        dm = hi.get("meme_pct", 0) - lo.get("meme_pct", 0)
        dc = hi.get("comm_pct", 0) - lo.get("comm_pct", 0)
        verdict = "✓支持" if dm > 2 else ("✗反例" if dm < -2 else "~持平")
        print(f"{r['creator']:<13}{hi.get('meme_pct',0):>7}{lo.get('meme_pct',0):>7}{dm:>+7.1f}  "
              f"{hi.get('comm_pct',0):>7}{lo.get('comm_pct',0):>7}{dc:>+7.1f}   {verdict}")

    print("\n各创作者签名反馈词(评论高频,已去创作者名):")
    for r in results:
        print(f"  {r['creator']:<13} {'  '.join(r['signature'])}")
    print("\n✅ 已写 data/cross_creator_meme.json — 把整段贴给我解读")


if __name__ == "__main__":
    asyncio.run(main())
