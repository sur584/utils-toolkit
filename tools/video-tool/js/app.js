/**
 * 小小工具箱 - 视频解析下载 3.0.0
 * 支持：抖音、快手、B站、微博、小红书、TikTok、YouTube、Instagram、Twitter/X、西瓜视频
 */

const API_BASE = window.location.origin;

// CORS 代理服务列表（用于服务端无法直连的平台，浏览器端通过代理获取 HTML 后交给服务端解析）
const CORS_PROXIES = [
    (url) => `https://corsproxy.io/?url=${encodeURIComponent(url)}`,
    (url) => `https://api.allorigins.win/raw?url=${encodeURIComponent(url)}`,
];

// 需要 CORS 代理中继的平台（服务端无法直接访问，依赖客户端代理获取 HTML）
const NEEDS_RELAY = ['tiktok'];

const PLATFORM_NAMES = {
    douyin: '抖音', bilibili: 'B站', weibo: '微博',
    xiaohongshu: '小红书', tiktok: 'TikTok', youtube: 'YouTube',
    instagram: 'Instagram', twitter: 'Twitter/X', xigua: '西瓜视频',
    wechat_channels: '微信视频号', direct: '直接链接',
};

async function readJsonResponse(resp, apiName = '接口') {
    const text = await resp.text();
    const trimmed = text.trim();

    if (!trimmed) {
        throw new Error(`${apiName}返回为空（HTTP ${resp.status}）`);
    }

    if (trimmed.startsWith('<')) {
        throw new Error(`${apiName}返回了 HTML 页面，不是 JSON。请确认后端 API 路由存在（HTTP ${resp.status}）`);
    }

    try {
        return JSON.parse(trimmed);
    } catch {
        throw new Error(`${apiName}返回的不是有效 JSON（HTTP ${resp.status}）`);
    }
}

// ─── 平台检测 & CORS 中继 ─────────────────────────
function _detectPlatform(url) {
    const patterns = {
        tiktok: /tiktok\.com\//,
        youtube: /youtube\.com\/|youtu\.be\//,
        instagram: /instagram\.com\//,
        twitter: /twitter\.com\/|x\.com\//,
    };
    for (const [name, re] of Object.entries(patterns)) {
        if (re.test(url)) return name;
    }
    return null;
}

async function _tryCorsProxyRelay(url) {
    const platform = _detectPlatform(url);
    if (!platform || !NEEDS_RELAY.includes(platform)) return null;

    // 提取视频 ID
    const vidMatch = url.match(/\/video\/(\d+)/);
    const userMatch = url.match(/\/(@[\w.-]+)\//);
    const videoId = vidMatch ? vidMatch[1] : '';
    const username = userMatch ? userMatch[1] : '@';

    const cleanUrl = url.split('?')[0];
    const apiUrl = `https://www.tiktok.com/oembed?url=${encodeURIComponent(cleanUrl)}`;
    const oembedUrls = [
        `${API_BASE}/api/tiktok-oembed?url=${encodeURIComponent(cleanUrl)}`,
        ...CORS_PROXIES.map((buildProxyUrl) => buildProxyUrl(apiUrl)),
    ];

    for (const oembedUrl of oembedUrls) {
        try {
            showStatus(statusBar, `🔄 获取 TikTok 数据...`, 'info');
            const resp = await fetch(oembedUrl, { signal: AbortSignal.timeout(15000) });
            if (!resp.ok) continue;
            const text = await resp.text();
            if (!text || text.length < 20) continue;
            const oembed = JSON.parse(text.trim());
            if (oembed && oembed.author_name) {
                return {
                    success: true,
                    data: {
                        id: videoId,
                        platform: 'tiktok',
                        title: oembed.title || '无标题',
                        author: (oembed.author_name || '').replace('@', ''),
                        cover: oembed.thumbnail_url || '',
                        duration: 0,
                        video_url: `tt://${username}/video/${videoId}`,
                        video_url_no_watermark: '',
                        digg_count: 0,
                        comment_count: 0,
                        share_count: 0,
                        is_relay_only: true,
                    }
                };
            }
        } catch {
            continue;
        }
    }

    return null;
}


// ─── 代理配置 ─────────────────────────────────────
async function loadProxyStatus() {
    try {
        const resp = await fetch(`${API_BASE}/api/proxy-config`);
        const data = await readJsonResponse(resp, '代理配置接口');
        if (proxyInput) proxyInput.value = data.client_proxy || '';
        updateProxyStatus(data.active);
    } catch { /* 忽略 */ }
}

function updateProxyStatus(activeProxy) {
    if (!proxyStatus) return;
    if (activeProxy) {
        proxyStatus.textContent = `（代理: ${activeProxy}）`;
        proxyStatus.style.color = 'var(--success, #22c55e)';
        if (proxyClearBtn) proxyClearBtn.style.display = 'inline-flex';
    } else {
        proxyStatus.textContent = '（未配置）';
        proxyStatus.style.color = 'var(--danger, #ef4444)';
        if (proxyClearBtn) proxyClearBtn.style.display = 'none';
    }
}

async function handleProxySave() {
    if (!proxyInput) return;
    const proxy = proxyInput.value.trim();
    try {
        const resp = await fetch(`${API_BASE}/api/proxy-config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ proxy }),
        });
        const data = await readJsonResponse(resp, '保存代理配置接口');
        if (data.success) {
            showToast('代理配置已保存', 'success');
            updateProxyStatus(proxy || '');
        } else {
            showToast('保存失败', 'error');
        }
    } catch (err) {
        showToast(`保存失败: ${err.message}`, 'error');
    }
}

async function handleProxyClear() {
    if (proxyInput) proxyInput.value = '';
    await handleProxySave();
}


// ─── DOM ───────────────────────────────────────────
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const navTabs = $$('.nav-tab');
const tabPanels = $$('.tab-panel');
const urlInput = $('#urlInput');
const pasteBtn = $('#pasteBtn');
const parseBtn = $('#parseBtn');
const statusBar = $('#statusBar');
const resultPanel = $('#resultPanel');
let videoCover = $('#videoCover');
let videoTitle = $('#videoTitle');
let videoAuthor = $('#videoAuthor');
let videoDuration = $('#videoDuration');
let videoDigg = $('#videoDigg');
let videoComment = $('#videoComment');
let platformBadge = $('#platformBadge');
const downloadBtn = $('#downloadBtn');
const copyLinkBtn = $('#copyLinkBtn');
const previewBtn = $('#previewBtn');
const playBtn = $('#playBtn');
const progressBar = $('#progressBar');
const progressFill = $('#progressFill');
const progressText = $('#progressText');
const batchInput = $('#batchInput');
const batchPasteBtn = $('#batchPasteBtn');
const batchParseBtn = $('#batchParseBtn');
const batchStatus = $('#batchStatus');
const batchResults = $('#batchResults');
const clearHistoryBtn = $('#clearHistoryBtn');
const historyList = $('#historyList');
const historyEmpty = $('#historyEmpty');
const previewModal = $('#previewModal');
const previewVideo = $('#previewVideo');
const previewFallback = $('#previewFallback');
const closeModalBtn = $('#closeModal');
const themeToggle = $('#themeToggle');
const proxyInput = $('#proxyInput');
const proxyDetectBtn = $('#proxyDetectBtn');
const proxySaveBtn = $('#proxySaveBtn');
const proxyClearBtn = $('#proxyClearBtn');
const proxyStatus = $('#proxyStatus');

let currentVideoData = null;
let selectedImages = new Set();
const activeDownloads = new Set();
let downloadAbortController = null;  // 单视频下载的取消控制器（非空 = 正在下载）

// ─── 博主主页 DOM 引用与状态 ─────────────────────
const profileInput = $('#profileInput');
const profileLimit = $('#profileLimit');
const profilePasteBtn = $('#profilePasteBtn');
const profileParseBtn = $('#profileParseBtn');
const profileStatus = $('#profileStatus');
const profileHeader = $('#profileHeader');
const profileAuthorName = $('#profileAuthorName');
const profileMeta = $('#profileMeta');
const profileSelectAll = $('#profileSelectAll');
const profileSelectedCount = $('#profileSelectedCount');
const profileDownloadSelectedBtn = $('#profileDownloadSelectedBtn');
const profileZipBtn = $('#profileZipBtn');
const profileCopyLinksBtn = $('#profileCopyLinksBtn');
const profileGrid = $('#profileGrid');
const profilePager = $('#profilePager');
const profilePrevBtn = $('#profilePrevBtn');
const profileNextBtn = $('#profileNextBtn');
const profilePageInfo = $('#profilePageInfo');

let profileVideos = [];
const profileSelected = new Set();
let profilePage = 1;
let profileHasMore = false;
let profileTotalPages = null;
let profileUrl = '';
let profilePlatform = null;

// ─── 代理自动检测 ────────────────────────────────

async function autoDetectProxy(silent = true) {
    if (proxyStatus && proxyStatus.textContent.includes('（未配置）') === false && silent) return;
    const origStatus = proxyStatus ? proxyStatus.textContent : '';

    if (proxyStatus) {
        proxyStatus.textContent = '（正在检测客户端代理...）';
        proxyStatus.style.color = 'var(--warning, #f59e0b)';
    }
    if (proxyDetectBtn) proxyDetectBtn.disabled = true;

    try {
        const resp = await fetch(`${API_BASE}/api/proxy-config/auto-detect`, { method: 'POST' });
        const data = await readJsonResponse(resp, '自动检测代理接口');
        if (data.success) {
            updateProxyStatus(data.active || data.proxy);
            if (proxyInput) proxyInput.value = data.proxy || '';
            if (!silent) showToast(`已检测到代理: ${data.proxy}`, 'success');
            return;
        }
        if (proxyStatus) proxyStatus.textContent = origStatus || '（未配置）';
        if (!silent) showToast(data.message || '未检测到可用代理', 'warning');
    } catch (err) {
        if (proxyStatus) proxyStatus.textContent = origStatus || '（未配置）';
        if (!silent) showToast(`自动检测失败: ${err.message}`, 'error');
    } finally {
        if (proxyDetectBtn) proxyDetectBtn.disabled = false;
    }
}


// ─── 初始化 ──────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initTabs();
    initEventListeners();
    loadProxyStatus();
    // 页面加载后自动检测代理（非阻塞，不要等待完成）
    autoDetectProxy();
});

// ─── 主题 ────────────────────────────────────────
function initTheme() {
    setTheme(localStorage.getItem('theme') || 'light');
}

function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
    themeToggle.querySelector('.theme-icon').textContent = theme === 'dark' ? '☀' : '☾';
}

themeToggle.addEventListener('click', () => {
    setTheme(document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
});

// ─── 标签页 ──────────────────────────────────────
function initTabs() {
    navTabs.forEach((tab) => {
        tab.addEventListener('click', () => {
            const target = tab.dataset.tab;
            navTabs.forEach((t) => t.classList.remove('active'));
            tab.classList.add('active');
            tabPanels.forEach((p) => p.classList.remove('active'));
            $(`#panel-${target}`).classList.add('active');
            if (target === 'history') loadHistory();
        });
    });
}

