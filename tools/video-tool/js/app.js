/**
 * 小小工具箱 - 视频解析下载 3.0.0
 * 支持：抖音、快手、B站、微博、小红书、TikTok、YouTube、Instagram、Twitter/X、西瓜视频
 */

const API_BASE = window.location.origin;

const PLATFORM_NAMES = {
    douyin: '抖音', bilibili: 'B站', weibo: '微博',
    xiaohongshu: '小红书', tiktok: 'TikTok', youtube: 'YouTube',
    instagram: 'Instagram', twitter: 'Twitter/X', xigua: '西瓜视频',
    wechat_channels: '微信视频号', direct: '直接链接',
};

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

let currentVideoData = null;
let selectedImages = new Set();

// ─── 初始化 ──────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initTabs();
    initEventListeners();
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
                downloadBtn.textContent = '⬇ 下载视频';
                downloadBtn.disabled = false;
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
        const result = await resp.json();
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
            hideSkeleton();
            resultPanel.style.display = 'none';
            let errorMsg = result.message || '解析失败';
            if (result.guide || result.hint) {
                errorMsg += '\n\n' + (result.guide || result.hint);
            }
            showStatus(statusBar, `❌ ${errorMsg}（${elapsed}s）`, 'error');
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
    if (isWechatNoUrl) {
        // 视频号但无直链：显示提示信息
        downloadBtn.textContent = '⚠ 需要抓包获取直链';
        downloadBtn.disabled = true;
        downloadBtn.title = '视频号需要抓包工具获取视频直链';
        previewBtn.textContent = '▶ 查看封面';
        copyLinkBtn.textContent = '🔗 复制封面链接';
    } else {
        downloadBtn.textContent = isVideo ? '⬇ 下载视频' : '⬇ 下载全部';
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
async function handleDownload() {
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

    if (!currentVideoData?.video_url) { showToast('无可用下载地址', 'error'); return; }

    downloadBtn.disabled = true;
    progressBar.style.display = 'block';
    progressFill.style.width = '0%';
    progressText.textContent = '0%';

    try {
        const rawUrl = currentVideoData.video_url || '';
        const videoUrl = (rawUrl.startsWith('yt://') || rawUrl.startsWith('tt://') || rawUrl.startsWith('bl://') || rawUrl.startsWith('wx://'))
            ? rawUrl
            : (currentVideoData.video_url_no_watermark || rawUrl);
        const title = (currentVideoData.title || 'video').substring(0, 50);
        const ref = getReferer(currentVideoData.platform);
        const resp = await fetch(`${API_BASE}/api/download?video_url=${encodeURIComponent(videoUrl)}&title=${encodeURIComponent(title)}&referer=${encodeURIComponent(ref)}`);

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${resp.status}`);
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
    } catch (err) {
        showToast(`下载失败: ${err.message}`, 'error');
    } finally {
        downloadBtn.disabled = false;
        setTimeout(() => { progressBar.style.display = 'none'; }, 2000);
    }
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
    await downloadImagesByIndices(indices);
}

async function downloadImagesByIndices(indices) {
    const referer = getReferer(currentVideoData.platform);
    const total = indices.length;
    showToast(`开始下载 ${total} 张图片...`, 'info');

    downloadBtn.disabled = true;
    progressBar.style.display = 'block';

    let done = 0;
    for (const i of indices) {
        const imgUrl = currentVideoData.image_list[i];
        if (!imgUrl) continue;
        try {
            const resp = await fetch(`${API_BASE}/api/proxy?video_url=${encodeURIComponent(imgUrl)}&referer=${encodeURIComponent(referer)}`);
            const blob = await resp.blob();
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = `${(currentVideoData.title || 'image').substring(0, 30)}_${i + 1}.jpg`;
            a.click();
            URL.revokeObjectURL(a.href);
            done++;
            const pct = Math.round((done / total) * 100);
            progressFill.style.width = pct + '%';
            progressText.textContent = `${done}/${total}`;
            downloadBtn.textContent = `⬇ 下载中 ${done}/${total}`;
            await new Promise(r => setTimeout(r, 300));
        } catch (e) {
            showToast(`第 ${i + 1} 张下载失败`, 'error');
        }
    }
    downloadBtn.textContent = `⬇ 下载全部`;
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
        const { results } = await resp.json();
        let ok = 0;
        results.forEach((r) => { if (r.success) ok++; renderBatchItem(r); });
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
        const { history } = await (await fetch(`${API_BASE}/api/history`)).json();
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
    if (btn) { doDownload(btn.dataset.url, btn.dataset.title, btn.dataset.platform); return; }
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

async function doDownload(videoUrl, title, platform) {
    try {
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
    } catch (err) { showToast(`下载失败: ${err.message}`, 'error'); }
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
