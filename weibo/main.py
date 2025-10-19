# weibo/main.py

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path  # 确保 Path 被导入
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import aiofiles

# --- 修改点 1: 定义脚本所在的目录和项目根目录 ---
# SCRIPT_DIR 会获取 main.py 文件所在的目录 (即 .../weibo/)
SCRIPT_DIR = Path(__file__).parent
# ROOT_DIR 会获取上级目录 (即 .../PyCharmMiscProject/)
ROOT_DIR = SCRIPT_DIR.parent

# --- 配置 ---
TRENDING_URL = "https://m.weibo.cn/api/container/getIndex?containerid=106003type%3D25%26t%3D3%26disable_hot%3D1%26filter_type%3Drealtimehot"
TRENDING_DETAIL_URL = "https://m.s.weibo.com/topic/detail?q=%s"
# --- 修改点 2: 让 README.md 路径指向项目根目录 ---
README_PATH = SCRIPT_DIR / "README.md"  # README.md 在 weibo 文件夹内
MAX_RETRIES = 5

# --- 日志配置 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


# --- 数据类型 (无需修改) ---
class WeiboItem:
    def __init__(self, title: str, category: str, description: str, url: str, hot: int, ads: bool,
                 read_count: Optional[int] = None, discuss_count: Optional[int] = None, origin: Optional[int] = None):
        self.title = title
        self.category = category
        self.description = description
        self.url = url
        self.hot = hot
        self.ads = ads
        self.read_count = read_count
        self.discuss_count = discuss_count
        self.origin = origin

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
        }


# --- 工具函数 (无需修改) ---
def create_list(words: List[WeiboItem]) -> str:
    last_update_time = datetime.now().strftime('%Y-%m-%d %I:%M %p')
    list_items = []
    for i, item in enumerate(words):
        category = f"`{item.category.strip()}`" if item.category else ''
        list_items.append(f"{i + 1}. [{item.title}]({item.url}) {category} - {item.hot}")

    return f"""
**最后更新时间**：{last_update_time}
{chr(10).join(list_items)}

"""


def create_archive(words: List[WeiboItem], date: str) -> str:
    return f"# {date}\n\n共 {len(words)} 条\n\n{create_list(words)}"


def ensure_dir(dir_path: Path):
    dir_path.mkdir(parents=True, exist_ok=True)


async def write_file(file_path: Path, content: str):
    try:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
            await f.write(content)
    except IOError as e:
        logging.error(f"写入文件失败: {file_path}", exc_info=True)
        raise e


async def read_file(path: Path) -> str:
    try:
        async with aiofiles.open(path, 'r', encoding='utf-8') as f:
            return await f.read()
    except FileNotFoundError:
        await write_file(path, '')
        return ''


def convert_to_number(val_str: str) -> int:
    val_str = val_str.strip()
    if '万' in val_str:
        return int(float(val_str.replace('万', '')) * 10000)
    elif '亿' in val_str:
        return int(float(val_str.replace('亿', '')) * 100000000)
    else:
        return int(float(val_str))


def extract_numbers(s: Optional[str]) -> int:
    if not s:
        return 0
    return int("".join(filter(str.isdigit, str(s))))


# --- 核心爬虫逻辑 (无需修改) ---
async def fetch_trending_data_with_playwright() -> Optional[Dict[str, Any]]:
    # ... (这部分代码无需修改)
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
                raise ValueError("页面内容为空")
            return json.loads(content)
        except Exception as e:
            logging.error("Playwright 获取数据失败", exc_info=True)
            return None
        finally:
            await browser.close()


async def fetch_trending_detail(title: str) -> Dict[str, Any]:
    # ... (这部分代码无需修改)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(TRENDING_DETAIL_URL % quote(title))
            response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        counts = []
        for li in soup.select('div.g-list-a.data ul li'):
            strong_text = li.find('strong').get_text(strip=True)
            counts.append(convert_to_number(strong_text))

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
    date = datetime.now().strftime('%Y-%m-%d')
    hour = datetime.now().strftime('%H')
    # --- 修改点 3: 使用 SCRIPT_DIR 作为基准路径 ---
    dir_path = SCRIPT_DIR / "api" / date
    full_path = dir_path / f"{hour}.json"
    ensure_dir(dir_path)

    unique_words = {word.title: word for word in words}.values()
    sorted_words = sorted(list(unique_words), key=lambda x: x.hot, reverse=True)

    await write_file(full_path, json.dumps([word.to_dict() for word in sorted_words], ensure_ascii=False, indent=2))


async def create_readme(words: List[WeiboItem]):
    try:
        content = await read_file(README_PATH)
        import re
        new_content = re.sub(r"[\s\S]*", create_list(words), content)
        await write_file(README_PATH, new_content)
    except Exception as e:
        logging.error("更新 README 失败", exc_info=True)


async def save_day_json(words: List[WeiboItem]):
    date = datetime.now().strftime('%Y-%m-%d')
    # --- 修改点 4: 使用 SCRIPT_DIR 作为基准路径 ---
    dir_path = SCRIPT_DIR / "api" / date
    full_path = dir_path / "summary.json"
    ensure_dir(dir_path)

    words_already_downloaded = []
    content = await read_file(full_path)
    if content:
        words_already_downloaded = [WeiboItem(**item) for item in json.loads(content)]

    word_map = {word.title: word for word in words_already_downloaded}
    for word in words:
        if word.title in word_map:
            old_word = word_map[word.title]
            old_word.hot = max(word.hot, old_word.hot)
        else:
            word_map[word.title] = word

    updated_words = sorted(list(word_map.values()), key=lambda x: x.hot, reverse=True)

    await write_file(full_path, json.dumps([word.to_dict() for word in updated_words], ensure_ascii=False, indent=2))

    # --- 修改点 5: 使用 SCRIPT_DIR 作为基准路径 ---
    archive_path = SCRIPT_DIR / "archives" / f"{date}.md"
    archive_data = create_archive(updated_words, date)
    await write_file(archive_path, archive_data)
    await create_readme(updated_words)


async def bootstrap():
    # ... (这部分代码无需修改)
    retry_count = 0
    while retry_count < MAX_RETRIES:
        try:
            data = await fetch_trending_data_with_playwright()
            if data and data.get("ok") == 1:
                items = data.get("data", {}).get("cards", [])[0].get("card_group", [])
                if items:
                    tasks = []
                    for item in items:
                        async def process_item(item_data):
                            detail = await fetch_trending_detail(item_data.get('desc', ''))
                            return WeiboItem(
                                title=item_data.get('desc'),
                                category=detail.get('category') or item_data.get('category'),
                                description=detail.get('desc') or item_data.get('description'),
                                url=item_data.get('scheme'),
                                hot=extract_numbers(item_data.get('desc_extr')),
                                ads=bool(item_data.get('promotion')),
                                read_count=detail.get('read_count'),
                                discuss_count=detail.get('discuss_count'),
                                origin=detail.get('origin'),
                            )

                        tasks.append(process_item(item))

                    words = await asyncio.gather(*tasks)
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