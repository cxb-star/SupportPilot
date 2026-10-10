"""CI / 运维健康检查脚本：定时调用，有告警就 POST /alerts。

用法：
    python -m scripts.health_check            本地直接跑
    或在 CI / cron 里定时跑这个脚本

逻辑：
    1. 调 metrics() 算指标
    2. 判断是否需要告警（紧急工单数 / LLM 成本 / 置信度）
    3. 有告警就写进 alerts 表
"""
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


def run() -> int:
    from monitoring import check_health, _ensure_alerts_table, router
    from fastapi.testclient import TestClient
    from app.main import app

    _ensure_alerts_table()
    client = TestClient(app)

    result = check_health()
    metrics = result.get("metrics", {})
    alerts = result.get("alerts", [])

    print(f"metrics: status={metrics.get('status')}")
    print(f"  tickets.open={metrics.get('tickets', {}).get('open')}")
    print(f"  tickets.urgent_open={metrics.get('tickets', {}).get('urgent_open')}")
    print(f"  llm.total_cost_last_100=${metrics.get('llm', {}).get('total_cost_usd_last_100')}")
    print(f"  audit.avg_confidence={metrics.get('audit', {}).get('avg_confidence_last_100')}")

    if alerts:
        print(f"\n!! {len(alerts)} 条告警：")
        for a in alerts:
            print(f"   [{a['severity']}] {a['alert_type']}: {a['message']}")
            resp = client.post("/alerts", json=a)
            print(f"   -> alert id={resp.json().get('id')} status={resp.status_code}")
    else:
        print("\n无告警，系统正常。")

    return 0


if __name__ == "__main__":
    sys.exit(run())
