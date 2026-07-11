"""
storage.py - 数据持久化模块
管理警报规则和触发历史的 JSON 文件存储
"""
import json
import uuid
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent / 'data'
ALERTS_FILE = DATA_DIR / 'alerts.json'
HISTORY_FILE = DATA_DIR / 'history.json'


def _ensure_data_dir():
    """确保 data 目录和 JSON 文件存在"""
    DATA_DIR.mkdir(exist_ok=True)
    if not ALERTS_FILE.exists():
        ALERTS_FILE.write_text('[]', encoding='utf-8')
    if not HISTORY_FILE.exists():
        HISTORY_FILE.write_text('[]', encoding='utf-8')


def load_alerts():
    """加载所有警报规则"""
    _ensure_data_dir()
    with open(ALERTS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_alerts(alerts):
    """保存所有警报规则"""
    _ensure_data_dir()
    with open(ALERTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(alerts, f, ensure_ascii=False, indent=2)


def add_alert(alert_data):
    """添加新警报规则"""
    alerts = load_alerts()
    alert = {
        'id': str(uuid.uuid4()),
        'symbol': alert_data['symbol'],
        'timeframe': alert_data.get('timeframe', '1h'),
        'condition_type': alert_data['condition_type'],
        'params': alert_data.get('params', {}),
        'message': alert_data.get('message', ''),
        'enabled': True,
        'cooldown': alert_data.get('cooldown', 300),
        'trigger_mode': alert_data.get('trigger_mode', 'once_per_bar_close'),
        'expiration_time': alert_data.get('expiration_time', None),
        'created_at': datetime.now().isoformat()
    }
    alerts.append(alert)
    save_alerts(alerts)
    return alert


def update_alert(alert_id, alert_data):
    """更新指定警报规则"""
    alerts = load_alerts()
    for i, alert in enumerate(alerts):
        if alert['id'] == alert_id:
            # 保留 id 和 created_at
            alert_data.pop('id', None)
            alert_data.pop('created_at', None)
            alerts[i].update(alert_data)
            save_alerts(alerts)
            return alerts[i]
    return None


def delete_alert(alert_id):
    """删除指定警报规则"""
    alerts = load_alerts()
    alerts = [a for a in alerts if a['id'] != alert_id]
    save_alerts(alerts)


def toggle_alert(alert_id):
    """切换警报的启用/禁用状态"""
    alerts = load_alerts()
    for alert in alerts:
        if alert['id'] == alert_id:
            alert['enabled'] = not alert['enabled']
            save_alerts(alerts)
            return alert
    return None


def load_history(limit=100):
    """加载警报触发历史（最近 N 条）"""
    _ensure_data_dir()
    with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
        history = json.load(f)
    return history[-limit:]


def add_history(entry):
    """添加一条触发历史记录"""
    _ensure_data_dir()
    with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
        history = json.load(f)
    entry['timestamp'] = datetime.now().isoformat()
    entry['id'] = str(uuid.uuid4())
    history.append(entry)
    # 只保留最近 500 条记录
    if len(history) > 500:
        history = history[-500:]
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    return entry


def delete_history(history_id):
    """删除指定触发历史记录"""
    _ensure_data_dir()
    with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
        history = json.load(f)
    history = [h for h in history if h.get('id') != history_id]
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def clear_history():
    """清空所有触发历史记录"""
    _ensure_data_dir()
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump([], f, ensure_ascii=False, indent=2)


