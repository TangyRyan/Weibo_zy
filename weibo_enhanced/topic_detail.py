import asyncio
import json
import logging
from typing import List, Optional
from urllib.parse import quote
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# --- 配置 ---
POSTS_SEARCH_URL = "https://s.weibo.com/weibo?q=%23{}%23&xsort=hot&suball=1&tw=hotweibo"
MAX_POSTS_TO_FETCH = 20
SCROLL_COUNT = 2
COOKIES_PATH = Path("./weibo_cookies.json")

# --- 日志配置 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


# --- 数据结构 ---
class WeiboPost:
    """用于存储单条微博内容的数据类"""

    def __init__(self, author: str, content: str, timestamp: str, forwards_count: int, comments_count: int,
                 likes_count: int):
        self.author = author
        self.content = content
        self.timestamp = timestamp
        self.forwards_count = forwards_count
        self.comments_count = comments_count
        self.likes_count = likes_count

    def to_dict(self):
        return {
            "author": self.author, "content": self.content, "timestamp": self.timestamp,
            "forwards_count": self.forwards_count, "comments_count": self.comments_count,
            "likes_count": self.likes_count,
        }

    def __repr__(self):
        return f"WeiboPost(author='{self.author}', content='{self.content[:20]}...')"


# --- 工具函数 ---
def _convert_to_number(val_str: Optional[str]) -> int:
    """内部辅助函数：将包含'万'或'亿'的字符串转换为数字"""
    if not val_str: return 0
    val_str = val_str.strip().replace('转发', '').replace('评论', '').replace('赞', '').strip()
    if not val_str: return 0
    if '万' in val_str: return int(float(val_str.replace('万', '')) * 10000)
    if '亿' in val_str: return int(float(val_str.replace('亿', '')) * 100000000)
    return int(float(val_str.replace(',', '')))


# --- 核心功能函数 ---
async def get_top_20_hot_posts(topic_title: str) -> List[WeiboPost]:
    """
    获取指定话题下按热门排序的前20条微博帖子。
    """
    posts = []
    url = POSTS_SEARCH_URL.format(quote(topic_title.replace("#", "")))
    logging.info(f"开始抓取话题 '{topic_title}' 的热门微博...")

    browser_context_args = {
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    if COOKIES_PATH.exists():
        try:
            with open(COOKIES_PATH, 'r') as f:
                cookies = json.load(f)
            browser_context_args['storage_state'] = {"cookies": cookies}
            logging.info("成功加载 Cookies 文件。")
        except Exception as e:
            logging.warning(f"加载 Cookies 文件失败: {e}。将以未登录状态继续。")
    else:
        logging.warning("未找到 Cookies 文件。将以未登录状态继续。")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(**browser_context_args)
        page = await context.new_page()
        try:
            # <<< --- 核心修改点 --- >>>
            # 1. 将 wait_until 修改为 'domcontentloaded'
            # 2. 增加 timeout 到 60000 毫秒 (60秒)
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)

            try:
                await page.wait_for_selector('div.card-wrap', timeout=10000)
            except Exception:
                logging.warning(f"页面 '{topic_title}' 未能找到关键元素，可能被重定向。请检查 Cookies 是否有效或已过期。")
                return []

            for _ in range(SCROLL_COUNT):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)

            html_content = await page.content()
            soup = BeautifulSoup(html_content, 'html.parser')

            post_cards = soup.select('div.card-wrap')

            for card in post_cards[:MAX_POSTS_TO_FETCH]:
                try:
                    if not card.select_one('p.txt'): continue
                    author = card.select_one('.content .info .name').get_text(strip=True) if card.select_one(
                        '.content .info .name') else ''
                    content = card.select_one('p.txt').get_text(strip=True)
                    timestamp = card.select_one('.content .from a').get_text(strip=True)
                    actions = card.select('.card-act ul li a')
                    forwards = _convert_to_number(actions[0].get_text(strip=True)) if len(actions) > 0 else 0
                    comments = _convert_to_number(actions[1].get_text(strip=True)) if len(actions) > 1 else 0
                    likes = _convert_to_number(actions[2].get_text(strip=True)) if len(actions) > 2 else 0
                    posts.append(WeiboPost(author, content, timestamp, forwards, comments, likes))
                except Exception:
                    continue
        except Exception as e:
            logging.error(f"抓取话题 '{topic_title}' 微博时发生未知错误", exc_info=True)
        finally:
            await browser.close()

    logging.info(f"成功抓取到 {len(posts)} 条关于 '{topic_title}' 的微博")
    return posts


# --- 使用示例 ---
if __name__ == '__main__':
    async def main():
        test_topic = "山西地震"
        print(f"正在测试功能：获取话题 '{test_topic}' 的前20条热门微博...")
        top_posts = await get_top_20_hot_posts(test_topic)

        if top_posts:
            print(f"\n成功获取 {len(top_posts)} 条微博：")
            posts_as_dicts = [post.to_dict() for post in top_posts]
            print(json.dumps(posts_as_dicts, ensure_ascii=False, indent=2))
        else:
            print("未能获取到任何微博内容。")


    asyncio.run(main())