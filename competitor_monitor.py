import os
import requests
import json
import xml.etree.ElementTree as ET
import datetime
from urllib.parse import urlparse
import google.generativeai as genai
from dateutil import parser
import re  # 新增正则提取库

# 配置环境变量
LARK_WEBHOOK_URL = os.environ.get("LARK_WEBHOOK_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# ==========================================
# 【竞品域名列表】
# ==========================================
COMPETITORS = [
    "https://fentybeauty.com",
    "https://fwee.us",
    "https://kajabeauty.com",
    "https://kyliecosmetics.com",
    "https://milkmakeup.com",
    "https://sacheu.com",
    "https://summerfridays.com",
    "https://tartecosmetics.com",
    "https://us.laneige.com",
    "https://wonderskin.com",
    "https://www.charlottetilbury.com",
    "https://www.glossier.com",
    "https://www.meritbeauty.com",
    "https://www.pixibeauty.com",
    "https://www.rarebeauty.com",
    "https://www.rhodeskin.com",
    "https://www.sheglam.com",
    "https://www.tower28beauty.com",
    "https://www.westman-atelier.com"
]

PROMPT_TEMPLATE = """
你是一位极度专业的美妆行业竞品分析师。
下面是我通过 RSS 抓取到的各大竞品独立站在【过去 7 天内】新上架或新更新的产品列表：

{raw_info}

请根据以上信息，为我生成一份【竞品独立站每周上新巡检报告】。

绝对遵守以下要求：
1. **飞书Markdown排版规范**：使用 `**加粗**` 突出品牌和产品名，使用 `-` 列表，**绝对禁止**使用 `#` 多级标题。
2. **格式要求**：请按品牌分类整理，指出该品牌本周上了什么新品。
3. **附带链接**：每个产品必须附上原始购买链接，格式：`[👉 直达链接](产品链接)`。
4. **反幻觉**：只能基于上面的 `raw_info` 撰写，不能自己捏造。
"""

def check_competitor_rss(domain, days=7):
    """访问 Shopify 的 RSS 接口获取最新产品"""
    rss_url = f"{domain}/collections/all.atom"
    brand_name = urlparse(domain).netloc.replace('www.', '').split('.')[0].capitalize()
    print(f"正在巡检 {brand_name}: {rss_url}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    new_products = []
    try:
        response = requests.get(rss_url, headers=headers, timeout=10)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            
            # Atom feeds use namespaces
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            entries = root.findall('atom:entry', ns)
            
            now = datetime.datetime.now(datetime.timezone.utc)
            
            for entry in entries:
                published_str = entry.find('atom:published', ns)
                if published_str is None:
                    continue
                    
                published_time = parser.parse(published_str.text)
                
                # Check if it was published in the last `days` days
                if (now - published_time).days <= days:
                    title = entry.find('atom:title', ns).text
                    link = entry.find('atom:link', ns).attrib['href']
                    
                    # 提取图片 URL
                    img_url = ""
                    summary = entry.find('atom:summary', ns)
                    if summary is not None and summary.text:
                        img_match = re.search(r'src="([^"]+)"', summary.text)
                        if img_match:
                            img_url = f"\n  🖼️ ![产品图]({img_match.group(1)})"
                    
                    new_products.append(f"- **【{brand_name}】** {title}\n  🔗 [直达链接]({link}){img_url}\n  🕒 上架时间: {published_time.strftime('%Y-%m-%d')}")
    except Exception as e:
        print(f"巡检 {brand_name} 失败: {e}")
        
    return new_products

def gather_new_products():
    all_new = []
    for domain in COMPETITORS:
        products = check_competitor_rss(domain, days=7)
        if products:
            all_new.extend(products)
    
    if not all_new:
        return ""
    
    return "\n\n".join(all_new)

def generate_report(raw_info):
    print("正在调用 Gemini AI 生成周报...")
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-flash-latest')
    prompt = PROMPT_TEMPLATE.replace("{raw_info}", raw_info)
    
    try:
        import time
        # 强行休眠 5 秒，错开高峰期，防止与其他的定时任务并发抢占免费额度
        time.sleep(5) 
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"调用 AI 失败: {e}")
        return "AI 生成内容失败，请检查配置。"

def send_to_lark(content):
    if not LARK_WEBHOOK_URL:
        print("未配置飞书 Webhook URL，跳过发送。")
        return
        
    print("正在发送至飞书...")
    headers = {"Content-Type": "application/json"}
    
    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"🕵️ 竞品独立站每周上新雷达 ({datetime.datetime.now().strftime('%m-%d')})"
                },
                "template": "purple"
            },
            "elements": [{"tag": "markdown", "content": content}]
        }
    }
    
    try:
        response = requests.post(LARK_WEBHOOK_URL, headers=headers, data=json.dumps(payload))
        if response.status_code == 200:
            print("飞书消息发送成功！")
        else:
            print(f"发送失败: {response.text}")
    except Exception as e:
        print(f"发送请求失败: {e}")

if __name__ == "__main__":
    if not GEMINI_API_KEY:
        print("错误: 未配置 GEMINI_API_KEY")
        exit(1)
        
    print(f"[{datetime.datetime.now()}] 开始执行每周竞品巡检任务...")
    
    raw_info = gather_new_products()
    if not raw_info.strip():
        print(f"[{datetime.datetime.now()}] 本周监控的竞品均无上新，任务结束，不发送推送。")
        exit(0)
        
    report = generate_report(raw_info)
    
    print("\n--- 生成的周报预览 ---\n")
    try:
        print(report)
    except Exception:
        print("预览跳过...")
    print("\n----------------------\n")
    
    send_to_lark(report)
    print("巡检完毕。")
