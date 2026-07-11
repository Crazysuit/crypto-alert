"""
app.py - Flask 主应用
提供 Web 管理面板和 REST API，启动监控引擎
"""
import os
import secrets
from flask import Flask, render_template, request, jsonify, send_from_directory, send_file, Response
from flask_socketio import SocketIO

from storage import (
    load_alerts, add_alert, update_alert, delete_alert, toggle_alert,
    load_history, delete_history, clear_history
)
from indicators import get_condition_types
from email_notifier import load_email_config, save_email_config, test_email_send
from monitor import MonitorEngine

# ========================================
# Flask 应用初始化
# ========================================
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or os.urandom(24).hex()
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins="*")

# 初始化监控引擎
monitor = MonitorEngine(socketio=socketio)


# ========================================
# 公网访问保护
# ========================================

@app.before_request
def require_login():
    """使用环境变量提供的 HTTP Basic Auth 保护管理页面和 API。"""
    if request.path == '/health':
        return None

    expected_user = os.environ.get('APP_USERNAME', '')
    expected_password = os.environ.get('APP_PASSWORD', '')
    if not expected_user or not expected_password:
        return jsonify({
            'error': '服务器尚未配置 APP_USERNAME 和 APP_PASSWORD'
        }), 503

    auth = request.authorization
    valid = (
        auth is not None
        and secrets.compare_digest(auth.username or '', expected_user)
        and secrets.compare_digest(auth.password or '', expected_password)
    )
    if not valid:
        return Response(
            '需要登录后才能访问 CryptoAlert',
            401,
            {'WWW-Authenticate': 'Basic realm="CryptoAlert"'}
        )
    return None


# ========================================
# 页面路由
# ========================================

@app.route('/')
def index():
    """主页面"""
    return render_template('index.html')


@app.route('/health')
def health():
    """托管平台健康检查，无敏感信息。"""
    return jsonify({'status': 'ok'})


@app.route('/manifest.json')
def manifest():
    """PWA Web App Manifest"""
    return send_from_directory(
        app.root_path, 'manifest.json',
        mimetype='application/manifest+json'
    )


@app.route('/sw.js')
def service_worker():
    """Service Worker (必须从根路径提供以确保正确的作用域)"""
    return send_from_directory(
        os.path.join(app.root_path, 'static', 'js'), 'sw.js',
        mimetype='application/javascript'
    )


# ========================================
# API 路由 — 警报管理
# ========================================

@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    """获取所有警报规则"""
    return jsonify(load_alerts())


@app.route('/api/alerts', methods=['POST'])
def create_alert():
    """创建新警报规则"""
    data = request.json
    if not data or 'symbol' not in data or 'condition_type' not in data:
        return jsonify({'error': '缺少必填字段: symbol, condition_type'}), 400
    alert = add_alert(data)
    monitor.refresh_subscriptions()
    return jsonify(alert), 201


@app.route('/api/alerts/<alert_id>', methods=['PUT'])
def modify_alert(alert_id):
    """更新指定警报规则"""
    data = request.json
    alert = update_alert(alert_id, data)
    if alert:
        monitor.refresh_subscriptions()
        return jsonify(alert)
    return jsonify({'error': '警报未找到'}), 404


@app.route('/api/alerts/<alert_id>', methods=['DELETE'])
def remove_alert(alert_id):
    """删除指定警报规则"""
    delete_alert(alert_id)
    monitor.refresh_subscriptions()
    return jsonify({'success': True})


@app.route('/api/alerts/<alert_id>/toggle', methods=['PUT'])
def toggle(alert_id):
    """切换警报的启用/禁用状态"""
    alert = toggle_alert(alert_id)
    if alert:
        monitor.refresh_subscriptions()
        return jsonify(alert)
    return jsonify({'error': '警报未找到'}), 404


# ========================================
# API 路由 — 数据查询
# ========================================

@app.route('/api/history', methods=['GET'])
def get_history():
    """获取警报触发历史"""
    limit = request.args.get('limit', 50, type=int)
    return jsonify(load_history(limit))


@app.route('/api/history', methods=['DELETE'])
def clear_all_history():
    """清空全部触发历史记录"""
    clear_history()
    return jsonify({'success': True})


