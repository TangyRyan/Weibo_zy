import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import aiofiles
import re

# --- 配置 ---
TRENDING_URL = "https://m.weibo.cn/api/container/getIndex?containerid=106003type%3D25%26t%3D3%26disable_hot%3D1%26filter_type%3Drealtimehot"
TRENDING_DETAIL_URL = "https://m.s.weibo.com/topic/detail?q=%s"
# 微博帖子搜索URL模板, 按热门排序
POSTS_SEARCH_URL = "https://s.weibo.com/weibo?q=%23{}%23&xsort=hot&suball=1&tw=hotweibo"
README_PATH = Path("./README.md")
MAX_RETRIES = 5
# 配置抓取微博帖子的数量和滚动次数
MAX_POSTS_TO_FETCH = 20  # 最多抓取20条微博
SCROLL_COUNT = 2  # 向下滚动次数以加载更多内容

# --- 日志配置 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


# --- 数据类型 ---

# 用于存储单条微博内容的数据类
class WeiboPost:
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
            "author": self.author,
            "content": self.content,
            "timestamp": self.timestamp,
            "forwards_count": self.forwards_count,
            "comments_count": self.comments_count,
            "likes_count": self.likes_count,
        }


# 用于存储单个热搜词条的数据类
class WeiboItem:
    def __init__(self, title: str, category: str, description: str, url: str, hot: int, ads: bool,
                 read_count: Optional[int] = None, discuss_count: Optional[int] = None, origin: Optional[int] = None,
                 posts: Optional[List[WeiboPost]] = None):
        self.title = title
        self.category = category
        self.description = description
        self.url = url
        self.hot = hot
        self.ads = ads
        self.read_count = read_count
        self.discuss_count = discuss_count
        self.origin = origin
        self.posts = posts or []

    def to_dict(self):
        return {
            "title": self.title,
            "category": self.category,
            "description": self.description,
            "url": self.url,
            "hot": self.hot,
            "ads": self.ads,
            "read_count": self.read_count,
            "discuss_count": self.discuss_count,
            "origin": self.origin,
            "posts": [post.to_dict() for post in self.posts],
        }


# --- 工具函数 ---
def create_list(words: List[WeiboItem]) -> str:
    """生成README.md中的热搜列表Markdown文本"""
    last_update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    list_items = []
    for i, item in enumerate(words):
        category = f"`{item.category.strip()}`" if item.category else ''
        list_items.append(f"{i + 1}. [{item.title}]({item.url}) {category} - {item.hot}")

    return f"""
**最后更新时间**：{last_update_time}
{chr(10).join(list_items)}

"""


def create_archive(words: List[WeiboItem], date: str) -> str:
    """生成每日归档的Markdown文本"""
    return f"# {date}\n\n共 {len(words)} 条\n\n{create_list(words)}"


def ensure_dir(dir_path: Path):
    """确保目录存在"""
    dir_path.mkdir(parents=True, exist_ok=True)


async def write_file(file_path: Path, content: str):
    """异步写入文件"""
    try:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
            await f.write(content)
    except IOError as e:
        logging.error(f"写入文件失败: {file_path}", exc_info=True)
        raise e


async def read_file(path: Path) -> str:
    """异步读取文件"""
    try:
        async with aiofiles.open(path, 'r', encoding='utf-8') as f:
            return await f.read()
    except FileNotFoundError:
        await write_file(path, '')
        return ''


def convert_to_number(val_str: Optional[str]) -> int:
    """将包含'万'或'亿'的字符串转换为数字"""
    if not val_str:
        return 0
    val_str = val_str.strip().replace('转发', '').replace('评论', '').replace('赞', '').strip()
    if not val_str:
        return 0
    if '万' in val_str:
        return int(float(val_str.replace('万', '')) * 10000)
    elif '亿' in val_str:
        return int(float(val_str.replace('亿', '')) * 100000000)
    else:
        return int(float(val_str.replace(',', '')))


def extract_numbers(s: Optional[str]) -> int:
    """从字符串中提取所有数字并组合成一个整数"""
    if not s:
        return 0
    return int("".join(filter(str.isdigit, str(s))))


