"""
indicators.py - 技术指标计算模块
封装 pandas-ta 的常用指标，提供统一的条件评估接口
支持 RSI、MACD、均线交叉、布林带、价格突破、成交量异动和自定义表达式
"""
import pandas as pd
import pandas_ta as ta


# ========================================
# 条件类型元数据定义
# ========================================
CONDITION_TYPES = {
    'smc': {
        'name': 'LuxAlgo - Smart Money Concepts',
        'description': 'Smart Money Concepts 智能货币概念技术指标警报',
        'params': [
            {
                'key': 'signal',
                'label': '信号类型',
                'type': 'select',
                'options': [
                    {'value': 'smc_internal_bullish_bos', 'label': 'Internal Bullish BOS (内部多头 BOS)'},
                    {'value': 'smc_internal_bullish_choch', 'label': 'Internal Bullish CHoCH (内部多头 CHoCH)'},
                    {'value': 'smc_internal_bearish_bos', 'label': 'Internal Bearish BOS (内部空头 BOS)'},
                    {'value': 'smc_internal_bearish_choch', 'label': 'Internal Bearish CHoCH (内部空头 CHoCH)'},
                    {'value': 'smc_bullish_bos', 'label': 'Swing Bullish BOS (波段多头 BOS)'},
                    {'value': 'smc_bullish_choch', 'label': 'Swing Bullish CHoCH (波段多头 CHoCH)'},
                    {'value': 'smc_bearish_bos', 'label': 'Swing Bearish BOS (波段空头 BOS)'},
                    {'value': 'smc_bearish_choch', 'label': 'Swing Bearish CHoCH (波段空头 CHoCH)'},
                    {'value': 'smc_bullish_internal_ob', 'label': 'Bullish Internal OB (内部多头 OB 突破)'},
                    {'value': 'smc_bearish_internal_ob', 'label': 'Bearish Internal OB (内部空头 OB 突破)'},
                    {'value': 'smc_bullish_swing_ob', 'label': 'Bullish Swing OB (波段多头 OB 突破)'},
                    {'value': 'smc_bearish_swing_ob', 'label': 'Bearish Swing OB (波段空头 OB 突破)'},
                    {'value': 'smc_equal_highs', 'label': 'Equal Highs (等高点 EQH)'},
                    {'value': 'smc_equal_lows', 'label': 'Equal Lows (等低点 EQL)'},
                    {'value': 'smc_bullish_fvg', 'label': 'Bullish FVG (看涨公允价值缺口)'},
                    {'value': 'smc_bearish_fvg', 'label': 'Bearish FVG (看跌公允价值缺口)'}
                ],
                'default': 'smc_internal_bullish_bos'
            }
        ]
    }
}


def get_condition_types():
    """返回所有可用的条件类型及其元数据"""
    return CONDITION_TYPES


# ========================================
# 条件评估引擎
# ========================================

def evaluate_condition(df, condition_type, params):
    """
    评估一个条件是否被触发
    
    Args:
        df: 包含 OHLCV 数据的 DataFrame (columns: open, high, low, close, volume)
        condition_type: 条件类型字符串
        params: 条件参数字典
    
    Returns:
        tuple: (triggered: bool, details: str)
    """
    if df is None or len(df) < 2:
        return False, "数据不足"

    try:
        handler = _HANDLERS.get(condition_type)
        if handler:
            return handler(df, params)
        return False, f"未知条件类型: {condition_type}"
    except Exception as e:
        return False, f"计算错误: {str(e)}"


# ========================================
# 各条件类型的处理函数
# ========================================

def _eval_rsi_above(df, params):
    length = int(params.get('length', 14))
    threshold = float(params.get('threshold', 70))
    rsi = df.ta.rsi(length=length)
    if rsi is None or rsi.empty or pd.isna(rsi.iloc[-1]):
        return False, "RSI 计算失败"
    current = rsi.iloc[-1]
    triggered = current > threshold
    return triggered, f"RSI({length}) = {current:.2f} {'>' if triggered else '≤'} {threshold}"