// ─── 事件 ────────────────────────────────────────
function initEventListeners() {
    pasteBtn.addEventListener('click', handlePaste);
    parseBtn.addEventListener('click', handleParse);
    downloadBtn.addEventListener('click', handleDownload);
    copyLinkBtn.addEventListener('click', handleCopyLink);
    previewBtn.addEventListener('click', handlePreview);
    playBtn.addEventListener('click', handlePreview);
    urlInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleParse();
    });
    batchPasteBtn.addEventListener('click', async () => {
        const t = await readClipboard();
        if (t) batchInput.value = t;
    });
    batchParseBtn.addEventListener('click', handleBatchParse);
    clearHistoryBtn.addEventListener('click', handleClearHistory);
    closeModalBtn.addEventListener('click', closePreview);
    previewModal.addEventListener('click', (e) => { if (e.target === previewModal) closePreview(); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closePreview(); });

    const selectAllCb = $('#selectAllCb');
    const downloadSelectedBtn = $('#downloadSelectedBtn');
    const downloadAllImagesBtn = $('#downloadAllImagesBtn');
    const copySelectedLinksBtn = $('#copySelectedLinksBtn');
    if (selectAllCb) selectAllCb.addEventListener('change', handleSelectAll);
    if (downloadSelectedBtn) downloadSelectedBtn.addEventListener('click', handleDownloadSelected);
    if (downloadAllImagesBtn) downloadAllImagesBtn.addEventListener('click', handleDownloadAllImages);
    if (copySelectedLinksBtn) copySelectedLinksBtn.addEventListener('click', handleCopySelectedLinks);

    // 博主主页
    if (profilePasteBtn) profilePasteBtn.addEventListener('click', async () => {
        const t = await readClipboard();
        if (t) profileInput.value = t;
    });
    if (profileParseBtn) profileParseBtn.addEventListener('click', () => handleProfileParse(1));
    if (profileInput) profileInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); handleProfileParse(1); }
    });
    if (profileSelectAll) profileSelectAll.addEventListener('change', handleProfileSelectAll);
    if (profileDownloadSelectedBtn) profileDownloadSelectedBtn.addEventListener('click', handleProfileDownloadSelected);
    if (profileZipBtn) profileZipBtn.addEventListener('click', handleProfileDownloadZip);
    if (profileCopyLinksBtn) profileCopyLinksBtn.addEventListener('click', handleProfileCopyLinks);
    if (profilePrevBtn) profilePrevBtn.addEventListener('click', () => { if (profilePage > 1) handleProfileParse(profilePage - 1); });
    if (profileNextBtn) profileNextBtn.addEventListener('click', () => { if (profileHasMore) handleProfileParse(profilePage + 1); });
    // 改「每页数量」后从第 1 页重新解析，避免翻页中途改数量导致偏移错位
    if (profileLimit) profileLimit.addEventListener('change', () => { if (profileUrl) handleProfileParse(1); });

    // 手动输入视频URL
    const applyVideoUrlBtn = document.getElementById('applyVideoUrlBtn');
    const manualVideoUrlInput = document.getElementById('manualVideoUrlInput');
    if (applyVideoUrlBtn && manualVideoUrlInput) {
        applyVideoUrlBtn.addEventListener('click', () => {
            const url = manualVideoUrlInput.value.trim();
            if (!url) {
                showToast('请输入视频URL', 'error');
                return;
            }
            if (!url.startsWith('http')) {
                showToast('请输入有效的URL', 'error');
                return;
            }
            // 更新当前视频数据
            if (currentVideoData) {
                currentVideoData.video_url = url;
                currentVideoData.video_url_no_watermark = url;
                // 更新按钮状态
                setDownloadLoading(false);
                downloadBtn.querySelector('.btn-text').textContent = '⬇ 下载视频';
                downloadBtn.title = '';
                previewBtn.textContent = '▶ 在线预览';
                copyLinkBtn.textContent = '🔗 复制直链';
                // 隐藏手动输入区域
                const manualVideoUrlEl = document.getElementById('manualVideoUrl');
                if (manualVideoUrlEl) manualVideoUrlEl.style.display = 'none';
                showToast('视频URL已应用，可以下载了', 'success');
            }
        });
        // 支持回车键
        manualVideoUrlInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') applyVideoUrlBtn.click();
        });
    }

    // 代理配置
    if (proxyDetectBtn) {
        proxyDetectBtn.addEventListener('click', () => autoDetectProxy(false));
    }
    if (proxySaveBtn) {
        proxySaveBtn.addEventListener('click', handleProxySave);
    }
    if (proxyClearBtn) {
        proxyClearBtn.addEventListener('click', handleProxyClear);
    }
    if (proxyInput) {
        proxyInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && proxySaveBtn) proxySaveBtn.click();
        });
    }
}

// ─── 剪贴板 ──────────────────────────────────────
async function readClipboard() {
    try { return await navigator.clipboard.readText(); }
    catch { showToast('无法读取剪贴板', 'error'); return ''; }
}

async function handlePaste() {
    const t = await readClipboard();
    if (t) { urlInput.value = t; showToast('已粘贴', 'success'); }
}

// ─── 状态 ────────────────────────────────────────
function showStatus(container, message, type = 'info') {
    container.style.display = 'flex';
    container.className = `status-bar ${type}`;
    container.textContent = '';
    const span = document.createElement('span');
    span.className = 'status-text';
    span.style.whiteSpace = 'pre-line';
    span.textContent = message;
    container.appendChild(span);
}

// ─── 平台高亮 ────────────────────────────────────
function highlightPlatform(platform) {
    $$('.platform-tag').forEach((t) => t.classList.remove('active'));
    if (platform) {
        const tag = $(`.platform-tag[data-platform="${platform}"]`);
        if (tag) tag.classList.add('active');
    }
}

// ─── 单个解析（带进度显示）────────────────────────
let parseTimer = null;
let parseStartTime = 0;

