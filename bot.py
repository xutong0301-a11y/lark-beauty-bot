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
                results.append(f"- 标题: {r['title']}\n  摘要: {r['body']}\n  来源链接: {r.get('url', '未知链接')}")
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
        "TikTok US overall viral trending topics",   # 泛TikTok美区整体热点（备用）
        "cross-border e-commerce US policy news"     # 整体跨境电商政策新闻（备用）
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
    你是一位极度专业、客观的数据分析师和跨境电商操盘手。
    你的任务是每天为美区 TikTok Shop 美妆卖家提炼全球资讯。
    
    下面是我通过爬虫抓取到的最新原始资讯，包含新闻的标题、摘要和来源链接：
    
    {raw_info}
    
    请根据以上信息，写一份【美妆行业每日速报】。
    
    绝对遵守以下要求：
    1. **极简客观**：绝对不要写任何“亲爱的战友们”、“搞钱斗志”、“冲鸭”等废话、口水话和彩虹屁。直接输出干货。
    2. **标明出处**：在提到具体的趋势、数据、爆品或政策时，**必须在句子结尾的括号内附上对应的来源链接 (URL)**。
    3. **降维打击/破圈思维**：如果今天抓取到的【美妆直接相关】资讯较少，请自动提炼抓取到的【泛 TikTok 热门话题】或【整体跨境电商政策/大新闻】作为补充，并用一两句话点拨一下跨境卖家可以如何蹭这个热点。
    4. 分为三个核心板块：
       - 📌 **美区政策与电商大盘** (重点写TikTok Shop规则，若无则写北美跨境电商政策大事)
       - 💄 **欧美圈热点与破圈玩法** (重点写美妆爆款/流行妆容。若无，则写今日TikTok大盘热门话题及蹭热点建议)
       - 🇰🇷 **产品研发与新兴风向** (重点列出韩国新技术、新概念、新成分或新品发布)
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
