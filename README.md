# 美区 TikTok Shop 飞书小助手 (Lark Beauty Bot)

这是一个自动化工具，每天定时利用 DuckDuckGo 搜索抓取全球（包括欧美 TikTok、Ins、Twitter 以及韩国）最新的美妆爆品趋势和 TikTok Shop 美区政策更新，并通过 Gemini 大语言模型整理汇总成精美的简报，最后推送到飞书/Lark 群聊中。

## 功能特性
- **完全自动化部署**：基于 GitHub Actions 每天定时运行（免费），完全不需要购买服务器。
- **免科学上网的数据采集**：在 GitHub 服务器上直接运行，可以毫无障碍地搜索外网信息。
- **AI 智能摘要**：不用再费力读枯燥的英文新闻，AI 会自动帮你提炼成具有煽动性、专业性且带排版的中文日报。

## 部署教程

### 第一步：获取必需的 API 密钥

1. **获取飞书群机器人 Webhook**：
   - 在你要推送的飞书群聊中，点击右上角设置 -> **群机器人** -> **添加机器人** -> 选择 **自定义机器人**。
   - 填写名字（比如“美妆潮流捕手”），添加完成后，复制页面上提供的 **Webhook 地址**。
2. **获取 Gemini API Key**：
   - 访问 [Google AI Studio](https://aistudio.google.com/)，登录你的谷歌账号。
   - 点击左侧的 "Get API Key"，然后点击 "Create API Key"，复制生成的密钥。

### 第二步：将代码上传到 GitHub

1. 在 GitHub (https://github.com) 注册或登录账号，点击右上角 **+** 创建一个新仓库 (New repository)，名字可以叫 `lark-beauty-bot`，设为 **Private**（私有库）。
2. 将本地的这四个文件上传到你的这个新仓库中：
   - `bot.py`
   - `requirements.txt`
   - `.github/workflows/daily_run.yml`
   - `README.md`

### 第三步：在 GitHub 中配置密钥 (Secrets)

为了让程序能够安全地读取到你刚才获取的两个密钥：
1. 进入你刚刚建好的 GitHub 仓库。
2. 点击上方的 **Settings** 选项卡。
3. 在左侧菜单栏找到 **Secrets and variables** -> 点击 **Actions**。
4. 点击绿色的 **New repository secret** 按钮，分别添加两个变量：
   - Name: `GEMINI_API_KEY` , Secret 填入你的 Gemini 密钥。
   - Name: `LARK_WEBHOOK_URL` , Secret 填入你的飞书 Webhook 地址。

### 第四步：测试与日常运行

- **测试运行**：配置好 Secret 后，点击仓库上方的 **Actions** 选项卡 -> 左侧选择 `Daily Lark Beauty Bot` -> 点击右侧出现的 `Run workflow` 按钮手动触发一次运行。去飞书群里看看是否收到了日报！
- **自动运行**：如果你在 `daily_run.yml` 里没有修改时间，它默认会在每天的北京时间上午 9:30 自动运行并发送飞书消息。

> 祝美区大卖！