def _eval_rsi_below(df, params):
    length = int(params.get('length', 14))
    threshold = float(params.get('threshold', 30))
    rsi = df.ta.rsi(length=length)
    if rsi is None or rsi.empty or pd.isna(rsi.iloc[-1]):
        return False, "RSI 计算失败"
    current = rsi.iloc[-1]
    triggered = current < threshold
    return triggered, f"RSI({length}) = {current:.2f} {'<' if triggered else '≥'} {threshold}"


def _eval_macd_cross(df, params, direction='up'):
    fast = int(params.get('fast', 12))
    slow = int(params.get('slow', 26))
    signal = int(params.get('signal', 9))
    macd_df = df.ta.macd(fast=fast, slow=slow, signal=signal)

    if macd_df is None or macd_df.empty:
        return False, "MACD 计算失败"

    macd_col = f'MACD_{fast}_{slow}_{signal}'
    signal_col = f'MACDs_{fast}_{slow}_{signal}'

    # 兼容不同版本的列名
    if macd_col not in macd_df.columns:
        macd_cols = [c for c in macd_df.columns if c.startswith('MACD') and 'MACDs' not in c and 'MACDh' not in c]
        signal_cols = [c for c in macd_df.columns if c.startswith('MACDs')]
        if not macd_cols or not signal_cols:
            return False, "MACD 列名不匹配"
        macd_col = macd_cols[0]
        signal_col = signal_cols[0]

    macd_line = macd_df[macd_col]
    signal_line = macd_df[signal_col]

    if pd.isna(macd_line.iloc[-1]) or pd.isna(signal_line.iloc[-1]):
        return False, "MACD 值无效"
    if pd.isna(macd_line.iloc[-2]) or pd.isna(signal_line.iloc[-2]):
        return False, "MACD 前值无效"

    if direction == 'up':
        triggered = (macd_line.iloc[-1] > signal_line.iloc[-1]) and \
                    (macd_line.iloc[-2] <= signal_line.iloc[-2])
        label = '金叉' if triggered else '未交叉'
    else:
        triggered = (macd_line.iloc[-1] < signal_line.iloc[-1]) and \
                    (macd_line.iloc[-2] >= signal_line.iloc[-2])
        label = '死叉' if triggered else '未交叉'

    return triggered, f"MACD {label} (MACD={macd_line.iloc[-1]:.4f}, Signal={signal_line.iloc[-1]:.4f})"


def _eval_macd_cross_up(df, params):
    return _eval_macd_cross(df, params, direction='up')


def _eval_macd_cross_down(df, params):
    return _eval_macd_cross(df, params, direction='down')


def _eval_ma_cross(df, params, direction='up'):
    fast_len = int(params.get('fast_length', 5))
    slow_len = int(params.get('slow_length', 20))
    ma_type = params.get('ma_type', 'EMA')

    if ma_type == 'EMA':
        fast_ma = df.ta.ema(length=fast_len)
        slow_ma = df.ta.ema(length=slow_len)
    else:
        fast_ma = df.ta.sma(length=fast_len)
        slow_ma = df.ta.sma(length=slow_len)

    if fast_ma is None or slow_ma is None:
        return False, "均线计算失败"
    if pd.isna(fast_ma.iloc[-1]) or pd.isna(slow_ma.iloc[-1]):
        return False, "均线值无效"
    if pd.isna(fast_ma.iloc[-2]) or pd.isna(slow_ma.iloc[-2]):
        return False, "均线前值无效"

    if direction == 'up':
        triggered = (fast_ma.iloc[-1] > slow_ma.iloc[-1]) and \
                    (fast_ma.iloc[-2] <= slow_ma.iloc[-2])
        label = '上穿' if triggered else '未穿越'
    else:
        triggered = (fast_ma.iloc[-1] < slow_ma.iloc[-1]) and \
                    (fast_ma.iloc[-2] >= slow_ma.iloc[-2])
        label = '下穿' if triggered else '未穿越'

    return triggered, f"{ma_type}({fast_len}) {label} {ma_type}({slow_len})"


def _eval_ma_cross_up(df, params):
    return _eval_ma_cross(df, params, direction='up')


def _eval_ma_cross_down(df, params):
    return _eval_ma_cross(df, params, direction='down')