# --- 核心爬虫逻辑 ---
async def fetch_trending_data_with_playwright() -> Optional[Dict[str, Any]]:
    """使用Playwright获取微博热搜主榜单"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Mobile/15E148 Safari/604.1'
        )
        page = await context.new_page()
        try:
            await page.goto(TRENDING_URL, wait_until='networkidle')
            content = await page.text_content('body')
            if not content:
                raise ValueError("热搜榜页面内容为空")
            return json.loads(content)
        except Exception as e:
            logging.error("Playwright 获取热搜榜数据失败", exc_info=True)
            return None
        finally:
            await browser.close()


async def fetch_topic_posts(topic_title: str) -> List[WeiboPost]:
    """抓取单个话题下的热门微博帖子"""
    posts = []
    # PC端URL不需要'#'符号
    url = POSTS_SEARCH_URL.format(quote(topic_title.replace("#", "")))
    logging.info(f"正在抓取话题 '{topic_title}' 的微博内容, URL: {url}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        )
        page = await context.new_page()
        try:
            await page.goto(url, wait_until='networkidle')

            # 确认关键内容容器是否存在，防止被重定向到登录页
            try:
                await page.wait_for_selector('div.card-wrap', timeout=10000)
            except Exception:
                logging.warning(f"页面 '{topic_title}' 未能找到关键元素，可能被重定向。跳过此话题。")
                return []

            # 模拟向下滚动以加载动态内容
            for _ in range(SCROLL_COUNT):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)

            html_content = await page.content()
            soup = BeautifulSoup(html_content, 'html.parser')

            post_cards = soup.select('div.card-wrap')

            for card in post_cards[:MAX_POSTS_TO_FETCH]:
                try:
                    # 跳过广告或其他非标准微博卡片
                    if not card.select_one('p.txt'):
                        continue

                    author = card.select_one('.content .info .name').get_text(strip=True) if card.select_one(
                        '.content .info .name') else ''
                    content = card.select_one('p.txt').get_text(strip=True)
                    timestamp = card.select_one('.content .from a').get_text(strip=True)

                    actions = card.select('.card-act ul li a')
                    # **修正后的索引**
                    forwards = convert_to_number(actions[0].get_text(strip=True)) if len(actions) > 0 else 0
                    comments = convert_to_number(actions[1].get_text(strip=True)) if len(actions) > 1 else 0
                    likes = convert_to_number(actions[2].get_text(strip=True)) if len(actions) > 2 else 0

                    posts.append(WeiboPost(
                        author=author, content=content, timestamp=timestamp,
                        forwards_count=forwards, comments_count=comments, likes_count=likes
                    ))
                except Exception:
                    # 解析单个卡片失败则跳过
                    continue
        except Exception as e:
            logging.error(f"抓取话题 '{topic_title}' 微博时发生未知错误", exc_info=True)
        finally:
            await browser.close()

    logging.info(f"成功抓取到 {len(posts)} 条关于 '{topic_title}' 的微博")
    return posts


async def fetch_trending_detail(title: str) -> Dict[str, Any]:
    """使用httpx获取热搜词条的详情（阅读、讨论数等）"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(TRENDING_DETAIL_URL % quote(title))
            response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        counts = [convert_to_number(li.find('strong').get_text(strip=True)) for li in
                  soup.select('div.g-list-a.data ul li')]

        category_element = soup.select_one('#pl_topicband dl > dd')
        desc_element = soup.select_one('#pl_topicband dl:nth-of-type(2) dd:not(.host-row)')

        return {
            "category": category_element.get_text(strip=True) if category_element else '',
            "desc": desc_element.get_text(strip=True) if desc_element else '',
            "read_count": counts[0] if len(counts) > 0 else 0,
            "discuss_count": counts[1] if len(counts) > 1 else 0,
            "origin": counts[2] if len(counts) > 2 else 0,
        }
    except Exception as e:
        logging.warning(f"获取详情失败: {title}", exc_info=True)
        return {}


async def save_hourly_json(words: List[WeiboItem]):
    """按小时保存当前的热搜数据"""
    date = datetime.now().strftime('%Y-%m-%d')
    hour = datetime.now().strftime('%H')
    dir_path = Path(f"./api/{date}")
    full_path = dir_path / f"{hour}.json"
    ensure_dir(dir_path)

    unique_words = {word.title: word for word in words}.values()
    sorted_words = sorted(list(unique_words), key=lambda x: x.hot, reverse=True)

    await write_file(full_path, json.dumps([word.to_dict() for word in sorted_words], ensure_ascii=False, indent=2))


