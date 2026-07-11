"""
notifier.py - Windows 桌面通知模块
使用 windows-toasts 发送原生 Windows 弹窗通知，支持冷却机制防止重复触发
"""
import time
import traceback

try:
    from windows_toasts import WindowsToaster, Toast
    _toaster = WindowsToaster('CryptoAlert')
    _toasts_available = True
except ImportError:
    _toasts_available = False
    print("[WARN] windows-toasts 未安装，桌面通知将使用控制台输出替代")
except Exception:
    _toasts_available = False
    print("[WARN] windows-toasts 初始化失败，桌面通知将使用控制台输出替代")

# 冷却追踪: {alert_id: 上次触发的时间戳}
_cooldowns = {}


def send_notification(title, message, alert_id=None, cooldown=300):
    """
    发送 Windows 桌面通知
    
    Args:
        title: 通知标题
        message: 通知正文
        alert_id: 警报ID（用于冷却追踪）
        cooldown: 冷却时间（秒），同一警报在冷却期内不重复触发
    
    Returns:
        bool: 是否成功发送通知
    """
    now = time.time()

    # 检查冷却
    if alert_id and alert_id in _cooldowns:
        elapsed = now - _cooldowns[alert_id]
        if elapsed < cooldown:
            remaining = int(cooldown - elapsed)
            print(f"[冷却中] {title} — 剩余 {remaining}s")
            return False

    # 发送通知
    try:
        if _toasts_available:
            toast = Toast()
            toast.text_fields = [title, message]
            _toaster.show_toast(toast)
        else:
            # 降级为控制台输出
            print(f"\n{'='*50}")
            print(f"🔔 {title}")
            print(f"   {message}")
            print(f"{'='*50}\n")

        # 记录冷却
        if alert_id:
            _cooldowns[alert_id] = now
        return True
    except Exception as e:
        print(f"[通知错误] {e}")
        traceback.print_exc()
        # 即使通知失败也记录冷却，避免反复出错
        if alert_id:
            _cooldowns[alert_id] = now
        return False


def clear_cooldown(alert_id):
    """清除指定警报的冷却状态"""
    _cooldowns.pop(alert_id, None)


def clear_all_cooldowns():
    """清除所有警报的冷却状态"""
    _cooldowns.clear()
