/**
 * VideoTranscript - Configuration Management Page
 */
(function () {
    'use strict';

    var $ = function (sel) { return document.querySelector(sel); };
    var $$ = function (sel) { return document.querySelectorAll(sel); };

    var configData = null;
    var MAX_TOASTS = 5;

    var els = {
        themeToggle: $('#themeToggle'),
        providerList: $('#providerList'),
        addProviderBtn: $('#addProviderBtn'),
        cloudSection: $('#cloudSection'),
        localSection: $('#localSection'),
        localAsrInfo: $('#localAsrInfo'),
        importExportSection: $('#importExportSection'),
        exportBtn: $('#exportBtn'),
        importBtn: $('#importBtn'),
        importFile: $('#importFile'),
        toastContainer: $('#toastContainer'),
    };

    // ==================== Theme ====================

    function initTheme() {
        var saved = localStorage.getItem('theme');
        if (saved) document.documentElement.setAttribute('data-theme', saved);
    }

    function toggleTheme() {
        var current = document.documentElement.getAttribute('data-theme');
        var next = current === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem('theme', next);
    }

    // ==================== Toast ====================

    function showToast(message, type, duration) {
        type = type || 'info';
        duration = duration || 3000;
        var toasts = els.toastContainer.children;
        while (toasts.length >= MAX_TOASTS) toasts[0].remove();
        var toast = document.createElement('div');
        toast.className = 'toast toast-' + type;
        var icons = {
            success: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
            error: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
            info: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>'
        };
        toast.innerHTML = '<span class="toast-icon">' + (icons[type] || icons.info) + '</span><span class="toast-text">' + escapeHtml(message) + '</span>';
        els.toastContainer.appendChild(toast);
        setTimeout(function () {
            toast.classList.add('removing');
            toast.addEventListener('animationend', function () { toast.remove(); });
        }, duration);
    }

    // ==================== Helpers ====================

    function isValidJson(str) {
        if (!str || !str.trim()) return true;
        try { JSON.parse(str); return true; } catch (e) { return false; }
    }

    // ==================== API ====================

    async function loadConfig() {
        try {
            var resp = await fetch('/api/transcript/config');
            var data = await resp.json();
            if (data.success) {
                configData = data.data;
                renderMode();
                renderProviders();
                renderLocalInfo();
            } else {
                showToast(data.message || '加载配置失败', 'error');
            }
        } catch (err) {
            showToast('无法连接到服务器', 'error');
        }
    }

    async function saveConfig() {
        try {
            var resp = await fetch('/api/transcript/config', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    mode: configData.mode || 'local',
                    default_provider: configData.default_provider || '',
                    providers: configData.providers || {},
                    cookies_path: configData.cookies_path || '',
                }),
            });
            var data = await resp.json();
            if (data.success) {
                showToast('配置已保存', 'success');
                return true;
            } else {
                showToast(data.message || '保存失败', 'error');
                return false;
            }
        } catch (err) {
            showToast('保存失败：网络错误', 'error');
            return false;
        }
    }

    async function testProvider(key) {
        var card = document.querySelector('[data-provider-key="' + key + '"]');
        var testBtn = card ? card.querySelector('.btn-test') : null;
        var resultEl = card ? card.querySelector('.test-result') : null;

        if (testBtn) { testBtn.disabled = true; testBtn.innerHTML = '<span class="spinner"></span> 测试中'; }
        if (resultEl) { resultEl.className = 'test-result'; resultEl.style.display = 'none'; }

        try {
            var resp = await fetch('/api/transcript/config/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ provider_key: key }),
            });
            var data = await resp.json();
            if (data.success) {
                var latency = data.data && data.data.latency_ms != null ? ' (' + escapeHtml(String(data.data.latency_ms)) + 'ms)' : '';
                if (resultEl) {
                    resultEl.className = 'test-result show success';
                    resultEl.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg> 连接成功' + latency;
                }
                showToast('连接成功' + latency, 'success');
            } else {
                var errMsg = data.message || '连接失败';
                if (resultEl) {
                    resultEl.className = 'test-result show error';
                    resultEl.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg> ' + escapeHtml(errMsg);
                }
                showToast('测试失败: ' + errMsg, 'error');
            }
        } catch (err) {
            console.error('[testProvider] error:', err);
            if (resultEl) {
                resultEl.className = 'test-result show error';
                resultEl.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg> 网络错误';
            }
            showToast('网络错误', 'error');
        } finally {
            if (testBtn) { testBtn.disabled = false; testBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg> 测试'; }
        }
    }

    // ==================== Mode ====================

    function renderMode() {
        var mode = configData.mode || 'local';
        $$('.mode-option').forEach(function (opt) {
            opt.classList.toggle('active', opt.getAttribute('data-mode') === mode);
        });
        els.cloudSection.style.display = mode === 'cloud' ? '' : 'none';
        els.localSection.style.display = mode === 'local' ? '' : 'none';
        els.importExportSection.style.display = mode === 'cloud' ? '' : 'none';
    }

    function setMode(mode) {
        if (configData.mode === mode) return;
        configData.mode = mode;
        saveConfig().then(function (ok) {
            if (ok) {
                renderMode();
                if (mode === 'cloud') renderProviders();
                renderLocalInfo();
            } else {
                configData.mode = mode === 'cloud' ? 'local' : 'cloud';
                renderMode();
            }
        });
    }

    // ==================== Local ASR Info ====================

    function renderLocalInfo() {
        var container = els.localAsrInfo;
        container.innerHTML = '';
        var items = [];
        if (configData.asr_active) items.push({ label: '当前引擎', value: configData.asr_active });
        if (configData.local_asr_available !== undefined) items.push({ label: '本地 Whisper', value: configData.local_asr_available ? '可用' : '不可用' });
        if (configData.local_asr_model) items.push({ label: '本地模型', value: configData.local_asr_model });
        if (configData.local_asr_device) items.push({ label: '计算设备', value: configData.local_asr_device });
        if (configData.mimo_configured !== undefined) items.push({ label: 'MiMo', value: configData.mimo_configured ? '已配置' : '未配置' });

        if (items.length === 0) {
            container.innerHTML = '<div class="empty-state">未检测到本地 ASR 配置</div>';
            return;
        }
        items.forEach(function (s) {
            var item = document.createElement('div');
            item.className = 'detail-item';
            item.innerHTML = '<span class="detail-label">' + escapeHtml(s.label) + '</span><span class="detail-value">' + escapeHtml(s.value) + '</span>';
            container.appendChild(item);
        });
    }

    // ==================== Render Providers ====================

    function renderProviders() {
        var container = els.providerList;
        container.innerHTML = '';
        if (!configData || !configData.providers || Object.keys(configData.providers).length === 0) {
            container.innerHTML = '<div class="empty-state">暂无提供商配置，点击下方按钮添加</div>';
            return;
        }
        for (var key in configData.providers) {
            if (configData.providers.hasOwnProperty(key)) {
                container.appendChild(createProviderCard(key, configData.providers[key]));
            }
        }
    }

    function createProviderCard(key, provider) {
        var isDefault = configData.default_provider === key;
        var card = document.createElement('div');
        card.className = 'provider-card' + (isDefault ? ' is-default' : '');
        card.setAttribute('data-provider-key', key);

        var typeClass = provider.type === 'whisper-api' ? 'whisper' : '';
        var typeLabel = provider.type === 'whisper-api' ? 'Whisper API' : 'OpenAI Compatible';

        card.innerHTML =
            '<div class="provider-view">' +
                '<div class="provider-card-header">' +
                    '<div class="provider-name-row">' +
                        '<span class="provider-name">' + escapeHtml(provider.name || key) + '</span>' +
                        '<span class="badge badge-type ' + typeClass + '">' + typeLabel + '</span>' +
                        (isDefault ? '<span class="badge badge-default">默认</span>' : '') +
                    '</div>' +
                    '<div class="provider-actions">' +
                        '<button class="btn btn-sm btn-secondary btn-test" title="测试连接"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg> 测试</button>' +
                        (isDefault ? '' : '<button class="btn btn-sm btn-secondary btn-set-default" title="设为默认">设为默认</button>') +
                        '<button class="btn btn-sm btn-secondary btn-edit" title="编辑"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button>' +
                        '<button class="btn btn-sm btn-danger btn-delete" title="删除"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg></button>' +
                    '</div>' +
                '</div>' +
                '<div class="provider-details">' +
                    (provider.model ? '<div class="detail-item"><span class="detail-label">模型</span><span class="detail-value">' + escapeHtml(provider.model) + '</span></div>' : '') +
                    (provider.base_url ? '<div class="detail-item"><span class="detail-label">地址</span><span class="detail-value">' + escapeHtml(provider.base_url) + '</span></div>' : '') +
                    (provider.api_key ? '<div class="detail-item"><span class="detail-label">密钥</span><span class="detail-value masked">' + maskApiKey(provider.api_key) + '</span></div>' : '') +
                '</div>' +
                '<div class="test-result"></div>' +
            '</div>' +
            '<div class="provider-edit-form">' + buildEditFormHTML(key, provider) + '</div>';

        bindCardEvents(card, key);
        return card;
    }

    function buildEditFormHTML(key, provider) {
        provider = provider || {};
        var headersStr = '';
        if (provider.headers && typeof provider.headers === 'object') {
            headersStr = JSON.stringify(provider.headers, null, 2);
        }
        return '<div class="form-grid">' +
            '<div class="form-group"><label class="form-label">名称</label><input type="text" class="form-input" data-field="name" value="' + escapeHtml(provider.name || '') + '" placeholder="如：MiMo ASR" required></div>' +
            '<div class="form-group"><label class="form-label">类型</label><select class="form-select" data-field="type"><option value="openai-compatible"' + (provider.type === 'openai-compatible' ? ' selected' : '') + '>OpenAI Compatible</option><option value="whisper-api"' + (provider.type === 'whisper-api' ? ' selected' : '') + '>Whisper API</option></select></div>' +
            '<div class="form-group"><label class="form-label">API 密钥</label><div class="password-wrapper"><input type="password" class="form-input" data-field="api_key" value="' + escapeHtml(provider.api_key || '') + '" placeholder="sk-..."><button type="button" class="password-toggle" title="显示/隐藏"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg></button></div></div>' +
            '<div class="form-group"><label class="form-label">模型</label><input type="text" class="form-input" data-field="model" value="' + escapeHtml(provider.model || '') + '" placeholder="mimo-v2.5-asr"></div>' +
            '<div class="form-group full-width"><label class="form-label">Base URL</label><input type="text" class="form-input" data-field="base_url" value="' + escapeHtml(provider.base_url || '') + '" placeholder="https://api.example.com/v1/chat/completions"></div>' +
            '<div class="form-group full-width"><label class="form-label">自定义 Headers (JSON)</label><textarea class="form-textarea" data-field="headers" placeholder=\'{"key": "value"}\'>' + escapeHtml(headersStr) + '</textarea></div>' +
        '</div>' +
        '<div class="form-actions"><button class="btn btn-secondary btn-cancel-edit">取消</button><button class="btn btn-primary btn-save-edit">保存</button></div>';
    }

    function bindCardEvents(card, key) {
        var testBtn = card.querySelector('.btn-test');
        if (testBtn) testBtn.addEventListener('click', function () { testProvider(key); });

        var editBtn = card.querySelector('.btn-edit');
        if (editBtn) editBtn.addEventListener('click', function () { enterEditMode(card); });

        var defaultBtn = card.querySelector('.btn-set-default');
        if (defaultBtn) defaultBtn.addEventListener('click', function () { setDefaultProvider(key); });

        var deleteBtn = card.querySelector('.btn-delete');
        if (deleteBtn) deleteBtn.addEventListener('click', function () { deleteProvider(key); });

        var pwdToggle = card.querySelector('.password-toggle');
        if (pwdToggle) pwdToggle.addEventListener('click', function () {
            var input = card.querySelector('[data-field="api_key"]');
            if (input) input.type = input.type === 'password' ? 'text' : 'password';
        });

        var cancelBtn = card.querySelector('.btn-cancel-edit');
        if (cancelBtn) cancelBtn.addEventListener('click', function () { exitEditMode(card); });

        var saveBtn = card.querySelector('.btn-save-edit');
        if (saveBtn) saveBtn.addEventListener('click', function () { saveProviderEdit(card, key); });
    }

    function enterEditMode(card) {
        card.classList.add('editing');
        var resultEl = card.querySelector('.test-result');
        if (resultEl) { resultEl.className = 'test-result'; resultEl.style.display = 'none'; }
        var firstInput = card.querySelector('.provider-edit-form .form-input');
        if (firstInput) firstInput.focus();
    }

    function exitEditMode(card) { card.classList.remove('editing'); }

    function saveProviderEdit(card, key) {
        var name = card.querySelector('[data-field="name"]').value.trim();
        if (!name) { showToast('请输入提供商名称', 'error'); return; }
        var baseUrl = card.querySelector('[data-field="base_url"]').value.trim();
        if (!baseUrl) { showToast('请输入 Base URL', 'error'); return; }
        var headersStr = card.querySelector('[data-field="headers"]').value.trim();
        if (!isValidJson(headersStr)) { showToast('自定义 Headers 必须是有效的 JSON', 'error'); return; }
        var headers = {};
        if (headersStr) try { headers = JSON.parse(headersStr); } catch (e) {}

        var provider = configData.providers[key];
        provider.name = name;
        provider.type = card.querySelector('[data-field="type"]').value;
        provider.api_key = card.querySelector('[data-field="api_key"]').value.trim();
        provider.model = card.querySelector('[data-field="model"]').value.trim();
        provider.base_url = baseUrl;
        provider.headers = headers;

        saveConfig().then(function (ok) { if (ok) renderProviders(); });
    }

    function setDefaultProvider(key) {
        configData.default_provider = key;
        saveConfig().then(function (ok) { if (ok) renderProviders(); });
    }

    function deleteProvider(key) {
        var name = configData.providers[key] ? (configData.providers[key].name || key) : key;
        if (!confirm('确认删除提供商 "' + name + '" ？')) return;
        delete configData.providers[key];
        if (configData.default_provider === key) {
            var remaining = Object.keys(configData.providers);
            configData.default_provider = remaining.length > 0 ? remaining[0] : '';
        }
        saveConfig().then(function (ok) { if (ok) renderProviders(); });
    }

    function addProvider() {
        var container = els.providerList;
        var existingNew = container.querySelector('[data-provider-key="__new__"]');
        if (existingNew) { existingNew.querySelector('[data-field="name"]').focus(); return; }
        var emptyState = container.querySelector('.empty-state');
        if (emptyState) emptyState.remove();

        var card = document.createElement('div');
        card.className = 'provider-card editing';
        card.setAttribute('data-provider-key', '__new__');
        card.innerHTML = '<div class="provider-view"></div><div class="provider-edit-form">' + buildEditFormHTML('__new__', {}) + '</div>';

        card.querySelector('.btn-cancel-edit').addEventListener('click', function () {
            card.remove();
            if (Object.keys(configData.providers).length === 0) {
                container.innerHTML = '<div class="empty-state">暂无提供商配置，点击下方按钮添加</div>';
            }
        });
        card.querySelector('.btn-save-edit').addEventListener('click', function () { saveNewProvider(card); });
        var pwdToggle = card.querySelector('.password-toggle');
        if (pwdToggle) pwdToggle.addEventListener('click', function () {
            var input = card.querySelector('[data-field="api_key"]');
            if (input) input.type = input.type === 'password' ? 'text' : 'password';
        });

        container.appendChild(card);
        card.querySelector('[data-field="name"]').focus();
    }

    function saveNewProvider(card) {
        var name = card.querySelector('[data-field="name"]').value.trim();
        if (!name) { showToast('请输入提供商名称', 'error'); return; }
        var baseUrl = card.querySelector('[data-field="base_url"]').value.trim();
        if (!baseUrl) { showToast('请输入 Base URL', 'error'); return; }
        var headersStr = card.querySelector('[data-field="headers"]').value.trim();
        if (!isValidJson(headersStr)) { showToast('自定义 Headers 必须是有效的 JSON', 'error'); return; }
        var headers = {};
        if (headersStr) try { headers = JSON.parse(headersStr); } catch (e) {}

        var baseKey = generateKey(name);
        var key = baseKey;
        var counter = 1;
        while (configData.providers[key]) { key = baseKey + '-' + counter; counter++; }

        configData.providers[key] = {
            name: name,
            type: card.querySelector('[data-field="type"]').value,
            api_key: card.querySelector('[data-field="api_key"]').value.trim(),
            model: card.querySelector('[data-field="model"]').value.trim(),
            base_url: baseUrl,
            headers: headers,
        };

        if (Object.keys(configData.providers).length === 1) configData.default_provider = key;

        saveConfig().then(function (ok) { if (ok) renderProviders(); });
    }

    // ==================== Import / Export ====================

    function exportConfig() {
        if (!configData) { showToast('没有可导出的配置', 'error'); return; }
        var json = JSON.stringify(configData, null, 2);
        var blob = new Blob([json], { type: 'application/json;charset=utf-8' });
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = 'video-transcript-config-' + new Date().toISOString().slice(0, 10) + '.json';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        showToast('配置已导出', 'success');
    }

    function importConfig() { els.importFile.click(); }

    function handleImportFile(file) {
        if (!file) return;
        var reader = new FileReader();
        reader.onload = function (e) {
            try {
                var imported = JSON.parse(e.target.result);
                if (!imported || typeof imported !== 'object') { showToast('无效的配置文件', 'error'); return; }
                if (imported.mode && !['local', 'cloud'].includes(imported.mode)) {
                    showToast('无效的 mode 值', 'error');
                    return;
                }
                if (imported.providers && typeof imported.providers !== 'object') {
                    showToast('providers 格式无效', 'error');
                    return;
                }
                if (!confirm('导入配置将覆盖当前设置，是否继续？')) return;
                configData = imported;
                saveConfig().then(function (ok) {
                    if (ok) { renderMode(); renderProviders(); renderLocalInfo(); showToast('配置已导入', 'success'); }
                });
            } catch (err) { showToast('配置文件格式错误：' + err.message, 'error'); }
        };
        reader.readAsText(file);
    }

    // ==================== Events ====================

    function bindEvents() {
        els.themeToggle.addEventListener('click', toggleTheme);
        els.addProviderBtn.addEventListener('click', addProvider);
        els.exportBtn.addEventListener('click', exportConfig);
        els.importBtn.addEventListener('click', importConfig);
        els.importFile.addEventListener('change', function () { handleImportFile(this.files[0]); this.value = ''; });

        $$('.mode-option').forEach(function (opt) {
            opt.addEventListener('click', function () { setMode(this.getAttribute('data-mode')); });
        });

        // Event delegation for provider card buttons
        els.providerList.addEventListener('click', function (e) {
            var btn = e.target.closest('button');
            if (!btn) return;
            var card = btn.closest('.provider-card');
            if (!card) return;
            var key = card.getAttribute('data-provider-key');
            if (!key) return;

            if (btn.classList.contains('btn-test')) {
                e.preventDefault();
                testProvider(key);
            } else if (btn.classList.contains('btn-edit')) {
                enterEditMode(card);
            } else if (btn.classList.contains('btn-set-default')) {
                setDefaultProvider(key);
            } else if (btn.classList.contains('btn-delete')) {
                deleteProvider(key);
            } else if (btn.classList.contains('btn-cancel-edit')) {
                exitEditMode(card);
            } else if (btn.classList.contains('btn-save-edit')) {
                saveProviderEdit(card, key);
            }
        });
    }

    function init() {
        initTheme();
        bindEvents();
        loadConfig();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