async function handleParse() {
    const url = urlInput.value.trim();
    if (!url) { showToast('请输入视频链接', 'error'); return; }

    setParseLoading(true);
    statusBar.style.display = 'none';
    resultPanel.style.display = 'none';
    selectedImages.clear();
    showSkeleton();

    parseStartTime = Date.now();
    const steps = [
        { time: 0, text: '🔍 正在识别平台...' },
        { time: 3, text: '📡 正在获取页面数据...' },
        { time: 8, text: '⏳ 正在解析视频信息（部分平台较慢）...' },
        { time: 15, text: '⏳ 解析时间较长，请耐心等待...' },
    ];

    function updateParseStatus() {
        const elapsed = ((Date.now() - parseStartTime) / 1000).toFixed(0);
        let step = steps[0].text;
        for (const s of steps) {
            if (elapsed >= s.time) step = s.text;
        }
        showStatus(statusBar, `${step} (${elapsed}s)`, 'info');
    }

    updateParseStatus();
    parseTimer = setInterval(updateParseStatus, 1000);

    try {
        const resp = await fetch(`${API_BASE}/api/parse`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url }),
        });
        const result = await readJsonResponse(resp, '视频解析接口');
        const elapsed = ((Date.now() - parseStartTime) / 1000).toFixed(1);

        if (result.success && result.data) {
            currentVideoData = result.data;
            renderVideoResult(result.data);
            highlightPlatform(result.data.platform);

            // 视频号无直链时显示提示
            let statusMsg = `✅ 解析成功 — ${PLATFORM_NAMES[result.data.platform] || result.data.platform}（${elapsed}s）`;
            let statusType = 'success';
            if (result.data.platform === 'wechat_channels' && !result.data.video_url) {
                statusMsg += '\n\n⚠️ 已获取视频元数据（标题、作者、封面等），但视频直链需要抓包工具获取';
                statusType = 'warning';
            }
            showStatus(statusBar, statusMsg, statusType);
        } else {
            // 直连解析失败时，尝试通过 CORS 代理中继获取页面 HTML
            const relayResult = await _tryCorsProxyRelay(url);
            if (relayResult && relayResult.data) {
                currentVideoData = relayResult.data;
                renderVideoResult(relayResult.data);
                highlightPlatform(relayResult.data.platform);
                showStatus(statusBar, `✅ 解析成功（CORS 代理中继）— ${PLATFORM_NAMES[relayResult.data.platform] || relayResult.data.platform}\n\n⚠️ 下载需要配置客户端代理或设备开启 VPN（${elapsed}s）`, 'warning');
            } else {
                hideSkeleton();
                resultPanel.style.display = 'none';
                let errorMsg = result.message || '解析失败';
                if (_detectPlatform(url) === 'tiktok') {
                    errorMsg += '\n\nTikTok 需要开启可访问 TikTok 的网络，或在上方配置 HTTP 代理地址。';
                } else if (result.guide || result.hint) {
                    errorMsg += '\n\n' + (result.guide || result.hint);
                }
                showStatus(statusBar, `❌ ${errorMsg}（${elapsed}s）`, 'error');
            }
        }
    } catch (err) {
        const elapsed = ((Date.now() - parseStartTime) / 1000).toFixed(1);
        hideSkeleton();
        resultPanel.style.display = 'none';
        showStatus(statusBar, `❌ 网络错误: ${err.message}（${elapsed}s）`, 'error');
    } finally {
        if (parseTimer) { clearInterval(parseTimer); parseTimer = null; }
        setParseLoading(false);
    }
}

function setParseLoading(loading) {
    parseBtn.querySelector('.btn-text').style.display = loading ? 'none' : 'inline';
    parseBtn.querySelector('.btn-loading').style.display = loading ? 'inline-flex' : 'none';
    parseBtn.disabled = loading;
}

// ─── 骨架屏 ──────────────────────────────────────
function showSkeleton() {
    resultPanel.style.display = 'block';
    const galleryActions = $('#galleryActions');
    if (galleryActions) galleryActions.style.display = 'none';

    const videoInfo = resultPanel.querySelector('.video-info');
    if (!videoInfo) return;
    videoInfo._savedHTML = videoInfo.innerHTML;
    videoInfo.innerHTML = `
        <div class="video-cover-wrap"><div class="skeleton skeleton-cover"></div></div>
        <div class="video-meta">
            <div class="skeleton skeleton-title"></div>
            <div class="skeleton skeleton-text"></div>
            <div class="skeleton skeleton-text" style="width:35%"></div>
        </div>`;
    resultPanel.querySelector('.action-buttons').style.display = 'none';
    const existingGallery = document.getElementById('imageGallery');
    if (existingGallery) existingGallery.style.display = 'none';
}

function hideSkeleton() {
    const videoInfo = resultPanel.querySelector('.video-info');
    if (videoInfo && videoInfo._savedHTML) {
        videoInfo.innerHTML = videoInfo._savedHTML;
        delete videoInfo._savedHTML;
    }
    resultPanel.querySelector('.action-buttons').style.display = 'flex';
    videoCover = $('#videoCover');
    videoTitle = $('#videoTitle');
    videoAuthor = $('#videoAuthor');
    videoDuration = $('#videoDuration');
    videoDigg = $('#videoDigg');
    videoComment = $('#videoComment');
    platformBadge = $('#platformBadge');
}

function renderVideoResult(data) {
    hideSkeleton();
    resultPanel.style.display = 'block';
    videoCover.src = data.cover || '';
    videoCover.onerror = () => {
        videoCover.src = 'data:image/svg+xml,' + encodeURIComponent(
            '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="400" fill="%231a1f35"><rect width="240" height="400"/><text x="120" y="200" text-anchor="middle" fill="%2364748b" font-size="14">无封面</text></svg>'
        );
    };
    videoTitle.textContent = data.title || '无标题';
    videoAuthor.textContent = data.author || '未知作者';

    const isImage = data.note_type === 'image' || (data.image_list && data.image_list.length > 0);
    if (isImage && data.image_list) {
        videoDuration.textContent = `图文 · ${data.image_list.length} 张`;
    } else {
        videoDuration.textContent = formatDuration(data.duration);
    }

    videoDigg.textContent = formatNumber(data.digg_count);
    videoComment.textContent = formatNumber(data.comment_count);
    platformBadge.textContent = PLATFORM_NAMES[data.platform] || data.platform || '';

    const isVideo = data.video_url && !isImage;
    const isWechatNoUrl = data.platform === 'wechat_channels' && !isImage && !data.video_url;

    // 显示/隐藏手动输入视频URL区域
    const manualVideoUrlEl = document.getElementById('manualVideoUrl');
    if (manualVideoUrlEl) {
        manualVideoUrlEl.style.display = isWechatNoUrl ? 'block' : 'none';
    }

    // 根据是否有视频链接设置按钮状态
    setDownloadLoading(false);
    if (isWechatNoUrl) {
        // 视频号但无直链：显示提示信息
        downloadBtn.querySelector('.btn-text').textContent = '⚠ 需要抓包获取直链';
        downloadBtn.disabled = true;
        downloadBtn.title = '视频号需要抓包工具获取视频直链';
        previewBtn.textContent = '▶ 查看封面';
        copyLinkBtn.textContent = '🔗 复制封面链接';
    } else {
        downloadBtn.querySelector('.btn-text').textContent = isVideo ? '⬇ 下载视频' : '⬇ 下载全部 ZIP';
        downloadBtn.disabled = false;
        downloadBtn.title = '';
        previewBtn.textContent = isVideo ? '▶ 在线预览' : '🖼 查看图片';
        copyLinkBtn.textContent = '🔗 复制直链';
    }

    let galleryEl = document.getElementById('imageGallery');
    const galleryActions = $('#galleryActions');
    selectedImages.clear();

    if (isImage && data.image_list) {
        if (!galleryEl) {
            galleryEl = document.createElement('div');
            galleryEl.id = 'imageGallery';
            galleryEl.className = 'image-gallery';
            resultPanel.querySelector('.video-info')?.after(galleryEl);
        }
        const referer = getReferer(data.platform);
        galleryEl.innerHTML = data.image_list.map((url, i) =>
            `<div class="gallery-item" data-index="${i}">
                <input type="checkbox" class="gallery-checkbox" data-index="${i}">
                <img src="${API_BASE}/api/proxy?video_url=${encodeURIComponent(url)}&referer=${encodeURIComponent(referer)}" alt="图片 ${i + 1}" loading="lazy" onerror="this.parentElement.style.display='none'">
                <span class="gallery-index">${i + 1}</span>
            </div>`
        ).join('');
        galleryEl.style.display = 'grid';
        if (galleryActions) galleryActions.style.display = 'flex';
        updateSelectedCount();
    } else if (galleryEl) {
        galleryEl.style.display = 'none';
        galleryEl.innerHTML = '';
        if (galleryActions) galleryActions.style.display = 'none';
    }
}

// ─── 下载 ────────────────────────────────────────
function setDownloadLoading(loading) {
    /** 设置下载按钮加载状态；下载中按钮保持可点击以便取消 */
    downloadBtn.querySelector('.btn-text').style.display = loading ? 'none' : 'inline';
    downloadBtn.querySelector('.btn-loading').style.display = loading ? 'inline-flex' : 'none';
    downloadBtn.disabled = false;
}

