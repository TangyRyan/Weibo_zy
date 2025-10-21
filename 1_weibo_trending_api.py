import json
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, jsonify
import logging

# --- 配置 ---
# 配置日志，方便调试
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 初始化 Flask 应用
app = Flask(__name__)

# 数据文件所在的根目录，相对于 1_weibo_trending_api.py 的位置
API_DATA_PATH = Path("./weibo/api")


def find_latest_json_file() -> Path | None:
    """
    智能查找最新的 hourly JSON 文件。
    它会先搜索今天的目录，如果找不到，再搜索昨天的目录。
    返回最新的数据文件的路径。
    """
    now = datetime.now()
    today_dir = API_DATA_PATH / now.strftime('%Y-%m-%d')
    yesterday = now - timedelta(days=1)
    yesterday_dir = API_DATA_PATH / yesterday.strftime('%Y-%m-%d')

    latest_file = None
    latest_timestamp = 0

    # 遍历今天和昨天的目录
    for directory in [today_dir, yesterday_dir]:
        if not directory.exists():
            continue

        # 查找所有数字命名的json文件（排除summary.json）
        for file_path in directory.glob('*.json'):
            if file_path.stem.isdigit():
                # 获取文件的修改时间
                timestamp = file_path.stat().st_mtime
                if timestamp > latest_timestamp:
                    latest_timestamp = timestamp
                    latest_file = file_path

    return latest_file


@app.route('/api/latest', methods=['GET'])
def get_latest_hot_list():
    """
    提供最新的微博热榜数据 API。
    """
    logging.info("收到 /api/latest 请求")

    try:
        latest_file = find_latest_json_file()

        if latest_file and latest_file.exists() and latest_file.stat().st_size > 0:
            logging.info(f"找到最新的数据文件: {latest_file}")
            with open(latest_file, 'r', encoding='utf-8') as f:
                data_to_serve = json.load(f)

            # 成功返回
            return jsonify({
                "success": True,
                # 使用文件的修改时间作为更新时间，更准确
                "update_time": datetime.fromtimestamp(latest_file.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                "data": data_to_serve
            })
        else:
            # 如果找不到任何有效的数据文件
            logging.warning("未找到任何有效的数据文件。")
            return jsonify({
                "success": False,
                "message": "暂无热榜数据，请确认爬虫脚本是否已成功运行。"
            }), 404

    except Exception as e:
        logging.error(f"处理请求时发生服务器内部错误: {e}", exc_info=True)
        return jsonify({"success": False, "message": f"服务器内部错误: {str(e)}"}), 500


if __name__ == '__main__':
    # host='0.0.0.0' 允许局域网内的其他设备访问
    app.run(host='0.0.0.0', port=5000, debug=True)