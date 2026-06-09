/**
 * Shared utility functions for utils-toolkit tools.
 * Extracted from inline tool pages to enable Vite bundling.
 */

/**
 * Format bytes into human-readable string (e.g. 1.5 MB).
 * @param {number} bytes
 * @param {number} [decimals=1]
 * @returns {string}
 */
export function fmt(bytes, decimals = 1) {
  if (!bytes) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(decimals)) + ' ' + sizes[i];
}

/**
 * Generate a random unique ID (8-char alphanumeric).
 * @returns {string}
 */
export function uid() {
  return Math.random().toString(36).slice(2, 11);
}

/**
 * Check if a File object is a supported image type.
 * Supports JPEG, PNG, WebP, BMP.
 * @param {File} file
 * @returns {boolean}
 */
export function isImgFile(file) {
  return ['image/jpeg', 'image/png', 'image/webp', 'image/bmp'].includes(file.type);
}

/**
 * Check if a filename has an image extension.
 * @param {string} name
 * @returns {boolean}
 */
export function isImgName(name) {
  return /\.(jpe?g|png|gif|webp|bmp|svg)$/i.test(name);
}

/**
 * Get file extension from MIME type.
 * @param {string} mimeType
 * @returns {string}
 */
export function mimeToExt(mimeType) {
  return ({ 'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp' })[mimeType] || 'jpg';
}

/**
 * Show a toast notification.
 * @param {string} msg - Message to display
 * @param {'ok'|'err'|'info'} [type='ok'] - Toast type
 */
export function showToast(msg, type = 'ok') {
  var el = document.createElement('div');
  el.style.cssText =
    'position:fixed;top:20px;left:50%;transform:translateX(-50%);z-index:9999;' +
    'padding:10px 20px;border-radius:10px;font-size:13px;font-weight:500;color:#fff;' +
    'pointer-events:none;animation:fadeUp .3s ease both;transition:opacity .3s';
  el.style.background =
    type === 'ok' ? '#10b981' : type === 'err' ? '#ef4444' : '#6366f1';
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(function () {
    el.style.opacity = '0';
    setTimeout(function () {
      el.remove();
    }, 300);
  }, 2200);
}

/**
 * Resize an image file using Canvas before upload.
 * Useful for reducing upload size and inference time.
 * @param {File} file
 * @param {number} [maxDim=2048] - Maximum dimension (width or height)
 * @returns {Promise<File|Blob>}
 */
export function resizeFile(file, maxDim = 2048) {
  return new Promise(function (resolve) {
    var img = new Image();
    img.onload = function () {
      var w = img.width,
        h = img.height;
      if (w <= maxDim && h <= maxDim) {
        resolve(file);
        return;
      }
      var ratio = maxDim / Math.max(w, h);
      var nw = Math.round(w * ratio),
        nh = Math.round(h * ratio);
      var canvas = document.createElement('canvas');
      canvas.width = nw;
      canvas.height = nh;
      var ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0, nw, nh);
      canvas.toBlob(
        function (blob) {
          resolve(blob ? new File([blob], file.name, { type: 'image/jpeg' }) : file);
        },
        'image/jpeg',
        0.9
      );
    };
    img.onerror = function () {
      resolve(file);
    };
    img.src = URL.createObjectURL(file);
  });
}

/**
 * Create a download link and trigger download.
 * @param {Blob|File} blob - File content
 * @param {string} filename - Download filename
 */
export function downloadFile(blob, filename) {
  if (!blob) return;
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

/**
 * Format duration in seconds to human-readable string.
 * @param {number} seconds
 * @returns {string} e.g. "1:23" or "12:34"
 */
export function formatDuration(seconds) {
  if (!seconds && seconds !== 0) return '--:--';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return m + ':' + String(s).padStart(2, '0');
}

// ─── 向后兼容别名 ──────────────────────────────────────
// 原始 main.jsx 使用的函数名，映射到共享模块的标准名

/** Alias for isImgFile - check if file is a supported image type */
export const isImg = isImgFile;

/** Alias for mimeToExt - get file extension from MIME type */
export const ext = mimeToExt;

/** Alias for showToast - show toast notification */
export const toast = showToast;