async def create_readme(words: List[WeiboItem]):
    """更新README.md文件"""
    try:
        content = await read_file(README_PATH)
        # 使用 re.sub 只替换一次，防止README中有其他内容时被错误覆盖
        new_content = re.sub(r"[\s\S]*", create_list(words), content, 1)
        await write_file(README_PATH, new_content)
    except Exception as e:
        logging.error("更新 README 失败", exc_info=True)


async def save_day_json(words: List[WeiboItem]):
    """保存每日汇总数据，并更新归档和README"""
    date = datetime.now().strftime('%Y-%m-%d')
    dir_path = Path(f"./api/{date}")
    full_path = dir_path / "summary.json"
    ensure_dir(dir_path)

    words_already_downloaded = []
    content = await read_file(full_path)
    if content:
        words_already_downloaded = json.loads(content)

    word_map = {word['title']: word for word in words_already_downloaded}
    for word in words:
        word_dict = word.to_dict()
        if word.title in word_map:
            old_word = word_map[word.title]
            old_word['hot'] = max(word.hot, old_word.get('hot', 0))
            old_word['read_count'] = max(word.read_count or 0, old_word.get('read_count', 0))
            old_word['discuss_count'] = max(word.discuss_count or 0, old_word.get('discuss_count', 0))
            old_word['origin'] = max(word.origin or 0, old_word.get('origin', 0))
            # 简单地用最新的帖子列表覆盖旧的
            old_word['posts'] = word_dict['posts']
        else:
            word_map[word.title] = word_dict

    updated_words_dicts = sorted(list(word_map.values()), key=lambda x: x.get('hot', 0), reverse=True)

    # 将字典列表重新构建为WeiboItem对象列表，以用于生成Markdown
    updated_words_items = [
        WeiboItem(
            posts=[WeiboPost(**p) for p in w.get('posts', [])],
            **{k: v for k, v in w.items() if k != 'posts'}
        ) for w in updated_words_dicts
    ]

    await write_file(full_path, json.dumps(updated_words_dicts, ensure_ascii=False, indent=2))

    archive_data = create_archive(updated_words_items, date)
    await write_file(Path(f"./archives/{date}.md"), archive_data)
    await create_readme(updated_words_items)


async def bootstrap():
    """主启动函数"""
    retry_count = 0
    while retry_count < MAX_RETRIES:
        try:
            data = await fetch_trending_data_with_playwright()
            if data and data.get("ok") == 1:
                items = data.get("data", {}).get("cards", [])[0].get("card_group", [])
                if items:
                    tasks = []
                    for item in items:
                        # 跳过广告
                        if item.get('promotion'):
                            continue

                        async def process_item(item_data):
                            title = item_data.get('desc')
                            if not title:
                                return None

                            # 并发获取详情和帖子
                            detail_task = fetch_trending_detail(title)
                            posts_task = fetch_topic_posts(title)
                            detail, posts = await asyncio.gather(detail_task, posts_task)

                            return WeiboItem(
                                title=title,
                                category=detail.get('category') or item_data.get('category'),
                                description=detail.get('desc') or item_data.get('description'),
                                url=item_data.get('scheme'),
                                hot=extract_numbers(item_data.get('desc_extr')),
                                ads=False,
                                read_count=detail.get('read_count'),
                                discuss_count=detail.get('discuss_count'),
                                origin=detail.get('origin'),
                                posts=posts
                            )

                        tasks.append(process_item(item))

                    # 过滤掉返回None的结果
                    words = [result for result in await asyncio.gather(*tasks) if result is not None]

                    # 并发保存数据
                    await asyncio.gather(save_hourly_json(words), save_day_json(words))
                break
            else:
                raise ValueError("API 返回数据格式不正确或 ok != 1")
        except Exception as e:
            logging.error(f"第 {retry_count + 1} 次尝试失败。", exc_info=True)
            retry_count += 1
            if retry_count >= MAX_RETRIES:
                logging.error("达到最大重试次数，程序退出。")
                break
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(bootstrap())