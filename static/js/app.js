/* ═══════════════════════════════════════════════════════════════
   CryptoAlert — Frontend Application
   Gate.io 智能监控系统
   Vanilla ES6+ · Socket.IO · Web Audio API
   ═══════════════════════════════════════════════════════════════ */

(() => {
    'use strict';

    // ── Theme Init ─────────────────────────────────────────────
    const currentTheme = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', currentTheme);

    // ── State ──────────────────────────────────────────────────
    const state = {
        alerts: [],
        conditions: {},
        symbols: [],
        prices: {},          // { symbol: { price, high, low, open, volume, timestamp } }
        prevPrices: {},      // previous prices for flash direction
        historyEntries: [],
        connected: false,
    };

    // ── DOM Cache ──────────────────────────────────────────────
    const $ = (sel, ctx = document) => ctx.querySelector(sel);
    const $$ = (sel, ctx = document) => ctx.querySelectorAll(sel);

    const dom = {
        connectionStatus: $('#connectionStatus'),
        statusDot:        $('#connectionStatus .status-dot'),
        statusLabel:      $('#connectionStatus .status-label'),
        priceTicker:      $('#priceTicker'),
        alertList:        $('#alertList'),
        alertCount:       $('#alertCount'),
        historyList:      $('#historyList'),
        historyCount:     $('#historyCount'),

        // Alert Modal
        alertModal:       $('#alertModal'),
        modalTitle:       $('#modalTitle'),
        alertForm:        $('#alertForm'),
        alertId:          $('#alertId'),
        alertSymbol:      $('#alertSymbol'),
        alertTimeframe:   $('#alertTimeframe'),
        alertCondition:   $('#alertCondition'),
        conditionDesc:    $('#conditionDesc'),
        dynamicParams:    $('#dynamicParams'),
        alertMessage:     $('#alertMessage'),
        alertCooldown:    $('#alertCooldown'),
        btnSubmitLabel:   $('#btnSubmitLabel'),

        // Pine Modal
        pineModal:        $('#pineModal'),

        // Email Modal
        emailModal:       $('#emailModal'),
        emailForm:        $('#emailForm'),
        emailEnabled:     $('#emailEnabled'),
        emailSmtpServer:  $('#emailSmtpServer'),
        emailSmtpPort:    $('#emailSmtpPort'),
        emailUseSsl:      $('#emailUseSsl'),
        emailSender:      $('#emailSender'),
        emailPassword:    $('#emailPassword'),
        emailReceiver:    $('#emailReceiver'),
        emailStartTime:   $('#emailStartTime'),
        emailEndTime:     $('#emailEndTime'),

        // Toasts
        toastContainer:   $('#toastContainer'),
    };

    // ══════════════════════════════════════════════════════════
    //  UTILITIES
    // ══════════════════════════════════════════════════════════

    /** Format a number with appropriate decimals */
    function formatPrice(price) {
        if (price == null) return '—';
        const p = parseFloat(price);
        if (p >= 1000) return p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        if (p >= 1) return p.toFixed(4);
        if (p >= 0.01) return p.toFixed(6);
        return p.toFixed(8);
    }

    /** Format symbol for display: BTC_USDT → BTC/USDT */
    function displaySymbol(s) {
        return s ? s.replace('_', '/') : s;
    }

    /** Format ISO timestamp to friendly string */
    function formatTime(ts) {
        if (!ts) return '';
        const d = new Date(ts);
        if (isNaN(d.getTime())) return ts;
        const now = new Date();
        const diff = (now - d) / 1000;
        if (diff < 60) return '刚刚';
        if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
        if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
        const pad = n => String(n).padStart(2, '0');
        return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    }

    /** Simple HTML escaping */
    function esc(str) {
        const el = document.createElement('span');
        el.textContent = str ?? '';
        return el.innerHTML;
    }

    /** Show toast notification */
    function toast(message, type = 'info', duration = 4000) {
        const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
        const el = document.createElement('div');
        el.className = `toast ${type}`;
        el.innerHTML = `<span class="toast-icon">${icons[type] || icons.info}</span><span>${esc(message)}</span>`;
        dom.toastContainer.appendChild(el);
        setTimeout(() => {
            el.classList.add('out');
            setTimeout(() => el.remove(), 350);
        }, duration);
    }

    // ── Web Audio API beep ─────────────────────────────────────
    let audioCtx = null;

    function playAlertSound() {
        try {
            if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            const osc = audioCtx.createOscillator();
            const gain = audioCtx.createGain();
            osc.connect(gain);
            gain.connect(audioCtx.destination);
            osc.type = 'sine';
            osc.frequency.setValueAtTime(880, audioCtx.currentTime);
            osc.frequency.exponentialRampToValueAtTime(440, audioCtx.currentTime + 0.15);
            gain.gain.setValueAtTime(0.18, audioCtx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.4);
            osc.start(audioCtx.currentTime);
            osc.stop(audioCtx.currentTime + 0.4);
            // second beep
            const osc2 = audioCtx.createOscillator();
            const gain2 = audioCtx.createGain();
            osc2.connect(gain2);
            gain2.connect(audioCtx.destination);
            osc2.type = 'sine';
            osc2.frequency.setValueAtTime(1100, audioCtx.currentTime + 0.2);
            osc2.frequency.exponentialRampToValueAtTime(660, audioCtx.currentTime + 0.35);
            gain2.gain.setValueAtTime(0.15, audioCtx.currentTime + 0.2);
            gain2.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.55);
            osc2.start(audioCtx.currentTime + 0.2);
            osc2.stop(audioCtx.currentTime + 0.55);
        } catch (e) { /* ignore audio errors */ }
    }

    // ══════════════════════════════════════════════════════════
    //  API HELPERS
    // ══════════════════════════════════════════════════════════

    async function api(path, options = {}) {
        try {
            const method = (options.method || 'GET').toUpperCase();
            let url = `/api/${path}`;
            if (method === 'GET') {
                const separator = url.includes('?') ? '&' : '?';
                url += `${separator}_t=${Date.now()}`;
            }
            const res = await fetch(url, {
                headers: { 'Content-Type': 'application/json' },
                ...options,
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ error: res.statusText }));
                throw new Error(err.error || err.message || `HTTP ${res.status}`);
            }
            return await res.json();
        } catch (e) {
            console.error(`API ${path}:`, e);
            throw e;
        }
    }

    // ══════════════════════════════════════════════════════════
    //  DATA LOADING
    // ══════════════════════════════════════════════════════════

    async function loadConditions() {
        try {
            const data = await api('conditions');
            state.conditions = data;
            populateConditionSelect();
        } catch (e) {
            toast('加载条件类型失败', 'error');
        }
    }

    async function loadSymbols() {
        try {
            const data = await api('symbols');
            state.symbols = Array.isArray(data) ? data : (data.symbols || []);
            populateSymbolSelect();
        } catch (e) {
            toast('加载交易对列表失败', 'error');
        }
    }

    async function loadAlerts() {
        try {
            const data = await api('alerts');
            state.alerts = Array.isArray(data) ? data : (data.alerts || []);
            renderAlerts();
        } catch (e) {
            toast('加载预警列表失败', 'error');
        }
    }

    async function loadHistory() {
        try {
            const data = await api('history');
            const entries = Array.isArray(data) ? data : (data.history || []);
            state.historyEntries = entries.reverse();
            renderHistory();
        } catch (e) {
            console.error('Load history failed:', e);
        }
    }

    async function loadPrices() {
        try {
            const data = await api('prices');
            if (data && typeof data === 'object') {
                Object.entries(data).forEach(([sym, info]) => {
                    state.prices[sym] = typeof info === 'object' ? info : { price: info };
                });
                renderPriceTicker();
            }
        } catch (e) {
            console.error('Load prices failed:', e);
        }
    }

    // ══════════════════════════════════════════════════════════
    //  RENDERING — PRICE TICKER
    // ══════════════════════════════════════════════════════════

    function renderPriceTicker() {
        const symbols = Object.keys(state.prices);
        if (!symbols.length) {
            dom.priceTicker.innerHTML = '<div class="ticker-placeholder">等待行情数据…</div>';
            return;
        }

        // Preserve existing cards; update or add
        const existing = new Map();
        dom.priceTicker.querySelectorAll('.price-card').forEach(el => {
            existing.set(el.dataset.symbol, el);
        });

        // Remove placeholder if present
        const ph = dom.priceTicker.querySelector('.ticker-placeholder');
        if (ph) ph.remove();

        symbols.forEach(sym => {
            const info = state.prices[sym];
            const price = parseFloat(info?.price ?? 0);
            const prev = parseFloat(state.prevPrices[sym]?.price ?? price);
            const dir = price > prev ? 'up' : price < prev ? 'down' : '';

            let card = existing.get(sym);
            if (!card) {
                card = document.createElement('div');
                card.className = 'price-card';
                card.dataset.symbol = sym;
                card.innerHTML = `
                    <span class="symbol">${esc(displaySymbol(sym))}</span>
                    <span class="price"></span>
                    <span class="change"></span>
                `;
                dom.priceTicker.appendChild(card);
            }

            const priceEl = card.querySelector('.price');
            const changeEl = card.querySelector('.change');

            priceEl.textContent = formatPrice(price);
            priceEl.className = `price ${dir}`;

            // Compute 24h change if open is available
            const open = parseFloat(info?.open ?? 0);
            if (open > 0) {
                const pct = ((price - open) / open * 100).toFixed(2);
                const changeDir = pct >= 0 ? 'up' : 'down';
                changeEl.textContent = `${pct >= 0 ? '+' : ''}${pct}%`;
                changeEl.className = `change ${changeDir}`;
            } else {
                changeEl.textContent = '';
                changeEl.className = 'change';
            }

            // Flash
            if (dir) {
                card.classList.remove('flash-green', 'flash-red');
                void card.offsetWidth; // reflow
                card.classList.add(dir === 'up' ? 'flash-green' : 'flash-red');
            }
        });
    }

    // ══════════════════════════════════════════════════════════
    //  RENDERING — ALERTS
    // ══════════════════════════════════════════════════════════

    function getConditionName(type) {
        if (state.conditions[type]) return state.conditions[type].name || type;
        return type;
    }

    function renderAlerts() {
        const list = state.alerts;
        dom.alertCount.textContent = list.length;

        if (!list.length) {
            dom.alertList.innerHTML = `
                <div class="empty-state">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" stroke-linecap="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
                    <p>暂无活跃预警</p>
                    <span>点击上方「新建预警」按钮创建第一条预警规则</span>
                </div>`;
            return;
        }

        dom.alertList.innerHTML = list.map((a, i) => {
            const condName = getConditionName(a.condition_type);
            let paramStr = '';
            if (a.params) {
                paramStr = Object.entries(a.params).map(([k, v]) => {
                    if (k === 'signal') {
                        const signalLabels = {
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
                        };
                        return signalLabels[v] || v;
                    }
                    return `${k}: ${v}`;
                }).join('，');
            }
            return `
            <div class="alert-card ${a.enabled ? '' : 'disabled'}" data-id="${esc(a.id)}" style="animation-delay: ${i * 0.05}s">
                <div class="alert-indicator"></div>
                <div class="alert-body">
                    <div class="alert-top">
                        <span class="alert-symbol">${esc(displaySymbol(a.symbol))}</span>
                        <span class="alert-tag">${esc(condName)}</span>
                        <span class="alert-tag timeframe">${esc(a.timeframe || '—')}</span>
                    </div>
                    <div class="alert-condition">${esc(paramStr)}</div>
                    ${a.message ? `<div class="alert-message">"${esc(a.message)}"</div>` : ''}
                </div>
                <div class="alert-actions">
                    <label class="toggle" title="${a.enabled ? '点击禁用' : '点击启用'}">
                        <input type="checkbox" ${a.enabled ? 'checked' : ''} data-action="toggle" data-id="${esc(a.id)}">
                        <span class="slider"></span>
                    </label>
                    <button class="btn-icon" data-action="edit" data-id="${esc(a.id)}" title="编辑">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                    </button>
                    <button class="btn-icon delete" data-action="delete" data-id="${esc(a.id)}" title="删除">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                    </button>
                </div>
            </div>`;
        }).join('');
    }

    // ══════════════════════════════════════════════════════════
    //  RENDERING — HISTORY
    // ══════════════════════════════════════════════════════════

    function renderHistory(highlightNew = false) {
        const list = state.historyEntries;
        dom.historyCount.textContent = list.length;

        if (!list.length) {
            dom.historyList.innerHTML = `
                <div class="empty-state">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                    <p>暂无触发记录</p>
                    <span>当预警条件被触发时，记录将显示在这里</span>
                </div>`;
            return;
        }

        dom.historyList.innerHTML = list.map((h, i) => {
            const isNew = highlightNew && i === 0;
            return `
            <div class="history-entry ${isNew ? 'new' : ''}" style="animation-delay: ${i * 0.04}s">
                <div class="entry-top">
                    <span class="entry-symbol">${esc(displaySymbol(h.symbol))}</span>
                    <div class="entry-meta">
                        <span class="entry-time">${formatTime(h.triggered_at || h.timestamp || h.created_at)}</span>
                        <button class="btn-history-delete" data-action="delete-history" data-id="${esc(h.id)}" title="删除触发记录">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <polyline points="3 6 5 6 21 6"></polyline>
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                            </svg>
                        </button>
                    </div>
                </div>
                <div class="entry-condition">${esc(getConditionName(h.condition_type))}</div>
                ${h.message ? `<div class="entry-message">${esc(h.message)}</div>` : ''}
                ${h.details ? `<div class="entry-message">${esc(typeof h.details === 'string' ? h.details : JSON.stringify(h.details))}</div>` : ''}
                ${h.price != null ? `<div class="entry-price">触发价格: ${formatPrice(h.price)}</div>` : ''}
            </div>`;
        }).join('');
    }

    // ══════════════════════════════════════════════════════════
    //  FORM — SELECTS
    // ══════════════════════════════════════════════════════════

    function populateSymbolSelect() {
        const sel = dom.alertSymbol;
        // keep the placeholder
        sel.innerHTML = '<option value="" disabled selected>选择交易对…</option>';
        state.symbols.forEach(s => {
            const opt = document.createElement('option');
            opt.value = s;
            opt.textContent = displaySymbol(s);
            sel.appendChild(opt);
        });
    }

    function populateConditionSelect() {
        const sel = dom.alertCondition;
        sel.innerHTML = '<option value="" disabled selected>选择条件…</option>';
        const entries = Object.entries(state.conditions);
        entries.forEach(([key, cond]) => {
            const opt = document.createElement('option');
            opt.value = key;
            opt.textContent = cond.name || key;
            sel.appendChild(opt);
        });
        if (entries.length === 1) {
            sel.value = entries[0][0];
            renderDynamicParams(entries[0][0]);
        }
    }

    // ── Dynamic parameter fields ───────────────────────────────
    function renderDynamicParams(conditionType) {
        dom.dynamicParams.innerHTML = '';
        dom.conditionDesc.textContent = '';

        const cond = state.conditions[conditionType];
        if (!cond) return;

        dom.conditionDesc.textContent = cond.description || '';

        if (conditionType === 'custom') {
            const group = document.createElement('div');
            group.className = 'form-group full-width custom-expression-wrapper';
            group.innerHTML = `
                <div class="expression-tabs">
                    <button type="button" class="tab-btn active" data-tab="python">Python 表达式</button>
                    <button type="button" class="tab-btn" data-tab="pine">Pine Script 自动转换</button>
                </div>
                
                <div class="tab-content" id="tabContentPython">
                    <label for="param_expression">表达式</label>
                    <textarea id="param_expression" name="expression" placeholder="例：RSI(14) > 70 and close > SMA(20)" rows="4"></textarea>
                    <p class="form-hint">使用 Python 表达式。支持 <code>close</code>, <code>high</code>, <code>low</code>, <code>open</code>, <code>volume</code>, <code>rsi()</code>, <code>sma()</code>, <code>ema()</code>, <code>crossover()</code>, <code>crossunder()</code> 等。</p>
                </div>
                
                <div class="tab-content hidden" id="tabContentPine">
                    <label for="pine_code_input">Pine Script 代码</label>
                    <textarea id="pine_code_input" placeholder="// 贴入你的 Pine Script 代码，例如：&#10;rsiVal = ta.rsi(close, 14)&#10;buySignal = ta.crossover(rsiVal, 30)" rows="6"></textarea>
                    <button type="button" class="btn btn-ghost btn-sm" id="btnConvertPine" style="margin-top: 8px;">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
                        <span>转换为 Python 表达式</span>
                    </button>
                    <p class="form-hint">系统将自动识别并转换常用的 Pine Script 语法和内置指标函数。</p>
                </div>
            `;
            dom.dynamicParams.appendChild(group);
            
            // Add tab toggle events
            const tabs = group.querySelectorAll('.tab-btn');
            tabs.forEach(tab => {
                tab.addEventListener('click', () => {
                    tabs.forEach(t => t.classList.remove('active'));
                    tab.classList.add('active');
                    const target = tab.dataset.tab;
                    if (target === 'python') {
                        group.querySelector('#tabContentPython').classList.remove('hidden');
                        group.querySelector('#tabContentPine').classList.add('hidden');
                    } else {
                        group.querySelector('#tabContentPython').classList.add('hidden');
                        group.querySelector('#tabContentPine').classList.remove('hidden');
                    }
                });
            });
            
            // Add Pine Convert event
            group.querySelector('#btnConvertPine').addEventListener('click', async () => {
                const pineCode = group.querySelector('#pine_code_input').value.trim();
                if (!pineCode) {
                    toast('请输入 Pine Script 代码', 'warning');
                    return;
                }
                
                try {
                    const btn = group.querySelector('#btnConvertPine');
                    const span = btn.querySelector('span');
                    const originalText = span.textContent;
                    span.textContent = '转换中...';
                    btn.disabled = true;
                    
                    const res = await api('convert-pine', {
                        method: 'POST',
                        body: JSON.stringify({ pine_code: pineCode })
                    });
                    
                    group.querySelector('#param_expression').value = res.expression;
                    
                    // Switch back to Python tab so the user can inspect/edit the converted output
                    group.querySelector('[data-tab="python"]').click();
                    toast('转换成功！已填入 Python 表达式', 'success');
                    
                    span.textContent = originalText;
                    btn.disabled = false;
                } catch (e) {
                    toast(`转换失败: ${e.message}`, 'error');
                    const btn = group.querySelector('#btnConvertPine');
                    btn.querySelector('span').textContent = '转换为 Python 表达式';
                    btn.disabled = false;
                }
            });
            
            return;
        }

        const params = cond.params || [];
        params.forEach(p => {
            const group = document.createElement('div');
            group.className = `form-group${params.length === 1 ? ' full-width' : ''}`;

            const label = document.createElement('label');
            label.setAttribute('for', `param_${p.key}`);
            label.textContent = p.label || p.key;
            group.appendChild(label);

            let input;
            if (p.type === 'select' && Array.isArray(p.options)) {
                input = document.createElement('select');
                p.options.forEach(o => {
                    const opt = document.createElement('option');
                    if (typeof o === 'object') {
                        opt.value = o.value;
                        opt.textContent = o.label || o.value;
                    } else {
                        opt.value = o;
                        opt.textContent = o;
                    }
                    input.appendChild(opt);
                });
                if (p.default != null) input.value = p.default;
            } else if (p.type === 'text') {
                input = document.createElement('input');
                input.type = 'text';
                if (p.default != null) input.value = p.default;
                input.placeholder = p.label || '';
            } else {
                input = document.createElement('input');
                input.type = 'number';
                input.step = p.type === 'float' ? '0.01' : '1';
                if (p.default != null) input.value = p.default;
            }

            input.id = `param_${p.key}`;
            input.name = p.key;
            input.className = '';
            group.appendChild(input);
            dom.dynamicParams.appendChild(group);
        });
    }

    // ══════════════════════════════════════════════════════════
    //  MODAL LOGIC
    // ══════════════════════════════════════════════════════════

    function openModal(mode = 'create', alert = null) {
        dom.alertForm.reset();
        dom.dynamicParams.innerHTML = '';
        dom.conditionDesc.textContent = '';
        dom.alertId.value = '';

        const triggerSelect = $('#alertTriggerMode');
        const expInput = $('#alertExpirationTime');

        if (mode === 'edit' && alert) {
            dom.modalTitle.textContent = '编辑警报';
            dom.btnSubmitLabel.textContent = '保存';
            dom.alertId.value = alert.id;
            dom.alertSymbol.value = alert.symbol;
            dom.alertTimeframe.value = alert.timeframe || '1h';
            dom.alertCondition.value = alert.condition_type;
            dom.alertMessage.value = alert.message || '';
            dom.alertCooldown.value = alert.cooldown ?? 300;
            
            if (triggerSelect) triggerSelect.value = alert.trigger_mode || 'once_per_bar_close';
            if (expInput) {
                expInput.value = alert.expiration_time ? alert.expiration_time.slice(0, 16) : '';
            }

            renderDynamicParams(alert.condition_type);

            // Fill param values
            if (alert.params) {
                Object.entries(alert.params).forEach(([k, v]) => {
                    const input = $(`#param_${k}`);
                    if (input) input.value = v;
                });
            }
        } else {
            dom.modalTitle.textContent = '创建警报';
            dom.btnSubmitLabel.textContent = '创建警报';
            
            const entries = Object.keys(state.conditions);
            if (entries.length === 1) {
                dom.alertCondition.value = entries[0];
                renderDynamicParams(entries[0]);
            }
            
            if (triggerSelect) triggerSelect.value = 'once_per_bar_close';
            if (expInput) {
                // Default expiration time: 1 month later
                const now = new Date();
                now.setMonth(now.getMonth() + 1);
                const year = now.getFullYear();
                const month = String(now.getMonth() + 1).padStart(2, '0');
                const day = String(now.getDate()).padStart(2, '0');
                const hours = String(now.getHours()).padStart(2, '0');
                const minutes = String(now.getMinutes()).padStart(2, '0');
                expInput.value = `${year}-${month}-${day}T${hours}:${minutes}`;
            }
        }

        dom.alertModal.classList.add('active');
        // Focus first select after animation
        setTimeout(() => dom.alertSymbol.focus(), 350);
    }

    function closeModal() {
        dom.alertModal.classList.remove('active');
    }

    function openPineModal() {
        dom.pineModal.classList.add('active');
    }

    function closePineModal() {
        dom.pineModal.classList.remove('active');
    }

    // ══════════════════════════════════════════════════════════
    //  ALERT CRUD
    // ══════════════════════════════════════════════════════════

    async function saveAlert(e) {
        e.preventDefault();

        const isEdit = !!dom.alertId.value;
        const condType = dom.alertCondition.value;

        // Collect dynamic params
        const params = {};
        const cond = state.conditions[condType];
        if (cond && cond.params) {
            cond.params.forEach(p => {
                const input = $(`#param_${p.key}`);
                if (input) {
                    let val = input.value;
                    if (p.type === 'int') val = parseInt(val, 10);
                    else if (p.type === 'float') val = parseFloat(val);
                    params[p.key] = val;
                }
            });
        }

        const triggerSelect = $('#alertTriggerMode');
        const expInput = $('#alertExpirationTime');

        const body = {
            symbol: dom.alertSymbol.value,
            timeframe: dom.alertTimeframe.value,
            condition_type: condType,
            params,
            message: dom.alertMessage.value.trim(),
            cooldown: parseInt(dom.alertCooldown.value, 10) || 0,
            trigger_mode: triggerSelect ? triggerSelect.value : 'once_per_bar_close',
            expiration_time: expInput && expInput.value ? expInput.value : null
        };

        try {
            if (isEdit) {
                await api(`alerts/${dom.alertId.value}`, { method: 'PUT', body: JSON.stringify(body) });
                toast('预警已更新', 'success');
            } else {
                await api('alerts', { method: 'POST', body: JSON.stringify(body) });
                toast('预警已创建', 'success');
            }
            closeModal();
            await loadAlerts();
        } catch (e) {
            toast(`保存失败: ${e.message}`, 'error');
        }
    }

    async function deleteAlert(id) {
        if (!confirm('确定删除此预警？此操作不可撤销。')) return;
        try {
            await api(`alerts/${id}`, { method: 'DELETE' });
            toast('预警已删除', 'info');
            await loadAlerts();
        } catch (e) {
            toast(`删除失败: ${e.message}`, 'error');
        }
    }

    async function toggleAlert(id) {
        try {
            await api(`alerts/${id}/toggle`, { method: 'PUT' });
            await loadAlerts();
        } catch (e) {
            toast(`切换状态失败: ${e.message}`, 'error');
        }
    }

    // ══════════════════════════════════════════════════════════
    //  SOCKET.IO
    // ══════════════════════════════════════════════════════════

    function initSocket() {
        const socket = io({ transports: ['websocket', 'polling'] });

        socket.on('connect', () => {
            state.connected = true;
            updateConnectionUI(true);
            console.log('[Socket] Connected');
        });

        socket.on('disconnect', () => {
            state.connected = false;
            updateConnectionUI(false);
            console.log('[Socket] Disconnected');
        });

        socket.on('connect_error', () => {
            state.connected = false;
            updateConnectionUI(false);
        });

        // ── Price updates ──
        socket.on('price_update', (data) => {
            const sym = data.symbol;
            if (!sym) return;
            state.prevPrices[sym] = state.prices[sym] ? { ...state.prices[sym] } : {};
            state.prices[sym] = data.data || { price: data.price };
            if (data.price && !state.prices[sym].price) {
                state.prices[sym].price = data.price;
            }
            renderPriceTicker();
        });

        socket.on('all_prices', (data) => {
            if (data && typeof data === 'object') {
                // Save prev
                Object.keys(data).forEach(sym => {
                    state.prevPrices[sym] = state.prices[sym] ? { ...state.prices[sym] } : {};
                });
                Object.entries(data).forEach(([sym, info]) => {
                    state.prices[sym] = typeof info === 'object' ? info : { price: info };
                });
                renderPriceTicker();
            }
        });

        // ── Alert triggered ──
        socket.on('alert_triggered', (data) => {
            console.log('[Socket] Alert triggered:', data);
            playAlertSound();

            const msg = data.message || `${displaySymbol(data.symbol)} ${getConditionName(data.condition_type)}`;
            toast(`🔔 ${msg}`, 'warning', 8000);

            // Prepend to history
            state.historyEntries.unshift(data);
            renderHistory(true);
        });

        // ── Status ──
        socket.on('status', (data) => {
            if (data && typeof data.connected === 'boolean') {
                updateConnectionUI(data.connected);
            }
        });
    }

    function updateConnectionUI(connected) {
        dom.statusDot.className = `status-dot ${connected ? 'connected' : 'disconnected'}`;
        dom.statusLabel.textContent = connected ? '已连接' : '未连接';
    }

    // ══════════════════════════════════════════════════════════
    //  EMAIL SETTINGS
    // ══════════════════════════════════════════════════════════

    async function openEmailModal() {
        if (!dom.emailModal) return;
        try {
            const config = await api('email-config');
            if (dom.emailEnabled)    dom.emailEnabled.checked = !!config.enabled;
            if (dom.emailSmtpServer) dom.emailSmtpServer.value = config.smtp_server || '';
            if (dom.emailSmtpPort)   dom.emailSmtpPort.value = config.smtp_port || 465;
            if (dom.emailUseSsl)     dom.emailUseSsl.checked = config.use_ssl !== false;
            if (dom.emailSender)     dom.emailSender.value = config.sender_email || '';
            if (dom.emailPassword)   dom.emailPassword.value = config.sender_password_masked || '';
            if (dom.emailReceiver)   dom.emailReceiver.value = config.receiver_email || '';
            if (dom.emailStartTime)  dom.emailStartTime.value = config.send_start_time || '22:00';
            if (dom.emailEndTime)    dom.emailEndTime.value = config.send_end_time || '08:00';
        } catch (e) {
            console.error('[Email] Load config failed:', e);
        }
        dom.emailModal.classList.add('active');
    }

    function closeEmailModal() {
        if (dom.emailModal) dom.emailModal.classList.remove('active');
    }

    function _getEmailFormData() {
        return {
            enabled:         dom.emailEnabled?.checked || false,
            smtp_server:     dom.emailSmtpServer?.value?.trim() || '',
            smtp_port:       parseInt(dom.emailSmtpPort?.value) || 465,
            use_ssl:         dom.emailUseSsl?.checked !== false,
            sender_email:    dom.emailSender?.value?.trim() || '',
            sender_password: dom.emailPassword?.value || '',
            receiver_email:  dom.emailReceiver?.value?.trim() || '',
            send_start_time: dom.emailStartTime?.value || '22:00',
            send_end_time:   dom.emailEndTime?.value || '08:00',
        };
    }

    async function saveEmailConfig(e) {
        if (e) e.preventDefault();
        const data = _getEmailFormData();
        try {
            await api('email-config', {
                method: 'PUT',
                body: JSON.stringify(data),
            });
            toast('邮件配置已保存', 'success');
            closeEmailModal();
        } catch (err) {
            toast('保存失败: ' + err.message, 'error');
        }
    }

    async function testEmailSend() {
        const data = _getEmailFormData();
        toast('正在发送测试邮件...', 'info', 5000);
        try {
            const result = await api('email-config/test', {
                method: 'POST',
                body: JSON.stringify(data),
            });
            if (result.success) {
                toast(result.message || '测试邮件已发送', 'success', 5000);
            } else {
                toast(result.message || '发送失败', 'error', 8000);
            }
        } catch (err) {
            toast('测试失败: ' + err.message, 'error', 8000);
        }
    }

    // ══════════════════════════════════════════════════════════
    //  EVENT LISTENERS
    // ══════════════════════════════════════════════════════════

    function bindEvents() {
        const safeAddEvent = (sel, event, handler) => {
            const el = typeof sel === 'string' ? $(sel) : sel;
            if (el) el.addEventListener(event, handler);
        };

        // Add alert button
        safeAddEvent('#btnAddAlert', 'click', () => openModal('create'));

        // Close modal
        safeAddEvent('#btnCloseModal', 'click', closeModal);
        safeAddEvent('#btnCancelModal', 'click', closeModal);
        if (dom.alertModal) {
            dom.alertModal.addEventListener('click', (e) => {
                if (e.target === dom.alertModal) closeModal();
            });
        }

        // Pine Script modals
        safeAddEvent('#btnPineRef', 'click', openPineModal);
        safeAddEvent('#btnClosePine', 'click', closePineModal);
        if (dom.pineModal) {
            dom.pineModal.addEventListener('click', (e) => {
                if (e.target === dom.pineModal) closePineModal();
            });
        }

        // Theme toggle button
        safeAddEvent('#btnThemeToggle', 'click', () => {
            const current = document.documentElement.getAttribute('data-theme') || 'dark';
            const next = current === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', next);
            localStorage.setItem('theme', next);
            toast(`已切换至${next === 'dark' ? '夜间' : '日间'}模式`, 'success');
        });

        // Email settings modal
        safeAddEvent('#btnEmailSettings', 'click', openEmailModal);
        safeAddEvent('#btnCloseEmail', 'click', closeEmailModal);
        safeAddEvent('#btnCancelEmail', 'click', closeEmailModal);
        safeAddEvent('#btnTestEmail', 'click', testEmailSend);
        if (dom.emailModal) {
            dom.emailModal.addEventListener('click', (e) => {
                if (e.target === dom.emailModal) closeEmailModal();
            });
        }
        if (dom.emailForm) {
            dom.emailForm.addEventListener('submit', saveEmailConfig);
        }

        // Keyboard
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                if (dom.alertModal && dom.alertModal.classList.contains('active')) closeModal();
                if (dom.pineModal && dom.pineModal.classList.contains('active')) closePineModal();
                if (dom.emailModal && dom.emailModal.classList.contains('active')) closeEmailModal();
            }
        });

        // Alert form submit
        if (dom.alertForm) {
            dom.alertForm.addEventListener('submit', saveAlert);
        }

        // Condition type change → dynamic params
        if (dom.alertCondition) {
            dom.alertCondition.addEventListener('change', (e) => {
                renderDynamicParams(e.target.value);
            });
        }

        // Alert list delegation (toggle, edit, delete)
        if (dom.alertList) {
            dom.alertList.addEventListener('click', (e) => {
                const btn = e.target.closest('[data-action]');
                if (!btn) return;
                const action = btn.dataset.action;
                const id = btn.dataset.id;

                if (action === 'delete') {
                    deleteAlert(id);
                } else if (action === 'edit') {
                    const alert = state.alerts.find(a => a.id === id);
                    if (alert) openModal('edit', alert);
                }
            });

            dom.alertList.addEventListener('change', (e) => {
                if (e.target.dataset.action === 'toggle') {
                    toggleAlert(e.target.dataset.id);
                }
            });
        }

        // Refresh history
        safeAddEvent('#btnRefreshHistory', 'click', loadHistory);

        // Clear all history records
        safeAddEvent('#btnClearHistory', 'click', async () => {
            if (confirm('确定要清空所有触发记录吗？此操作不可恢复。')) {
                try {
                    const result = await api('history', { method: 'DELETE' });
                    if (result.success) {
                        toast('所有历史记录已清空', 'success');
                        state.historyEntries = [];
                        renderHistory();
                    } else {
                        toast('清空失败', 'error');
                    }
                } catch (err) {
                    toast('清空失败: ' + err.message, 'error');
                }
            }
        });

        // Delete single history entry
        if (dom.historyList) {
            dom.historyList.addEventListener('click', async (e) => {
                const btn = e.target.closest('[data-action="delete-history"]');
                if (!btn) return;
                const id = btn.dataset.id;
                if (confirm('确定要删除这条触发记录吗？')) {
                    try {
                        const result = await api(`history/${id}`, { method: 'DELETE' });
                        if (result.success) {
                            toast('历史记录已删除', 'success');
                            state.historyEntries = state.historyEntries.filter(h => h.id !== id);
                            renderHistory();
                        } else {
                            toast('删除失败', 'error');
                        }
                    } catch (err) {
                        toast('删除失败: ' + err.message, 'error');
                    }
                }
            });
        }
    }

    // ══════════════════════════════════════════════════════════
    //  INIT
    // ══════════════════════════════════════════════════════════

    async function init() {
        bindEvents();

        // Load data in parallel
        await Promise.allSettled([
            loadConditions(),
            loadSymbols(),
            loadAlerts(),
            loadHistory(),
            loadPrices(),
        ]);

        // Connect Socket.IO
        initSocket();

        // Auto-refresh history every 30 seconds
        setInterval(loadHistory, 30_000);

        console.log('[CryptoAlert] 初始化完成 ✨');
    }

    // Wait for DOM
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