@app.route('/api/history/<history_id>', methods=['DELETE'])
def remove_history(history_id):
    """删除指定触发历史记录"""
    delete_history(history_id)
    return jsonify({'success': True})


@app.route('/api/conditions', methods=['GET'])
def get_conditions():
    """获取所有可用的条件类型及其参数定义"""
    return jsonify(get_condition_types())


@app.route('/api/convert-pine', methods=['POST'])
def convert_pine():
    """将 Pine Script 代码转换为自定义 Python 表达式"""
    data = request.json
    if not data or 'pine_code' not in data:
        return jsonify({'error': '缺少 pine_code 字段'}), 400
    
    from pine_converter import convert_pine_to_python
    try:
        converted = convert_pine_to_python(data['pine_code'])
        return jsonify({'expression': converted})
    except Exception as e:
        return jsonify({'error': f'转换失败: {str(e)}'}), 500


@app.route('/api/prices', methods=['GET'])
def get_prices():
    """获取当前监控中所有交易对的实时价格"""
    return jsonify(monitor.get_prices())


@app.route('/api/symbols', methods=['GET'])
def get_symbols():
    """获取可用的交易对列表（Gate.io 热门交易对）"""
    symbols = [
        'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT',
        'DOGE/USDT', 'ADA/USDT', 'AVAX/USDT', 'DOT/USDT', 'MATIC/USDT',
        'LINK/USDT', 'UNI/USDT', 'ATOM/USDT', 'LTC/USDT', 'ETC/USDT',
        'FIL/USDT', 'APT/USDT', 'ARB/USDT', 'OP/USDT', 'SUI/USDT',
        'NEAR/USDT', 'AAVE/USDT', 'INJ/USDT', 'TIA/USDT', 'SEI/USDT',
        'PEPE/USDT', 'WIF/USDT', 'BONK/USDT', 'FLOKI/USDT', 'SHIB/USDT',
        'TRX/USDT', 'TON/USDT', 'RENDER/USDT', 'FET/USDT', 'ONDO/USDT',
        'WLD/USDT', 'JUP/USDT', 'PENDLE/USDT', 'STX/USDT', 'IMX/USDT'
    ]
    return jsonify(symbols)


@app.route('/api/email-config', methods=['GET'])
def get_email_config():
    """获取邮件通知配置（密码脱敏）"""
    config = load_email_config()
    # 前端展示时隐藏密码
    password_is_set = bool(config.pop('sender_password', ''))
    config['sender_password_masked'] = '••••••••' if password_is_set else ''
    return jsonify(config)


@app.route('/api/email-config', methods=['PUT'])
def update_email_config():
    """更新邮件通知配置"""
    data = request.json
    if not data:
        return jsonify({'error': '请求体为空'}), 400
    # 如果前端没有修改密码（传来的是掩码），保留原密码
    if data.get('sender_password') == '••••••••':
        old_config = load_email_config()
        data['sender_password'] = old_config.get('sender_password', '')
    save_email_config(data)
    return jsonify({'success': True})


@app.route('/api/email-config/test', methods=['POST'])
def test_email():
    """测试邮件发送（忽略时间窗口）"""
    data = request.json
    if not data:
        return jsonify({'error': '请求体为空'}), 400
    # 如果密码是掩码，用已存储的密码
    if data.get('sender_password') == '••••••••':
        old_config = load_email_config()
        data['sender_password'] = old_config.get('sender_password', '')
    success, message = test_email_send(data)
    return jsonify({'success': success, 'message': message})


# ========================================
# Socket.IO 事件
# ========================================

@socketio.on('connect')
def handle_connect():
    """客户端连接时发送当前价格数据"""
    prices = monitor.get_prices()
    socketio.emit('all_prices', prices)


# ========================================
# 启动入口
# ========================================

if __name__ == '__main__':
    print()
    print("=" * 56)
    print("   ╔═══════════════════════════════════════════════╗")
    print("   ║   CryptoAlert — 加密货币指标监控系统          ║")
    print("   ║   交易所: Gate.io                             ║")
    print("   ║   访问: http://localhost:5000                 ║")
    print("   ╚═══════════════════════════════════════════════╝")
    print("=" * 56)
    print()
    monitor.start()
    port = int(os.environ.get('PORT', '5000'))
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)
