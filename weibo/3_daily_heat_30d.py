# weibo/daily_heat_30d.py
from pathlib import Path
from datetime import datetime, timedelta
import json
import csv

SCRIPT_DIR = Path(__file__).parent          # weibo/
API_DIR = SCRIPT_DIR / "api"                # weibo/api

def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

def sum_hot_from_summary(summary_path: Path) -> int:
    data = read_json(summary_path)
    if not data:
        return 0
    # 口径A：summary.json 已经是“同题取当日最大 hot”，直接把 hot 累加即可
    return sum(int(item.get("hot", 0) or 0) for item in data)

def sum_hot_from_hours(day_dir: Path) -> int:
    """
    当天没有 summary.json 时的回退：遍历当日所有小时 *.json，
    对相同 title 取最大 hot，再求和（与 summary 的口径保持一致）。
    如果你想做“逐小时累加（不去重）”，把 max 改成累加即可。
    """
    title_max = {}
    for p in sorted(day_dir.glob("*.json")):
        if p.name == "summary.json":
            continue
        data = read_json(p) or []
        for item in data:
            title = item.get("title") or ""
            hot = int(item.get("hot", 0) or 0)
            # 口径A：同题取当日最大
            if title in title_max:
                title_max[title] = max(title_max[title], hot)
            else:
                title_max[title] = hot
            # 若想用口径B（逐小时累加、同题不去重），改为：
            # title_max[f"{title}@@{p.name}"] = hot
    return sum(title_max.values())

def recent_dates(n=30):
    today = datetime.now().date()
    for i in range(n):
        yield (today - timedelta(days=i)).strftime("%Y-%m-%d")

def main():
    results = []
    for d in recent_dates(30):
        day_dir = API_DIR / d
        if not day_dir.exists():
            continue
        summary_path = day_dir / "summary.json"
        if summary_path.exists():
            total = sum_hot_from_summary(summary_path)
        else:
            total = sum_hot_from_hours(day_dir)
        results.append({"date": d, "total_hot": int(total)})

    # 结果按日期升序输出（柱状图好看）
    results.sort(key=lambda x: x["date"])

    # 写 JSON
    out_json = API_DIR / "last_30_days_heat.json"
    out_json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    # 写 CSV
    out_csv = API_DIR / "last_30_days_heat.csv"
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "total_hot"])
        for r in results:
            w.writerow([r["date"], r["total_hot"]])

    print(f"[OK] Wrote {out_json}")
    print(f"[OK] Wrote {out_csv}")

if __name__ == "__main__":
    main()