def _eval_bb_break(df, params, direction='upper'):
    length = int(params.get('length', 20))
    std = float(params.get('std', 2.0))
    bbands = df.ta.bbands(length=length, std=std)

    if bbands is None or bbands.empty:
        return False, "布林带计算失败"

    close = df['close'].iloc[-1]

    # 查找对应的列名（兼容不同命名格式）
    upper_col = lower_col = None
    for col in bbands.columns:
        if 'BBU' in col:
            upper_col = col
        elif 'BBL' in col:
            lower_col = col

    if direction == 'upper':
        if upper_col is None:
            return False, "布林上轨列未找到"
        upper = bbands[upper_col].iloc[-1]
        if pd.isna(upper):
            return False, "布林上轨值无效"
        triggered = close > upper
        return triggered, f"Close={close:.4f} {'>' if triggered else '≤'} BBU={upper:.4f}"
    else:
        if lower_col is None:
            return False, "布林下轨列未找到"
        lower = bbands[lower_col].iloc[-1]
        if pd.isna(lower):
            return False, "布林下轨值无效"
        triggered = close < lower
        return triggered, f"Close={close:.4f} {'<' if triggered else '≥'} BBL={lower:.4f}"


def _eval_bb_break_upper(df, params):
    return _eval_bb_break(df, params, direction='upper')


def _eval_bb_break_lower(df, params):
    return _eval_bb_break(df, params, direction='lower')


def _eval_price_above(df, params):
    price = float(params.get('price', 0))
    close = df['close'].iloc[-1]
    prev_close = df['close'].iloc[-2]
    # 只在上穿时触发（不是持续高于）
    triggered = close > price and prev_close <= price
    return triggered, f"Price={close:.4f} {'突破' if triggered else '未突破'} {price}"


def _eval_price_below(df, params):
    price = float(params.get('price', 0))
    close = df['close'].iloc[-1]
    prev_close = df['close'].iloc[-2]
    triggered = close < price and prev_close >= price
    return triggered, f"Price={close:.4f} {'跌破' if triggered else '未跌破'} {price}"


def _eval_volume_spike(df, params):
    length = int(params.get('length', 20))
    multiplier = float(params.get('multiplier', 2.0))
    vol_sma = df['volume'].rolling(length).mean()

    if pd.isna(vol_sma.iloc[-1]):
        return False, "成交量均值计算失败"

    current_vol = df['volume'].iloc[-1]
    avg_vol = vol_sma.iloc[-1]
    ratio = current_vol / avg_vol if avg_vol > 0 else 0
    triggered = ratio > multiplier
    return triggered, f"Vol={current_vol:.0f} ({ratio:.1f}x avg) {'>' if triggered else '≤'} {multiplier}x"


class PineSeries:
    """
    PineSeries 包装 pandas.Series，支持像 Pine Script 那样访问：
    series[0] 表示当前 Bar (最新值)
    series[1] 表示前 1 个 Bar (前一个值)
    以此类推。同时支持数值运算和逻辑比对。
    """
    def __init__(self, series):
        self._series = series
    
    def __getitem__(self, key):
        if isinstance(key, int):
            idx = -1 - key
            if idx < -len(self._series) or idx >= len(self._series):
                return float('nan')
            return float(self._series.iloc[idx])
        raise TypeError("索引必须是整数")
        
    def __float__(self):
        if self._series is None or self._series.empty:
            return float('nan')
        return float(self._series.iloc[-1])
        
    def __lt__(self, other):
        return float(self) < float(other)
    def __le__(self, other):
        return float(self) <= float(other)
    def __gt__(self, other):
        return float(self) > float(other)
    def __ge__(self, other):
        return float(self) >= float(other)
    def __eq__(self, other):
        return float(self) == float(other)
    def __ne__(self, other):
        return float(self) != float(other)
        
    def __add__(self, other): return float(self) + float(other)
    def __radd__(self, other): return float(other) + float(self)
    def __sub__(self, other): return float(self) - float(other)
    def __rsub__(self, other): return float(other) - float(self)
    def __mul__(self, other): return float(self) * float(other)
    def __rmul__(self, other): return float(other) * float(self)
    def __truediv__(self, other): return float(self) / float(other)
    def __rtruediv__(self, other): return float(other) / float(self)
    
    def __repr__(self):
        return str(float(self))


