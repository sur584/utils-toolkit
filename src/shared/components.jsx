/**
 * Shared UI components for utils-toolkit tools.
 * Only includes components that are identical across multiple tools.
 */

import React, { useState, useEffect, useRef } from 'react';
import { isImg } from './utils.js';
import { Upload, Plus, Grip } from './icons.jsx';

/**
 * Zoom controls overlay (used in bg-remover and text-remover).
 * @param {number} zoom - Current zoom level (0.25 - 10)
 * @param {Function} setZoom - Setter for zoom level
 * @param {Function} handleZoomReset - Reset zoom to 1
 */
export function ZoomControls({ zoom, setZoom, handleZoomReset }) {
  return (
    <div className="absolute bottom-3 left-1/2 -translate-x-1/2 flex items-center gap-1 px-2 py-1 rounded-lg bg-black/60 backdrop-blur-sm z-10 select-none">
      <button
        onClick={function () {
          setZoom(function (z) {
            return Math.max(0.25, z - 0.25);
          });
        }}
        className="w-6 h-6 flex items-center justify-center text-white/80 hover:text-white rounded hover:bg-white/10 transition-colors text-sm font-bold"
      >
        -
      </button>
      <span className="text-white/80 text-xs w-12 text-center">
        {Math.round(zoom * 100)}%
      </span>
      <button
        onClick={function () {
          setZoom(function (z) {
            return Math.min(10, z + 0.25);
          });
        }}
        className="w-6 h-6 flex items-center justify-center text-white/80 hover:text-white rounded hover:bg-white/10 transition-colors text-sm font-bold"
      >
        +
      </button>
      {zoom !== 1 && (
        <button
          onClick={handleZoomReset}
          className="ml-1 px-1.5 py-0.5 text-[10px] text-white/70 hover:text-white rounded hover:bg-white/10 transition-colors"
        >
          重置
        </button>
      )}
    </div>
  );
}

/**
 * Themed button component.
 * @param {'primary'|'ghost'} variant - Button style variant
 * @param {'sm'|'md'} size - Button size
 * @param {'purple'|'rose'|'blue'|'orange'} theme - Accent color theme
 * @param {boolean} disabled - Disabled state
 * @param {boolean} loading - Show loading spinner
 */
export function Btn({ children, variant = 'primary', size = 'md', theme = 'blue', disabled, loading, className = '', ...props }) {
  var styles = {
    primary: {
      purple: 'bg-purple-500 hover:bg-purple-600 text-white shadow-sm',
      rose: 'bg-rose-500 hover:bg-rose-600 text-white shadow-sm',
      blue: 'bg-blue-500 hover:bg-blue-600 text-white shadow-sm',
      orange: 'bg-orange-500 hover:bg-orange-600 text-white shadow-sm',
    },
    ghost: 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-50 hover:border-gray-300',
  };
  var sizes = { sm: 'px-3.5 py-2 text-xs gap-1.5', md: 'px-4 py-2.5 text-sm gap-1.5' };
  var v = typeof styles[variant] === 'string' ? styles[variant] : (styles[variant] || {})[theme] || styles.primary.blue;
  return (
    <button
      disabled={disabled || loading}
      className={'inline-flex items-center justify-center font-medium rounded-lg transition-all duration-200 active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed ' + v + ' ' + (sizes[size] || sizes.md) + ' ' + className}
      {...props}
    >
      {loading && <span className="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" />}
      {children}
    </button>
  );
}

/**
 * Themed file upload zone with drag-and-drop, paste, and click support.
 * @param {'purple'|'rose'|'blue'|'orange'} theme - Accent color theme
 * @param {Function} onFiles - Callback receiving validated File array
 * @param {string} accept - Accepted file types (input accept attribute)
 * @param {boolean} multiple - Allow multiple files (default true)
 * @param {boolean} isButton - Render as compact button instead of full zone
 */
