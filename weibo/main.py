import asyncio
import json
import logging
import aiofiles
import httpx
import subprocess
import sys
from bs4 import BeautifulSoup
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from asyncio import Semaphore
from playwright.async_api import async_playwright

# -------------------- 基础配置 --------------------
BASE_DIR = Path(__file__).parent
API_DIR = BASE_DIR / "api"
ARCHIVE_DIR = BASE_DIR / "archives"
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "run.log"

TRENDING_URL = "https://m.weibo.cn/api/container/getIndex?containerid=106003type%3D25%26t%3D3%26disable_hot%3D1%26filter_type%3Drealtimehot"
DETAIL_URL = "https://m.s.weibo.com/topic/detail?q=%s"

MAX_RETRIES = 3
CONCURRENCY_LIMIT = 5           # 防止封号
TEN_MINUTES_SECONDS = 600       # 失败后延迟重试时间（10分钟）

# -------------------- 日志系统 --------------------
def setup_logging():
    LOG_DIR.mkdir(exist_ok=True)
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # 避免重复添加 handler（任务计划程序反复调用时可能复用进程）
    if not logger.handlers:
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setLevel(logging.INFO)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)

        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

# -------------------- 工具函数 --------------------
def to_number(val: str) -> int:
    if not val:
        return 0
    val = val.strip()
    if "万" in val:
        return int(float(val.replace("万", "")) * 10000)
    if "亿" in val:
        return int(float(val.replace("亿", "")) * 100000000)
    try:
        return int(float(val))
    except ValueError:
        return 0


def extract_digits(s) -> int:
    """从字符串或数字中提取数字部分"""
    if s is None:
        return 0
    if isinstance(s, (int, float)):
        return int(s)
    s = str(s)
    digits = "".join(filter(str.isdigit, s))
    return int(digits) if digits else 0


async def write_json(path: Path, data: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(data, ensure_ascii=False, indent=2))


async def write_text(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(content)


# -------------------- 抓取逻辑 --------------------
async def fetch_trending_data() -> list:
    """
    从微博API获取热搜榜数据
    ⚙️ 使用 Playwright 持久化浏览器上下文，自动复用登录态，无需每次登录。
    首次运行如需登录，登录成功后状态会保存在 BASE_DIR/browser_data/ 中。
    """
    user_data_dir = BASE_DIR / "browser_data"
    user_data_dir.mkdir(exist_ok=True)

    async with async_playwright() as p:
        # ✅ 使用持久化上下文，记住 Cookie / LocalStorage / 会话状态
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=True,
        )
        page = await browser.new_page()

        for attempt in range(MAX_RETRIES):
            try:
                await page.goto(TRENDING_URL, wait_until="networkidle")
                body = await page.text_content("body")
                data = json.loads(body)
                if data.get("ok") == 1:
                    await browser.close()
                    return data["data"]["cards"][0]["card_group"]
            except Exception as e:
                logging.warning(f"获取热搜失败 (第{attempt+1}次): {e}")
                await asyncio.sleep(2)

        await browser.close()
        logging.error("多次重试仍失败，退出。")
        return []


SEM = Semaphore(CONCURRENCY_LIMIT)


async def fetch_topic_detail(title: str) -> dict:
    """抓取详情页内容（非登录接口，httpx直连）"""
    async with SEM:
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    res = await client.get(DETAIL_URL % quote(title))
                soup = BeautifulSoup(res.text, "html.parser")

                category = soup.select_one("#pl_topicband dl > dd")
                desc = soup.select_one("#pl_topicband dl:nth-of-type(2) dd:not(.host-row)")
                nums = [to_number(i.get_text(strip=True)) for i in soup.select("div.g-list-a.data ul li strong")]

                return {
                    "category": category.get_text(strip=True) if category else "",
                    "description": desc.get_text(strip=True) if desc else "",
                    "read_count": nums[0] if len(nums) > 0 else 0,
                    "discuss_count": nums[1] if len(nums) > 1 else 0,
                    "origin": nums[2] if len(nums) > 2 else 0,
                }
            except Exception as e:
                logging.warning(f"详情页获取失败({title}) 重试({attempt+1}/3): {e}")
                await asyncio.sleep(1)
        return {}

