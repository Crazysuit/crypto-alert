"""独立的现货模拟交易引擎。

第一阶段只使用实时行情进行纸面成交，不持有或使用交易所 API 密钥，
也不会向 Gate.io 提交真实订单。
"""
from __future__ import annotations

import json
import threading
import traceback
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import ccxt
import pandas as pd


DEFAULT_CONFIG = {
    'enabled': False,
    'mode': 'paper',
    'symbol': 'BTC/USDT',
    'timeframe': '15m',
    'initial_balance': 200.0,
    'poll_seconds': 60,
    'ema_fast': 20,
    'ema_slow': 50,
    'rsi_period': 14,
    'stop_loss_pct': 0.02,
    'take_profit_pct': 0.03,
    'risk_per_trade_pct': 0.005,
    'max_position_pct': 0.25,
    'max_daily_loss': 2.0,
    'monthly_profit_target': 20.0,
    'fee_rate': 0.002,
}


def _utc_now():
    return datetime.now(timezone.utc)


def _iso_now():
    return _utc_now().isoformat()


def _new_state(initial_balance=200.0):
    now = _utc_now()
    return {
        'cash': float(initial_balance),
        'position': None,
        'realized_pnl': 0.0,
        'daily_realized_pnl': 0.0,
        'monthly_realized_pnl': 0.0,
        'day_key': now.strftime('%Y-%m-%d'),
        'month_key': now.strftime('%Y-%m'),
        'current_price': None,
        'last_candle_time': None,
        'last_signal': '等待启动',
        'last_error': '',
        'paused_reason': '',
        'trade_count': 0,
        'updated_at': _iso_now(),
    }


