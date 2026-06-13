"""
viralens 配置模板 —— 复制本文件为 config_local.py 再填入你自己的密钥。
config_local.py 已被 .gitignore 排除,不会上传到 GitHub。

【Bilibili】怎么拿 SESSDATA:
1. 浏览器登录 www.bilibili.com
2. F12 → Application → Cookies → https://www.bilibili.com → 找 SESSDATA
3. 复制 Value(形如 abc123%2Cxxxx%2Cyyy...),粘到下面引号里

【YouTube】怎么拿 YOUTUBE_API_KEY(免费):
1. https://console.cloud.google.com → 新建项目
2. 搜索并启用 "YouTube Data API v3"
3. 凭据 → 创建凭据 → API 密钥 → 复制,粘到下面引号里
   (只抓公开元数据,不需要登录你的 Google 账号;每天额度够跑几十个频道)

只用 B 站就只填 SESSDATA,只用 YouTube 就只填 YOUTUBE_API_KEY,两个都用就都填。

【PROXY】可选,只有「分析 YouTube 视频开头/配乐」这一步要下视频时才用得到:
- 墙外用户:留空,直连即可。
- 国内用户:YouTube 要翻墙才能下视频。填你的代理地址,例如 http://127.0.0.1:10809。
  (留空时也会自动读系统的 HTTPS_PROXY 环境变量;填了这里就以这里为准。
   B 站则相反,永远强制直连,不走代理。)
"""
SESSDATA = ""          # Bilibili 登录 cookie(抓 B 站时用)
YOUTUBE_API_KEY = ""   # YouTube Data API v3 key(抓 YouTube 时用)
PROXY = ""             # 可选:下 YouTube 视频用的代理(国内填 http://127.0.0.1:10809)
BUVID3 = ""            # 可选:B 站 Cookie 里的 buvid3。一般不用填;抓取报 -352 时再补