async function handleDownload() {
    // 正在下载时再次点击 = 取消
    if (downloadAbortController) {
        downloadAbortController.abort();
        return;
    }

    const isImage = currentVideoData?.note_type === 'image' || (currentVideoData?.image_list?.length > 0);

    if (isImage && currentVideoData.image_list) {
        await handleDownloadAllImages();
        return;
    }

    // 视频号无直链时的处理
    if (currentVideoData?.platform === 'wechat_channels' && !currentVideoData?.video_url) {
        showToast('视频号需要抓包工具获取视频直链，请使用 Fiddler/mitmproxy', 'warning');
        return;
    }

    // TikTok CORS 中继模式：需要代理才能下载
    if (currentVideoData?.platform === 'tiktok' && currentVideoData?.is_relay_only) {
        const hasProxy = proxyInput?.value && proxyInput.value.trim().length > 0;
        if (!hasProxy) {
            showToast('TikTok 下载需要配置客户端代理（或设备开启 VPN），请在页面上方配置代理地址', 'warning');
            return;
        }
    }

    if (!currentVideoData?.video_url) { showToast('无可用下载地址', 'error'); return; }

    downloadAbortController = new AbortController();
    const signal = downloadAbortController.signal;
    setDownloadLoading(true);
    progressBar.style.display = 'block';
    progressFill.style.width = '0%';
    progressText.textContent = '0%';
    showStatus(statusBar, '⏳ 正在获取视频（可点击按钮取消）...', 'info');

    try {
        const videoUrl = currentVideoData.video_url_no_watermark || currentVideoData.video_url || '';
        const title = (currentVideoData.title || 'video').substring(0, 50);
        const ref = getReferer(currentVideoData.platform);

        // 对于需要中继的平台（如 TikTok），优先客户端直连下载（浏览器使用客户端的代理/VPN）
        if (NEEDS_RELAY.includes(currentVideoData.platform)) {
            const done = await _relayDownload(videoUrl, title, ref, signal);
            if (done) return;
            // 客户端下载失败，回退到服务端下载
        }

        const resp = await fetch(`${API_BASE}/api/download?video_url=${encodeURIComponent(videoUrl)}&title=${encodeURIComponent(title)}&referer=${encodeURIComponent(ref)}`, { signal });

        if (!resp.ok) {
            let detail = `HTTP ${resp.status}`;
            try {
                const err = await readJsonResponse(resp, '下载接口');
                detail = err.detail || detail;
            } catch (e) {
                detail = `${detail}: ${e.message}`;
            }
            throw new Error(detail);
        }

        const blob = await resp.blob();
        const filename = resp.headers.get('Content-Disposition')?.match(/filename=(.+)/)?.[1] || `${title}.mp4`;
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = filename;
        a.click();
        URL.revokeObjectURL(a.href);
        showToast('下载完成', 'success');
        progressFill.style.width = '100%';
        progressText.textContent = '100%';
        showStatus(statusBar, '✅ 下载完成', 'success');
    } catch (err) {
        if (err.name === 'AbortError') {
            showToast('已取消下载', 'info');
            showStatus(statusBar, '已取消下载', 'info');
        } else {
            showToast(`下载失败: ${err.message}`, 'error');
        }
    } finally {
        downloadAbortController = null;
        setDownloadLoading(false);
        setTimeout(() => { progressBar.style.display = 'none'; }, 3000);
    }
}

