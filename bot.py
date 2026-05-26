import os
import requests
import json
import datetime
from duckduckgo_search import DDGS
import google.generativeai as genai

# 配置环境变量
LARK_WEBHOOK_URL = os.environ.get("LARK_WEBHOOK_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

def search_news(query, max_results=5):
    """使用 DuckDuckGo 搜索特定主题的最新资讯"""
    print(f"正在搜索: {query}...")
    results = []
    try:
        with DDGS() as ddgs:
            # 搜索新闻，获取最近一个月的新闻
            ddgs_news_gen = ddgs.news(
                keywords=query,
                region="wt-wt",
                safesearch="off",
                timelimit="m",
                max_results=max_results
            )
            for r in ddgs_news_gen:
                results.append(f"- 标题: {r['title']}\n  摘要: {r['body']}\n  来源: {r['source']}")
    except Exception as e:
        print(f"搜索 {query} 时出错: {e}")
        return f"无法获取 {query} 的相关资讯。"
    
    if not results:
        return f"未找到关于 {query} 的最新资讯。"
    return "\n".join(results)

def gather_information():
    """收集美妆趋势和 TikTok Shop 政策信息"""
    queries = [
        "TikTok Shop US seller rules policy update", # 美区政策更新
        "TikTok US viral beauty makeup trends",      # TikTok 美国美妆趋势
        "Instagram US beauty trends",                # Instagram 美妆趋势
        "South Korea skincare new releases trends"   # 韩国护肤美妆新品与趋势
    ]
    
    all_info = ""
    for q in queries:
        all_info += f"=== 关于 '{q}' 的搜索结果 ===\n"
        all_info += search_news(q, max_results=5) + "\n\n"
        
    return all_info

def generate_report(raw_info):
    """使用 Gemini AI 生成日报"""
    print("正在调用 Gemini AI 生成日报...")
    genai.configure(api_key=GEMINI_API_KEY)
    
    # 使用最新一代免费速度最快的基础模型
    model = genai.GenerativeModel('gemini-flash-latest')
    
    prompt = f"""
    你是一个资深的美区 TikTok Shop 美妆类目卖家运营助手。
    你的任务是每天向团队播报全球美妆趋势、近期可蹭的热点，以及美区 TikTok Shop 的政策变动。
    
    下面是我通过搜索引擎抓取到的关于"美区政策"、"美国TikTok/Ins美妆热点"和"韩国美妆护肤新品"的最新资讯：
    
    {raw_info}
    
    请根据以上信息，写一份精美的【每日美区TikTok Shop与美妆热点速报】。
    要求：
    1. 语言必须是中文，并且口吻专业、有网感、有煽动性。
    2. 分为三个核心板块：
       - 📣 **TikTok Shop 美区政策与动态** (提取涉及规则、政策、发货、罚款等关键信息)
       - 💅 **欧美圈美妆热点与趋势** (提取在 TikTok/Ins 上火爆的妆容、成分或新玩法，给出蹭热点的建议)
       - 🇰🇷 **韩国及全球新兴风向标** (提及新品发布、韩国大热的新概念)
    3. 如果某板块没有抓取到有价值的信息，请用简短的话语带过，不要编造。
    4. 排版要美观，多用 emoji，重点加粗，适合在飞书/微信群内阅读。
    5. 最后加一句打气的话，鼓励团队今天爆单。
    """
    
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
    
    # 将 markdown 格式稍微调整以适应飞书的富文本/文本
    payload = {
        "msg_type": "text",
        "content": {
            "text": content
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
    
    # 1. 抓取资讯
    raw_news = gather_information()
    
    # 2. AI 提炼
    report = generate_report(raw_news)
    print("\n--- 生成的报告预览 ---\n")
    try:
        print(report)
    except Exception:
        print("报告含有无法在控制台显示的特殊字符，跳过打印...")
    print("\n----------------------\n")
    
    # 3. 发送飞书
    send_to_lark(report)
    
    print("任务执行完毕。")
