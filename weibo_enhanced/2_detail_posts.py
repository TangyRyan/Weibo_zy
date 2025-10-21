import json
import asyncio
import os
import logging
from topic_detail import get_top_20_hot_posts  # 从 topic_detail.py 导入核心函数

# --- 自动路径配置 (修复路径问题) ---
# 1. 获取当前脚本 (2_detail_posts.py) 所在的目录
#    例如: C:\Users\...\PyCharmMiscProject\weibo_enhanced
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 2. 获取项目根目录 (weibo_enhanced 的上一级, 即 PyCharmMiscProject)
#    例如: C:\Users\...\PyCharmMiscProject
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))

# --- 日志配置 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 配置 ---

# 1. API输入根目录 (自动定位到 'PyCharmMiscProject/weibo/api')
#    【!!! 这是唯一的修改点 !!!】
INPUT_API_DIR = os.path.join(PROJECT_ROOT, 'weibo', 'api')

# 2. 输出根目录 (自动定位到 'PyCharmMiscProject/weibo_enhanced/hot_posts_details')
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'hot_posts_details')

# 3. 异步请求之间的延迟（秒），强烈建议保留，防止IP被封
DELAY_PER_TOPIC = 1.5


async def process_hourly_file(input_path: str, output_path: str):
    """
    处理单个小时的 .json 文件
    """
    logging.info(f"  正在读取: {input_path}")
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            topics_data = json.load(f)
    except FileNotFoundError:
        logging.error(f"    错误：找不到文件 {input_path}")
        return
    except json.JSONDecodeError:
        logging.error(f"    错误：文件 {input_path} 不是有效的JSON。")
        return

    if not isinstance(topics_data, list):
        logging.warning(f"    警告：文件 {input_path} 的内容不是一个列表。跳过。")
        return

    enriched_data = []  # 存放添加了热门贴文的新数据
    total_topics = len(topics_data)

    logging.info(f"    共找到 {total_topics} 个话题。")

    for index, topic_item in enumerate(topics_data):
        title = topic_item.get('title')
        if not title:
            logging.warning("    发现一个条目没有 'title'，已跳过。")
            enriched_data.append(topic_item)  # 即使没有标题也保留原条目
            continue

        logging.info(f"    [{index + 1}/{total_topics}] 正在获取 '{title}' 的热门微博...")

        try:
            top_posts = await get_top_20_hot_posts(title)

            if top_posts:
                topic_item['top_posts'] = [post.to_dict() for post in top_posts]
                logging.info(f"      > 成功获取 {len(topic_item['top_posts'])} 条微博。")
            else:
                topic_item['top_posts'] = []
                logging.warning(f"      > 未能为 '{title}' 获取到微博。")

            enriched_data.append(topic_item)

            logging.info(f"    ...等待{DELAY_PER_TOPIC}秒...")
            await asyncio.sleep(DELAY_PER_TOPIC)

        except Exception as e:
            logging.error(f"    处理话题 '{title}' 时发生严重错误: {e}")
            topic_item['top_posts'] = []
            enriched_data.append(topic_item)
            continue

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(enriched_data, f, ensure_ascii=False, indent=2)
        logging.info(f"  [成功] 结果已保存至: {output_path}\n")
    except IOError as e:
        logging.error(f"  [错误] 无法写入文件 {output_path}。原因: {e}\n")


async def main():
    """
    主执行函数 (实时逻辑)
    """
    logging.info(f"--- 实时处理任务启动 ---")
    logging.info(f"扫描API输入目录: {INPUT_API_DIR}")
    logging.info(f"详情输出目录: {OUTPUT_DIR}")

    # --- 步骤 1: 自动查找最新的日期文件夹 ---
    try:
        # 检查 API 目录是否存在
        if not os.path.isdir(INPUT_API_DIR):
            logging.critical(f"错误：找不到API目录！请检查路径 {INPUT_API_DIR}")
            return

        date_folders = [d for d in os.listdir(INPUT_API_DIR) if os.path.isdir(os.path.join(INPUT_API_DIR, d))]
        if not date_folders:
            logging.critical(f"错误：在 {INPUT_API_DIR} 中未找到任何日期文件夹。")
            return

        date_folders.sort()
        latest_day_folder = date_folders[-1]
        target_input_dir = os.path.join(INPUT_API_DIR, latest_day_folder)

    except Exception as e:
        logging.critical(f"扫描日期文件夹时出错: {e}")
        return

    logging.info(f"--- 自动定位到最新日期: {latest_day_folder} ---")

    # --- 步骤 2: 自动查找最新的小时JSON文件 ---
    try:
        hourly_files = [
            f for f in os.listdir(target_input_dir)
            if f.endswith('.json') and 'summary.json' not in f
        ]
        if not hourly_files:
            logging.warning(f"警告：在 '{target_input_dir}' 中没有找到任何小时数据。")
            return

        hourly_files.sort()
        latest_hourly_file = hourly_files[-1]

    except FileNotFoundError:
        logging.critical(f"错误：无法访问目录 {target_input_dir}。")
        return

    logging.info(f"--- 自动定位到最新文件: {latest_hourly_file} ---")

    # --- 步骤 3: 处理这一个最新文件 ---
    input_file_path = os.path.join(target_input_dir, latest_hourly_file)

    target_output_dir = os.path.join(OUTPUT_DIR, latest_day_folder)
    output_file_path = os.path.join(target_output_dir, latest_hourly_file)

    logging.info(f"--- 开始处理文件: {input_file_path} ---")
    await process_hourly_file(input_file_path, output_file_path)

    logging.info(f"--- 最新文件处理完毕 ---")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        logging.critical(f"脚本执行时发生未捕获的严重错误: {e}")