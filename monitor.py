"""
monitor.py - Gate.io WebSocket 监控引擎
连接 Gate.io WebSocket 获取实时 K 线数据，评估警报条件并触发通知
"""
import json
import threading
import time
import traceback
from datetime import datetime

import websocket
import pandas as pd
import ccxt

from indicators import evaluate_condition
from notifier import send_notification
from email_notifier import send_alert_email
from storage import load_alerts, add_history


def safe_print(*args, **kwargs):
    """
    安全打印函数，防止 Windows 控制台因 GBK 编码不支持某些 Unicode 字符（如表情符号）而崩溃
    """
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        try:
            # 尝试将每个 String 参数单独进行 GBK 降级编码
            encoded_args = []
            for arg in args:
                if isinstance(arg, str):
                    encoded_args.append(arg.encode('gbk', errors='ignore').decode('gbk'))
                else:
                    encoded_args.append(arg)
            print(*encoded_args, **kwargs)
        except Exception:
            pass  # 极端情况下忽略打印异常，防止监控后台线程异常退出



class MonitorEngine:
    """
    WebSocket 监控引擎
    - 通过 Gate.io WebSocket 接收实时 K 线数据
    - 使用 ccxt 获取初始历史数据
    - 当 K 线关闭时评估所有相关警报条件
    - 触发时发送 Windows 桌面通知
    """

    # Gate.io WebSocket 时间周期映射
    TIMEFRAME_MAP = {
        '1m': '1m', '5m': '5m', '15m': '15m', '30m': '30m',
        '1h': '1h', '4h': '4h', '8h': '8h', '1d': '1d',
        '7d': '7d', '30d': '30d',
    }

    def __init__(self, socketio=None):
        self.socketio = socketio
        self._running = False
        self._ws = None
        self._ws_thread = None
        self._candle_data = {}       # {symbol_timeframe: DataFrame}
        self._subscriptions = set()  # {(symbol, timeframe)} e.g., ('BTC_USDT', '1h')
        self._lock = threading.Lock()
        self._prices = {}            # {symbol: {price, high, low, open, volume, timestamp}}
        self._exchange = ccxt.gate()
        self._reconnect_delay = 5
        self._last_trigger_bars = {} # {alert_id: last_triggered_bar_timestamp}

    def start(self):
        """启动监控引擎"""
        self._running = True
        # 启动条件评估循环
        eval_thread = threading.Thread(target=self._evaluation_loop, daemon=True)
        eval_thread.start()
        # 初始订阅更新
        self._update_subscriptions()
        print("[引擎] 监控引擎已启动")

    def stop(self):
        """停止监控引擎"""
        self._running = False
        if self._ws:
            self._ws.close()
        print("[引擎] 监控引擎已停止")

    # ===========================================
    # 订阅管理
    # ===========================================

    def _symbol_to_gate(self, symbol):
        """将 ccxt 格式的交易对转为 Gate.io 格式: BTC/USDT -> BTC_USDT"""
        return symbol.replace('/', '_')

    def _symbol_from_gate(self, symbol):
        """将 Gate.io 格式转回 ccxt 格式: BTC_USDT -> BTC/USDT"""
        return symbol.replace('_', '/')

    def _update_subscriptions(self):
        """根据活跃警报更新 WebSocket 订阅"""
        alerts = load_alerts()
        new_subs = set()
        for alert in alerts:
            if alert.get('enabled', True):
                symbol = self._symbol_to_gate(alert['symbol'])
                timeframe = self.TIMEFRAME_MAP.get(
                    alert.get('timeframe', '1h'), '1h'
                )
                new_subs.add((symbol, timeframe))

        # 如果无活跃预警，默认订阅 BTC, ETH, SOL 以使页面行情栏显示实时价格
        if not new_subs:
            new_subs.add(('BTC_USDT', '1m'))
            new_subs.add(('ETH_USDT', '1m'))
            new_subs.add(('SOL_USDT', '1m'))

        if new_subs != self._subscriptions:
            self._subscriptions = new_subs
            self._reconnect_ws()

    def refresh_subscriptions(self):
        """外部调用：刷新订阅（添加/删除警报后）"""
        self._update_subscriptions()

    # ===========================================
    # Gate.io WebSocket 连接
    # ===========================================

    def _reconnect_ws(self):
        """重新连接 WebSocket 并订阅新的频道"""
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass

        if not self._subscriptions:
            print("[WS] 无活跃订阅，跳过连接")
            return

        url = "wss://api.gateio.ws/ws/v4/"

        def on_open(ws):
            print(f"[WS] 连接已建立，订阅 {len(self._subscriptions)} 个频道")
            # 发送订阅消息
            for symbol, timeframe in self._subscriptions:
                subscribe_msg = {
                    "time": int(time.time()),
                    "channel": "spot.candlesticks",
                    "event": "subscribe",
                    "payload": [timeframe, symbol]
                }
                ws.send(json.dumps(subscribe_msg))
                print(f"[WS] 订阅: {symbol} @ {timeframe}")

            if self.socketio:
                self.socketio.emit('status', {
                    'connected': True,
                    'streams': len(self._subscriptions)
                })
            self._reconnect_delay = 5  # 重置重连延迟

        def on_message(ws, message):
            try:
                data = json.loads(message)
                self._process_gate_message(data)
            except Exception as e:
                print(f"[WS] 消息处理错误: {e}")

        def on_error(ws, error):
            print(f"[WS] 错误: {error}")

        def on_close(ws, status_code, msg):
            print(f"[WS] 连接关闭: code={status_code}, msg={msg}")
            if self.socketio:
                self.socketio.emit('status', {'connected': False, 'streams': 0})
            # 自动重连
            if self._running:
                if ws == self._ws:
                    print(f"[WS] {self._reconnect_delay}s 后尝试重连...")
                    time.sleep(self._reconnect_delay)
                    self._reconnect_delay = min(self._reconnect_delay * 2, 60)
                    self._reconnect_ws()

        self._ws = websocket.WebSocketApp(
            url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )

        self._ws_thread = threading.Thread(
            target=self._ws.run_forever,
            kwargs={'ping_interval': 20, 'ping_timeout': 10},
            daemon=True
        )
        self._ws_thread.start()

    def _process_gate_message(self, data):
        """
        处理 Gate.io WebSocket 消息
        
        Gate.io K 线消息格式:
        {
            "time": 1234567890,
            "channel": "spot.candlesticks",
            "event": "update",
            "result": {
                "t": "1234567890",   # 时间戳（秒）
                "v": "1000",          # 成交量
                "c": "50000.5",       # 收盘价
                "h": "50100.0",       # 最高价
                "l": "49900.0",       # 最低价
                "o": "49950.0",       # 开盘价
                "n": "1h_BTC_USDT",   # 频道名：timeframe_symbol
                "a": "50000000",      # 成交额
                "w": false            # 是否为最终窗口（K线是否关闭）
            }
        }
        """
        channel = data.get('channel', '')
        event = data.get('event', '')

        if channel != 'spot.candlesticks' or event != 'update':
            return

        result = data.get('result', {})
        if not result:
            return

        # 解析频道名: "1h_BTC_USDT" -> timeframe="1h", symbol="BTC_USDT"
        name_parts = result.get('n', '').split('_', 1)
        if len(name_parts) < 2:
            return

        timeframe = name_parts[0]
        symbol = name_parts[1]  # e.g., "BTC_USDT"
        close_price = float(result.get('c', 0))
        is_closed = result.get('w', False)

        # 更新实时价格
        self._prices[symbol] = {
            'price': close_price,
            'high': float(result.get('h', 0)),
            'low': float(result.get('l', 0)),
            'open': float(result.get('o', 0)),
            'volume': float(result.get('v', 0)),
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S')
        }

        # 推送价格到前端
        if self.socketio:
            self.socketio.emit('price_update', {
                'symbol': symbol,
                'price': close_price,
                'data': self._prices[symbol]
            })

        # 实时更新或追加 K 线数据 DataFrame
        key = f"{symbol}_{timeframe}"
        candle = {
            'timestamp': pd.to_datetime(int(result.get('t', 0)), unit='s'),
            'open': float(result.get('o', 0)),
            'high': float(result.get('h', 0)),
            'low': float(result.get('l', 0)),
            'close': close_price,
            'volume': float(result.get('v', 0))
        }
        self._update_realtime_candle(key, candle)

    # ===========================================
    # K 线数据管理
    # ===========================================

    def _update_realtime_candle(self, key, candle):
        """实时更新或追加 K 线数据"""
        with self._lock:
            if key not in self._candle_data:
                self._candle_data[key] = pd.DataFrame([candle])
                return

            df = self._candle_data[key]
            if df.empty:
                self._candle_data[key] = pd.DataFrame([candle])
                return

            last_ts = df['timestamp'].iloc[-1]
            new_ts = candle['timestamp']

            if new_ts == last_ts:
                # 处于同一个 K 线周期，更新当前 K 线的数据
                df.iloc[-1, df.columns.get_loc('close')] = candle['close']
                df.iloc[-1, df.columns.get_loc('high')] = max(df['high'].iloc[-1], candle['high'])
                df.iloc[-1, df.columns.get_loc('low')] = min(df['low'].iloc[-1], candle['low'])
                df.iloc[-1, df.columns.get_loc('volume')] = candle['volume']
            elif new_ts > last_ts:
                # 新的 K 线周期开始，追加新 K 线，并限制最大行数
                new_row = pd.DataFrame([candle])
                df = pd.concat([df, new_row], ignore_index=True)
                if len(df) > 1000:
                    df = df.iloc[-1000:]
                self._candle_data[key] = df

    def _fetch_initial_data(self, symbol, timeframe):
        """
        使用 ccxt 获取初始历史 K 线数据
        symbol: Gate 格式 "BTC_USDT"
        timeframe: "1h"
        """
        key = f"{symbol}_{timeframe}"
        if key in self._candle_data and len(self._candle_data[key]) >= 50:
            return  # 已有足够数据

        try:
            ccxt_symbol = self._symbol_from_gate(symbol)  # "BTC/USDT"
            ohlcv = self._exchange.fetch_ohlcv(ccxt_symbol, timeframe, limit=1000)
            if ohlcv:
                df = pd.DataFrame(
                    ohlcv,
                    columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                )
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                with self._lock:
                    self._candle_data[key] = df
                print(f"[数据] 已获取 {len(df)} 根 K 线: {ccxt_symbol} @ {timeframe}")
        except Exception as e:
            print(f"[数据] 获取历史数据失败 {symbol}/{timeframe}: {e}")

    # ===========================================
    # 条件评估循环
    # ===========================================

    def _evaluation_loop(self):
        """主评估循环：定期检查所有警报条件"""
        while self._running:
            try:
                # 定期刷新订阅
                self._update_subscriptions()

                # 为新订阅获取历史数据
                for symbol, timeframe in self._subscriptions:
                    self._fetch_initial_data(symbol, timeframe)

                # 评估所有启用的警报
                alerts = load_alerts()
                alerts_changed = False

                for alert in alerts:
                    if not alert.get('enabled', True):
                        continue

                    # 1. 检查到期时间
                    exp_time_str = alert.get('expiration_time')
                    if exp_time_str:
                        try:
                            # 兼容各种可能的时间格式
                            if 'T' in exp_time_str:
                                exp_time = datetime.fromisoformat(exp_time_str)
                            else:
                                exp_time = datetime.strptime(exp_time_str, "%Y-%m-%d %H:%M")
                            
                            if datetime.now() > exp_time:
                                # 已到期，禁用该警报
                                alert['enabled'] = False
                                alerts_changed = True
                                safe_print(f"[监控] 警报 {alert['id']} 已过期，自动禁用")
                                continue
                        except Exception as ex:
                            safe_print(f"[监控] 解析警报到期时间失败 {exp_time_str}: {ex}")

                    symbol = self._symbol_to_gate(alert['symbol'])
                    timeframe = self.TIMEFRAME_MAP.get(
                        alert.get('timeframe', '1h'), '1h'
                    )
                    key = f"{symbol}_{timeframe}"

                    with self._lock:
                        df = self._candle_data.get(key)

                    if df is None or len(df) < 2:
                        continue

                    # 评估条件
                    eval_df = df.copy()
                    trigger_mode = alert.get('trigger_mode', 'once_per_bar_close')
                    if trigger_mode == 'once_per_bar_close':
                        eval_df = eval_df.iloc[:-1]  # 只评估已经收盘的 K 线

                    if len(eval_df) < 2:
                        continue

                    triggered, details = evaluate_condition(
                        eval_df,
                        alert['condition_type'],
                        alert.get('params', {})
                    )

                    if triggered:
                        # 2. 如果是 Bar 触发模式，进行 Bar 级别排重
                        if trigger_mode in ['once_per_bar', 'once_per_bar_close']:
                            current_bar_time = str(eval_df['timestamp'].iloc[-1])
                            last_bar = self._last_trigger_bars.get(alert['id'])
                            if last_bar == current_bar_time:
                                # 当前 Bar 已经触发过了，跳过发送
                                continue

                        price = eval_df['close'].iloc[-1]
                        title = f"🚨 {alert['symbol']} - {alert.get('message') or alert['condition_type']}"
                        body = f"{details}\n价格: {price}"

                        # 3. 确定冷却时间参数
                        cooldown = alert.get('cooldown', 300)
                        if trigger_mode == 'once':
                            cooldown = 0
                        elif trigger_mode == 'once_per_minute':
                            cooldown = 60

                        sent = send_notification(
                            title, body,
                            alert_id=alert['id'],
                            cooldown=cooldown
                        )

                        if sent:
                            # 记录最后触发的 K 线时间
                            if trigger_mode in ['once_per_bar', 'once_per_bar_close']:
                                self._last_trigger_bars[alert['id']] = current_bar_time

                            # 如果是「仅一次」模式，触发后禁用该警报
                            if trigger_mode == 'once':
                                alert['enabled'] = False
                                alerts_changed = True
                                safe_print(f"[监控] 「仅一次」警报 {alert['id']} 已触发，自动禁用")

                            history_entry = {
                                'alert_id': alert['id'],
                                'symbol': alert['symbol'],
                                'condition_type': alert['condition_type'],
                                'message': alert.get('message', ''),
                                'details': details,
                                'price': price
                            }
                            add_history(history_entry)

                            if self.socketio:
                                self.socketio.emit('alert_triggered', history_entry)

                            # 尝试发送邮件（内部自动判断是否启用及时间窗口）
                            send_alert_email(title, body)

                            safe_print(f"[警报触发] {title} — {details}")

                # 如果有警报状态变更（过期或一次性触发禁用），持久化保存
                if alerts_changed:
                    from storage import save_alerts
                    save_alerts(alerts)

                time.sleep(5)  # 每 5 秒评估一次

            except Exception as e:
                safe_print(f"[评估循环错误] {e}")
                try:
                    traceback.print_exc()
                except Exception:
                    pass
                time.sleep(10)

    # ===========================================
    # 公共接口
    # ===========================================

    def get_prices(self):
        """获取所有监控中交易对的当前价格"""
        return dict(self._prices)
