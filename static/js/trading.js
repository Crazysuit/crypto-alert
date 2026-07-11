(() => {
    'use strict';

    const $ = (id) => document.getElementById(id);
    let initialized = false;

    async function api(path, options = {}) {
        const response = await fetch(`/api/trading/${path}`, {
            headers: { 'Content-Type': 'application/json' },
            ...options,
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
        return data;
    }

    function number(value, digits = 2) {
        const n = Number(value);
        return Number.isFinite(n) ? n.toFixed(digits) : '—';
    }

    function setPnl(element, value) {
        const n = Number(value || 0);
        element.textContent = `${n >= 0 ? '+' : ''}${n.toFixed(2)} USDT`;
        element.classList.toggle('positive', n > 0);
        element.classList.toggle('negative', n < 0);
    }

    function fillConfig(config) {
        if (initialized) return;
        $('symbol').value = config.symbol;
        $('timeframe').value = config.timeframe;
        $('stopLoss').value = number(config.stop_loss_pct * 100, 1);
        $('takeProfit').value = number(config.take_profit_pct * 100, 1);
        $('riskPerTrade').value = number(config.risk_per_trade_pct * 100, 1);
        $('maxPosition').value = number(config.max_position_pct * 100, 0);
        $('dailyLoss').value = number(config.max_daily_loss, 1);
        $('monthlyTarget').value = number(config.monthly_profit_target, 0);
        initialized = true;
    }

    function render(data) {
        const { running, config, state } = data;
        fillConfig(config);
        $('runStatus').textContent = running ? '运行中' : '已停止';
        $('runStatus').className = running ? 'positive' : '';
        $('lastSignal').textContent = state.last_error || state.last_signal || '—';
        $('equity').textContent = number(data.equity);
        setPnl($('monthlyPnl'), state.monthly_realized_pnl);
        setPnl($('dailyPnl'), state.daily_realized_pnl);
        setPnl($('totalPnl'), state.realized_pnl);
        setPnl($('unrealizedPnl'), data.unrealized_pnl);
        $('cash').textContent = number(state.cash);
        $('currentPrice').textContent = state.current_price == null ? '—' : number(state.current_price, 4);
        $('tradeCount').textContent = state.trade_count || 0;
        $('updatedAt').textContent = state.updated_at ? new Date(state.updated_at).toLocaleString() : '—';

        document.querySelectorAll('#configForm input, #configForm select').forEach((el) => {
            el.disabled = running;
        });
        $('startBtn').disabled = running;
        $('stopBtn').disabled = !running;
        $('resetBtn').disabled = running;

        if (state.position) {
            const p = state.position;
            $('positionEmpty').classList.add('hidden');
            $('positionDetails').classList.remove('hidden');
            $('positionSymbol').textContent = p.symbol;
            $('positionQty').textContent = number(p.quantity, 8);
            $('entryPrice').textContent = number(p.entry_price, 4);
            $('stopPrice').textContent = number(p.stop_price, 4);
            $('takePrice').textContent = number(p.take_profit_price, 4);
        } else {
            $('positionEmpty').classList.remove('hidden');
            $('positionDetails').classList.add('hidden');
        }
    }

    function renderHistory(items) {
        const body = $('historyBody');
        if (!items.length) {
            body.innerHTML = '<tr><td colspan="8" class="empty-row">暂无模拟成交</td></tr>';
            return;
        }
        body.innerHTML = items.slice().reverse().map((item) => {
            const side = item.side === 'buy' ? '买入' : '卖出';
            const pnlClass = item.pnl > 0 ? 'positive' : item.pnl < 0 ? 'negative' : '';
            return `<tr>
                <td>${new Date(item.timestamp).toLocaleString()}</td>
                <td class="${item.side === 'buy' ? 'positive' : 'negative'}">${side}</td>
                <td>${item.symbol}</td><td>${number(item.price, 4)}</td>
                <td>${number(item.quantity, 8)}</td><td>${number(item.fee, 4)}</td>
                <td class="${pnlClass}">${item.pnl >= 0 ? '+' : ''}${number(item.pnl)}</td>
                <td>${item.reason}</td>
            </tr>`;
        }).join('');
    }

    function configPayload() {
        return {
            symbol: $('symbol').value,
            timeframe: $('timeframe').value,
            stop_loss_pct: Number($('stopLoss').value) / 100,
            take_profit_pct: Number($('takeProfit').value) / 100,
            risk_per_trade_pct: Number($('riskPerTrade').value) / 100,
            max_position_pct: Number($('maxPosition').value) / 100,
            max_daily_loss: Number($('dailyLoss').value),
            monthly_profit_target: Number($('monthlyTarget').value),
        };
    }

    async function refresh() {
        try {
            const [status, history] = await Promise.all([api('status'), api('history?limit=100')]);
            render(status);
            renderHistory(history);
            $('errorText').textContent = '';
        } catch (error) {
            $('errorText').textContent = error.message;
        }
    }

    $('startBtn').addEventListener('click', async () => {
        try {
            await api('config', { method: 'PUT', body: JSON.stringify(configPayload()) });
            await api('start', { method: 'POST' });
            await refresh();
        } catch (error) { $('errorText').textContent = error.message; }
    });
    $('stopBtn').addEventListener('click', async () => {
        try { await api('stop', { method: 'POST' }); await refresh(); }
        catch (error) { $('errorText').textContent = error.message; }
    });
    $('resetBtn').addEventListener('click', async () => {
        if (!window.confirm('确认清空全部模拟成交和盈亏，并恢复为 200 USDT？')) return;
        try { await api('reset', { method: 'POST' }); await refresh(); }
        catch (error) { $('errorText').textContent = error.message; }
    });

    refresh();
    setInterval(refresh, 10000);
})();
