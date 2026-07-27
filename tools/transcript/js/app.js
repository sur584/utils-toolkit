/**
 * Video Transcript Extractor - Frontend Application
 */

(function () {
    'use strict';

    var $ = function (sel) { return document.querySelector(sel); };
    var $$ = function (sel) { return document.querySelectorAll(sel); };

    // ─── Platform Icons Mapping ──────────────
    var PLATFORM_ICONS = {
        douyin: '抖音', bilibili: 'B站', youtube: 'YouTube',
        tiktok: 'TikTok', xiaohongshu: '小红书', weibo: '微博',
        instagram: 'Instagram', twitter: 'Twitter'
    };

    var PLATFORM_SVGS = {
        douyin: '<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><path d="M19.59 6.69a4.83 4.83 0 01-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 01-2.88 2.5 2.89 2.89 0 01-2.89-2.89 2.89 2.89 0 012.89-2.89c.28 0 .54.04.79.1v-3.5a6.37 6.37 0 00-.79-.05A6.34 6.34 0 003.15 15.2a6.34 6.34 0 007.04 6.3 6.34 6.34 0 005.14-6.22V9.12a8.16 8.16 0 004.77 1.52v-3.4a4.85 4.85 0 01-.51-.55z"/></svg>',
        tiktok: '<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><path d="M19.59 6.69a4.83 4.83 0 01-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 01-2.88 2.5 2.89 2.89 0 01-2.89-2.89 2.89 2.89 0 012.89-2.89c.28 0 .54.04.79.1v-3.5a6.37 6.37 0 00-.79-.05A6.34 6.34 0 003.15 15.2a6.34 6.34 0 007.04 6.3 6.34 6.34 0 005.14-6.22V9.12a8.16 8.16 0 004.77 1.52v-3.4a4.85 4.85 0 01-.51-.55z"/></svg>',
        youtube: '<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><path d="M23.498 6.186a3.016 3.016 0 00-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 00.502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 002.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 002.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>',
        bilibili: '<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z"/></svg>',
        xiaohongshu: '<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zM6 20V4h7v5h5v11H6z"/><path d="M9 13l2 2 4-4"/></svg>',
        weibo: '<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="2"/><path d="M16.24 7.76a6 6 0 010 8.49m-8.48-.01a6 6 0 010-8.49m11.31-2.82a10 10 0 010 14.14m-14.14 0a10 10 0 010-14.14"/></svg>',
        instagram: '<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><rect x="2" y="2" width="20" height="20" rx="5"/><circle cx="12" cy="12" r="5"/><circle cx="17.5" cy="6.5" r="1.5"/></svg>',
        twitter: '<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><path d="M22 4s-.7 2.1-2 3.5c1.6 10-9.4 17.5-18 11.5 4 2 9 1 11-3 0 0 5 1 9-4 0 0 1.5-4.5 0-8z"/></svg>',
    };

    // ─── Elements ────────────────────────────
    var elements = {
        themeToggle: $('#themeToggle'),
        urlInput: $('#urlInput'),
        pasteBtn: $('#pasteBtn'),
        submitBtn: $('#submitBtn'),
        progressSection: $('#progressSection'),
        statusMessage: $('#statusMessage'),
        resultArea: $('#resultArea'),
        videoPreview: $('#videoPreview'),
        videoTitle: $('#videoTitle'),
        videoAuthor: $('#videoAuthor'),
        videoPlatform: $('#videoPlatform'),
        videoDuration: $('#videoDuration'),
        transcriptText: $('#transcriptText'),
        copyBtn: $('#copyBtn'),
        downloadBtn: $('#downloadBtn'),
        downloadSrtBtn: $('#downloadSrtBtn'),
        retryBtn: $('#retryBtn'),
        errorArea: $('#errorArea'),
        errorMessage: $('#errorMessage'),
        retryFromErrorBtn: $('#retryFromErrorBtn'),
        toastContainer: $('#toastContainer'),
        progressBar: $('#progressBar'),
        progressPercent: $('#progressPercent'),
        fileInput: $('#fileInput'),
        uploadZone: $('#uploadZone'),
        fileList: $('#fileList'),
        uploadResults: $('#uploadResults'),
        uploadBtn: $('#uploadBtn'),
        stepPills: $('.step-pills'),
    };

    // ─── State ───────────────────────────────
    var pollTimer = null;
    var isProcessing = false;
    var pollCount = 0;
    var currentJobId = null;
    var fetchAbort = null;
    var startTime = 0;
    var elapsedTimer = null;
    var MAX_POLL = 150;
    var MAX_TOASTS = 5;
    var FETCH_TIMEOUT = 15000;
    var MAX_FILE_MB = 500;
    var selectedFiles = [];
    var uploadRunning = false;
    var currentMode = 'link';
    var lastResult = null;

    // ─── URL Extraction ─────────────────────
    function extractUrl(text) {
        var m = text.match(/https?:\/\/[^\s<>"')\]]+/);
        return m ? m[0] : null;
    }

    // ─── Theme ──────────────────────────────
    function initTheme() {
        var saved = localStorage.getItem('theme');
        if (saved) {
            document.documentElement.setAttribute('data-theme', saved);
        }
    }

    function toggleTheme() {
        var current = document.documentElement.getAttribute('data-theme');
        var next = current === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem('theme', next);
    }

    // ─── Toast ──────────────────────────────
    function showToast(message, type, duration) {
        type = type || 'info';
        duration = duration || 3000;
        var toasts = elements.toastContainer.children;
        while (toasts.length >= MAX_TOASTS) {
            toasts[0].remove();
        }
        var toast = document.createElement('div');
        toast.className = 'toast toast-' + type;
        var icons = {
            success: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>',
            error: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>',
            info: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>'
        };
        toast.innerHTML = '<span class="toast-icon">' + (icons[type] || icons.info) + '</span><span class="toast-text">' + escapeHtml(message) + '</span>';
        elements.toastContainer.appendChild(toast);
        setTimeout(function () {
            toast.classList.add('removing');
            toast.addEventListener('animationend', function () { toast.remove(); });
        }, duration);
    }

    // ─── UI Helpers ─────────────────────────
    function setProcessing(state) {
        isProcessing = state;
        elements.submitBtn.disabled = state;
        elements.pasteBtn.disabled = state;
        elements.urlInput.disabled = state;
    }

    function showProgress() {
        elements.progressSection.style.display = '';
        elements.resultArea.style.display = 'none';
        elements.errorArea.style.display = 'none';
    }

    function showResult() {
        elements.progressSection.style.display = 'none';
        elements.resultArea.style.display = '';
        elements.errorArea.style.display = 'none';
    }

    function showError(message) {
        elements.progressSection.style.display = 'none';
        elements.resultArea.style.display = 'none';
        elements.errorArea.style.display = '';
        elements.errorMessage.textContent = message;
    }

    function resetUI() {
        stopPolling();
        stopTimer();
        setProcessing(false);
        elements.progressSection.style.display = 'none';
        elements.resultArea.style.display = 'none';
        elements.errorArea.style.display = 'none';
        clearSteps();
        if (elements.stepPills) elements.stepPills.style.display = '';
    }

    // ─── Step Progress ──────────────────────
    var stepOrder = ['parsing', 'subtitles', 'asr'];

    function clearSteps() {
        $$('.step-pill').forEach(function (el) {
            el.classList.remove('active', 'completed');
        });
        elements.statusMessage.textContent = '';
        setProgress(0);
    }

    function setProgress(pct) {
        pct = Math.max(0, Math.min(100, pct));
        elements.progressBar.style.width = pct + '%';
        var text = pct + '%';
        if (startTime > 0) {
            var sec = Math.floor((Date.now() - startTime) / 1000);
            text = pct + '%  ' + sec + 's';
        }
        elements.progressPercent.textContent = text;
    }

    function startTimer() {
        startTime = Date.now();
        elapsedTimer = setInterval(function () {
            if (startTime > 0) {
                var sec = Math.floor((Date.now() - startTime) / 1000);
                var pct = parseInt(elements.progressBar.style.width) || 0;
                elements.progressPercent.textContent = pct + '%  ' + sec + 's';
            }
        }, 1000);
    }

    function stopTimer() {
        if (elapsedTimer) { clearInterval(elapsedTimer); elapsedTimer = null; }
        startTime = 0;
    }

    function updateSteps(currentStep) {
        var idx = stepOrder.indexOf(currentStep);
        if (idx === -1) return;
        $$('.step-pill').forEach(function (el) {
            var step = el.getAttribute('data-step');
            var stepIdx = stepOrder.indexOf(step);
            el.classList.remove('active', 'completed');
            if (stepIdx < idx) {
                el.classList.add('completed');
            } else if (stepIdx === idx) {
                el.classList.add('active');
            }
        });
    }

    // ─── Fetch with timeout + abort ─────────
    function fetchWithTimeout(url, options, timeout) {
        timeout = timeout || FETCH_TIMEOUT;
        if (fetchAbort) { fetchAbort.abort(); }
        fetchAbort = new AbortController();
        var timer = setTimeout(function () { fetchAbort.abort(); }, timeout);
        return fetch(url, Object.assign({}, options, { signal: fetchAbort.signal }))
            .finally(function () { clearTimeout(timer); });
    }

    // ─── Clipboard ──────────────────────────
    async function pasteFromClipboard() {
        try {
            var text = await navigator.clipboard.readText();
            if (text) {
                var url = extractUrl(text);
                if (url) {
                    elements.urlInput.value = url;
                    showToast('已自动提取链接', 'success', 1500);
                } else {
                    elements.urlInput.value = text;
                    showToast('已粘贴', 'success', 1500);
                }
            }
        } catch (err) {
            showToast('无法读取剪贴板，请手动粘贴', 'error');
        }
    }

    async function copyToClipboard() {
        var text = elements.transcriptText.textContent || '';
        if (!text) { showToast('没有可复制的内容', 'error'); return; }
        try {
            await navigator.clipboard.writeText(text);
            showToast('已复制到剪贴板', 'success');
        } catch (err) {
            // Fallback: select text from transcript div
            var range = document.createRange();
            range.selectNodeContents(elements.transcriptText);
            var sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
            try { document.execCommand('copy'); sel.removeAllRanges(); showToast('已复制到剪贴板', 'success'); }
            catch (e) { showToast('复制失败，请手动选择复制', 'error'); }
        }
    }

    // ─── 通用复制/下载（供上传多卡片复用） ───
    async function copyText(text) {
        text = text || '';
        if (!text) { showToast('没有可复制的内容', 'error'); return; }
        try {
            await navigator.clipboard.writeText(text);
            showToast('已复制到剪贴板', 'success');
        } catch (err) {
            var ta = document.createElement('textarea');
            ta.value = text;
            ta.style.position = 'fixed';
            ta.style.opacity = '0';
            document.body.appendChild(ta);
            ta.select();
            try { document.execCommand('copy'); showToast('已复制到剪贴板', 'success'); }
            catch (e) { showToast('复制失败，请手动选择复制', 'error'); }
            document.body.removeChild(ta);
        }
    }

    function downloadText(filename, content) {
        content = content || '';
        if (!content) { showToast('没有可下载的内容', 'error'); return; }
        var blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        showToast('文件已下载', 'success');
    }

    // ─── Download ───────────────────────────
    function downloadAsTxt() {
        var text = elements.transcriptText.textContent || '';
        if (!text) { showToast('没有可下载的内容', 'error'); return; }
        var title = elements.videoTitle.textContent || 'transcript';
        var safeName = title.replace(/[\\/:*?"<>|]/g, '_').substring(0, 80);
        var blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = safeName + '.txt';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        showToast('文件已下载', 'success');
    }

    function downloadAsSrt() {
        // 优先用后端返回的 srt（含真实时间轴）；旧缓存/旧后端无此字段时，前端用文案+时长兜底合成
        var srt = (lastResult && lastResult.srt) ||
            buildSrtFromText(
                (lastResult && lastResult.transcript) || elements.transcriptText.textContent || '',
                (lastResult && lastResult.duration) || 0
            );
        if (!srt) { showToast('没有可下载的内容', 'error'); return; }
        var title = elements.videoTitle.textContent || 'transcript';
        var safeName = title.replace(/[\\/:*?"<>|]/g, '_').substring(0, 80);
        var blob = new Blob([srt], { type: 'text/plain;charset=utf-8' });
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = safeName + '.srt';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        showToast('字幕已下载', 'success');
    }

    // 前端兜底：按句末标点切分，按字符占比在 [0, duration] 分配时间轴，合成近似 SRT
    function buildSrtFromText(text, duration) {
        text = (text || '').trim();
        if (!text) return '';
        var chunks = text.split(/(?<=[。！？；.!?;\n])/).map(function (c) { return c.trim(); }).filter(Boolean);
        if (!chunks.length) chunks = [text];
        var totalChars = chunks.reduce(function (n, c) { return n + c.length; }, 0);
        if (!duration || duration <= 0) duration = Math.max(totalChars / 5, 1);
        var cursor = 0, out = [];
        for (var i = 0; i < chunks.length; i++) {
            var span = totalChars ? duration * (chunks[i].length / totalChars) : duration;
            var start = cursor;
            var end = i === chunks.length - 1 ? duration : Math.min(cursor + span, duration);
            out.push((i + 1) + '\n' + fmtSrtTime(start) + ' --> ' + fmtSrtTime(end) + '\n' + chunks[i]);
            cursor = end;
        }
        return out.join('\n\n');
    }

    function fmtSrtTime(sec) {
        if (sec < 0) sec = 0;
        var ms = Math.round(sec * 1000);
        var h = Math.floor(ms / 3600000); ms -= h * 3600000;
        var m = Math.floor(ms / 60000); ms -= m * 60000;
        var s = Math.floor(ms / 1000); ms -= s * 1000;
        var p = function (n, w) { return String(n).padStart(w, '0'); };
        return p(h, 2) + ':' + p(m, 2) + ':' + p(s, 2) + ',' + p(ms, 3);
    }

    // ─── Format Transcript ──────────────────
    function formatTranscript(text) {
        if (!text) return '';
        return escapeHtml(text).replace(/\n/g, '<br>');
    }

    // ─── Format Duration ────────────────────
    function formatDuration(seconds) {
        if (!seconds || seconds <= 0) return '-';
        var h = Math.floor(seconds / 3600);
        var m = Math.floor((seconds % 3600) / 60);
        var s = Math.floor(seconds % 60);
        if (h > 0) return h + ':' + String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
        return m + ':' + String(s).padStart(2, '0');
    }

    // ─── Estimate Read Time ─────────────────
    function estimateReadTime(chars) {
        var minutes = Math.ceil(chars / 400);
        return minutes + ' 分钟';
    }

    // ─── Highlight Platform ─────────────────
    function highlightPlatform(platform) {
        var icons = document.querySelectorAll('.platform-icon');
        icons.forEach(function (icon) {
            icon.classList.remove('active');
            if (icon.getAttribute('data-platform') === platform) {
                icon.classList.add('active');
            }
        });
    }

    // ─── Dynamic Platform Icons ──────────────
    function renderPlatforms(platforms) {
        var container = document.querySelector('.platform-icons');
        if (!container) return;
        container.innerHTML = '';
        platforms.forEach(function (p) {
            var icon = document.createElement('div');
            icon.className = 'platform-icon';
            icon.setAttribute('data-platform', p.key);
            icon.title = p.name;
            icon.innerHTML = PLATFORM_SVGS[p.key] || '';
            container.appendChild(icon);
        });
    }

    async function loadPlatforms() {
        try {
            var res = await fetch('/api/transcript/config');
            var json = await res.json();
            if (json.success && json.data && json.data.supported_platforms) {
                renderPlatforms(json.data.supported_platforms);
            }
        } catch (err) {
            console.warn('加载平台列表失败:', err);
        }
    }

    // ─── Submit ─────────────────────────────
    async function submitUrl() {
        var raw = elements.urlInput.value.trim();
        if (!raw) {
            showToast('请输入视频链接', 'error');
            elements.urlInput.focus();
            return;
        }
        var url = extractUrl(raw);
        if (!url) {
            showToast('未找到有效链接，请粘贴包含视频链接的文本', 'error');
            elements.urlInput.focus();
            return;
        }
        if (url !== raw) {
            elements.urlInput.value = url;
        }

        resetUI();
        showProgress();
        setProcessing(true);
        updateSteps('parsing');
        setProgress(5);
        elements.statusMessage.textContent = '正在提交任务...';

        try {
            var res = await fetchWithTimeout('/api/transcript', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: url })
            }, 10000);
            var json = await res.json();
            if (!res.ok || !json.success) {
                throw new Error(json.message || '服务器错误 (' + res.status + ')');
            }
            var jobId = json.data && json.data.job_id;
            if (!jobId) throw new Error('服务器未返回任务 ID');
            elements.statusMessage.textContent = '任务已创建，正在处理...';
            startTimer();
            startPolling(jobId);
        } catch (err) {
            if (err.name === 'AbortError') {
                showError('请求超时，请检查网络后重试');
            } else if (err.name === 'TypeError' && err.message.indexOf('fetch') !== -1) {
                showError('网络连接失败，请检查网络后重试');
            } else {
                showError(err.message || '提交失败，请重试');
            }
            setProcessing(false);
        }
    }

    // ─── Tab 切换 ───────────────────────────
    function switchTab(mode) {
        if (mode === currentMode) return;
        currentMode = mode;
        resetUI();
        $$('.tab-item').forEach(function (t) {
            t.classList.toggle('active', t.getAttribute('data-tab') === mode);
        });
        $$('.tab-panel').forEach(function (p) {
            p.hidden = p.getAttribute('data-panel') !== mode;
        });
    }

    // ─── 文件选择（多文件）───────────────────
    function formatFileSize(bytes) {
        return (bytes / 1024 / 1024).toFixed(1) + 'MB';
    }

    function addFiles(fileList) {
        if (!fileList || !fileList.length) return;
        var added = 0, rejected = 0;
        for (var i = 0; i < fileList.length; i++) {
            var f = fileList[i];
            var type = f.type || '';
            var isMedia = type.indexOf('video/') === 0 || type.indexOf('audio/') === 0 ||
                /\.(mp4|mov|mkv|avi|flv|webm|m4v|ts|mts|3gp|wmv|mp3|m4a|wav|aac|flac|ogg|wma)$/i.test(f.name);
            if (!isMedia) { rejected++; continue; }
            if (f.size > MAX_FILE_MB * 1024 * 1024) {
                showToast('“' + f.name + '” 超过 ' + MAX_FILE_MB + 'MB，已跳过', 'error');
                continue;
            }
            // 去重：同名同大小视为同一文件
            var dup = selectedFiles.some(function (s) { return s.name === f.name && s.size === f.size; });
            if (dup) continue;
            selectedFiles.push(f);
            added++;
        }
        if (rejected) showToast('已跳过 ' + rejected + ' 个非音视频文件', 'error');
        renderFileList();
    }

    function removeFile(index) {
        selectedFiles.splice(index, 1);
        renderFileList();
    }

    function renderFileList() {
        var list = elements.fileList;
        if (!list) return;
        list.innerHTML = '';
        if (!selectedFiles.length) {
            list.hidden = true;
            if (elements.uploadBtn) elements.uploadBtn.disabled = true;
            return;
        }
        list.hidden = false;
        selectedFiles.forEach(function (f, i) {
            var li = document.createElement('li');
            li.className = 'file-list-item';
            li.innerHTML =
                '<span class="fli-icon"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg></span>' +
                '<span class="fli-name">' + escapeHtml(f.name) + '</span>' +
                '<span class="fli-size">' + formatFileSize(f.size) + '</span>' +
                '<button class="fli-remove" title="移除" type="button"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>';
            li.querySelector('.fli-remove').addEventListener('click', function () {
                if (uploadRunning) { showToast('正在转写中，无法移除文件', 'error'); return; }
                removeFile(i);
            });
            list.appendChild(li);
        });
        if (elements.uploadBtn) elements.uploadBtn.disabled = uploadRunning;
    }

    // ─── 上传提交（串行队列 + 逐卡结果）──────────
    async function submitUpload() {
        if (uploadRunning) return;
        if (!selectedFiles.length) { showToast('请先选择文件', 'error'); return; }

        // 上传流程使用独立的多卡容器，隐藏链接流程的单结果/进度/错误区
        resetUI();
        if (elements.stepPills) elements.stepPills.style.display = 'none';
        elements.uploadResults.innerHTML = '';
        uploadRunning = true;
        elements.uploadBtn.disabled = true;
        renderFileList();

        var files = selectedFiles.slice();
        var okCount = 0;
        for (var i = 0; i < files.length; i++) {
            var card = createUploadCard(files[i].name);
            elements.uploadResults.appendChild(card);
            try {
                var data = await transcribeFile(files[i], card);
                fillUploadCardResult(card, data, files[i].name);
                okCount++;
            } catch (err) {
                setCardError(card, err.message || '转写失败');
            }
        }

        uploadRunning = false;
        elements.uploadBtn.disabled = false;
        renderFileList();
        showToast('已完成 ' + okCount + '/' + files.length + ' 个文件', okCount ? 'success' : 'error');
    }

    // 上传单个文件并轮询至完成，返回结果 data（Promise）
    async function transcribeFile(file, card) {
        setCardStatus(card, '正在上传...', '');
        setCardProgress(card, 5);

        var fd = new FormData();
        fd.append('file', file);
        fd.append('language', 'zh');

        var res = await fetch('/api/transcript/upload', { method: 'POST', body: fd });
        var json = await res.json();
        if (!res.ok || !json.success) {
            var msg = (json && json.detail && json.detail.message) || (json && json.message) || ('上传失败 (' + res.status + ')');
            throw new Error(msg);
        }
        var jobId = json.data && json.data.job_id;
        if (!jobId) throw new Error('服务器未返回任务 ID');

        setCardStatus(card, '正在转写...', '');
        return await pollJob(jobId, card);
    }

    // 轮询单个 job，进度回写到卡片；完成 resolve(data)，失败 reject
    function pollJob(jobId, card) {
        return new Promise(function (resolve, reject) {
            var count = 0;
            function tick() {
                fetchWithTimeout('/api/transcript/' + encodeURIComponent(jobId), null, 10000)
                    .then(function (res) { return res.json(); })
                    .then(function (json) {
                        if (!json.success) throw new Error(json.message || '查询失败');
                        var data = json.data;
                        if (data.status === 'completed') { resolve(data); return; }
                        if (data.status === 'failed') { reject(new Error(data.message || '转写失败')); return; }
                        if (data.progress != null) setCardProgress(card, data.progress);
                        if (data.message) setCardStatus(card, data.message, '');
                        next();
                    })
                    .catch(function (err) {
                        if (err.name === 'AbortError' || count <= 3) { next(); return; }
                        reject(err);
                    });
            }
            function next() {
                count++;
                if (count >= MAX_POLL) { reject(new Error('处理超时')); return; }
                setTimeout(tick, document.hidden ? 5000 : 1200);
            }
            setTimeout(tick, 500);
        });
    }

    // ─── 上传结果卡 ─────────────────────────
    function createUploadCard(filename) {
        var card = document.createElement('div');
        card.className = 'result-card upload-result-card';
        card.innerHTML =
            '<div class="urc-header">' +
            '<span class="urc-filename">' + escapeHtml(filename) + '</span>' +
            '<span class="urc-status">排队中...</span>' +
            '</div>' +
            '<div class="urc-progress-track"><div class="urc-progress-fill"></div></div>' +
            '<div class="urc-body"></div>';
        return card;
    }

    function setCardStatus(card, text, cls) {
        var el = card.querySelector('.urc-status');
        if (el) { el.textContent = text; el.className = 'urc-status' + (cls ? ' ' + cls : ''); }
    }

    function setCardProgress(card, pct) {
        var fill = card.querySelector('.urc-progress-fill');
        if (fill) fill.style.width = Math.max(0, Math.min(100, pct)) + '%';
    }

    function setCardError(card, message) {
        setCardStatus(card, '失败', 'error');
        setCardProgress(card, 0);
        var track = card.querySelector('.urc-progress-track');
        if (track) track.style.display = 'none';
        var body = card.querySelector('.urc-body');
        if (body) body.innerHTML = '<p class="error-message" style="text-align:left">' + escapeHtml(message) + '</p>';
    }

    function fillUploadCardResult(card, data, filename) {
        setCardStatus(card, '完成', 'done');
        setCardProgress(card, 100);
        var track = card.querySelector('.urc-progress-track');
        if (track) track.style.display = 'none';

        var body = card.querySelector('.urc-body');
        body.innerHTML =
            '<div class="text-section">' +
            '<div class="section-label">标题文案：</div>' +
            '<div class="section-content title-content"></div>' +
            '</div>' +
            '<div class="text-section">' +
            '<div class="section-label">视频文案：</div>' +
            '<div class="transcript-box"><div class="transcript-text"></div></div>' +
            '</div>' +
            '<div class="export-bar">' +
            '<div class="export-actions">' +
            '<button class="btn btn-primary urc-copy"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>复制全文</button>' +
            '<button class="btn btn-secondary urc-txt"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>导出 TXT</button>' +
            '<button class="btn btn-secondary urc-srt"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>导出 SRT</button>' +
            '</div>' +
            '<div class="export-stats"><span>字数: <strong></strong></span><span>预计阅读: <strong></strong></span></div>' +
            '</div>';

        body.querySelector('.title-content').textContent = data.title || filename || '-';
        body.querySelector('.transcript-text').innerHTML = formatTranscript(data.transcript || '');
        var stats = body.querySelectorAll('.export-stats strong');
        stats[0].textContent = data.char_count != null ? data.char_count.toLocaleString() : '0';
        stats[1].textContent = estimateReadTime(data.char_count || 0);

        var baseName = (data.title || filename || 'transcript').replace(/\.[^.]+$/, '');
        var safeName = baseName.replace(/[\\/:*?"<>|]/g, '_').substring(0, 80);
        var text = data.transcript || body.querySelector('.transcript-text').textContent || '';
        var srt = data.srt || buildSrtFromText(text, data.duration || 0);

        body.querySelector('.urc-copy').addEventListener('click', function () { copyText(text); });
        body.querySelector('.urc-txt').addEventListener('click', function () { downloadText(safeName + '.txt', text); });
        body.querySelector('.urc-srt').addEventListener('click', function () {
            if (!srt) { showToast('没有可下载的内容', 'error'); return; }
            downloadText(safeName + '.srt', srt);
        });
    }


    // ─── Polling ────────────────────────────
    function startPolling(jobId) {
        stopPolling();
        pollCount = 0;
        currentJobId = jobId;
        pollTimer = setTimeout(function () { pollOnce(jobId); }, 500);
    }

    function stopPolling() {
        if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
        currentJobId = null;
        pollCount = 0;
    }

    function scheduleNext(jobId) {
        pollCount++;
        if (pollCount >= MAX_POLL) {
            stopPolling();
            setProcessing(false);
            showError('处理超时，请重试');
            return;
        }
        var delay = document.hidden ? 5000 : 1200;
        pollTimer = setTimeout(function () { pollOnce(jobId); }, delay);
    }

    async function pollOnce(jobId) {
        if (jobId !== currentJobId) return;
        try {
            var res = await fetchWithTimeout('/api/transcript/' + encodeURIComponent(jobId), null, 10000);
            var json = await res.json();
            if (!res.ok) throw new Error(json.message || '查询失败 (' + res.status + ')');
            if (!json.success) throw new Error(json.message || '查询失败');

            var data = json.data;

            if (data.status === 'completed') {
                stopPolling();
                stopTimer();
                setProgress(100);
                setProcessing(false);
                renderResult(data);
                showToast('文案提取成功', 'success');
                return;
            }
            if (data.status === 'failed' || data.status === 'error') {
                stopPolling();
                stopTimer();
                setProcessing(false);
                showError(data.message || '提取失败，请重试');
                return;
            }

            if (data.step) updateSteps(data.step);
            if (data.message) elements.statusMessage.textContent = data.message;
            if (data.progress != null) setProgress(data.progress);
            scheduleNext(jobId);
        } catch (err) {
            console.warn('Poll error:', err.name, err.message);
            if (err.name === 'AbortError') {
                scheduleNext(jobId);
            } else if (pollCount > 3) {
                stopPolling();
                setProcessing(false);
                showError(err.message || '网络连接异常，请重试');
            } else {
                elements.statusMessage.textContent = '查询状态异常，正在重试...';
                scheduleNext(jobId);
            }
        }
    }

    // ─── Render Result ──────────────────────
    function renderResult(data) {
        lastResult = data;
        elements.videoTitle.textContent = data.title || '-';
        elements.videoAuthor.textContent = data.author || '-';
        elements.videoPlatform.textContent = data.platform || '-';
        elements.videoDuration.textContent = formatDuration(data.duration);

        // Video thumbnail
        var preview = elements.videoPreview;
        preview.innerHTML = '';
        preview.style.cursor = 'default';
        preview.onclick = null;

        if (data.cover) {
            var img = document.createElement('img');
            img.src = data.cover;
            img.alt = data.title || '视频封面';
            img.onerror = function () {
                preview.innerHTML = '<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3"><polygon points="5 3 19 12 5 21 5 3"/></svg>';
            };
            preview.appendChild(img);
        } else {
            preview.innerHTML = '<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3"><polygon points="5 3 19 12 5 21 5 3"/></svg>';
        }

        // Click to play video inline
        if (data.video_url) {
            // Add play button overlay
            var playBtn = document.createElement('div');
            playBtn.className = 'play-btn-overlay';
            playBtn.innerHTML = '<svg width="36" height="36" viewBox="0 0 24 24" fill="white"><polygon points="5 3 19 12 5 21 5 3"/></svg>';
            preview.appendChild(playBtn);

            var platform = data.platform || 'douyin';
            var refererMap = {
                douyin: 'https://www.douyin.com/',
                bilibili: 'https://www.bilibili.com/',
                weibo: 'https://weibo.com/',
                xiaohongshu: 'https://www.xiaohongshu.com/',
                tiktok: 'https://www.tiktok.com/',
                youtube: 'https://www.youtube.com/',
                instagram: 'https://www.instagram.com/',
            };
            var referer = refererMap[platform] || 'https://www.douyin.com/';
            var proxyUrl = '/api/transcript/proxy?video_url=' + encodeURIComponent(data.video_url) + '&referer=' + encodeURIComponent(referer);

            preview.style.cursor = 'pointer';
            preview.onclick = function () {
                var video = document.createElement('video');
                video.src = proxyUrl;
                video.controls = true;
                video.autoplay = true;
                video.loop = true;
                video.playsInline = true;
                video.style.cssText = 'width:100%;height:100%;object-fit:contain;background:#000;border-radius:var(--radius-md);';
                video.onerror = function () {
                    window.open(data.video_url, '_blank');
                };
                preview.innerHTML = '';
                preview.appendChild(video);
                preview.style.cursor = 'default';
                preview.onclick = null;
            };
        }

        // Format transcript
        elements.transcriptText.innerHTML = formatTranscript(data.transcript || '');

        // Update stats
        var charCountStat = document.getElementById('charCountStat');
        var readTime = document.getElementById('readTime');
        if (charCountStat) charCountStat.textContent = data.char_count != null ? data.char_count.toLocaleString() : '0';
        if (readTime) readTime.textContent = estimateReadTime(data.char_count || 0);

        // Highlight matching platform icon
        highlightPlatform(data.platform);

        showResult();
    }

    // ─── Retry ──────────────────────────────
    function handleRetry() {
        resetUI();
        elements.urlInput.focus();
    }

    // ─── Events ─────────────────────────────
    function bindEvents() {
        elements.themeToggle.addEventListener('click', toggleTheme);
        elements.pasteBtn.addEventListener('click', pasteFromClipboard);
        elements.submitBtn.addEventListener('click', submitUrl);
        elements.copyBtn.addEventListener('click', copyToClipboard);
        elements.downloadBtn.addEventListener('click', downloadAsTxt);
        if (elements.downloadSrtBtn) elements.downloadSrtBtn.addEventListener('click', downloadAsSrt);
        elements.retryBtn.addEventListener('click', handleRetry);
        elements.retryFromErrorBtn.addEventListener('click', handleRetry);

        // Auto-resize textarea on input
        elements.urlInput.addEventListener('input', function () {
            this.style.height = 'auto';
            this.style.height = Math.min(this.scrollHeight, 120) + 'px';
        });

        elements.urlInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitUrl(); }
        });

        elements.urlInput.addEventListener('paste', function (e) {
            setTimeout(function () {
                var text = elements.urlInput.value.trim();
                var url = extractUrl(text);
                if (url) {
                    if (url !== text) {
                        elements.urlInput.value = url;
                        showToast('已自动提取链接', 'success', 1500);
                    }
                    submitUrl();
                }
            }, 100);
        });

        // Tab 切换
        $$('.tab-item').forEach(function (t) {
            t.addEventListener('click', function () { switchTab(t.getAttribute('data-tab')); });
        });
        // 上传区交互
        if (elements.uploadZone) {
            elements.uploadZone.addEventListener('click', function () { elements.fileInput.click(); });
            elements.uploadZone.addEventListener('dragover', function (e) { e.preventDefault(); elements.uploadZone.classList.add('dragover'); });
            elements.uploadZone.addEventListener('dragleave', function () { elements.uploadZone.classList.remove('dragover'); });
            elements.uploadZone.addEventListener('drop', function (e) {
                e.preventDefault();
                elements.uploadZone.classList.remove('dragover');
                if (e.dataTransfer.files && e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
            });
        }
        if (elements.fileInput) {
            elements.fileInput.addEventListener('change', function (e) {
                if (e.target.files && e.target.files.length) addFiles(e.target.files);
                elements.fileInput.value = '';
            });
        }
        if (elements.uploadBtn) elements.uploadBtn.addEventListener('click', submitUpload);

        // Cleanup on page unload
        window.addEventListener('beforeunload', function () {
            stopPolling();
            if (fetchAbort) { fetchAbort.abort(); }
        });

        // Reduce polling frequency when page is hidden
        document.addEventListener('visibilitychange', function () {
            if (document.hidden && pollTimer) {
                clearTimeout(pollTimer);
                pollTimer = setTimeout(function () {
                    if (currentJobId) pollOnce(currentJobId);
                }, 5000);
            }
        });
    }

    // ─── Init ───────────────────────────────
    function init() {
        initTheme();
        loadPlatforms();
        bindEvents();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
