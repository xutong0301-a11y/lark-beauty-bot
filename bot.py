import os
import requests
import json
import datetime
from duckduckgo_search import DDGS
import google.generativeai as genai

# 配置环境变量
LARK_WEBHOOK_URL = os.environ.get("LARK_WEBHOOK_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# ==========================================
# 【提示词配置区】你可以随意修改这里的 Prompt
# ==========================================
PROMPT_TEMPLATE = """
你是一位极度专业、客观的数据分析师和跨境电商操盘手。
今天是 {today_date}，你的任务是每天为美区 TikTok Shop 美妆卖家提炼全球资讯。

下面是我通过爬虫抓取到的最新原始资讯（每一条都包含标题、摘要、发布时间、真实的来源链接，部分包含图片链接）：

{raw_info}

请根据以上信息，写一份【美妆行业每日速报】。

绝对遵守以下排版和内容要求：
1. **飞书Markdown排版规范**：
   - **允许**使用 `**加粗**` 语法来突出重点。
   - **绝对禁止**使用 `#` 或 `##` 等多级标题语法（飞书卡片不支持），如果需要小标题，请直接使用 `**【小标题】**`。
   - 列表项请使用 `-` 或 `1. 2. 3.`。
2. **极简客观**：不要写“亲爱的战友们”、“冲鸭”等废话。直接输出干货。
3. **标明真实出处、时间与图片（极其重要）**：
   - 在每一条资讯或趋势分析的末尾，**必须附上它的发布时间和原本的真实出处链接**，格式为：`[👉 时间：(原始资讯中的发布时间) | 来源阅读](原始资讯中的“来源链接”)`。
   - 如果该条原始资讯中提供了图片链接，**必须同时附带**：`[🖼️ 查看相关图片](原始资讯中的“图片链接”)`。
4. **反幻觉与兜底机制（绝对禁止捏造）**：
   - **你只能基于我上面提供的 `raw_info` 里的文本进行总结！**
   - 如果今天缺乏足够的美妆/政策相关资讯，你可以提取抓取到的“国际重要新闻”进行播报（请自建一个 `**【🌍 国际要闻与大环境视点】**` 的板块）。
   - 如果某个板块毫无素材，直接写上“今日暂无相关最新动态”。
   - **绝对禁止自己编造新闻，绝对禁止编造虚假的来源链接！**
5. **分为三个核心板块（请用换行和分割线明确区分）**：
   - 📌 **美区政策与电商大盘**
   - 💄 **欧美圈热点与破圈玩法**
   - 🇰🇷 **产品研发与新兴风向**
   - (若前三个板块内容极少，请增加上述的“国际要闻”板块)
"""

def search_news(query, max_results=5):
    """使用 DuckDuckGo 搜索特定主题的最新资讯"""
    print(f"正在搜索: {query}...")
    results = []
    try:
        with DDGS() as ddgs:
            # timelimit="w" 获取最近一周的新闻，保证新闻时效性且数据不为空
            ddgs_news_gen = ddgs.news(
                keywords=query,
                region="wt-wt",
                safesearch="off",
                timelimit="w",
                max_results=max_results
            )
            for r in ddgs_news_gen:
                url = r.get('url', '未知链接')
                if 'msn.com' in url.lower():
                    continue
                title = r.get('title', '')
                body = r.get('body', '')
                image = r.get('image', '')
                date = r.get('date', '')
                
                # 简单处理一下日期格式，截取前10位 (如 2024-05-27)
                if date:
                    date = date[:10]
                else:
                    date = "未知时间"
                
                info = f"- 标题: {title}\n  发布时间: {date}\n  摘要: {body}\n  来源链接: {url}"
                if image:
                    info += f"\n  图片链接: {image}"
                results.append(info)
    except Exception as e:
        print(f"搜索 {query} 时出错: {e}")
        return f"无法获取 {query} 的相关资讯。"
    
    if not results:
        return f"未找到关于 {query} 的最新资讯。"
    return "\n".join(results)

def gather_information():
    """收集美妆趋势和 TikTok Shop 政策信息"""
    queries = [
        "TikTok Shop US Seller Center policy rules", # 官方政策
        "viral beauty skincare trends TikTok USA",   # TikTok美区护肤美妆爆款
        "new trending beauty ingredients",           # 新兴美妆热门成分
        "K-beauty skincare innovations releases",    # 韩国护肤新品与技术
        "global beauty market consumer trends",      # 全球美妆消费者洞察
        "top global international breaking news"     # 全球重磅国际新闻（作为无美妆新闻时的兜底素材）
    ]
    
    all_info = ""
    for q in queries:
        all_info += f"=== 关于 '{q}' 的搜索结果 ===\n"
        all_info += search_news(q, max_results=4) + "\n\n"
        
    return all_info

def generate_report(raw_info):
    """使用 Gemini AI 生成日报"""
    print("正在调用 Gemini AI 生成日报...")
    genai.configure(api_key=GEMINI_API_KEY)
    
    model = genai.GenerativeModel('gemini-flash-latest')
    
    today_date = datetime.datetime.now().strftime("%Y-%m-%d")
    prompt = PROMPT_TEMPLATE.replace("{today_date}", today_date).replace("{raw_info}", raw_info)
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"调用 AI 失败: {e}")
        return "AI 生成内容失败，请检查 API 密钥或网络限制。"

def send_to_lark(content):
    """将生成的报告发送到飞书群机器人"""
    if not LARK_WEBHOOK_URL:
        print("未配置飞书 Webhook URL，跳过发送。")
        return
        
    print("正在发送至飞书...")
    headers = {
        "Content-Type": "application/json"
    }
    
    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"✨ 美区TikTok Shop与美妆速报 ({datetime.datetime.now().strftime('%m-%d')}) ✨"
                },
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": content
                }
            ]
        }
    }
    
    try:
        response = requests.post(LARK_WEBHOOK_URL, headers=headers, data=json.dumps(payload))
        if response.status_code == 200:
            print("飞书消息发送成功！")
        else:
            print(f"发送失败，状态码: {response.status_code}, 返回: {response.text}")
    except Exception as e:
        print(f"发送请求失败: {e}")

if __name__ == "__main__":
    if not GEMINI_API_KEY:
        print("错误: 未配置 GEMINI_API_KEY 环境变量。")
        exit(1)
        
    print(f"[{datetime.datetime.now()}] 开始执行每日资讯收集任务...")
    
    raw_news = gather_information()
    report = generate_report(raw_news)
    
    print("\n--- 生成的报告预览 ---\n")
    try:
        print(report)
    except Exception:
        print("报告含有无法在控制台显示的特殊字符，跳过打印...")
    print("\n----------------------\n")
    
    send_to_lark(report)
    print("任务执行完毕。")