def _eval_custom(df, params):
    """评估用户自定义的 Python 表达式或脚本"""
    expression = params.get('expression', '').strip()
    if not expression:
        return False, "表达式为空"

    try:
        # 包装 Series
        close = PineSeries(df['close'])
        high = PineSeries(df['high'])
        low = PineSeries(df['low'])
        open_ser = PineSeries(df['open'])
        volume = PineSeries(df['volume'])
        
        # 兼容旧表达式的 prev_close 变量
        prev_close = df['close'].iloc[-2] if len(df) > 1 else df['close'].iloc[-1]

        def get_series(x):
            if isinstance(x, PineSeries):
                return x._series
            if isinstance(x, pd.Series):
                return x
            return pd.Series(x, index=df.index)

        def rsi(arg1, arg2=None):
            if arg2 is None:
                src = close
                length = int(arg1)
            else:
                src = arg1
                length = int(arg2)
            res = ta.rsi(get_series(src), length=length)
            return PineSeries(res)

        def sma(arg1, arg2=None):
            if arg2 is None:
                src = close
                length = int(arg1)
            else:
                src = arg1
                length = int(arg2)
            res = ta.sma(get_series(src), length=length)
            return PineSeries(res)

        def ema(arg1, arg2=None):
            if arg2 is None:
                src = close
                length = int(arg1)
            else:
                src = arg1
                length = int(arg2)
            res = ta.ema(get_series(src), length=length)
            return PineSeries(res)

        def wma(arg1, arg2=None):
            if arg2 is None:
                src = close
                length = int(arg1)
            else:
                src = arg1
                length = int(arg2)
            res = ta.wma(get_series(src), length=length)
            return PineSeries(res)

        def hma(arg1, arg2=None):
            if arg2 is None:
                src = close
                length = int(arg1)
            else:
                src = arg1
                length = int(arg2)
            res = ta.hma(get_series(src), length=length)
            return PineSeries(res)

        def macd(arg1, arg2=None, arg3=None, arg4=None):
            if arg2 is None:
                src = close
                fast, slow, signal = 12, 26, 9
            else:
                src = arg1
                fast = int(arg2)
                slow = int(arg3) if arg3 is not None else 26
                signal = int(arg4) if arg4 is not None else 9
            res = ta.macd(get_series(src), fast=fast, slow=slow, signal=signal)
            if res is None or res.empty:
                nan_series = pd.Series([float('nan')] * len(df), index=df.index)
                return PineSeries(nan_series), PineSeries(nan_series), PineSeries(nan_series)
            macd_col = [c for c in res.columns if 'MACD' in c and 's' not in c and 'h' not in c][0]
            sig_col = [c for c in res.columns if 'MACDs' in c][0]
            hist_col = [c for c in res.columns if 'MACDh' in c][0]
            return PineSeries(res[macd_col]), PineSeries(res[sig_col]), PineSeries(res[hist_col])

        def bb(arg1, arg2=None, arg3=None):
            if arg2 is None:
                src = close
                length = 20
                std = 2.0
            elif arg3 is None:
                if isinstance(arg1, PineSeries) or isinstance(arg1, pd.Series):
                    src = arg1
                    length = int(arg2)
                    std = 2.0
                else:
                    src = close
                    length = int(arg1)
                    std = float(arg2)
            else:
                src = arg1
                length = int(arg2)
                std = float(arg3)
            res = ta.bbands(get_series(src), length=length, std=std)
            if res is None or res.empty:
                nan_series = pd.Series([float('nan')] * len(df), index=df.index)
                return PineSeries(nan_series), PineSeries(nan_series), PineSeries(nan_series)
            bbl_col = [c for c in res.columns if 'BBL' in c][0]
            bbm_col = [c for c in res.columns if 'BBM' in c][0]
            bbu_col = [c for c in res.columns if 'BBU' in c][0]
            return PineSeries(res[bbm_col]), PineSeries(res[bbu_col]), PineSeries(res[bbl_col])

        def crossover(x, y):
            x_curr = x[0] if isinstance(x, PineSeries) else float(x)
            x_prev = x[1] if isinstance(x, PineSeries) else float(x)
            y_curr = y[0] if isinstance(y, PineSeries) else float(y)
            y_prev = y[1] if isinstance(y, PineSeries) else float(y)
            return x_curr > y_curr and x_prev <= y_prev

        def crossunder(x, y):
            x_curr = x[0] if isinstance(x, PineSeries) else float(x)
            x_prev = x[1] if isinstance(x, PineSeries) else float(x)
            y_curr = y[0] if isinstance(y, PineSeries) else float(y)
            y_prev = y[1] if isinstance(y, PineSeries) else float(y)
            return x_curr < y_curr and x_prev >= y_prev

        # 构建安全的命名空间
        namespace = {
            'close': close,
            'high': high,
            'low': low,
            'open': open_ser,
            'volume': volume,
            'prev_close': prev_close,
            'rsi': rsi,
            'RSI': rsi,
            'sma': sma,
            'SMA': sma,
            'ema': ema,
            'EMA': ema,
            'wma': wma,
            'WMA': wma,
            'hma': hma,
            'HMA': hma,
            'macd': macd,
            'MACD': macd,
            'bb': bb,
            'BB': bb,
            'crossover': crossover,
            'crossunder': crossunder,
            'abs': abs,
            'min': min,
            'max': max,
            'round': round,
        }

        # 兼容旧的 MACD 大写命名空间（针对 12_26_9 的默认值）
        macd_df = df.ta.macd()
        if macd_df is not None and not macd_df.empty:
            for col in macd_df.columns:
                if col.startswith('MACD_') and 'MACDs' not in col and 'MACDh' not in col:
                    namespace['MACD_VAL'] = macd_df[col].iloc[-1]
                elif 'MACDs' in col:
                    namespace['MACD_SIGNAL'] = macd_df[col].iloc[-1]
                elif 'MACDh' in col:
                    namespace['MACD_HIST'] = macd_df[col].iloc[-1]
        
        if 'MACD_VAL' in namespace:
            namespace['MACD_DEFAULT'] = namespace['MACD_VAL']

        # 安全执行表达式/脚本
        is_script = '\n' in expression or ('=' in expression and '==' not in expression and '!=' not in expression and '<=' not in expression and '>=' not in expression)
        
        if is_script:
            exec(expression, {"__builtins__": {}}, namespace)
            # 寻找触发条件变量
            target_keys = ['trigger', 'signal', 'cond', 'buy', 'sell', 'buySignal', 'sellSignal', 'condition']
            trigger_val = None
            for key in target_keys:
                if key in namespace:
                    trigger_val = namespace[key]
                    break
            else:
                # 获取最后定义的一个变量（排除内置 key）
                initial_keys = {'close', 'high', 'low', 'open', 'volume', 'prev_close', 'rsi', 'RSI', 'sma', 'SMA', 'ema', 'EMA', 'wma', 'WMA', 'hma', 'HMA', 'macd', 'MACD', 'bb', 'BB', 'crossover', 'crossunder', 'abs', 'min', 'max', 'round', 'MACD_VAL', 'MACD_SIGNAL', 'MACD_HIST', 'MACD_DEFAULT'}
                defined_keys = [k for k in namespace.keys() if k not in initial_keys]
                if defined_keys:
                    trigger_val = namespace[defined_keys[-1]]
                else:
                    return False, "未定义任何变量或触发条件"
            return bool(trigger_val), f"脚本执行成功, 触发状态: {trigger_val}"
        else:
            result = eval(expression, {"__builtins__": {}}, namespace)
            return bool(result), f"表达式结果: {result}"
    except Exception as e:
        return False, f"计算错误: {str(e)}"


