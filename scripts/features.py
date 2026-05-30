"""
viralens · features.py
把一条视频的元数据 → 一组「通用特征」。
刻意只用 标题 / 时长 / 发布时间 / 播放 / 评论 / 弹幕 —— 不依赖任何分区专属知识,
所以知识区、数码区、生活区、美食区…任何类型 UP 主都能用。

被 scan_signals.py 调用。纯标准库,零依赖。
"""
import re
from datetime import datetime

# —— 偏离"招牌形式"的粗标记(通用:商单 / vlog / 访谈 / 直播 / 音乐)——
OFF_MARKERS = {
    "商单": ["×", "合作", "赞助", "广告", "推广", "联名"],
    "vlog": ["vlog"],
    "直播": ["直播回放", "录播", "直播录"],
    "访谈": ["专访", "对谈", "采访", "对话"],
    "音乐": ["翻唱", "弹唱", "音乐区"],
    # 英文(给 YouTube 等英文标题用;只用多字符安全词,绝不误伤中文标题)
    "EN": ["sponsored", "#ad", "(ad)", "[ad]", "paid promotion",
           "podcast", "q&a", "interview", "livestream", "live stream"],
}
# 标题里的"夸张/钩子"词(通用 clickbait 信号)
SUPERLATIVE = ["最", "史上", "第一", "唯一", "居然", "竟然", "震惊", "千万",
               "全网", "没人", "真相", "终于", "99%", "100%", "绝了", "炸裂", "崩溃"]
SECOND_PERSON = ["你", "您", "your", "you "]
# —— 标题情绪/意图细分(三类) ——
CURIOSITY = ["为什么", "原来", "揭秘", "真相", "背后", "竟然", "居然", "到底",
             "其实", "没想到", "你不知道", "意想不到", "神秘", "之谜"]      # 好奇钩子
WARNING = ["千万", "警惕", "小心", "危险", "别再", "注意", "后果", "致命",
           "踩坑", "避雷", "慎"]                                          # 警告/紧迫
HOWTO = ["教程", "教学", "攻略", "方法", "手把手", "如何", "技巧", "指南",
         "测评", "评测", "实测", "上手", "教你"]                          # 教程/实用


def off_tag(title, desc=""):
    """命中任一偏离标记就返回标签,否则空串。宁紧勿松,靠人眼复核标题。"""
    s = (title + " " + desc).lower()
    for label, ms in OFF_MARKERS.items():
        if any(m.lower() in s for m in ms):
            return label
    return ""


def extract(v, now):
    """v: 一条视频 dict;now: time.time()。返回 metrics + features 合一的 dict。"""
    title = v.get("title") or ""
    desc = v.get("description") or ""
    ts = v.get("created_ts") or 0
    play = v.get("play") or 0
    dur = v.get("duration_sec") or 0
    comment = v.get("comment") or 0
    danmaku = v.get("danmaku") or 0
    days = max((now - ts) / 86400, 1.0) if ts else 1.0

    f = {
        # —— 可切换的"被比较指标" ——
        "play": play,
        "play_per_day": play / days,                       # 控累积:每天涨多少播放
        "comment_per_10k": comment / (play / 1e4) if play else 0,   # 互动率:每万播放多少评论
        "danmaku_per_min": danmaku / (dur / 60) if dur else 0,      # 弹幕密度:每分钟多少弹幕
        "days_since": days,
        # —— 数值型特征(算相关性) ——
        "duration_sec": dur,
        "title_len": len(title),
        # —— 二元特征(分两组比中位数) ——
        # YouTube 简介塞满品牌/链接/hashtag,扫 desc 会把正常挑战视频误判成偏题 →
        # 只扫 title(与 compare_form.py 一致);B 站简介短而精,继续扫 title+desc。
        "off_format": bool(off_tag(title, "" if (v.get("platform") == "youtube") else desc)),
        "is_series": bool(re.search(r"第\s*\d+\s*[期集]", title)
                          or re.search(r"\d+\s*$", title) or "系列" in title),
        "has_number": bool(re.search(r"\d", title)),
        "has_question": ("?" in title or "？" in title),
        "has_exclaim": ("!" in title or "！" in title),
        "has_2nd_person": any(w in title.lower() for w in SECOND_PERSON),
        "has_superlative": any(w in title for w in SUPERLATIVE),
        "has_bracket": ("【" in title or "《" in title or "「" in title),
        "has_colon": ("：" in title or ":" in title),
        "has_curiosity": any(w in title for w in CURIOSITY),
        "has_warning": any(w in title for w in WARNING),
        "has_howto": any(w in title for w in HOWTO),
    }
    if ts:
        dt = datetime.fromtimestamp(ts)
        f["dow"] = dt.weekday()                 # 0=周一 … 6=周日
        f["hour"] = dt.hour
        f["is_weekend"] = dt.weekday() >= 5
        f["daypart"] = ("夜 0-6" if dt.hour < 6 else "晨 6-12" if dt.hour < 12
                        else "午 12-18" if dt.hour < 18 else "晚 18-24")
    f["dur_bucket"] = ("短 <5min" if dur < 300 else "中 5-12min" if dur < 720 else "长 >12min")

    # —— 封面图像特征(仅当 fetch_covers.py 算过、且已 merge 进 v 时才加) ——
    cov = v.get("cover") or {}
    if cov:
        f["cover_brightness"] = cov.get("brightness", 0)
        f["cover_saturation"] = cov.get("saturation", 0)
        f["cover_contrast"] = cov.get("contrast", 0)
        f["cover_colorfulness"] = cov.get("colorfulness", 0)
        f["cover_edge"] = cov.get("edge", 0)
        f["cover_warm"] = cov.get("warm", 0)
    return f


# —— 展示用中文名(扫描器打印 + 报告用) ——
BINARY_LABELS = {
    "off_format":     "偏离招牌形式(商单/vlog/访谈…)",
    "is_series":      "系列 / 带集数",
    "has_number":     "标题带数字",
    "has_question":   "标题带问号",
    "has_exclaim":    "标题带感叹号",
    "has_2nd_person": "标题带「你」(第二人称)",
    "has_superlative":"标题带夸张词(最/史上/震惊)",
    "has_bracket":    "标题带【】/书名号",
    "has_colon":      "标题带冒号(副标题式)",
    "has_curiosity":  "标题带好奇钩子(为什么/揭秘/真相)",
    "has_warning":    "标题带警告/紧迫(千万/警惕/别)",
    "has_howto":      "标题带教程/实用(方法/测评/如何)",
    "is_weekend":     "周末发布",
}
CAT_LABELS = {"dur_bucket": "视频时长档", "daypart": "发布时段"}
NUMERIC_LABELS = {"duration_sec": "时长(秒)", "title_len": "标题字数", "hour": "发布小时",
                  "cover_brightness": "封面亮度", "cover_saturation": "封面饱和度",
                  "cover_contrast": "封面对比度", "cover_colorfulness": "封面色彩丰富度",
                  "cover_edge": "封面繁简(边缘密度)", "cover_warm": "封面暖色占比"}

# 可切换的指标(扫描器逐个跑)
METRIC_LABELS = {
    "play_per_day":   "播放/天(控累积)",
    "play":           "总播放",
    "comment_per_10k":"互动率(评论/万播放)",
    "danmaku_per_min":"弹幕密度(条/分钟)",
}
