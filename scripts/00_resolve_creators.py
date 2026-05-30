"""
viralens · 00_resolve_creators.py
按创作者名字搜 B站,补全 UID(选粉丝最多的账号,防同名假号)。
跑完核对候选 → 我帮你把正确 UID 写回 creators.py。

依赖: bilibili-api-python  /  SESSDATA 从 config_local.py 读
跑: python 00_resolve_creators.py
"""
import asyncio
import sys

from bilibili_api import search, Credential
from bilibili_api.search import SearchObjectType

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

try:
    from config_local import SESSDATA
except ImportError:
    SESSDATA = ""
from creators import CREATORS


async def resolve(name, cred):
    """返回按粉丝降序的前 3 个候选用户,或 (None, 原始返回片段)"""
    try:
        res = await search.search_by_type(
            keyword=name, search_type=SearchObjectType.USER, page=1, credential=cred)
    except TypeError:   # 旧版签名不收 credential
        res = await search.search_by_type(
            keyword=name, search_type=SearchObjectType.USER, page=1)
    users = res.get("result") or []
    if not users:
        return None, str(res)[:300]
    users.sort(key=lambda u: -(u.get("fans") or 0))
    return users[:3], None


async def main():
    cred = Credential(sessdata=SESSDATA) if SESSDATA else None
    print("搜索创作者 UID 中...\n")
    for c in CREATORS:
        if (c.get("platform") or "bilibili").lower() != "bilibili":
            continue   # 只解析 B 站 UID;YouTube 用 @handle,不需要搜索
        if c.get("uid"):
            print(f"  ✓ {c['name']:<16} 已有 UID {c['uid']}")
            continue
        try:
            cands, raw = await resolve(c["name"], cred)
        except Exception as e:
            print(f"  ✗ {c['name']}: 搜索失败 {type(e).__name__}: {e}")
            continue
        if not cands:
            print(f"  ✗ {c['name']}: 没搜到用户。原始返回: {raw}")
            continue
        print(f"\n  「{c['name']}」候选(按粉丝降序,通常取第1个):")
        for u in cands:
            uname = u.get("uname", "")
            mid = u.get("mid", "")
            fans = u.get("fans", 0) or 0
            sign = (u.get("usign", "") or "").replace("\n", " ")[:28]
            print(f"     UID {mid:<12} 粉丝 {fans:>11,}  {uname}  | {sign}")
        await asyncio.sleep(0.5)
    print("\n核对上面候选,把正确的 UID 发我,我写回 creators.py")


if __name__ == "__main__":
    asyncio.run(main())
