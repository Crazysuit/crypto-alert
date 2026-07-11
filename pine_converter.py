import re

def convert_pine_to_python(pine_code: str) -> str:
    """
    将 TradingView Pine Script 代码翻译为自定义 Python 表达式/脚本。
    """
    lines = pine_code.split('\n')
    output_lines = []
    
    # 记录脚本中的变量赋值
    assigned_vars = []
    
    for line in lines:
        line_strip = line.strip()
        
        # 1. 过滤注释和编译器指令
        if not line_strip or line_strip.startswith('//@') or line_strip.startswith('//'):
            continue
            
        # 移除行尾注释 (例如 x = 1 // 默认值)
        if '//' in line:
            line = line.split('//')[0]
            line_strip = line.strip()
            
        # 2. 忽略不需要的声明/绘图/策略函数
        if re.match(r'^(indicator|strategy|plot|plotshape|plotchar|plotarrow|alertcondition|alert|fill|bgcolor|barcolor|hline)\b', line_strip):
            # 特殊处理 alertcondition 函数，提取出触发条件
            # alertcondition(condition, title, message)
            alert_match = re.search(r'alertcondition\(([^,)]+)', line_strip)
            if alert_match:
                cond_var = alert_match.group(1).strip()
                output_lines.append(f"trigger = {cond_var}")
            continue

        # 3. 替换逻辑操作符
        # 替换 && 为 and, || 为 or
        line = re.sub(r'\b&&\b', ' and ', line)
        line = re.sub(r'\b\|\|\b', ' or ', line)
        # 替换 ! 为 not (注意避开 !=)
        line = re.sub(r'!(?!=)', 'not ', line)
        
        # 4. 替换赋值操作符 := 为 =
        line = line.replace(':=', '=')
        
        # 5. 替换 Pine 库命名空间
        line = line.replace('ta.rsi', 'rsi')
        line = line.replace('ta.sma', 'sma')
        line = line.replace('ta.ema', 'ema')
        line = line.replace('ta.wma', 'wma')
        line = line.replace('ta.hma', 'hma')
        line = line.replace('ta.macd', 'macd')
        line = line.replace('ta.bb', 'bb')
        line = line.replace('ta.crossover', 'crossover')
        line = line.replace('ta.crossunder', 'crossunder')
        
        line = line.replace('math.abs', 'abs')
        line = line.replace('math.min', 'min')
        line = line.replace('math.max', 'max')
        line = line.replace('math.round', 'round')

        # 6. 检测变量赋值并记录变量名
        # 例如: x = rsi(close, 14)
        assign_match = re.match(r'^([\w_]+)\s*=', line.strip())
        if assign_match:
            var_name = assign_match.group(1)
            if var_name not in assigned_vars:
                assigned_vars.append(var_name)

        output_lines.append(line.strip())

    # 检查是否已定义显式触发条件
    has_trigger = any(re.match(r'^(trigger|signal|cond|buy|sell|buySignal|sellSignal|condition)\b', l) for l in output_lines)
    
    if output_lines and not has_trigger:
        # 寻找已定义变量中的买卖/信号标识作为 trigger
        potential_triggers = ['buySignal', 'sellSignal', 'buy', 'sell', 'signal', 'cond', 'condition', 'trigger']
        found_trigger = None
        for pt in potential_triggers:
            if pt in assigned_vars:
                found_trigger = pt
                break
        
        if found_trigger:
            output_lines.append(f"trigger = {found_trigger}")
        elif assigned_vars:
            # 默认将最后一个赋值的变量作为 trigger
            output_lines.append(f"trigger = {assigned_vars[-1]}")
            
    return '\n'.join(output_lines)