# ========================================
# LuxAlgo Smart Money Concepts (SMC) 计算
# ========================================

def simulate_structure(df, L):
    """
    模拟 LuxAlgo SMC 的 Swing/Internal 结构（BOS、CHoCH、Order Blocks）
    L: 窗口半径 (Swing=50, Internal=5)
    """
    n = len(df)
    high = df['high']
    low = df['low']
    close = df['close']
    open_p = df['open']
    
    ph = [None] * n
    pl = [None] * n
    for i in range(L, n - L):
        val_h = high.iloc[i]
        is_ph = True
        for j in range(i - L, i + L + 1):
            if high.iloc[j] > val_h:
                is_ph = False
                break
        if is_ph:
            ph[i] = val_h
            
        val_l = low.iloc[i]
        is_pl = True
        for j in range(i - L, i + L + 1):
            if low.iloc[j] < val_l:
                is_pl = False
                break
        if is_pl:
            pl[i] = val_l

    bos_bull = [False] * n
    bos_bear = [False] * n
    choch_bull = [False] * n
    choch_bear = [False] * n
    
    active_phs = [] # 存储多头结构线: {'val': float, 'idx': int}
    active_pls = [] # 存储空头结构线: {'val': float, 'idx': int}
    
    trend = 0  # 1: 多头, -1: 空头
    
    obs = []
    ob_bull_triggered = [False] * n
    ob_bear_triggered = [False] * n

    for t in range(n):
        confirmed_idx = t - L
        if confirmed_idx >= 0:
            if ph[confirmed_idx] is not None:
                active_phs.append({'val': ph[confirmed_idx], 'idx': confirmed_idx})
            if pl[confirmed_idx] is not None:
                active_pls.append({'val': pl[confirmed_idx], 'idx': confirmed_idx})
                
        if t > 0:
            c_close = close.iloc[t]
            p_close = close.iloc[t-1]
            
            # 多头结构突破 (BOS / CHoCH)
            triggered_bull = False
            broken_phs = []
            for ph_item in active_phs:
                ph_val = ph_item['val']
                if c_close > ph_val and p_close <= ph_val:
                    triggered_bull = True
                    broken_phs.append(ph_item)
            
            if triggered_bull:
                if trend == -1 or trend == 0:
                    choch_bull[t] = True
                    trend = 1
                else:
                    bos_bull[t] = True
                
                # 形成多头 OB
                for ph_item in broken_phs:
                    ph_idx = ph_item['idx']
                    if ph_idx < t:
                        ob_range_lows = low.iloc[ph_idx:t]
                        min_idx = ob_range_lows.idxmin()
                        obs.append({
                            'high': high.loc[min_idx],
                            'low': low.loc[min_idx],
                            'bias': 1
                        })
                
                # 从活跃高点列表中移除已突破的高点
                active_phs = [p for p in active_phs if p not in broken_phs]
                
            # 空头结构跌破 (BOS / CHoCH)
            triggered_bear = False
            broken_pls = []
            for pl_item in active_pls:
                pl_val = pl_item['val']
                if c_close < pl_val and p_close >= pl_val:
                    triggered_bear = True
                    broken_pls.append(pl_item)
            
            if triggered_bear:
                if trend == 1 or trend == 0:
                    choch_bear[t] = True
                    trend = -1
                else:
                    bos_bear[t] = True
                
                # 形成空头 OB
                for pl_item in broken_pls:
                    pl_idx = pl_item['idx']
                    if pl_idx < t:
                        ob_range_highs = high.iloc[pl_idx:t]
                        max_idx = ob_range_highs.idxmax()
                        obs.append({
                            'high': high.loc[max_idx],
                            'low': low.loc[max_idx],
                            'bias': -1
                        })
                
                # 从活跃低点列表中移除已跌破的低点
                active_pls = [p for p in active_pls if p not in broken_pls]

            # 评估订单块 (OB) 触碰/突破
            still_active_obs = []
            for ob in obs:
                if ob['bias'] == 1:
                    # 多头 OB 支撑测试且收阳线
                    if c_close < ob['low']:
                        continue  # 被跌破，失效
                    if low.iloc[t] <= ob['high'] and c_close >= ob['low'] and c_close > open_p.iloc[t]:
                        ob_bull_triggered[t] = True
                else:
                    # 空头 OB 阻力测试且收阴线
                    if c_close > ob['high']:
                        continue  # 被突破，失效
                    if high.iloc[t] >= ob['low'] and c_close <= ob['high'] and c_close < open_p.iloc[t]:
                        ob_bear_triggered[t] = True
                still_active_obs.append(ob)
            obs = still_active_obs
            
    return bos_bull, bos_bear, choch_bull, choch_bear, ob_bull_triggered, ob_bear_triggered