// 客户端直连下载（利用浏览器所在设备的代理/VPN）
async function _relayDownload(videoUrl, title, ref, signal) {
    // tt:// / yt:// / bl:// 不是真实 URL，跳过客户端直连尝试
    if (videoUrl.startsWith('tt://') || videoUrl.startsWith('yt://') || videoUrl.startsWith('bl://')) {
        return false;
    }

    // 组合外部取消信号与 30s 超时
    const relaySignal = signal
        ? AbortSignal.any([signal, AbortSignal.timeout(30000)])
        : AbortSignal.timeout(30000);

    // 先尝试直接 fetch 视频（客户端代理会处理连接）
    try {
        showStatus(statusBar, '🔄 尝试客户端直连下载...', 'info');
        const resp = await fetch(videoUrl, {
            headers: { 'Referer': ref, 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' },
            signal: relaySignal,
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const blob = await resp.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `${title}.mp4`;
        a.click();
        URL.revokeObjectURL(a.href);
        showToast('下载完成', 'success');
        progressFill.style.width = '100%';
        progressText.textContent = '100%';
        showStatus(statusBar, '✅ 下载完成', 'success');
        return true;
    } catch (e) {
        // 用户主动取消：向上抛出，由 handleDownload 统一提示，不再回退
        if (signal?.aborted) throw e;
        // 直连失败，尝试通过 CORS 代理下载
        try {
            showStatus(statusBar, '🔄 尝试通过 CORS 代理下载...', 'info');
            for (const buildProxyUrl of CORS_PROXIES) {
                try {
                    const proxyUrl = buildProxyUrl(videoUrl);
                    const resp = await fetch(proxyUrl, { signal: relaySignal });
                    if (!resp.ok) continue;
                    const blob = await resp.blob();
                    if (blob.size < 10240) continue;
                    const a = document.createElement('a');
                    a.href = URL.createObjectURL(blob);
                    a.download = `${title}.mp4`;
                    a.click();
                    URL.revokeObjectURL(a.href);
                    showToast('下载完成（CORS 代理）', 'success');
                    progressFill.style.width = '100%';
                    progressText.textContent = '100%';
                    return true;
                } catch (e2) {
                    if (signal?.aborted) throw e2;
                    continue;
                }
            }
        } catch (e3) {
            if (signal?.aborted) throw e3;
            /* 所有方式都失败，回退到服务端下载 */
        }
    }
    return false;
}

// ─── 图片选择操作 ────────────────────────────────
function handleSelectAll(e) {
    const checked = e.target.checked;
    const items = $$('.gallery-item');
    selectedImages.clear();
    if (checked) {
        items.forEach((item, i) => {
            selectedImages.add(i);
            item.classList.add('selected');
            const cb = item.querySelector('.gallery-checkbox');
            if (cb) cb.checked = true;
        });
    } else {
        items.forEach((item) => {
            item.classList.remove('selected');
            const cb = item.querySelector('.gallery-checkbox');
            if (cb) cb.checked = false;
        });
    }
    updateSelectedCount();
}

function updateSelectedCount() {
    const countEl = $('#selectedCount');
    if (countEl) {
        const total = currentVideoData?.image_list?.length || 0;
        countEl.textContent = selectedImages.size > 0
            ? `已选 ${selectedImages.size} / ${total} 张`
            : `共 ${total} 张`;
    }
    const selectAllCb = $('#selectAllCb');
    if (selectAllCb) {
        const total = currentVideoData?.image_list?.length || 0;
        selectAllCb.checked = total > 0 && selectedImages.size === total;
    }
}

async function handleDownloadSelected() {
    if (selectedImages.size === 0) { showToast('请先选择要下载的图片', 'error'); return; }
    const indices = [...selectedImages].sort((a, b) => a - b);
    await downloadImagesByIndices(indices);
}

async function handleDownloadAllImages() {
    if (!currentVideoData?.image_list?.length) return;
    const indices = currentVideoData.image_list.map((_, i) => i);
    await downloadImagesAsZip(indices);
}

async function downloadImagesAsZip(indices) {
    const referer = getReferer(currentVideoData.platform);
    const total = indices.length;
    const title = sanitizeFilename((currentVideoData.title || 'images').substring(0, 50));
    const files = [];
    let done = 0;

    showToast(`开始打包 ${total} 张图片...`, 'info');
    setImageDownloadLoading(true, `打包中 0/${total}`);
    progressBar.style.display = 'block';
    progressFill.style.width = '0%';
    progressText.textContent = `0/${total}`;
    showStatus(statusBar, '⏳ 正在下载图片并生成 ZIP...', 'info');

    for (const i of indices) {
        const imgUrl = currentVideoData.image_list[i];
        if (!imgUrl) continue;
        try {
            const resp = await fetch(`${API_BASE}/api/proxy?video_url=${encodeURIComponent(imgUrl)}&referer=${encodeURIComponent(referer)}`);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const blob = await resp.blob();
            const ext = getImageExtension(imgUrl, blob.type);
            files.push({ name: `${title}_${String(i + 1).padStart(2, '0')}.${ext}`, blob });
            done++;
            const pct = Math.round((done / total) * 100);
            progressFill.style.width = `${pct}%`;
            progressText.textContent = `${done}/${total}`;
            setImageDownloadLoading(true, `打包中 ${done}/${total}`);
        } catch {
            showToast(`第 ${i + 1} 张下载失败`, 'error');
        }
    }

    if (!files.length) {
        showStatus(statusBar, '❌ 图片下载失败，未生成 ZIP', 'error');
        showToast('图片下载失败，未生成 ZIP', 'error');
        setImageDownloadLoading(false);
        setTimeout(() => { progressBar.style.display = 'none'; }, 1500);
        return;
    }

    const zipBlob = await createZipBlob(files);
    downloadBlob(zipBlob, `${title}.zip`);
    progressFill.style.width = '100%';
    progressText.textContent = `${files.length}/${total}`;
    showStatus(statusBar, `✅ ZIP 已生成：${files.length}/${total} 张图片`, files.length === total ? 'success' : 'warning');
    showToast(`${files.length}/${total} 张图片已打包下载`, files.length === total ? 'success' : 'warning');
    setImageDownloadLoading(false);
    setTimeout(() => { progressBar.style.display = 'none'; }, 1500);
}

async function downloadImagesByIndices(indices) {
    const referer = getReferer(currentVideoData.platform);
    const total = indices.length;
    showToast(`开始下载 ${total} 张图片...`, 'info');

    downloadBtn.disabled = true;
    progressBar.style.display = 'block';

    const title = sanitizeFilename((currentVideoData.title || 'image').substring(0, 30));
    let done = 0;
    for (const i of indices) {
        const imgUrl = currentVideoData.image_list[i];
        if (!imgUrl) continue;
        try {
            const resp = await fetch(`${API_BASE}/api/proxy?video_url=${encodeURIComponent(imgUrl)}&referer=${encodeURIComponent(referer)}`);
            const blob = await resp.blob();
            const ext = getImageExtension(imgUrl, blob.type);
            downloadBlob(blob, `${title}_${i + 1}.${ext}`);
            done++;
            const pct = Math.round((done / total) * 100);
            progressFill.style.width = pct + '%';
            progressText.textContent = `${done}/${total}`;
            downloadBtn.querySelector(".btn-text").textContent = `⬇ ${done}/${total}`;
            await new Promise(r => setTimeout(r, 300));
        } catch (e) {
            showToast(`第 ${i + 1} 张下载失败`, 'error');
        }
    }
    downloadBtn.querySelector('.btn-text').textContent = `⬇ 下载全部 ZIP`;
    downloadBtn.disabled = false;
    setTimeout(() => { progressBar.style.display = 'none'; }, 1500);
    showToast(`${done}/${total} 张图片下载完成`, done === total ? 'success' : 'warning');
}

function handleCopySelectedLinks() {
    if (!currentVideoData?.image_list?.length) return;
    const indices = selectedImages.size > 0
        ? [...selectedImages].sort((a, b) => a - b)
        : currentVideoData.image_list.map((_, i) => i);
    const links = indices.map(i => currentVideoData.image_list[i]).filter(Boolean).join('\n');
    navigator.clipboard.writeText(links).then(
        () => showToast(`${indices.length} 个图片链接已复制`, 'success'),
        () => showToast('复制失败', 'error')
    );
}

// ─── 复制直链 ────────────────────────────────────
function handleCopyLink() {
    const isImage = currentVideoData?.note_type === 'image' || (currentVideoData?.image_list?.length > 0);
    if (isImage && currentVideoData.image_list) {
        const links = currentVideoData.image_list.join('\n');
        navigator.clipboard.writeText(links).then(
            () => showToast(`${currentVideoData.image_list.length} 个图片链接已复制`, 'success'),
            () => showToast('复制失败', 'error')
        );
        return;
    }

    // 视频号无直链时复制封面
    if (currentVideoData?.platform === 'wechat_channels' && !currentVideoData?.video_url) {
        if (currentVideoData?.cover) {
            navigator.clipboard.writeText(currentVideoData.cover).then(
                () => showToast('封面链接已复制', 'success'),
                () => showToast('复制失败', 'error')
            );
        } else {
            showToast('无可用链接', 'error');
        }
        return;
    }

    if (!currentVideoData?.video_url) { showToast('无可用地址', 'error'); return; }
    const link = currentVideoData.video_url_no_watermark || currentVideoData.video_url;
    navigator.clipboard.writeText(link).then(
        () => showToast('直链已复制', 'success'),
        () => showToast('复制失败', 'error')
    );
}

// ─── 在线预览 ────────────────────────────────────
// 公共：显示 iframe 预览
function showIframePreview(embedUrl) {
    previewVideo.style.display = 'none';
    previewFallback.style.display = 'block';
    previewFallback.innerHTML = `<iframe src="${embedUrl}" style="width:100%;height:100%;min-height:500px;border:none;border-radius:8px" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>`;
    previewModal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
}

function handlePreview() {
    const isImage = currentVideoData?.note_type === 'image' || (currentVideoData?.image_list?.length > 0);

    if (isImage && currentVideoData.image_list) {
        previewVideo.style.display = 'none';
        previewFallback.style.display = 'block';
        const ref = getReferer(currentVideoData.platform);
        const imgs = currentVideoData.image_list.map((url, i) =>
            `<img src="${API_BASE}/api/proxy?video_url=${encodeURIComponent(url)}&referer=${encodeURIComponent(ref)}" alt="图片 ${i + 1}" style="width:100%;max-width:600px;margin:8px auto;display:block;border-radius:8px" loading="lazy">`
        ).join('');
        previewFallback.innerHTML = `<div style="max-height:80vh;overflow-y:auto;padding:10px">${imgs}</div>`;
        previewModal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
        return;
    }

    // 视频号无直链时显示封面
    if (currentVideoData?.platform === 'wechat_channels' && !currentVideoData?.video_url) {
        if (currentVideoData?.cover) {
            previewVideo.style.display = 'none';
            previewFallback.style.display = 'block';
            previewFallback.innerHTML = `
                <div style="text-align:center;padding:20px">
                    <img src="${currentVideoData.cover}" style="max-width:100%;max-height:60vh;border-radius:8px" alt="视频封面">
                    <p style="margin-top:16px;color:var(--text-secondary)">视频号需要抓包工具获取视频直链才能在线预览</p>
                </div>`;
            previewModal.style.display = 'flex';
            document.body.style.overflow = 'hidden';
        } else {
            showToast('无可用预览', 'error');
        }
        return;
    }

    if (!currentVideoData?.video_url) { showToast('无可用地址', 'error'); return; }

    const videoUrl = currentVideoData.video_url_no_watermark || currentVideoData.video_url;
    const platform = currentVideoData.platform;

    if (platform === 'youtube') {
        const vid = videoUrl.replace('yt://', '');
        showIframePreview(`https://www.youtube.com/embed/${vid}?autoplay=1`);
        return;
    }

    if (platform === 'tiktok') {
        showIframePreview(`https://www.tiktok.com/embed/v2/${currentVideoData.id}`);
        return;
    }

    if (platform === 'bilibili') {
        showIframePreview(`https://player.bilibili.com/player.html?bvid=${currentVideoData.id}&autoplay=1`);
        return;
    }

    if (['instagram', 'twitter'].includes(platform)) {
        previewVideo.style.display = 'none';
        previewFallback.style.display = 'block';
        previewFallback.innerHTML = `<p>该平台视频请在新窗口打开预览</p><a href="${videoUrl}" target="_blank" style="color:var(--accent);margin-top:10px;display:inline-block">在新窗口打开</a>`;
        previewModal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
        return;
    }

    const proxyUrl = `${API_BASE}/api/proxy?video_url=${encodeURIComponent(videoUrl)}&referer=${encodeURIComponent(getReferer(platform))}`;
    previewVideo.style.display = 'block';
    previewFallback.style.display = 'none';
    previewVideo.src = proxyUrl;
    previewModal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
}

function getReferer(platform) {
    const map = {
        douyin: 'https://www.douyin.com/',
        bilibili: 'https://www.bilibili.com/', weibo: 'https://weibo.com/',
        xiaohongshu: 'https://www.xiaohongshu.com/', tiktok: 'https://www.tiktok.com/',
        youtube: 'https://www.youtube.com/', instagram: 'https://www.instagram.com/',
        twitter: 'https://x.com/', xigua: 'https://www.ixigua.com/',
        wechat_channels: 'https://channels.weixin.qq.com/',
    };
    return map[platform] || 'https://www.douyin.com/';
}

function closePreview() {
    previewModal.style.display = 'none';
    previewVideo.pause();
    previewVideo.src = '';
    previewFallback.innerHTML = '';
    previewFallback.style.display = 'none';
    document.body.style.overflow = '';
}

// ─── 批量解析 ────────────────────────────────────
async function handleBatchParse() {
    const text = batchInput.value.trim();
    if (!text) { showToast('请输入链接', 'error'); return; }

    const urls = text.split('\n').map((l) => l.trim()).filter(Boolean);
    if (!urls.length) { showToast('未找到有效链接', 'error'); return; }

    batchParseBtn.disabled = true;
    batchResults.innerHTML = '';
    showStatus(batchStatus, `正在解析 ${urls.length} 个链接...`, 'info');

    try {
        const resp = await fetch(`${API_BASE}/api/batch-parse`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ urls }),
        });
        const { results } = await readJsonResponse(resp, '批量解析接口');
        const finalResults = await Promise.all(results.map(async (r, index) => {
            if (r.success || _detectPlatform(urls[index]) !== 'tiktok') return r;
            const relayResult = await _tryCorsProxyRelay(urls[index]);
            return relayResult || r;
        }));
        let ok = 0;
        finalResults.forEach((r) => { if (r.success) ok++; renderBatchItem(r); });
        showStatus(batchStatus, `完成: ${ok}/${urls.length} 成功`, ok === urls.length ? 'success' : 'warning');
    } catch (err) {
        showStatus(batchStatus, `❌ 失败: ${err.message}`, 'error');
    } finally {
        batchParseBtn.disabled = false;
    }
}

