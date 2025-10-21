#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
topic_detail.py - 最终版（支持新版 woo-picture，图片+视频共存、图片转 large 并补全 https）
(v9.2: 修复图片 403 Forbidden，wx 替换为 ww，并扩展 /large/ 替换列表)
"""

import asyncio
import json
import logging
from typing import List, Optional
from urllib.parse import quote, urljoin
from pathlib import Path
from datetime import datetime, timedelta
import re

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, BrowserContext, TimeoutError

# --- 配置 ---
POSTS_SEARCH_URL = "https://s.weibo.com/weibo?q=%23{}%23&xsort=hot&suball=1&tw=hotweibo"
MAX_POSTS_TO_FETCH = 20
MAX_SEARCH_PAGES = 2  # number of result pages to fetch via ?page=
SCROLL_COUNT = 2  # base scroll count per page
SCROLL_DELAY_MS = 2000  # delay between scrolls in ms
COOKIES_PATH = Path("./weibo_cookies.json")
AUTH_STATE_PATH = Path("./auth_state.json")
HEADLESS = True  # 可改为 False 便于调试
LOGIN_HEADLESS = False  # 登录流程默认弹出浏览器窗口
LOGIN_URL = ("https://passport.weibo.com/sso/signin?entry=miniblog&source=miniblog&disp=popup"
             "&url=https%3A%2F%2Fweibo.com%2Fnewlogin%3Ftabtype%3Dweibo%26gid%3D102803%26openLoginLayer%3D0"
             "%26url%3Dhttps%253A%252F%252Fweibo.com%252F&from=weibopro")
LOGIN_SUCCESS_SELECTOR = "text=首页"
LOGIN_TIMEOUT = 120000  # ms


def _load_cookies_from_file() -> List[dict]:
    if not COOKIES_PATH.exists():
        return []
    try:
        with open(COOKIES_PATH, 'r', encoding='utf-8') as f:
            cookies = json.load(f)
        if isinstance(cookies, list):
            return cookies
        logging.warning("Cookies 文件格式异常，期望为列表。")
    except Exception as exc:
        logging.warning(f"读取 Cookies 文件失败: {exc}")
    return []


def _persist_login_state(storage_state: dict) -> List[dict]:
    cookies = storage_state.get("cookies", []) if isinstance(storage_state, dict) else []
    try:
        AUTH_STATE_PATH.write_text(json.dumps(storage_state, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception as exc:
        logging.warning(f"写入 auth_state.json 失败: {exc}")
    try:
        COOKIES_PATH.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding='utf-8')
        logging.info("已更新 weibo_cookies.json 文件。")
    except Exception as exc:
        logging.warning(f"写入 weibo_cookies.json 失败: {exc}")
    return cookies


async def _login_and_update_cookies(playwright) -> Optional[List[dict]]:
    """
    触发手动登录流程，登录成功后更新本地 auth_state.json 和 weibo_cookies.json。
    """
    browser = await playwright.chromium.launch(headless=LOGIN_HEADLESS)

    context_kwargs = {}
    if AUTH_STATE_PATH.exists():
        context_kwargs["storage_state"] = str(AUTH_STATE_PATH)

    context = await browser.new_context(**context_kwargs)
    page = await context.new_page()

    # 优先尝试使用已保存的状态直接进入首页
    if context_kwargs:
        try:
            await page.goto("https://weibo.com", wait_until='load', timeout=60000)
            await page.wait_for_selector(LOGIN_SUCCESS_SELECTOR, timeout=15000)
            logging.info("已通过保存的登录状态自动登录。")
            storage = await context.storage_state()
            cookies = _persist_login_state(storage)
            await context.close()
            await browser.close()
            return cookies
        except Exception:
            logging.info("保存的登录状态已失效，准备进行手动登录。")
            await context.close()
            context = await browser.new_context()
            page = await context.new_page()


    logging.info("请在打开的浏览器窗口中完成微博登录...")
    await page.goto(LOGIN_URL, wait_until='load', timeout=60000)
    try:
        await page.wait_for_selector(LOGIN_SUCCESS_SELECTOR, timeout=LOGIN_TIMEOUT)
        logging.info("登录成功，正在更新本地 Cookie。")
    except TimeoutError:
        logging.error("登录超时，未能更新 Cookie。")
        await context.close()
        await browser.close()
        return None

    storage = await context.storage_state()
    cookies = _persist_login_state(storage)

    await context.close()
    await browser.close()
    return cookies

# --- 日志 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class WeiboPost:
    def __init__(self, author: str, content: str, timestamp: str, source: str,
                 forwards_count: int, comments_count: int, likes_count: int,
                 image_links: List[str], video_link: str):
        self.author = author
        self.content = content
        self.timestamp = timestamp
        self.source = source
        self.forwards_count = forwards_count
        self.comments_count = comments_count
        self.likes_count = likes_count
        self.image_links = image_links
        self.video_link = video_link

    def to_dict(self):
        # A 顺序
        return {
            "author": self.author,
            "content": self.content,
            "timestamp": self.timestamp,
            "source": self.source,
            "forwards_count": self.forwards_count,
            "comments_count": self.comments_count,
            "likes_count": self.likes_count,
            "image_links": self.image_links,
            "video_link": self.video_link,
        }

    def __repr__(self):
        return f"WeiboPost(author='{self.author}', images={len(self.image_links)}, video={'Yes' if self.video_link else 'No'})"


# ---------------- 辅助函数 ----------------
def _convert_to_number(val_str: Optional[str]) -> int:
    try:
        if not val_str:
            return 0
        s = val_str.strip()
        s = re.sub(r'[^\d\.万亿,]', '', s)
        if not s:
            return 0
        if '亿' in s:
            return int(float(s.replace('亿', '')) * 100000000)
        if '万' in s:
            return int(float(s.replace('万', '')) * 10000)
        s = s.replace(',', '')
        return int(float(s))
    except Exception:
        return 0


def _pad_time_part(time_part: str) -> str:
    """把各种时间片段补成 02 位格式 'HH:MM'"""
    try:
        parts = time_part.strip().split(':')
        if len(parts) != 2:
            return "00:00"
        h = int(parts[0])
        m = int(parts[1])
        return f"{h:02d}:{m:02d}"
    except Exception:
        return "00:00"


def normalize_time(raw: str) -> str:
    """
    统一返回 YYYY-MM-DD HH:mm（T1）
    支持：刚刚 / x分钟前 / x小时前 / 今天 HH:mm / 昨天 HH:mm / M月D日 HH:mm / YYYY-MM-DD HH:mm
    """
    if not raw:
        return ""

    raw = raw.strip()
    raw = raw.replace("发布于", "").strip()
    now = datetime.now()

    if raw == "刚刚":
        return now.strftime("%Y-%m-%d %H:%M")

    m = re.match(r'^\s*(\d+)\s*分钟前', raw)
    if m:
        mins = int(m.group(1))
        dt = now - timedelta(minutes=mins)
        return dt.strftime("%Y-%m-%d %H:%M")

    m = re.match(r'^\s*(\d+)\s*小时前', raw)
    if m:
        hrs = int(m.group(1))
        dt = now - timedelta(hours=hrs)
        return dt.strftime("%Y-%m-%d %H:%M")

    m = re.match(r'^(?:今天)\s*(\d{1,2}:\d{1,2})$', raw)
    if m:
        tp = _pad_time_part(m.group(1))
        return now.strftime(f"%Y-%m-%d {tp}")

    m = re.match(r'^(?:昨天)\s*(\d{1,2}:\d{1,2})$', raw)
    if m:
        tp = _pad_time_part(m.group(1))
        dt = now - timedelta(days=1)
        return dt.strftime(f"%Y-%m-%d {tp}")

    m = re.match(r'^\s*(\d{1,2})月(\d{1,2})日(?:\s*(\d{1,2}:\d{1,2}))?\s*$', raw)
    if m:
        month = int(m.group(1))
        day = int(m.group(2))
        time_part = m.group(3) or "00:00"
        time_part = _pad_time_part(time_part)
        year = now.year
        try:
            dt = datetime.strptime(f"{year}-{month:02d}-{day:02d} {time_part}", "%Y-%m-%d %H:%M")
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return raw

    m = re.match(r'^\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:\s+(\d{1,2}:\d{1,2}))?\s*$', raw)
    if m:
        year = int(m.group(1))
        month = int(m.group(2))
        day = int(m.group(3))
        time_part = m.group(4) or "00:00"
        time_part = _pad_time_part(time_part)
        try:
            dt = datetime.strptime(f"{year}-{month:02d}-{day:02d} {time_part}", "%Y-%m-%d %H:%M")
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return raw

    # 兜底：查找 M月D日 HH:mm
    m = re.search(r'(\d{1,2})月(\d{1,2})日.*?(\d{1,2}:\d{1,2})', raw)
    if m:
        month = int(m.group(1))
        day = int(m.group(2))
        tp = _pad_time_part(m.group(3))
        year = now.year
        try:
            dt = datetime.strptime(f"{year}-{month:02d}-{day:02d} {tp}", "%Y-%m-%d %H:%M")
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return raw

    return raw


def _is_text_node_likely_time(node) -> bool:
    """
    判断文本节点是否在可能含时间/元信息的区域（避免正文误判）
    """
    try:
        el = node.parent
        depth = 0
        while el is not None and depth < 6:
            tag = getattr(el, 'name', '')
            classes = " ".join(el.get('class') or []) if hasattr(el, 'get') else ''
            id_attr = el.get('id') if hasattr(el, 'get') else ''
            combined = f"{tag} {classes} {id_attr}".lower()
            if tag and tag.lower() in ('time',):
                return True
            if any(k in combined for k in
                   ('from', 'wb_from', 'time', 'publish', 'publish_time', 'date', 'meta', 'info')):
                return True
            el = el.parent
            depth += 1
    except Exception:
        pass
    return False


# ---------------- 详情页抓取 ----------------
async def get_post_details(context: BrowserContext, detail_url: str, post_data: dict) -> WeiboPost:
    """
    访问详情页，补充 timestamp/source/image_links/video_link 等
    detail_url 也作为 video_link 返回（V1）
    """
    page = await context.new_page()
    try:
        logging.info(f"正在访问详情页: {detail_url}")
        await page.goto(detail_url, wait_until='load', timeout=30000)

        # 尝试等待常见节点
        try:
            await page.wait_for_selector('div.from, .WB_from, .woo-picture-slot, .picture', timeout=8000)
        except Exception:
            logging.debug("详情页未找到常用选择器，继续解析页面内容。")

        html_content = await page.content()
        soup = BeautifulSoup(html_content, 'html.parser')

        # ---- 时间与来源 ----
        timestamp_final = ""
        source_final = ""
        from_node = soup.select_one('div.from') or soup.select_one('.WB_from') or soup.select_one('.info .from')
        if from_node:
            a_tags = from_node.select('a')
            if a_tags:
                raw_time = a_tags[0].get_text(strip=True)
                timestamp_final = normalize_time(raw_time)
                if len(a_tags) > 1:
                    source_final = a_tags[1].get_text(strip=True)
                else:
                    t = from_node.get_text(separator=' ', strip=True)
                    t = t.replace(raw_time, '').strip()
                    if t:
                        source_final = t

        # meta / time 标签补充
        if not timestamp_final or re.search(r'[今昨天分钟前小时]', timestamp_final):
            meta_time = soup.find('meta', {'name': 'weibo:publish_time'})
            if meta_time and meta_time.get('content'):
                timestamp_final = normalize_time(meta_time.get('content'))

        if not timestamp_final:
            time_tag = soup.find('time')
            if time_tag and time_tag.get('datetime'):
                timestamp_final = normalize_time(time_tag.get('datetime'))
            elif time_tag:
                ts_txt = time_tag.get_text(strip=True)
                if ts_txt:
                    timestamp_final = normalize_time(ts_txt)

        # 兜底从靠近元信息的短文本节点找时间，避免正文误判
        if not timestamp_final:
            candidate = ""
            text_nodes = soup.find_all(string=True)
            for t in text_nodes:
                if not isinstance(t, str):
                    continue
                txt = t.strip()
                if not txt or len(txt) > 60:
                    continue
                if re.search(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', txt) or re.search(r'\d{1,2}月\d{1,2}日', txt):
                    if _is_text_node_likely_time(t):
                        candidate = txt
                        break
            if candidate:
                timestamp_final = normalize_time(candidate)

        # 最后兜底使用列表页时间
        if not timestamp_final:
            list_time = post_data.get('timestamp', '') or ""
            timestamp_final = normalize_time(list_time) if list_time else ""

        post_data['timestamp'] = timestamp_final or ""
        post_data['source'] = source_final or ""

        # ---- 图片抓取（始终执行，不与视频互斥） ----
        image_links: List[str] = []
        # 选择器集合：覆盖新版 woo-picture、picture、旧版 media-piclist、WB_media_a 等
        pic_selectors = [
            'div.woo-picture-slot img',
            'div.woo-picture-main img',
            'div.picture img',
            'div.picture-box_row_3DIwo img',
            'div.picture_inlineNum3_3P7K1 img',
            'div.media-piclist ul li img',
            'div.WB_media_a img',
            'img[node-type="feed_list_media_img"]',
            'img[action-type="feed_list_media_img"]',
            'div.pic_box img',
            'div.photo_list img',
        ]

        found_nodes = []
        for sel in pic_selectors:
            nodes = soup.select(sel)
            if nodes:
                # extend while preserving order; avoid duplicates
                for n in nodes:
                    if n not in found_nodes:
                        found_nodes.append(n)

        for img in found_nodes:
            src = img.get('src') or img.get('data-src') or img.get('data-original') or img.get('data-url')
            if not src:
                continue

            # --- 【!!! 核心修改点 (v9.2)：扩展替换列表 !!!】 ---
            # 1. 转为 large 高质量（P1）
            large_src = src.replace('/orj360/', '/large/').replace('/orj180/', '/large/') \
                .replace('/thumb150/', '/large/').replace('/square/', '/large/') \
                .replace('/bmiddle/', '/large/').replace('/wap360/', '/large/') \
                .replace('/orj480/', '/large/').replace('/mw690/', '/large/') \
                .replace('/mw1024/', '/large/').replace('/mw2000/', '/large/')  # <-- 新增

            # 2. 补全协议
            if large_src.startswith('//'):
                large_src = 'https:' + large_src

            # 3. 将 wx (微信) 域名替换为 ww (微博) 域名 (解决 403 Forbidden)
            large_src = large_src.replace('://wx1.sinaimg.cn/', '://ww1.sinaimg.cn/') \
                .replace('://wx2.sinaimg.cn/', '://ww2.sinaimg.cn/') \
                .replace('://wx3.sinaimg.cn/', '://ww3.sinaimg.cn/') \
                .replace('://wx4.sinaimg.cn/', '://ww4.sinaimg.cn/')

            # 4. 补全相对路径
            if large_src.startswith('/'):
                large_src = urljoin('https://weibo.com', large_src)

            if large_src not in image_links:
                image_links.append(large_src)

        post_data['image_links'] = image_links

        # ---- video_link (V1：原帖 detail_url)，优先查找 /tv/show/ 播放页 ----
        video_page_link = detail_url
        try:
            for a in soup.find_all('a', href=True):
                href = a.get('href')
                if href and '/tv/show/' in href:
                    video_page_link = href if href.startswith('http') else urljoin('https://weibo.com', href)
                    break
        except Exception:
            pass

        post_data['video_link'] = video_page_link or ""

        # ---- content 清理：若有视频则删除 'Lxxx的微博视频'（B） ----
        content = post_data.get('content', '') or ""
        if post_data['video_link']:
            content = re.sub(r'L[^\s\u200b]*的微博视频', '', content)
            content = re.sub(r'\s{2,}', ' ', content).strip()
            post_data['content'] = content

        # 返回 WeiboPost 对象
        return WeiboPost(
            author=post_data.get('author', '') or '',
            content=post_data.get('content', '') or '',
            timestamp=post_data.get('timestamp', '') or '',
            source=post_data.get('source', '') or '',
            forwards_count=int(post_data.get('forwards_count', 0) or 0),
            comments_count=int(post_data.get('comments_count', 0) or 0),
            likes_count=int(post_data.get('likes_count', 0) or 0),
            image_links=post_data.get('image_links', []) or [],
            video_link=post_data.get('video_link', '') or ""
        )

    except Exception as e:
        logging.warning(f"访问详情页 {detail_url} 失败: {e}，将返回列表页已有数据（尽量完善）。")
        # 失败时返回列表页数据，normalize timestamp，并按 B 清理 content（若 detail_url 存在）
        list_time = post_data.get('timestamp', '') or ""
        content = post_data.get('content', '') or ""
        if detail_url:
            content = re.sub(r'L[^\s\u200b]*的微博视频', '', content)
            content = re.sub(r'\s{2,}', ' ', content).strip()
        return WeiboPost(
            author=post_data.get('author', '') or '',
            content=content,
            timestamp=normalize_time(list_time) if list_time else "",
            source=post_data.get('source', '') or '',
            forwards_count=int(post_data.get('forwards_count', 0) or 0),
            comments_count=int(post_data.get('comments_count', 0) or 0),
            likes_count=int(post_data.get('likes_count', 0) or 0),
            image_links=post_data.get('image_links', []) or [],
            video_link=detail_url or ""
        )
    finally:
        try:
            await page.close()
        except Exception:
            pass


# ---------------- 主流程 ----------------
async def get_top_20_hot_posts(topic_title: str) -> List[WeiboPost]:
    url = POSTS_SEARCH_URL.format(quote(topic_title.replace("#", "")))
    logging.info(f"开始抓取话题 '{topic_title}' 的热门微博...")

    cookies_for_context = _load_cookies_from_file()

    async with async_playwright() as p:
        browser = None
        context = None
        page = None

        attempt = 0
        while attempt < 2:
            attempt += 1
            browser_context_args = {
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36'
            }
            if cookies_for_context:
                browser_context_args['storage_state'] = {"cookies": cookies_for_context}
                logging.info("已加载本地 Cookies，准备发起请求。")
            else:
                logging.info("未找到可用 Cookies，将以未登录状态尝试访问。")

            browser = await p.chromium.launch(headless=HEADLESS)
            context = await browser.new_context(**browser_context_args)
            page = await context.new_page()

            try:
                await page.goto(url, wait_until='load', timeout=60000)
                await page.wait_for_selector('div.card-wrap', timeout=10000)
                break  # 成功加载
            except Exception:
                await browser.close()
                browser = None
                context = None
                page = None

                if attempt >= 2:
                    logging.warning("连续两次访问失败，可能仍需登录。")
                    return []

                logging.info("疑似 Cookies 失效，开始调用登录流程刷新 Cookie。")
                cookies_for_context = await _login_and_update_cookies(p)
                if not cookies_for_context:
                    logging.error("登录失败，无法继续抓取。")
                    return []
                logging.info("登录成功，已刷新 Cookie，准备重新尝试访问。")
                continue

        try:
            base_search_url = url
            page_urls = [base_search_url] + [
                f"{base_search_url}&page={page_idx}"
                for page_idx in range(2, MAX_SEARCH_PAGES + 1)
            ]

            initial_posts_data: List[dict] = []
            seen_detail_urls = set()

            async def collect_list_page(page_obj, page_index: int) -> bool:
                if SCROLL_COUNT > 0:
                    for _ in range(SCROLL_COUNT):
                        await page_obj.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await page_obj.wait_for_timeout(SCROLL_DELAY_MS)

                html_content_local = await page_obj.content()
                soup_local = BeautifulSoup(html_content_local, 'html.parser')
                post_cards_local = soup_local.select('div.card-wrap')
                logging.info(f"Search page {page_index} returned {len(post_cards_local)} cards.")

                for card in post_cards_local:
                    try:
                        if not card.select_one('p.txt'):
                            continue

                        author = card.select_one('.content .info .name').get_text(strip=True) if card.select_one(
                            '.content .info .name') else ''
                        content = card.select_one('p.txt').get_text(strip=True) or ''

                        detail_url = ""
                        timestamp = ""
                        from_node = card.select_one('.content .from')
                        if from_node:
                            timestamp_tag = from_node.select_one('a')
                            if timestamp_tag:
                                href = timestamp_tag.get('href', '')
                                if href.startswith('//'):
                                    detail_url = 'https:' + href
                                elif href.startswith('http'):
                                    detail_url = href
                                else:
                                    detail_url = urljoin('https://weibo.com', href)
                                timestamp = timestamp_tag.get_text(strip=True)

                        if not detail_url or detail_url in seen_detail_urls:
                            continue

                        actions = card.select('.card-act ul li a')
                        forwards = _convert_to_number(actions[0].get_text(strip=True)) if len(actions) > 0 else 0
                        comments = _convert_to_number(actions[1].get_text(strip=True)) if len(actions) > 1 else 0
                        likes = _convert_to_number(actions[2].get_text(strip=True)) if len(actions) > 2 else 0

                        seen_detail_urls.add(detail_url)
                        initial_posts_data.append({
                            "author": author,
                            "content": content,
                            "timestamp": timestamp,
                            "source": "",
                            "forwards_count": forwards,
                            "comments_count": comments,
                            "likes_count": likes,
                            "image_links": [],
                            "video_link": "",
                            "detail_url": detail_url
                        })

                        if len(initial_posts_data) >= MAX_POSTS_TO_FETCH:
                            return True
                    except Exception:
                        continue
                return False

            # process first search page (already loaded)
            await collect_list_page(page, 1)

            # fetch additional pages if needed
            next_page_index = 2
            while len(initial_posts_data) < MAX_POSTS_TO_FETCH and next_page_index <= MAX_SEARCH_PAGES:
                page_url = page_urls[next_page_index - 1]
                logging.info(f"Fetching additional search page {next_page_index}: {page_url}")
                extra_page = await context.new_page()
                page_completed = False
                try:
                    await extra_page.goto(page_url, wait_until='load', timeout=60000)
                    await extra_page.wait_for_selector('div.card-wrap', timeout=10000)
                    page_completed = await collect_list_page(extra_page, next_page_index)
                    if page_completed:
                        logging.info("Reached target post count from search pages.")
                except Exception as exc:
                    logging.warning(f"Failed to load search page {next_page_index}: {exc}")
                finally:
                    try:
                        await extra_page.close()
                    except Exception:
                        pass
                if page_completed:
                    break
                next_page_index += 1

            try:
                await page.close()
            except Exception:
                pass

            logging.info(f"列表页抓取完成：共 {len(initial_posts_data)} 条，开始抓取详情页...")
            tasks = []
            for post_data in initial_posts_data:
                detail = post_data.pop("detail_url")
                tasks.append(get_post_details(context, detail, post_data))

            posts = await asyncio.gather(*tasks)
            posts = [p for p in posts if p is not None]

        except Exception as e:
            logging.error(f"抓取话题 '{topic_title}' 时发生错误", exc_info=True)
            posts = []
        finally:
            try:
                if browser:
                    await browser.close()
            except Exception:
                pass

    logging.info(f"成功抓取到 {len(posts)} 条关于 '{topic_title}' 的微博详情")
    return posts


# ---------------- 入口 / 测试 ----------------
if __name__ == '__main__':
    async def main():
        test_topic = "卢浮宫劫案可能是粉红豹所为"
        print(f"正在测试：获取话题 '{test_topic}' 的前{MAX_POSTS_TO_FETCH} 条热门微博...")
        top_posts = await get_top_20_hot_posts(test_topic)

        if top_posts:
            print(f"\n成功获取 {len(top_posts)} 条微博：")
            posts_as_dicts = [post.to_dict() for post in top_posts]
            print(json.dumps(posts_as_dicts, ensure_ascii=False, indent=2))
        else:
            print("未能获取到任何微博内容。")


    asyncio.run(main())