def find_equal_highs_lows(df, threshold_atr_mult=0.1):
    """
    寻找等高点 (EQH) 和等低点 (EQL)
    """
    atr = ta.atr(df['high'], df['low'], df['close'], length=14)
    if atr is None or atr.empty:
        atr = (df['high'] - df['low']).rolling(14).mean()
        
    eqh = [False] * len(df)
    eql = [False] * len(df)
    
    L = 3
    ph3 = [None] * len(df)
    pl3 = [None] * len(df)
    for i in range(L, len(df) - L):
        window_high = df['high'].iloc[i-L : i+L+1]
        if df['high'].iloc[i] == window_high.max():
            ph3[i] = df['high'].iloc[i]
        window_low = df['low'].iloc[i-L : i+L+1]
        if df['low'].iloc[i] == window_low.min():
            pl3[i] = df['low'].iloc[i]
            
    last_confirmed_ph = None
    last_confirmed_pl = None
    for t in range(len(df)):
        confirmed_idx = t - L
        if confirmed_idx >= 0:
            if pl3[confirmed_idx] is not None:
                current_pl = pl3[confirmed_idx]
                if last_confirmed_pl is not None:
                    diff = abs(current_pl - last_confirmed_pl)
                    limit = threshold_atr_mult * (atr.iloc[t] if not pd.isna(atr.iloc[t]) else (df['high'].iloc[t] - df['low'].iloc[t]))
                    if diff < limit:
                        eql[t] = True
                last_confirmed_pl = current_pl
            
            if ph3[confirmed_idx] is not None:
                current_ph = ph3[confirmed_idx]
                if last_confirmed_ph is not None:
                    diff = abs(current_ph - last_confirmed_ph)
                    limit = threshold_atr_mult * (atr.iloc[t] if not pd.isna(atr.iloc[t]) else (df['high'].iloc[t] - df['low'].iloc[t]))
                    if diff < limit:
                        eqh[t] = True
                last_confirmed_ph = current_ph
                
    return eqh, eql


