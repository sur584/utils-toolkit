/**
 * Shared download helpers for utils-toolkit tools.
 * Provides single-file and batch (zip) download utilities.
 */

/* saveAs and JSZip are loaded as global scripts in index.html */

/**
 * Download a single processed image.
 * @param {Object} img - Image object with resultBlob and name properties
 * @param {string} suffix - Filename suffix before extension (e.g. '_remove', '_no_text')
 * @param {string} format - Export format ('png' or 'webp')
 */
export function downloadOne(img, suffix, format) {
  if (!img.resultBlob) return;
  var ext = format === 'webp' ? '.webp' : '.png';
  var name = img.name.replace(/\.[^.]+$/, '') + suffix + ext;
  saveAs(img.resultBlob, name);
}

/**
 * Download multiple processed images as a zip file.
 * Falls back to single download when only one item.
 * @param {Array} items - Array of image objects with resultBlob and name properties
 * @param {string} suffix - Filename suffix before extension (e.g. '_remove', '_no_text')
 * @param {string} format - Export format ('png' or 'webp')
 * @param {string} zipName - Output zip filename (e.g. 'removed_images.zip')
 */
export async function downloadMultiple(items, suffix, format, zipName) {
  if (!items.length) return;
  if (items.length === 1) { downloadOne(items[0], suffix, format); return; }
  var zip = new JSZip();
  var ext = format === 'webp' ? '.webp' : '.png';
  items.forEach(function (img) {
    zip.file(img.name.replace(/\.[^.]+$/, '') + suffix + ext, img.resultBlob);
  });
  saveAs(await zip.generateAsync({ type: 'blob' }), zipName);
}
