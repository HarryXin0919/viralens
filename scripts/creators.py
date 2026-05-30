"""
viralens 创作者配置(可提交,无密钥)。
任意平台 / 任意分区 / 任意创作者 —— 想对比谁,就在这里加一行。

每条字段:
  name      显示名
  platform  "bilibili"(默认,可省略)或 "youtube"
  alias     输出文件名 data/<alias>_videos.json(英文/拼音,别重复)
  zone      分区 / 赛道名,自己定。基准对比按 zone 分组,所以"同一个池子"的人用同一个 zone。
            ⚠️ 跨平台别混用 zone:B站和 YouTube 受众体量不同,给 YouTube 用各自的 zone 名
            (例:B站知识区写 "知识",YouTube 科普写 "STEM-YT"),否则基准就是在跨平台硬比。
  —— Bilibili 专用 ——
  uid       B站用户 UID(数字)。留 None 由 00_resolve_creators.py 按 name 搜索补全
  —— YouTube 专用 ——
  channel   "@handle"(推荐,稳定可核对) / "UCxxxx频道ID" / 频道名(兜底搜索)
"""
CREATORS = [
    # ———————————————————————— Bilibili ————————————————————————
    {"name": "毕导",              "platform": "bilibili", "uid": 254463269, "alias": "bidao",         "zone": "知识"},
    {"name": "妈咪说MommyTalk",   "platform": "bilibili", "uid": 223146252, "alias": "mommytalk",     "zone": "知识"},
    {"name": "李永乐老师官方",     "platform": "bilibili", "uid": 9458053,   "alias": "liyongle",      "zone": "知识"},
    {"name": "无穷小亮的科普日常",  "platform": "bilibili", "uid": 14804670,  "alias": "xiaoliang",     "zone": "知识"},
    {"name": "影视飓风",          "platform": "bilibili", "uid": 946974,    "alias": "yingshijufeng", "zone": "知识"},
    {"name": "老师好我叫何同学",   "platform": "bilibili", "uid": 163637592, "alias": "hetongxue",     "zone": "知识"},
    {"name": "钟文泽",            "platform": "bilibili", "uid": 25910292,  "alias": "zhongwenze",    "zone": "数码"},
    {"name": "极客湾Geekerwan",   "platform": "bilibili", "uid": 25876945,  "alias": "geekerwan",     "zone": "数码"},
    {"name": "itsRae",           "platform": "bilibili", "uid": 26770204,  "alias": "itsrae",        "zone": "生活"},
    {"name": "房琪kiki",          "platform": "bilibili", "uid": 263223596, "alias": "fangqi",        "zone": "生活"},
    {"name": "美食作家王刚R",      "platform": "bilibili", "uid": 290526283, "alias": "wanggang",      "zone": "美食"},
    {"name": "盗月社食遇记",       "platform": "bilibili", "uid": 99157282,  "alias": "daoyueshe",     "zone": "美食"},
    {"name": "老番茄",            "platform": "bilibili", "uid": 546195,    "alias": "laofanqie",     "zone": "游戏"},
    {"name": "中国boy超级大猩猩",  "platform": "bilibili", "uid": 562197,    "alias": "chinaboy",      "zone": "游戏"},

    # ——————————————— YouTube ———————————————
    # 已填 YOUTUBE_API_KEY,跑 fetch_multi.py 会抓下面未注释的。

    # —— Entertainment-YT(挑战 / 真人秀) ——
    # min_duration_sec=180:这些频道都同时发 Shorts 和长视频,Shorts 是另一套算法+广告体系,form
    # 测试必须排除。设 180s 把"Long Shorts"(1-2 分钟)也排掉,只留 3min+ 真长视频。
    {"name": "MrBeast",      "platform": "youtube", "channel": "@MrBeast",      "alias": "mrbeast",    "zone": "Entertainment-YT", "min_duration_sec": 180},
    {"name": "Dude Perfect", "platform": "youtube", "channel": "@DudePerfect",  "alias": "dudeperfect","zone": "Entertainment-YT", "min_duration_sec": 180},
    {"name": "Airrack",      "platform": "youtube", "channel": "@airrack",      "alias": "airrack",    "zone": "Entertainment-YT", "min_duration_sec": 180},
    {"name": "Ryan Trahan",  "platform": "youtube", "channel": "@ryan",         "alias": "ryantrahan", "zone": "Entertainment-YT", "min_duration_sec": 180},

    # —— STEM-YT(待启用:第一次跑专注 MrBeast,以后做"中美 STEM 跨平台比较"再放开)——
    # {"name": "Veritasium",   "platform": "youtube", "channel": "@veritasium",  "alias": "veritasium", "zone": "STEM-YT"},
    # {"name": "3Blue1Brown",  "platform": "youtube", "channel": "@3blue1brown", "alias": "3b1b",       "zone": "STEM-YT"},
    # {"name": "Mark Rober",   "platform": "youtube", "channel": "@MarkRober",   "alias": "markrober",  "zone": "STEM-YT"},
]