function renderBatchItem(result) {
    const div = document.createElement('div');
    div.className = 'batch-item';
    if (result.success && result.data) {
        const d = result.data;
        const vUrl = (d.video_url?.startsWith('yt://') || d.video_url?.startsWith('tt://') || d.video_url?.startsWith('bl://') || d.video_url?.startsWith('wx://'))
            ? d.video_url : (d.video_url_no_watermark || d.video_url);
        const pName = PLATFORM_NAMES[d.platform] || d.platform || '';
        div.innerHTML = `
            <img class="batch-item-cover" src="${escAttr(d.cover)}" alt="" onerror="this.style.display='none'">
            <div class="batch-item-info">
                <div class="batch-item-title" title="${esc(d.title)}">${esc(d.title)}</div>
                <div class="batch-item-author">${pName} · ${esc(d.author)} · ${formatDuration(d.duration)}</div>
            </div>
            <span class="batch-item-status success">成功</span>
            <div class="batch-item-actions">
                <button class="btn btn-primary btn-sm js-download" data-url="${escAttr(vUrl)}" data-title="${escAttr(d.title)}" data-platform="${escAttr(d.platform)}">⬇ 下载</button>
                <button class="btn btn-ghost btn-sm js-copy" data-url="${escAttr(vUrl)}">🔗</button>
            </div>`;
    } else {
        div.innerHTML = `
            <div class="batch-item-info"><div class="batch-item-title" style="color:var(--danger)">${esc(result.message)}</div></div>
            <span class="batch-item-status error">失败</span>`;
    }
    batchResults.appendChild(div);
}

// ─── 历史记录 ────────────────────────────────────
async function loadHistory() {
    try {
        const resp = await fetch(`${API_BASE}/api/history`);
        const { history } = await readJsonResponse(resp, '历史记录接口');
        historyList.querySelectorAll('.history-item').forEach((el) => el.remove());
        if (!history?.length) { historyEmpty.style.display = 'block'; return; }
        historyEmpty.style.display = 'none';
        history.forEach((item) => {
            const div = document.createElement('div');
            div.className = 'history-item';
            const vUrl = (item.video_url?.startsWith('yt://') || item.video_url?.startsWith('tt://') || item.video_url?.startsWith('bl://') || item.video_url?.startsWith('wx://'))
                ? item.video_url : (item.video_url_no_watermark || item.video_url);
            const pName = PLATFORM_NAMES[item.platform] || item.platform || '';
            div.innerHTML = `
                <img class="history-cover" src="${escAttr(item.cover)}" alt="" onerror="this.style.display='none'">
                <div class="history-info">
                    <div class="history-title" title="${esc(item.title)}">${esc(item.title)}</div>
                    <div class="history-meta">${pName} · ${esc(item.author)} · ${item.parse_time || ''}</div>
                </div>
                <div class="history-actions">
                    <button class="btn btn-primary btn-sm js-download" data-url="${escAttr(vUrl)}" data-title="${escAttr(item.title)}" data-platform="${escAttr(item.platform)}">⬇</button>
                    <button class="btn btn-ghost btn-sm js-copy" data-url="${escAttr(vUrl)}">🔗</button>
                    <button class="history-delete js-delete-history" data-id="${item.id}" title="删除">✕</button>
                </div>`;
            historyList.appendChild(div);
        });
    } catch { showToast('加载历史失败', 'error'); }
}

async function deleteHistoryItem(id) {
    try {
        await fetch(`${API_BASE}/api/history/${id}`, { method: 'DELETE' });
        loadHistory();
    } catch { showToast('删除失败', 'error'); }
}

async function handleClearHistory() {
    if (!confirm('确定清空所有历史记录？')) return;
    try {
        await fetch(`${API_BASE}/api/history`, { method: 'DELETE' });
        loadHistory();
        showToast('已清空', 'success');
    } catch { showToast('清空失败', 'error'); }
}

// ─── 事件委托 ────────────────────────────────────
document.addEventListener('click', (e) => {
    const btn = e.target.closest('.js-download');
    if (btn) { doDownload(btn.dataset.url, btn.dataset.title, btn.dataset.platform, btn); return; }
    const copyBtn = e.target.closest('.js-copy');
    if (copyBtn) {
        navigator.clipboard.writeText(copyBtn.dataset.url).then(
            () => showToast('已复制', 'success'), () => showToast('复制失败', 'error')
        );
        return;
    }
    const delBtn = e.target.closest('.js-delete-history');
    if (delBtn) { deleteHistoryItem(delBtn.dataset.id); return; }

    const galleryItem = e.target.closest('.gallery-item');
    if (galleryItem && !e.target.classList.contains('gallery-checkbox')) {
        const idx = parseInt(galleryItem.dataset.index);
        if (selectedImages.has(idx)) {
            selectedImages.delete(idx);
            galleryItem.classList.remove('selected');
        } else {
            selectedImages.add(idx);
            galleryItem.classList.add('selected');
        }
        const cb = galleryItem.querySelector('.gallery-checkbox');
        if (cb) cb.checked = selectedImages.has(idx);
        updateSelectedCount();
    }

    if (e.target.classList.contains('gallery-checkbox')) {
        const idx = parseInt(e.target.dataset.index);
        const item = e.target.closest('.gallery-item');
        if (e.target.checked) {
            selectedImages.add(idx);
            if (item) item.classList.add('selected');
        } else {
            selectedImages.delete(idx);
            if (item) item.classList.remove('selected');
        }
        updateSelectedCount();
    }
});

async function doDownload(videoUrl, title, platform, button) {
    const downloadKey = `${platform || ''}:${videoUrl || ''}`;
    if (activeDownloads.has(downloadKey)) {
        showToast('正在下载，请稍候', 'info');
        return;
    }

    const originalText = button?.textContent || '';
    activeDownloads.add(downloadKey);
    if (button) {
        button.disabled = true;
        button.textContent = '下载中...';
    }
    showToast('正在下载...', 'info');

    try {
        // 需要中继的平台优先客户端直连（仅对 http(s) 直链，自定义协议如 tt:// 直接走服务端）
        if (NEEDS_RELAY.includes(platform) && /^https?:/i.test(videoUrl)) {
            const ref = getReferer(platform || '');
            try {
                const resp = await fetch(videoUrl, {
                    headers: { 'Referer': ref, 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' },
                    signal: AbortSignal.timeout(15000),
                });
                if (resp.ok) {
                    const blob = await resp.blob();
                    const a = document.createElement('a');
                    a.href = URL.createObjectURL(blob);
                    a.download = `${(title || 'video').substring(0, 50)}.mp4`;
                    a.click();
                    URL.revokeObjectURL(a.href);
                    showToast('下载完成', 'success');
                    return;
                }
            } catch { /* 回退到服务端 */ }
        }

        const ref = getReferer(platform || '');
        const resp = await fetch(`${API_BASE}/api/download?video_url=${encodeURIComponent(videoUrl)}&title=${encodeURIComponent(title || 'video')}&referer=${encodeURIComponent(ref)}`);
        if (!resp.ok) throw new Error('下载失败');
        const blob = await resp.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `${(title || 'video').substring(0, 50)}.mp4`;
        a.click();
        URL.revokeObjectURL(a.href);
        showToast('下载完成', 'success');
    } catch (err) {
        showToast(`下载失败: ${err.message}`, 'error');
    } finally {
        activeDownloads.delete(downloadKey);
        if (button) {
            button.disabled = false;
            button.textContent = originalText;
        }
    }
}

// ─── 博主主页解析与批量下载 ──────────────────────
async function handleProfileParse(page = 1) {
    // page===1 取输入框；翻页复用已保存的 profileUrl
    const url = page === 1 ? profileInput.value.trim() : profileUrl;
    if (!url) { showToast('请输入博主主页链接', 'error'); return; }

    profileParseBtn.disabled = true;
    if (profilePrevBtn) profilePrevBtn.disabled = true;
    if (profileNextBtn) profileNextBtn.disabled = true;
    const btnText = profileParseBtn.querySelector('.btn-text');
    const btnLoading = profileParseBtn.querySelector('.btn-loading');
    if (btnText) btnText.style.display = 'none';
    if (btnLoading) btnLoading.style.display = 'inline-flex';

    // 仅新解析（第 1 页）立即清空；翻页时保留当前页，成功后再替换，避免失败抹掉已有结果
    if (page === 1) {
        profileHeader.style.display = 'none';
        profileGrid.innerHTML = '';
        profileVideos = [];
        profileSelected.clear();
    }

    const limit = parseInt(profileLimit.value, 10) || 20;
    const started = Date.now();
    showStatus(profileStatus, `🔍 正在解析主页视频列表（第 ${page} 页，可能需要 10~30 秒）...`, 'info');

    try {
        const resp = await fetch(`${API_BASE}/api/parse-profile`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, limit, page }),
        });
        const result = await readJsonResponse(resp, '主页解析接口');
        const elapsed = ((Date.now() - started) / 1000).toFixed(1);
        const data = result.data || {};
        const videos = data.videos || [];

        if (!result.success || videos.length === 0) {
            showStatus(profileStatus, `❌ ${result.message || '未解析到视频'}（${elapsed}s）`, 'error');
            // 翻页失败：本页已到尽头，禁用「下一页」并保留当前页；新解析失败：隐藏分页条
            if (page > 1) profileHasMore = false;
            renderProfilePager();
            return;
        }

        profileUrl = url;
        profilePage = data.page || page;
        profileHasMore = !!data.has_more;
        profileTotalPages = data.total_pages || null;
        profilePlatform = data.platform || null;
        profileVideos = videos;
        profileSelected.clear();
        renderProfileResult(data, elapsed);
        renderProfilePager();
    } catch (err) {
        showStatus(profileStatus, `❌ 解析失败: ${err.message}`, 'error');
        if (page > 1) profileHasMore = false;
        renderProfilePager();
    } finally {
        profileParseBtn.disabled = false;
        if (btnText) btnText.style.display = '';
        if (btnLoading) btnLoading.style.display = 'none';
    }
}

