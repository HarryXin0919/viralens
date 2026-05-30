"""
viralens · benchmarks.py —— 私有指标的「参照系」。

创作者上传自己的后台数据(完播率 / CTR 等)后,得有个东西告诉他「这个数字算好还是差」。
但别人优秀 UP 主的私有数据我们**拿不到**(平台只给创作者本人看),所以这里放的是
**行业公开的粗略参考区间**,不是哪个具体 UP 主的真实值。

⚠️ 现在是「粗略版」:只按平台 + 视频时长分档。
   D3(术语库 + 分区基准线)会把它细化到「各分区各平台」更准的数字。

每个指标返回 (good 线, ok 线):≥good=做得好,≥ok=尚可,<ok=偏弱。
"""

# 完播率 / 平均观看百分比(average percentage viewed):视频越长,这个数自然越低,所以按时长分档
def retention_band(platform, duration_sec):
    d = duration_sec or 0
    if d and d <= 60:
        return (70, 50)       # 短视频 / Shorts:能看完一大半才算稳
    if d and d <= 300:
        return (55, 38)       # 5 分钟内
    if d and d <= 600:
        return (42, 28)       # 5–10 分钟
    return (32, 20)           # 10 分钟以上:能留住 1/3 就不错了


# 曝光点击率 CTR:YouTube 和 B站「点击率」分母口径不同,分平台给(都只是粗参考)
def ctr_band(platform):
    if (platform or "").lower().startswith("bili"):
        return (10.0, 5.0)   # B站点击率口径不同、整体偏高,给更宽的粗参考
    return (6.0, 3.0)        # YouTube 官方:多数频道 2%–10%,6%+ 亮眼,3% 以下偏弱


# 平均观看时长(秒):没有绝对好坏,主要看「占视频比例」(=完播率),这里只给个「太短」的下限提示
def avd_floor_sec():
    return 30


def level_by_band(value, band):
    """value 跟 (good, ok) 比,返回 good/ok/warn。"""
    if value is None:
        return "na"
    good, ok = band
    if value >= good:
        return "good"
    if value >= ok:
        return "ok"
    return "warn"


# 给前端 / 卡片用的一句「参考线」说明(双语)
def retention_ref(platform, duration_sec):
    good, ok = retention_band(platform, duration_sec)
    return {"zh": f"同长度参考:≥{good}% 好 · ≥{ok}% 尚可",
            "en": f"for this length: ≥{good}% good · ≥{ok}% ok"}


def ctr_ref(platform):
    good, ok = ctr_band(platform)
    tag = "B站口径,仅粗参考" if (platform or "").lower().startswith("bili") else "行业粗略值"
    return {"zh": f"参考:≥{good:.0f}% 好 · ≥{ok:.0f}% 尚可({tag})",
            "en": f"ref: ≥{good:.0f}% good · ≥{ok:.0f}% ok (rough)"}
