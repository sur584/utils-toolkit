/**
 * Shared utilities for VideoTranscript frontend.
 */
function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function maskApiKey(key) {
    if (!key) return '';
    if (key.length <= 8) return '***';
    return key.substring(0, 4) + '****' + key.substring(key.length - 4);
}

function generateKey(name) {
    if (name) {
        return name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'provider';
    }
    return 'k_' + Date.now().toString(36) + Math.random().toString(36).substring(2, 8);
}