def _get_smc_results(df):
    """
    计算 SMC 指标并缓存，避免重复计算
    """
    if '_smc_cache' in df.attrs:
        return df.attrs['_smc_cache']
        
    # 计算 Swing 结构 (L = 50)
    swing_bos_bull, swing_bos_bear, swing_choch_bull, swing_choch_bear, swing_ob_bull, swing_ob_bear = simulate_structure(df, 50)
    
    # 计算 Internal 结构 (L = 5)
    int_bos_bull, int_bos_bear, int_choch_bull, int_choch_bear, int_ob_bull, int_ob_bear = simulate_structure(df, 5)
    
    # 计算 EQH/EQL (L = 3)
    eqh, eql = find_equal_highs_lows(df, threshold_atr_mult=0.1)
    
    # 计算 FVG
    bull_fvg = (df['low'] > df['high'].shift(2)) & (df['close'].shift(1) > df['open'].shift(1))
    bear_fvg = (df['high'] < df['low'].shift(2)) & (df['close'].shift(1) < df['open'].shift(1))
    
    cache = {
        'smc_internal_bullish_bos': int_bos_bull,
        'smc_internal_bearish_bos': int_bos_bear,
        'smc_internal_bullish_choch': int_choch_bull,
        'smc_internal_bearish_choch': int_choch_bear,
        
        'smc_bullish_bos': swing_bos_bull,
        'smc_bearish_bos': swing_bos_bear,
        'smc_bullish_choch': swing_choch_bull,
        'smc_bearish_choch': swing_choch_bear,
        
        'smc_bullish_internal_ob': int_ob_bull,
        'smc_bearish_internal_ob': int_ob_bear,
        'smc_bullish_swing_ob': swing_ob_bull,
        'smc_bearish_swing_ob': swing_ob_bear,
        
        'smc_equal_highs': eqh,
        'smc_equal_lows': eql,
        
        'smc_bullish_fvg': bull_fvg,
        'smc_bearish_fvg': bear_fvg
    }
    
    # 转为 bool 类型的 Series
    for k in cache:
        cache[k] = pd.Series(cache[k], index=df.index).fillna(False).astype(bool)
        
    df.attrs['_smc_cache'] = cache
    return cache