export function UploadZone({ theme = 'blue', onFiles, accept = 'image/jpeg,image/png,image/webp,image/bmp', multiple = true, isButton = false }) {
  var ref = useRef(null);
  var handle = function (f) {
    var v = Array.from(f).filter(isImg);
    if (v.length && onFiles) onFiles(v);
  };
  useEffect(function () {
    var onPaste = function (e) {
      var files = Array.from(e.clipboardData?.items || [])
        .filter(function (i) { return i.type.startsWith('image/'); })
        .map(function (i) { return i.getAsFile(); })
        .filter(Boolean)
        .filter(isImg);
      if (files.length && onFiles) onFiles(files);
    };
    document.addEventListener('paste', onPaste);
    return function () { document.removeEventListener('paste', onPaste); };
  }, [onFiles]);

  var themeColors = {
    purple: { border: 'hover:border-purple-400', text: 'hover:text-purple-500', bg: 'hover:bg-purple-50/50', ringBg: 'bg-purple-50', ringBgHover: 'group-hover:bg-purple-100', ringText: 'text-purple-500', hoverBorder: 'hover:border-purple-400', hoverBg: 'hover:bg-purple-50/30' },
    rose: { border: 'hover:border-rose-400', text: 'hover:text-rose-500', bg: 'hover:bg-rose-50/50', ringBg: 'bg-rose-50', ringBgHover: 'group-hover:bg-rose-100', ringText: 'text-rose-500', hoverBorder: 'hover:border-rose-400', hoverBg: 'hover:bg-rose-50/30' },
    blue: { border: 'hover:border-blue-400', text: 'hover:text-blue-500', bg: 'hover:bg-blue-50/50', ringBg: 'bg-blue-50', ringBgHover: 'group-hover:bg-blue-100', ringText: 'text-blue-500', hoverBorder: 'hover:border-blue-400', hoverBg: 'hover:bg-blue-50/30' },
    orange: { border: 'hover:border-orange-400', text: 'hover:text-orange-500', bg: 'hover:bg-orange-50/50', ringBg: 'bg-orange-50', ringBgHover: 'group-hover:bg-orange-100', ringText: 'text-orange-500', hoverBorder: 'hover:border-orange-400', hoverBg: 'hover:bg-orange-50/30' },
  };
  var c = themeColors[theme] || themeColors.blue;

  if (isButton) return (
    <>
      <button
        onClick={function () { ref.current?.click(); }}
        className={'w-full flex items-center justify-center gap-2 py-2.5 px-3 rounded-lg border border-dashed border-gray-300 text-xs text-gray-500 ' + c.border + ' ' + c.text + ' ' + c.bg + ' transition-all'}
      >
        <Plus />添加图片
      </button>
      <input ref={ref} type="file" multiple={multiple} accept={accept} className="hidden" onChange={function (e) { handle(e.target.files || []); e.target.value = ''; }} />
    </>
  );

  return (
    <div
      onDrop={function (e) { e.preventDefault(); handle(e.dataTransfer?.files || []); }}
      onDragOver={function (e) { e.preventDefault(); }}
      onClick={function () { ref.current?.click(); }}
      className={'flex flex-col items-center justify-center py-10 px-4 rounded-xl border-2 border-dashed border-gray-200 ' + c.hoverBorder + ' ' + c.hoverBg + ' cursor-pointer transition-all group'}
    >
      <div className={'w-10 h-10 rounded-full ' + c.ringBg + ' flex items-center justify-center mb-2.5 ' + c.ringBgHover + ' transition-colors ' + c.ringText}>
        <Upload />
      </div>
      <p className="text-sm font-medium text-gray-700 mb-0.5">拖拽图片到此处</p>
      <p className="text-xs text-gray-400">支持 JPG, PNG, WebP, BMP</p>
      <input ref={ref} type="file" multiple={multiple} accept={accept} className="hidden" onChange={function (e) { handle(e.target.files || []); e.target.value = ''; }} />
    </div>
  );
}

/**
 * Themed resizable divider for sidebar/panel splitting.
 * Supports mouse and touch drag.
 * @param {'purple'|'rose'|'blue'|'orange'} theme - Accent color theme
 * @param {Function} onDrag - Callback receiving clientX during drag
 */
export function Divider({ theme = 'blue', onDrag }) {
  var [hovering, setHovering] = useState(false);
  var dragging = useRef(false);

  var handleDown = function (e) {
    e.preventDefault();
    dragging.current = true;
    var onMove = function (ev) { if (dragging.current) onDrag(ev.clientX); };
    var onUp = function () {
      dragging.current = false;
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  var handleTouchStart = function (e) {
    dragging.current = true;
    var onMove = function (ev) { if (dragging.current && ev.touches[0]) onDrag(ev.touches[0].clientX); };
    var onEnd = function () {
      dragging.current = false;
      document.removeEventListener('touchmove', onMove);
      document.removeEventListener('touchend', onEnd);
    };
    document.addEventListener('touchmove', onMove, { passive: false });
    document.addEventListener('touchend', onEnd);
  };

  var themeColors = {
    purple: { hoverBg: 'hover:bg-purple-200/50', handleBg: 'group-hover:bg-purple-400' },
    rose: { hoverBg: 'hover:bg-rose-200/50', handleBg: 'group-hover:bg-rose-400' },
    blue: { hoverBg: 'hover:bg-blue-200/50', handleBg: 'group-hover:bg-blue-400' },
    orange: { hoverBg: 'hover:bg-orange-200/50', handleBg: 'group-hover:bg-orange-400' },
  };
  var c = themeColors[theme] || themeColors.blue;

  return (
    <div
      className={'relative flex-shrink-0 w-1.5 cursor-col-resize group z-10 ' + c.hoverBg + ' transition-colors'}
      onMouseDown={handleDown}
      onTouchStart={handleTouchStart}
      onMouseEnter={function () { setHovering(true); }}
      onMouseLeave={function () { setHovering(false); }}
    >
      <div className={'absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-4 h-10 rounded bg-gray-300/60 ' + c.handleBg + ' transition-colors flex items-center justify-center ' + (hovering ? 'opacity-100' : 'opacity-0 group-hover:opacity-100')}>
        <Grip />
      </div>
    </div>
  );
}

/**
 * Empty state placeholder when no images are loaded.
 * @param {React.ReactNode} icon - Icon element to display
 * @param {string} title - Main heading text
 * @param {string} description - Subtitle text
 * @param {'purple'|'rose'|'blue'|'orange'} theme - Accent color theme
 */
export function EmptyState({ icon, title, description, theme = 'blue' }) {
  var themeColors = {
    purple: 'bg-purple-50 text-purple-500',
    rose: 'bg-rose-50 text-rose-500',
    blue: 'bg-blue-50 text-blue-500',
    orange: 'bg-orange-50 text-orange-500',
  };
  var c = themeColors[theme] || themeColors.blue;

  return (
    <div className="flex-1 flex items-center justify-center h-full animate-fade-up">
      <div className="text-center max-w-sm">
        <div className={'w-20 h-20 rounded-2xl ' + c + ' flex items-center justify-center mx-auto mb-5'}>{icon}</div>
        <h2 className="text-xl font-semibold text-gray-800 mb-2">{title}</h2>
        <p className="text-sm text-gray-400 mb-5">{description}</p>
      </div>
    </div>
  );
}
