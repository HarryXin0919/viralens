"""
viralens · shared_markers.py —— 「偏离招牌形式」关键词的**唯一数据源**。

历史上 features.py 和 compare_form.py 各自定义了一份 OFF_MARKERS,内容已经漂移
(features 多了 "联名" 和 "livestream"/"live stream"),两套分析口径不一致。这里收口成
一处,保留两份**故意不同**的命名常量:

- OFF_MARKERS_FULL    —— features.extract() 的全维度扫描用(口径较全)。
- OFF_MARKERS_COMPARE —— compare_form 的头尾对比报告用(故意更保守,见下方注释)。

只含常量、不含逻辑,所以谁都能 import,绝无循环依赖。改关键词只改这里一处。
"""

# 全口径:特征工程 / 信号扫描用(features.py)
OFF_MARKERS_FULL = {
    "商单": ["×", "合作", "赞助", "广告", "推广", "联名"],
    "vlog": ["vlog"],
    "直播": ["直播回放", "录播", "直播录"],
    "访谈": ["专访", "对谈", "采访", "对话"],
    "音乐": ["翻唱", "弹唱", "音乐区"],
    # 英文(给 YouTube 等英文标题用;只用多字符安全词,绝不误伤中文标题)
    "EN": ["sponsored", "#ad", "(ad)", "[ad]", "paid promotion",
           "podcast", "q&a", "interview", "livestream", "live stream"],
}

# 保守口径:头尾形式对比报告用(compare_form.py)。比 FULL 少两类,**刻意为之**:
# - 去掉 "联名":对比报告里宁可漏判,避免把联名款正片误标偏题。
# - 去掉 "livestream"/"live stream":有些 Entertainment 创作者把
#   "secretly in X livestream" 当招牌挑战在用,误伤太大;真正的直播录像偏题标题
#   通常含 "(Live)"/"VOD"/"Live Recording",不靠这两个词。
OFF_MARKERS_COMPARE = {
    "商单": ["×", "合作", "赞助", "广告", "推广"],
    "vlog": ["vlog"],
    "直播": ["直播回放", "录播", "直播录"],
    "访谈": ["专访", "对谈", "采访", "对话"],
    "音乐": ["翻唱", "弹唱", "音乐区"],
    "EN": ["sponsored", "#ad", "(ad)", "[ad]", "paid promotion",
           "podcast", "q&a", "interview"],
}