# -------------------- 存储逻辑 --------------------
async def save_hourly_data(items: list) -> Path:
    """保存每小时热搜，并返回文件路径"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    hour_str = datetime.now().strftime("%H")
    path = API_DIR / date_str / f"{hour_str}.json"

    await write_json(path, items)
    logging.info(f"保存小时数据成功: {path}")
    return path


async def update_daily_summary(items: list):
    """合并当日数据并生成 Markdown"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    dir_path = API_DIR / date_str
    summary_path = dir_path / "summary.json"

    existing = []
    if summary_path.exists():
        async with aiofiles.open(summary_path, "r", encoding="utf-8") as f:
            try:
                existing = json.loads(await f.read())
            except json.JSONDecodeError:
                pass

    all_items = {i["title"]: i for i in existing + items}.values()
    sorted_items = sorted(all_items, key=lambda x: x["hot"], reverse=True)[:50]

    await write_json(summary_path, list(sorted_items))
    logging.info(f"更新每日汇总成功: {summary_path}")

    md_path = ARCHIVE_DIR / f"{date_str}.md"
    lines = [f"# {date_str} 微博热搜（前50条）\n"]
    for idx, item in enumerate(sorted_items, start=1):
        line = f"{idx}. [{item['title']}]({item['url']})"
        if item.get("category"):
            line += f" `{item['category']}`"
        line += f" - {item['hot']}\n"
        lines.append(line)

    await write_text(md_path, "\n".join(lines))
    logging.info(f"生成 Markdown 归档: {md_path}")


# -------------------- 自动执行 detail_posts --------------------
def run_detail_script_if_ready(latest_json_path: Path):
    """仅在最新JSON存在且非空时执行 2_detail_posts.py"""
    try:
        if not latest_json_path.exists():
            logging.warning("未找到最新的 JSON 文件，跳过执行 2_detail_posts.py。")
            return

        if latest_json_path.stat().st_size == 0:
            logging.warning(f"最新 JSON 文件为空 ({latest_json_path})，跳过执行。")
            return

        script_path = BASE_DIR.parent / "weibo_enhanced" / "2_detail_posts.py"

        if script_path.exists():
            logging.info(f"开始执行 {script_path} ...")
            subprocess.run([sys.executable, str(script_path)], check=True)
            logging.info("2_detail_posts.py 执行完毕 ✅")
        else:
            logging.error(f"未找到 2_detail_posts.py 文件: {script_path}")
    except subprocess.CalledProcessError as e:
        logging.error(f"执行 2_detail_posts.py 出错: {e}")
    except Exception as e:
        logging.error(f"调用 2_detail_posts.py 发生异常: {e}", exc_info=True)


# -------------------- 主流程 --------------------
async def main():
    setup_logging()
    logging.info("任务开始执行...")

    # 第一次拉取
    raw_items = await fetch_trending_data()

    # ★ 若失败：等待 10 分钟再自动重试一次
    if not raw_items:
        logging.error("未获取到热搜数据，10分钟后自动重试一次。")
        await asyncio.sleep(TEN_MINUTES_SECONDS)
        raw_items = await fetch_trending_data()
        if not raw_items:
            logging.error("第二次重试仍失败，任务结束。")
            return

    raw_items = raw_items[:55]
    raw_items = [i for i in raw_items if not i.get("promotion") and extract_digits(i.get("desc_extr")) > 0]

    async def process_item(item):
        detail = await fetch_topic_detail(item.get("desc", ""))
        return {
            "title": item.get("desc"),
            "category": detail.get("category") or item.get("category"),
            "description": detail.get("description") or item.get("description"),
            "url": item.get("scheme"),
            "hot": extract_digits(item.get("desc_extr")),
            "ads": bool(item.get("promotion")),
            "read_count": detail.get("read_count", 0),
            "discuss_count": detail.get("discuss_count", 0),
            "origin": detail.get("origin", 0),
        }

    tasks = [process_item(i) for i in raw_items]
    results = await asyncio.gather(*tasks)

    latest_json_path = await save_hourly_data(results)
    await update_daily_summary(results)

    logging.info("任务完成 ✅")

    # ✅ 仅在JSON生成成功后再执行 detail_posts
    run_detail_script_if_ready(latest_json_path)


# -------------------- 程序入口 --------------------
if __name__ == "__main__":
    asyncio.run(main())