def _eval_smc(df, params):
    """
    SMC 综合指标评估
    """
    signal = params.get('signal', 'smc_internal_bullish_bos')
    cache = _get_smc_results(df)
    series = cache.get(signal)
    if series is None or series.empty:
        return False, "SMC 计算失败"
    triggered = bool(series.iloc[-1])
    
    # 信号人性化名称映射
    signal_labels = {
        'smc_internal_bullish_bos': 'Internal Bullish BOS',
        'smc_internal_bullish_choch': 'Internal Bullish CHoCH',
        'smc_internal_bearish_bos': 'Internal Bearish BOS',
        'smc_internal_bearish_choch': 'Internal Bearish CHoCH',
        'smc_bullish_bos': 'Swing Bullish BOS',
        'smc_bullish_choch': 'Swing Bullish CHoCH',
        'smc_bearish_bos': 'Swing Bearish BOS',
        'smc_bearish_choch': 'Swing Bearish CHoCH',
        'smc_bullish_internal_ob': 'Bullish Internal OB',
        'smc_bearish_internal_ob': 'Bearish Internal OB',
        'smc_bullish_swing_ob': 'Bullish Swing OB',
        'smc_bearish_swing_ob': 'Bearish Swing OB',
        'smc_equal_highs': 'Equal Highs (EQH)',
        'smc_equal_lows': 'Equal Lows (EQL)',
        'smc_bullish_fvg': 'Bullish FVG',
        'smc_bearish_fvg': 'Bearish FVG',
    }
    
    label = signal_labels.get(signal, signal)
    price = df['close'].iloc[-1]
    
    if triggered:
        return True, f"SMC 触发: {label} (价格: {price})"
        
    return False, f"未触发 {label}"


# 条件类型 -> 处理函数的映射
_HANDLERS = {
    'rsi_above': _eval_rsi_above,
    'rsi_below': _eval_rsi_below,
    'macd_cross_up': _eval_macd_cross_up,
    'macd_cross_down': _eval_macd_cross_down,
    'ma_cross_up': _eval_ma_cross_up,
    'ma_cross_down': _eval_ma_cross_down,
    'bb_break_upper': _eval_bb_break_upper,
    'bb_break_lower': _eval_bb_break_lower,
    'price_above': _eval_price_above,
    'price_below': _eval_price_below,
    'volume_spike': _eval_volume_spike,
    'custom': _eval_custom,
    
    # 注册 SMC 综合处理函数
    'smc': _eval_smc,
    
    # 兼容直接注册的 16 个 SMC 子信号
    'smc_internal_bullish_bos': lambda df, p: _eval_smc(df, {'signal': 'smc_internal_bullish_bos'}),
    'smc_internal_bullish_choch': lambda df, p: _eval_smc(df, {'signal': 'smc_internal_bullish_choch'}),
    'smc_internal_bearish_bos': lambda df, p: _eval_smc(df, {'signal': 'smc_internal_bearish_bos'}),
    'smc_internal_bearish_choch': lambda df, p: _eval_smc(df, {'signal': 'smc_internal_bearish_choch'}),
    'smc_bullish_bos': lambda df, p: _eval_smc(df, {'signal': 'smc_bullish_bos'}),
    'smc_bullish_choch': lambda df, p: _eval_smc(df, {'signal': 'smc_bullish_choch'}),
    'smc_bearish_bos': lambda df, p: _eval_smc(df, {'signal': 'smc_bearish_bos'}),
    'smc_bearish_choch': lambda df, p: _eval_smc(df, {'signal': 'smc_bearish_choch'}),
    'smc_bullish_internal_ob': lambda df, p: _eval_smc(df, {'signal': 'smc_bullish_internal_ob'}),
    'smc_bearish_internal_ob': lambda df, p: _eval_smc(df, {'signal': 'smc_bearish_internal_ob'}),
    'smc_bullish_swing_ob': lambda df, p: _eval_smc(df, {'signal': 'smc_bullish_swing_ob'}),
    'smc_bearish_swing_ob': lambda df, p: _eval_smc(df, {'signal': 'smc_bearish_swing_ob'}),
    'smc_equal_highs': lambda df, p: _eval_smc(df, {'signal': 'smc_equal_highs'}),
    'smc_equal_lows': lambda df, p: _eval_smc(df, {'signal': 'smc_equal_lows'}),
    'smc_bullish_fvg': lambda df, p: _eval_smc(df, {'signal': 'smc_bullish_fvg'}),
    'smc_bearish_fvg': lambda df, p: _eval_smc(df, {'signal': 'smc_bearish_fvg'}),
}