function renderProfilePager() {
    if (!profilePager) return;
    // 无视频、或 SSR 平台只有 1 页且无更多 → 隐藏分页条
    const hasNav = profileVideos.length > 0 && (profilePage > 1 || profileHasMore || (profileTotalPages && profileTotalPages > 1));
    if (!hasNav) { profilePager.style.display = 'none'; return; }
    profilePager.style.display = 'flex';
    profilePageInfo.textContent = profileTotalPages
        ? `第 ${profilePage} / ${profileTotalPages} 页`
        : `第 ${profilePage} 页`;
    profilePrevBtn.disabled = profilePage <= 1;
    profileNextBtn.disabled = !profileHasMore;
}

function renderProfileResult(data, elapsed) {
    const platformName = PLATFORM_NAMES[data.platform] || data.platform || '';
    profileAuthorName.textContent = data.author || '未知博主';
    profileMeta.textContent = `${platformName} · 共 ${data.total || profileVideos.length} 个视频`;
    profileHeader.style.display = 'flex';

    profileGrid.innerHTML = profileVideos.map((v, i) => renderProfileCard(v, i)).join('');

    // 绑定卡片交互
    profileGrid.querySelectorAll('.profile-card').forEach((card) => {
        const idx = parseInt(card.dataset.idx, 10);
        const cb = card.querySelector('.check-box input');
        const dlBtn = card.querySelector('.card-dl-btn');

        card.addEventListener('click', (e) => {
            if (e.target.closest('.card-dl-btn') || e.target.closest('.check-box')) return;
            toggleProfileSelect(idx, !profileSelected.has(idx));
        });
        if (cb) cb.addEventListener('change', () => toggleProfileSelect(idx, cb.checked));
        if (dlBtn) dlBtn.addEventListener('click', () => downloadProfileVideo(idx, dlBtn));
    });

    if (profileSelectAll) profileSelectAll.checked = false;
    updateProfileSelectedCount();
    showStatus(profileStatus, `✅ 解析成功 — ${platformName}，共 ${profileVideos.length} 个视频（${elapsed}s）`, 'success');
}

function renderProfileCard(v, idx) {
    const cover = v.cover ? `<img class="card-cover" src="${escAttr(v.cover)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.style.display='none'">` : '<div class="card-cover card-cover-empty">无封面</div>';
    const durationBadge = v.duration ? `<span class="duration-badge">${formatDuration(v.duration)}</span>` : '';
    const title = esc(v.title || '无标题');
    return `
        <div class="profile-card" data-idx="${idx}">
            <div class="cover-wrap">
                ${cover}
                ${durationBadge}
                <label class="check-box"><input type="checkbox"></label>
            </div>
            <div class="card-body">
                <div class="card-title" title="${escAttr(v.title || '')}">${title}</div>
                <div class="card-actions">
                    <button class="btn btn-primary btn-sm card-dl-btn">⬇ 下载</button>
                </div>
            </div>
        </div>`;
}

function toggleProfileSelect(idx, selected) {
    const card = profileGrid.querySelector(`.profile-card[data-idx="${idx}"]`);
    const cb = card ? card.querySelector('.check-box input') : null;
    if (selected) {
        profileSelected.add(idx);
        if (card) card.classList.add('selected');
    } else {
        profileSelected.delete(idx);
        if (card) card.classList.remove('selected');
    }
    if (cb) cb.checked = selected;
    updateProfileSelectedCount();
}

function handleProfileSelectAll() {
    const selectAll = profileSelectAll.checked;
    profileVideos.forEach((_, idx) => toggleProfileSelect(idx, selectAll));
}

function updateProfileSelectedCount() {
    const total = profileVideos.length;
    const selected = profileSelected.size;
    profileSelectedCount.textContent = `已选 ${selected} / ${total}`;
    profileDownloadSelectedBtn.disabled = selected === 0;
    if (profileSelectAll) profileSelectAll.checked = total > 0 && selected === total;
}

// 单个视频下载：tt://yt://bl:// 直接复用 doDownload；抖音/小红书 need_reparse 先取直链
async function downloadProfileVideo(idx, button) {
    const v = profileVideos[idx];
    if (!v) return;

    if (v.need_reparse) {
        const originalText = button ? button.textContent : '';
        if (button) { button.disabled = true; button.textContent = '解析中...'; }
        try {
            const resp = await fetch(`${API_BASE}/api/parse`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: v.detail_url || v.video_url }),
            });
            const result = await readJsonResponse(resp, '视频解析接口');
            if (!result.success || !result.data || !result.data.video_url) {
                showToast(`「${(v.title || '视频').substring(0, 12)}」解析失败`, 'error');
                return;
            }
            await doDownload(result.data.video_url, v.title || result.data.title, result.data.platform || v.platform, button);
        } catch (err) {
            showToast(`解析失败: ${err.message}`, 'error');
        } finally {
            if (button) { button.disabled = false; button.textContent = originalText; }
        }
        return;
    }

    await doDownload(v.video_url, v.title, v.platform, button);
}

// 串行逐个下载，每个间隔 800ms
async function handleProfileDownloadSelected() {
    if (profileSelected.size === 0) { showToast('请先选择视频', 'error'); return; }
    const indices = Array.from(profileSelected).sort((a, b) => a - b);

    profileDownloadSelectedBtn.disabled = true;
    const originalText = profileDownloadSelectedBtn.textContent;
    let done = 0;

    for (const idx of indices) {
        done += 1;
        profileDownloadSelectedBtn.textContent = `下载中 ${done}/${indices.length}...`;
        const card = profileGrid.querySelector(`.profile-card[data-idx="${idx}"]`);
        const dlBtn = card ? card.querySelector('.card-dl-btn') : null;
        await downloadProfileVideo(idx, dlBtn);
        if (done < indices.length) await new Promise((r) => setTimeout(r, 800));
    }

    profileDownloadSelectedBtn.textContent = originalText;
    profileDownloadSelectedBtn.disabled = false;
    showToast(`已触发 ${indices.length} 个视频下载`, 'success');
}

function handleProfileCopyLinks() {
    const indices = profileSelected.size > 0
        ? Array.from(profileSelected).sort((a, b) => a - b)
        : profileVideos.map((_, i) => i);
    if (indices.length === 0) { showToast('没有可复制的链接', 'error'); return; }
    const links = indices.map((i) => {
        const v = profileVideos[i];
        return v.detail_url || v.video_url || '';
    }).filter(Boolean).join('\n');
    navigator.clipboard.writeText(links)
        .then(() => showToast(`已复制 ${indices.length} 个链接`, 'success'))
        .catch(() => showToast('复制失败', 'error'));
}