class PaperTradingEngine:
    """EMA 趋势 + RSI 过滤的现货做多模拟交易引擎。"""

    ALLOWED_TIMEFRAMES = {'5m', '15m', '30m', '1h', '4h'}
    ALLOWED_SYMBOLS = {'BTC/USDT', 'ETH/USDT'}
    EDITABLE_FIELDS = {
        'symbol', 'timeframe', 'poll_seconds', 'stop_loss_pct',
        'take_profit_pct', 'risk_per_trade_pct', 'max_position_pct',
        'max_daily_loss', 'monthly_profit_target', 'fee_rate',
    }

    def __init__(self, data_dir=None, on_trade=None, exchange=None):
        self.data_dir = Path(data_dir or Path(__file__).parent / 'data')
        self.config_file = self.data_dir / 'trading_config.json'
        self.state_file = self.data_dir / 'trading_state.json'
        self.history_file = self.data_dir / 'trading_history.json'
        self.on_trade = on_trade
        self.exchange = exchange or ccxt.gate({'enableRateLimit': True})
        self._lock = threading.RLock()
        self._thread = None
        self._stop_event = threading.Event()
        self._running = False
        self._ensure_files()

    def _read_json(self, path, default):
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            return deepcopy(default)

    def _write_json(self, path, value):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + '.tmp')
        temp.write_text(
            json.dumps(value, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        temp.replace(path)

    def _ensure_files(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.config_file.exists():
            self._write_json(self.config_file, DEFAULT_CONFIG)
        if not self.state_file.exists():
            self._write_json(
                self.state_file,
                _new_state(DEFAULT_CONFIG['initial_balance']),
            )
        if not self.history_file.exists():
            self._write_json(self.history_file, [])

    def load_config(self):
        saved = self._read_json(self.config_file, DEFAULT_CONFIG)
        config = deepcopy(DEFAULT_CONFIG)
        config.update(saved)
        config['mode'] = 'paper'
        return config

    def save_config(self, config):
        config = deepcopy(config)
        config['mode'] = 'paper'
        self._write_json(self.config_file, config)

    def load_state(self):
        config = self.load_config()
        default = _new_state(config['initial_balance'])
        saved = self._read_json(self.state_file, default)
        default.update(saved)
        return default

    def save_state(self, state):
        state = deepcopy(state)
        state['updated_at'] = _iso_now()
        self._write_json(self.state_file, state)

    def load_history(self, limit=100):
        history = self._read_json(self.history_file, [])
        return history[-max(1, min(int(limit), 500)):]

    def _append_history(self, entry):
        history = self._read_json(self.history_file, [])
        history.append(entry)
        self._write_json(self.history_file, history[-500:])

    def update_config(self, changes):
        with self._lock:
            if self._running:
                raise ValueError('请先停止模拟交易，再修改参数')
            config = self.load_config()
            for key, value in changes.items():
                if key in self.EDITABLE_FIELDS:
                    config[key] = value
            self._validate_config(config)
            self.save_config(config)
            return config

    def _validate_config(self, config):
        if config['symbol'] not in self.ALLOWED_SYMBOLS:
            raise ValueError('当前仅支持 BTC/USDT 和 ETH/USDT')
        if config['timeframe'] not in self.ALLOWED_TIMEFRAMES:
            raise ValueError('不支持的时间周期')
        numeric_ranges = {
            'poll_seconds': (30, 3600),
            'stop_loss_pct': (0.005, 0.10),
            'take_profit_pct': (0.005, 0.20),
            'risk_per_trade_pct': (0.001, 0.02),
            'max_position_pct': (0.05, 0.50),
            'max_daily_loss': (0.5, 20.0),
            'monthly_profit_target': (1.0, 100.0),
            'fee_rate': (0.0, 0.01),
        }
        for key, (low, high) in numeric_ranges.items():
            try:
                config[key] = float(config[key])
            except (TypeError, ValueError):
                raise ValueError(f'{key} 必须是数字') from None
            if not low <= config[key] <= high:
                raise ValueError(f'{key} 必须在 {low} 到 {high} 之间')
        config['poll_seconds'] = int(config['poll_seconds'])

    def start(self):
        with self._lock:
            if self._running:
                return False
            config = self.load_config()
            self._validate_config(config)
            config['enabled'] = True
            self.save_config(config)
            state = self.load_state()
            state['paused_reason'] = ''
            state['last_signal'] = '模拟交易已启动，等待新K线'
            self.save_state(state)
            self._stop_event.clear()
            self._running = True
            self._thread = threading.Thread(
                target=self._run_loop,
                name='paper-trading-engine',
                daemon=True,
            )
            self._thread.start()
            return True

    def start_if_enabled(self):
        if self.load_config().get('enabled'):
            return self.start()
        return False

    def stop(self, reason='用户手动停止'):
        with self._lock:
            config = self.load_config()
            config['enabled'] = False
            self.save_config(config)
            self._running = False
            self._stop_event.set()
            state = self.load_state()
            state['paused_reason'] = reason
            state['last_signal'] = reason
            self.save_state(state)
            return True

    def reset(self):
        with self._lock:
            if self._running:
                raise ValueError('请先停止模拟交易，再重置账户')
            config = self.load_config()
            self.save_state(_new_state(config['initial_balance']))
            self._write_json(self.history_file, [])
            return self.status()

    def _roll_periods(self, state):
        now = _utc_now()
        day_key = now.strftime('%Y-%m-%d')
        month_key = now.strftime('%Y-%m')
        if state.get('day_key') != day_key:
            state['day_key'] = day_key
            state['daily_realized_pnl'] = 0.0
            if state.get('paused_reason') == '达到每日最大亏损':
                state['paused_reason'] = ''
        if state.get('month_key') != month_key:
            state['month_key'] = month_key
            state['monthly_realized_pnl'] = 0.0
            if state.get('paused_reason') == '达到月盈利目标':
                state['paused_reason'] = ''

    @staticmethod
    def _add_indicators(frame, config):
        df = frame.copy()
        close = df['close'].astype(float)
        df['ema_fast'] = close.ewm(
            span=int(config['ema_fast']), adjust=False
        ).mean()
        df['ema_slow'] = close.ewm(
            span=int(config['ema_slow']), adjust=False
        ).mean()
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(
            alpha=1 / int(config['rsi_period']), adjust=False
        ).mean()
        loss = (-delta.clip(upper=0)).ewm(
            alpha=1 / int(config['rsi_period']), adjust=False
        ).mean()
        rs = gain / loss.replace(0, float('nan'))
        df['rsi'] = (100 - (100 / (1 + rs))).fillna(50)
        return df

    def _fetch_frame(self, config):
        rows = self.exchange.fetch_ohlcv(
            config['symbol'], config['timeframe'], limit=120
        )
        if len(rows) < int(config['ema_slow']) + 3:
            raise RuntimeError('历史K线数量不足')
        return pd.DataFrame(
            rows,
            columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'],
        )

    def run_cycle(self, frame=None):
        """执行一次策略评估；frame 参数用于测试。"""
        with self._lock:
            config = self.load_config()
            state = self.load_state()
            self._roll_periods(state)
            frame = frame if frame is not None else self._fetch_frame(config)
            df = self._add_indicators(frame, config)

            # 最后一根K线通常尚未收盘，因此使用倒数第二根。
            previous = df.iloc[-3]
            current = df.iloc[-2]
            candle_key = str(int(current['timestamp']))
            price = float(current['close'])
            state['current_price'] = price
            state['last_error'] = ''

            if state.get('last_candle_time') == candle_key:
                self.save_state(state)
                return self.status()
            state['last_candle_time'] = candle_key

            position = state.get('position')
            if position:
                stop_hit = price <= float(position['stop_price'])
                take_hit = price >= float(position['take_profit_price'])
                cross_down = (
                    float(previous['ema_fast']) >= float(previous['ema_slow'])
                    and float(current['ema_fast']) < float(current['ema_slow'])
                )
                if stop_hit:
                    self._execute_sell(state, config, price, '止损')
                elif take_hit:
                    self._execute_sell(state, config, price, '止盈')
                elif cross_down:
                    self._execute_sell(state, config, price, 'EMA趋势反转')
                else:
                    state['last_signal'] = '持仓中，等待止盈/止损或趋势反转'
            else:
                if state['monthly_realized_pnl'] >= config['monthly_profit_target']:
                    self._pause_from_engine(state, config, '达到月盈利目标')
                elif state['daily_realized_pnl'] <= -config['max_daily_loss']:
                    state['paused_reason'] = '达到每日最大亏损'
                    state['last_signal'] = '今日停止开仓，次日自动恢复'
                elif not state.get('paused_reason'):
                    cross_up = (
                        float(previous['ema_fast']) <= float(previous['ema_slow'])
                        and float(current['ema_fast']) > float(current['ema_slow'])
                    )
                    rsi_ok = float(current['rsi']) < 70
                    if cross_up and rsi_ok:
                        self._execute_buy(state, config, price, float(current['rsi']))
                    else:
                        state['last_signal'] = (
                            f"等待买入信号：EMA{config['ema_fast']}/"
                            f"EMA{config['ema_slow']}，RSI {float(current['rsi']):.1f}"
                        )

            self.save_state(state)
            return self.status()

    def _execute_buy(self, state, config, price, rsi):
        cash = float(state['cash'])
        equity = cash
        risk_budget = equity * float(config['risk_per_trade_pct'])
        risk_sized_notional = risk_budget / float(config['stop_loss_pct'])
        max_notional = equity * float(config['max_position_pct'])
        notional = min(risk_sized_notional, max_notional)
        fee_rate = float(config['fee_rate'])
        notional = min(notional, cash / (1 + fee_rate))
        if notional < 5:
            state['last_signal'] = '可用资金不足，未模拟买入'
            return

        fee = notional * fee_rate
        quantity = notional / price
        state['cash'] = cash - notional - fee
        state['position'] = {
            'symbol': config['symbol'],
            'quantity': quantity,
            'entry_price': price,
            'notional': notional,
            'entry_fee': fee,
            'stop_price': price * (1 - float(config['stop_loss_pct'])),
            'take_profit_price': price * (1 + float(config['take_profit_pct'])),
            'opened_at': _iso_now(),
        }
        state['last_signal'] = f'模拟买入，RSI {rsi:.1f}'
        self.save_state(state)
        self._record_trade('buy', state['position'], price, quantity, fee, 0.0, 'EMA金叉')

    def _execute_sell(self, state, config, price, reason):
        position = state['position']
        quantity = float(position['quantity'])
        gross = quantity * price
        exit_fee = gross * float(config['fee_rate'])
        pnl = (
            gross - exit_fee - float(position['notional'])
            - float(position['entry_fee'])
        )
        state['cash'] = float(state['cash']) + gross - exit_fee
        state['position'] = None
        state['realized_pnl'] = float(state['realized_pnl']) + pnl
        state['daily_realized_pnl'] = float(state['daily_realized_pnl']) + pnl
        state['monthly_realized_pnl'] = float(state['monthly_realized_pnl']) + pnl
        state['trade_count'] = int(state.get('trade_count', 0)) + 1
        state['last_signal'] = f'模拟卖出：{reason}，盈亏 {pnl:+.2f} USDT'
        self.save_state(state)
        self._record_trade('sell', position, price, quantity, exit_fee, pnl, reason)

        if state['monthly_realized_pnl'] >= float(config['monthly_profit_target']):
            self._pause_from_engine(state, config, '达到月盈利目标')

    def _record_trade(self, side, position, price, quantity, fee, pnl, reason):
        entry = {
            'timestamp': _iso_now(),
            'mode': 'paper',
            'side': side,
            'symbol': position['symbol'],
            'price': round(float(price), 8),
            'quantity': round(float(quantity), 12),
            'fee': round(float(fee), 8),
            'pnl': round(float(pnl), 8),
            'reason': reason,
        }
        self._append_history(entry)
        if self.on_trade:
            try:
                self.on_trade(entry)
            except Exception:
                traceback.print_exc()

    def _pause_from_engine(self, state, config, reason):
        config['enabled'] = False
        self.save_config(config)
        state['paused_reason'] = reason
        state['last_signal'] = f'{reason}，模拟交易已自动停止'
        self._running = False
        self._stop_event.set()

    def status(self):
        with self._lock:
            config = self.load_config()
            state = self.load_state()
            price = state.get('current_price')
            position = state.get('position')
            unrealized = 0.0
            equity = float(state['cash'])
            if position:
                mark = float(price or position['entry_price'])
                position_value = float(position['quantity']) * mark
                estimated_exit_fee = position_value * float(config['fee_rate'])
                unrealized = (
                    position_value - estimated_exit_fee - float(position['notional'])
                    - float(position['entry_fee'])
                )
                equity += position_value - estimated_exit_fee
            return {
                'running': self._running,
                'config': config,
                'state': state,
                'equity': round(equity, 8),
                'unrealized_pnl': round(unrealized, 8),
                'target_progress_pct': round(
                    max(0.0, state['monthly_realized_pnl'])
                    / float(config['monthly_profit_target']) * 100,
                    2,
                ),
            }

    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                self.run_cycle()
            except Exception as exc:
                with self._lock:
                    state = self.load_state()
                    state['last_error'] = str(exc)
                    state['last_signal'] = '行情获取或策略计算失败，稍后重试'
                    self.save_state(state)
                print(f'[模拟交易] 运行错误: {exc}')
            config = self.load_config()
            self._stop_event.wait(max(30, int(config['poll_seconds'])))
        self._running = False
