"""
email_notifier.py - 邮件通知模块
在指定时间窗口内，当警报触发时自动发送邮件通知。
使用 Python 内置 smtplib，无需额外安装依赖。
"""
import json
import smtplib
import threading
import traceback
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path


CONFIG_FILE = Path(__file__).parent / 'data' / 'email_config.json'

# 默认配置
_DEFAULT_CONFIG = {
    'enabled': False,
    'smtp_server': '',
    'smtp_port': 465,
    'use_ssl': True,
    'sender_email': '',
    'sender_password': '',
    'receiver_email': '',
    # 发送时间窗口 (24h 格式): 仅在此时间段内发送邮件
    # 例如 "22:00" ~ "08:00" 表示晚上10点到早上8点
    'send_start_time': '22:00',
    'send_end_time': '08:00',
}


def load_email_config():
    """加载邮件配置"""
    if not CONFIG_FILE.exists():
        return dict(_DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            saved = json.load(f)
        # 合并默认值（确保新增字段有默认值）
        config = dict(_DEFAULT_CONFIG)
        config.update(saved)
        return config
    except Exception:
        return dict(_DEFAULT_CONFIG)


def save_email_config(config):
    """保存邮件配置"""
    CONFIG_FILE.parent.mkdir(exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def _is_in_send_window(config):
    """
    判断当前时间是否在发送窗口内。
    支持跨午夜的时间段，例如 22:00 ~ 08:00。
    """
    start_str = config.get('send_start_time', '22:00')
    end_str = config.get('send_end_time', '08:00')

    try:
        now = datetime.now()
        current_minutes = now.hour * 60 + now.minute
        
        start_parts = start_str.split(':')
        start_minutes = int(start_parts[0]) * 60 + int(start_parts[1])
        
        end_parts = end_str.split(':')
        end_minutes = int(end_parts[0]) * 60 + int(end_parts[1])

        if start_minutes <= end_minutes:
            # 不跨午夜: e.g. 09:00 ~ 18:00
            return start_minutes <= current_minutes < end_minutes
        else:
            # 跨午夜: e.g. 22:00 ~ 08:00
            return current_minutes >= start_minutes or current_minutes < end_minutes
    except Exception:
        return False


def _do_send_email(config, subject, body):
    """实际发送邮件（在子线程中调用）"""
    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = config['sender_email']
        msg['To'] = config['receiver_email']
        msg['Subject'] = subject

        # 纯文本部分
        text_part = MIMEText(body, 'plain', 'utf-8')
        msg.attach(text_part)

        # HTML 部分（美化邮件）
        html_body = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                    max-width: 500px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #1e222d, #2a2e39); 
                        border-radius: 12px; padding: 24px; color: #d1d4dc;">
                <h2 style="margin: 0 0 16px; color: #f0b90b; font-size: 18px;">
                    ⚡ CryptoAlert 警报触发
                </h2>
                <div style="background: rgba(255,255,255,0.05); border-radius: 8px; 
                            padding: 16px; margin-bottom: 12px; white-space: pre-line;
                            font-size: 14px; line-height: 1.6;">
{body}
                </div>
                <div style="font-size: 12px; color: #787b86; margin-top: 12px;">
                    发送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                </div>
            </div>
        </div>
        """
        html_part = MIMEText(html_body, 'html', 'utf-8')
        msg.attach(html_part)

        if config.get('use_ssl', True):
            with smtplib.SMTP_SSL(config['smtp_server'], config['smtp_port'], timeout=15) as server:
                server.login(config['sender_email'], config['sender_password'])
                server.send_message(msg)
        else:
            with smtplib.SMTP(config['smtp_server'], config['smtp_port'], timeout=15) as server:
                server.starttls()
                server.login(config['sender_email'], config['sender_password'])
                server.send_message(msg)

        print(f"[邮件] 发送成功 -> {config['receiver_email']}")
        return True
    except Exception as e:
        print(f"[邮件] 发送失败: {e}")
        traceback.print_exc()
        return False


def send_alert_email(title, body):
    """
    尝试发送警报邮件。
    - 如果邮件功能未启用，静默跳过
    - 如果当前时间不在发送窗口内，静默跳过
    - 邮件发送在子线程中异步执行，不阻塞主监控流程
    """
    config = load_email_config()

    if not config.get('enabled', False):
        return

    # 检查必填字段
    required = ['smtp_server', 'sender_email', 'sender_password', 'receiver_email']
    if not all(config.get(k) for k in required):
        return

    # 检查时间窗口
    if not _is_in_send_window(config):
        return

    # 异步发送，不阻塞评估循环
    thread = threading.Thread(
        target=_do_send_email,
        args=(config, title, body),
        daemon=True
    )
    thread.start()


def test_email_send(config):
    """
    测试邮件发送（忽略时间窗口限制）。
    返回 (success: bool, message: str)
    """
    required = ['smtp_server', 'sender_email', 'sender_password', 'receiver_email']
    for k in required:
        if not config.get(k):
            return False, f"缺少必填字段: {k}"

    subject = "🔔 CryptoAlert 邮件测试"
    body = "这是一封测试邮件。\n如果您收到此邮件，说明邮件配置正确。\n\n— CryptoAlert 监控系统"
    
    success = _do_send_email(config, subject, body)
    if success:
        return True, "测试邮件发送成功，请检查收件箱"
    else:
        return False, "邮件发送失败，请检查 SMTP 配置"