// 取单个主页视频的 blob（need_reparse 先取直链），失败返回 null
async function fetchProfileVideoBlob(v) {
    let videoUrl = v.video_url;
    let platform = v.platform;
    let title = v.title || 'video';

    if (v.need_reparse) {
        const resp = await fetch(`${API_BASE}/api/parse`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: v.detail_url || v.video_url }),
        });
        const result = await readJsonResponse(resp, '视频解析接口');
        if (!result.success || !result.data || !result.data.video_url) return null;
        videoUrl = result.data.video_url;
        platform = result.data.platform || platform;
        title = v.title || result.data.title || title;
    }
    if (!videoUrl) return null;

    const ref = getReferer(platform);
    const dlResp = await fetch(`${API_BASE}/api/download?video_url=${encodeURIComponent(videoUrl)}&title=${encodeURIComponent(title.substring(0, 50))}&referer=${encodeURIComponent(ref)}`);
    if (!dlResp.ok) return null;
    return await dlResp.blob();
}

// 打包本页为 ZIP：选中则打包选中，未选则打包本页全部（串行取 blob，浏览器端打包）
async function handleProfileDownloadZip() {
    const indices = profileSelected.size > 0
        ? Array.from(profileSelected).sort((a, b) => a - b)
        : profileVideos.map((_, i) => i);
    if (indices.length === 0) { showToast('本页没有可打包的视频', 'error'); return; }
    if (indices.length > 20) {
        showToast('视频较多，浏览器端打包会占用较多内存，请耐心等待…', 'warning');
    }

    profileZipBtn.disabled = true;
    const originalText = profileZipBtn.textContent;
    const total = indices.length;
    const files = [];
    const failed = [];
    let done = 0;

    for (const idx of indices) {
        done += 1;
        profileZipBtn.textContent = `打包中 ${done}/${total}...`;
        showStatus(profileStatus, `⏳ 正在下载并打包（${done}/${total}）...`, 'info');
        const v = profileVideos[idx];
        const seq = String(idx + 1).padStart(2, '0');
        const shortTitle = (v.title || '视频').substring(0, 24);
        try {
            const blob = await fetchProfileVideoBlob(v);
            if (!blob) { failed.push({ seq, title: shortTitle }); continue; }
            const name = `${seq}_${sanitizeFilename((v.title || 'video').substring(0, 40))}.mp4`;
            files.push({ name, blob });
        } catch (err) {
            failed.push({ seq, title: shortTitle, reason: err.message });
        }
    }

    profileZipBtn.textContent = originalText;
    profileZipBtn.disabled = false;

    // 失败清单（多行，序号与 ZIP 内文件名前缀一致，便于对照）
    const failText = failed.length
        ? `\n⚠ ${failed.length} 个下载失败：\n` +
          failed.map((f) => `  #${f.seq} ${f.title}${f.reason ? `（${f.reason}）` : ''}`).join('\n')
        : '';

    if (files.length === 0) {
        showStatus(profileStatus, '❌ 全部下载失败，未生成 ZIP' + failText, 'error');
        showToast(`全部下载失败（共 ${total} 个），未生成 ZIP`, 'error');
        return;
    }

    showStatus(profileStatus, '📦 正在生成 ZIP...', 'info');
    const zipBlob = await createZipBlob(files);
    const author = sanitizeFilename(profileAuthorName.textContent || 'profile');
    downloadBlob(zipBlob, `${author}-第${profilePage}页.zip`);
    showStatus(
        profileStatus,
        `✅ ZIP 已生成：成功 ${files.length}/${total} 个视频` + failText,
        failed.length ? 'warning' : 'success'
    );
    showToast(
        failed.length
            ? `已打包 ${files.length}/${total}，${failed.length} 个失败（详见状态栏）`
            : `${files.length} 个视频已打包下载`,
        failed.length ? 'warning' : 'success'
    );
}

// ─── 工具函数 ────────────────────────────────────
function formatDuration(s) {
    if (!s) return '未知';
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

function formatNumber(n) {
    if (!n) return '0';
    if (n >= 10000) return (n / 10000).toFixed(1) + '万';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
    return String(n);
}

function esc(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function escAttr(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

function setImageDownloadLoading(loading, text = '') {
    downloadBtn.disabled = loading;
    const selectedBtn = $('#downloadSelectedBtn');
    const allBtn = $('#downloadAllImagesBtn');
    if (selectedBtn) selectedBtn.disabled = loading;
    if (allBtn) {
        allBtn.disabled = loading;
        allBtn.textContent = loading ? text : '⬇ 下载全部 ZIP';
    }
    downloadBtn.querySelector('.btn-text').textContent = loading ? `⬇ ${text}` : '⬇ 下载全部 ZIP';
}

function sanitizeFilename(name) {
    return String(name || 'download').replace(/[\\/:*?"<>|]/g, '_').trim() || 'download';
}

function getImageExtension(url, mimeType = '') {
    const typeMap = { 'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp', 'image/gif': 'gif', 'image/avif': 'avif' };
    if (typeMap[mimeType]) return typeMap[mimeType];
    const cleanUrl = String(url).split('?')[0];
    const match = cleanUrl.match(/\.([a-zA-Z0-9]{2,5})$/);
    return match ? match[1].toLowerCase() : 'jpg';
}

function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    // 延迟撤销：a.click() 异步启动下载，立即 revoke 会让大 blob（如整页 ZIP）下载失败
    setTimeout(() => URL.revokeObjectURL(url), 60000);
}

async function createZipBlob(files) {
    const encoder = new TextEncoder();
    const localParts = [];
    const centralParts = [];
    let offset = 0;

    for (const file of files) {
        const data = new Uint8Array(await file.blob.arrayBuffer());
        const nameBytes = encoder.encode(file.name);
        const crc = crc32(data);
        const localHeader = createZipLocalHeader(nameBytes, crc, data.length);
        localParts.push(localHeader, nameBytes, data);
        centralParts.push(createZipCentralHeader(nameBytes, crc, data.length, offset), nameBytes);
        offset += localHeader.length + nameBytes.length + data.length;
    }

    const centralSize = centralParts.reduce((sum, part) => sum + part.length, 0);
    const endRecord = createZipEndRecord(files.length, centralSize, offset);
    return new Blob([...localParts, ...centralParts, endRecord], { type: 'application/zip' });
}

function createZipLocalHeader(nameBytes, crc, size) {
    const header = new Uint8Array(30);
    const view = new DataView(header.buffer);
    view.setUint32(0, 0x04034b50, true);
    view.setUint16(4, 20, true);
    view.setUint16(6, 0x0800, true);
    view.setUint16(8, 0, true);
    view.setUint16(10, 0, true);
    view.setUint16(12, 0, true);
    view.setUint32(14, crc, true);
    view.setUint32(18, size, true);
    view.setUint32(22, size, true);
    view.setUint16(26, nameBytes.length, true);
    view.setUint16(28, 0, true);
    return header;
}

function createZipCentralHeader(nameBytes, crc, size, offset) {
    const header = new Uint8Array(46);
    const view = new DataView(header.buffer);
    view.setUint32(0, 0x02014b50, true);
    view.setUint16(4, 20, true);
    view.setUint16(6, 20, true);
    view.setUint16(8, 0x0800, true);
    view.setUint16(10, 0, true);
    view.setUint16(12, 0, true);
    view.setUint16(14, 0, true);
    view.setUint32(16, crc, true);
    view.setUint32(20, size, true);
    view.setUint32(24, size, true);
    view.setUint16(28, nameBytes.length, true);
    view.setUint16(30, 0, true);
    view.setUint16(32, 0, true);
    view.setUint16(34, 0, true);
    view.setUint16(36, 0, true);
    view.setUint32(38, 0, true);
    view.setUint32(42, offset, true);
    return header;
}

function createZipEndRecord(fileCount, centralSize, centralOffset) {
    const record = new Uint8Array(22);
    const view = new DataView(record.buffer);
    view.setUint32(0, 0x06054b50, true);
    view.setUint16(4, 0, true);
    view.setUint16(6, 0, true);
    view.setUint16(8, fileCount, true);
    view.setUint16(10, fileCount, true);
    view.setUint32(12, centralSize, true);
    view.setUint32(16, centralOffset, true);
    view.setUint16(20, 0, true);
    return record;
}

function crc32(data) {
    let crc = -1;
    for (let i = 0; i < data.length; i++) {
        crc = (crc >>> 8) ^ CRC32_TABLE[(crc ^ data[i]) & 0xff];
    }
    return (crc ^ -1) >>> 0;
}

const CRC32_TABLE = (() => {
    const table = new Uint32Array(256);
    for (let i = 0; i < 256; i++) {
        let c = i;
        for (let k = 0; k < 8; k++) {
            c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
        }
        table[i] = c >>> 0;
    }
    return table;
})();
