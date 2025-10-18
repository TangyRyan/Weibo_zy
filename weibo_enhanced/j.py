import json
import asyncio
import os
from topic_detail import get_top_20_hot_posts  # 从 topic_detail.py 导入核心函数

# --- 配置 ---

# 1. 输入文件路径
SUMMARY_FILE_PATH = 'api/2025-10-18/summary.json'

# 2. 输出文件夹路径 (脚本会自动创建这个文件夹)
OUTPUT_DIR = 'hot_posts_details'


async def main():
    """
    主执行函数
    """
    # --- 步骤 1: 读取 summary.json 文件并提取所有标题 ---
    print(f"正在从 '{SUMMARY_FILE_PATH}' 读取热搜标题...")

    try:
        with open(SUMMARY_FILE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"错误：找不到文件！请检查路径 '{SUMMARY_FILE_PATH}' 是否正确。")
        return
    except json.JSONDecodeError:
        print(f"错误：文件 '{SUMMARY_FILE_PATH}' 不是有效的JSON格式。")
        return

    # 提取所有标题，并过滤掉空标题
    titles = [item.get('title') for item in data if item.get('title')]

    if not titles:
        print("未能从文件中提取到任何标题。")
        return

    print(f"成功提取 {len(titles)} 个标题，准备开始获取热门微博...")

    # 确保输出目录存在
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # --- 步骤 2: 遍历标题，调用异步函数获取数据 ---
    for index, title in enumerate(titles):
        print(f"\n[{index + 1}/{len(titles)}] --- 正在为话题 '{title}' 获取热门微博 ---")

        # 调用从 topic_detail.py 导入的异步函数
        # 使用 await 来等待异步操作完成
        top_posts = await get_top_20_hot_posts(title)

        # --- 步骤 3: 处理返回的数据 ---
        if top_posts:
            print(f"成功获取 {len(top_posts)} 条微博。")

            # 将每个 post 对象转换为字典 (根据您 topic_detail.py 中的示例)
            posts_as_dicts = [post.to_dict() for post in top_posts]

            # 创建一个安全的文件名，防止标题中包含特殊字符
            safe_filename = "".join(x for x in title if x.isalnum()) + ".json"
            output_path = os.path.join(OUTPUT_DIR, safe_filename)

            # 将结果保存为独立的 JSON 文件
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(posts_as_dicts, f, ensure_ascii=False, indent=2)

            print(f"结果已保存至: {output_path}")

        else:
            print(f"未能为话题 '{title}' 获取到任何微博内容。")

        # 增加一个短暂的延时，避免请求过于频繁导致被封禁
        print("...等待1秒...")
        await asyncio.sleep(1)


if __name__ == '__main__':
    # 运行主异步函数
    asyncio.run(main())