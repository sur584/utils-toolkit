import { useState, useEffect, useRef, useCallback } from 'react';
import ReactDOM from 'react-dom/client';
import { fmt, uid, isImg, toast, resizeFile, downloadFile } from '../shared/utils.js';
import { Download, X, Trash, Check, Alert, Refresh } from '../shared/icons.jsx';
import { ZoomControls, Btn, UploadZone, Divider, EmptyState } from '../shared/components.jsx';
import { useZoomPan } from '../shared/hooks.js';

// ==================== Global State ====================
let _images = [], _ls = new Set(), _sel = new Set(), _activeId = null;
let _tab = 'detect', _method = 'lsb', _strength = 5, _batchProgress = null;
const sub = fn => { _ls.add(fn); return () => _ls.delete(fn) };
const notify = () => _ls.forEach(fn => fn());

const addImages = files => {
  var v = Array.from(files).filter(isImg);
  if (!v.length) return;
  var n = v.map(f => ({
    id: uid(), file: f, name: f.name, size: f.size,
    thumb: URL.createObjectURL(f),
    status: 'idle', detectStatus: 'idle',
    detectResult: null, removeResult: null, removeUrl: null, error: null
  }));
  _images = [..._images, ...n];
  if (!_activeId && n.length) _activeId = n[0].id;
  notify();
};
const rmImg = id => {
  var i = _images.find(x => x.id === id);
  if (i) {
    URL.revokeObjectURL(i.thumb);
    if (i.removeUrl) URL.revokeObjectURL(i.removeUrl);
  }
  _images = _images.filter(x => x.id !== id);
  _sel.delete(id);
  if (_activeId === id) _activeId = _images[0]?.id || null;
  notify();
};
const clearAll = () => {
  _images.forEach(i => { URL.revokeObjectURL(i.thumb); if (i.removeUrl) URL.revokeObjectURL(i.removeUrl) });
  _images = []; _sel.clear(); _activeId = null; notify();
};
const upd = (id, u) => { _images = _images.map(i => i.id === id ? { ...i, ...u } : i); notify() };
const setActiveId = id => { _activeId = id; notify() };
const toggleSel = id => { _sel.has(id) ? _sel.delete(id) : _sel.add(id); notify() };
const selAll = () => { _images.forEach(i => _sel.add(i.id)); notify() };
const deselAll = () => { _sel.clear(); notify() };
const setTab = t => { _tab = t; notify() };
const setMethod = m => { _method = m; notify() };
const setStrength = s => { _strength = s; notify() };
const useStore = () => {
  const [, t] = useState(0);
  useEffect(() => { const u = sub(() => t(x => x + 1)); return u }, []);
  return { images: _images, sel: _sel, activeId: _activeId, tab: _tab, method: _method, strength: _strength, batchProgress: _batchProgress };
};

// ==================== Tool Icons ====================
var Shield = function () {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /></svg>;
};
var Search = function () {
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>;
};
var Eraser = function () {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20 20H7L3 16l9-9 8 8-4 4z" /><path d="m6.5 17.5 5-5" /></svg>;
};
var Layers = function () {
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="12 2 2 7 12 12 22 7 12 2" /><polyline points="2 17 12 22 22 17" /><polyline points="2 12 12 17 22 12" /></svg>;
};

// ==================== Detection Methods Config ====================
var DETECT_METHODS = [
  { key: 'lsb', name: 'LSB 隐写', icon: '🔍', desc: '最低有效位分析' },
  { key: 'dct', name: 'DCT 变换', icon: '📊', desc: '离散余弦变换域检测' },
  { key: 'dwt', name: 'DWT 小波', icon: '🌊', desc: '小波变换域检测' },
  { key: 'alpha', name: 'Alpha 通道', icon: '🔲', desc: '透明通道水印检测' },
  { key: 'visual', name: '可见水印', icon: '👁', desc: '视觉水印识别' },
  { key: 'statistical', name: '统计分析', icon: '📈', desc: '统计特征异常检测' },
];

var DETAIL_LABELS = {
  lsb: {
    bit_planes_analyzed: '分析位平面',
    lsb_bias: 'LSB 偏差值',
    affected_pixel_ratio: '受影响像素比例',
    estimated_capacity_kb: '估计嵌入容量',
    chi_square_statistic: '卡方统计量',
    rs_regular_blocks: 'RS Regular 块',
    rs_singular_blocks: 'RS Singular 块',
  },
  dct: {
    block_count: 'DCT 块数量',
    zero_coeff_ratio: '零系数比例',
    anomalous_frequency_count: '异常频率位置数',
    ac_energy_mean: '平均 AC 能量',
    dc_mean: 'DC 系数均值',
    quantization_noise_estimate: '量化噪声估计',
  },
  dwt: {
    high_freq_energy_ratio: '高频能量占比',
    image_dimensions: '小波分解尺寸',
  },
  alpha: {
    unique_alpha_values: '唯一 Alpha 值数',
    non_trivial_pixel_count: '非二值像素数',
    non_trivial_pixel_ratio: '非二值像素比例',
    alpha_mean: 'Alpha 均值',
    alpha_std: 'Alpha 标准差',
    value_distribution: '值分布类型',
  },
  statistical: {
    image_entropy: '图像熵',
    max_possible_entropy: '最大可能熵',
    entropy_utilization: '熵利用率',
    histogram_chi_square: '直方图卡方值',
    pair_symmetry_index: '偶奇对称性指数',
    unique_pixel_values: '唯一像素值数',
    pixel_distribution: '像素分布类型',
  },
  visual: {},
};

var REMOVE_METHODS = [
  { key: 'lsb', name: 'LSB 清除', desc: '清除最低有效位中的隐藏信息' },
  { key: 'blur', name: '高斯模糊', desc: '对水印区域进行模糊处理' },
  { key: 'jpeg', name: 'JPEG 重压缩', desc: '通过 JPEG 压缩消除频域水印' },
  { key: 'bitplane', name: '位平面清除', desc: '清除特定位平面的嵌入数据' },
  { key: 'combo', name: '组合清除', desc: '多种方法联合使用，效果更强' },
];

// ==================== API Functions ====================
async function detectSingle(img) {
  upd(img.id, { detectStatus: 'detecting', error: null });
  try {
    var uploadFile = await resizeFile(img.file, 2048);
    var formData = new FormData();
    formData.append('file', uploadFile, img.file.name);
    var resp = await fetch('/api/watermark/detect', { method: 'POST', body: formData });
    if (!resp.ok) {
      var err = await resp.json().catch(function () { return {} });
      throw new Error(err.detail || ('HTTP ' + resp.status));
    }
    var data = await resp.json();
    upd(img.id, {
      detectStatus: 'done',
      detectResult: data,
      status: data.has_watermark ? 'watermark' : 'clean'
    });
  } catch (e) {
    upd(img.id, { detectStatus: 'error', status: 'error', error: e.message });
  }
}

async function removeSingle(img) {
  upd(img.id, { status: 'removing', error: null });
  try {
    var uploadFile = await resizeFile(img.file, 2048);
    var formData = new FormData();
    formData.append('file', uploadFile, img.file.name);
    formData.append('method', _method);
    formData.append('strength', String(_strength));
    var resp = await fetch('/api/watermark/remove', { method: 'POST', body: formData });
    if (!resp.ok) {
      var err = await resp.json().catch(function () { return {} });
      throw new Error(err.detail || ('HTTP ' + resp.status));
    }
    var blob = await resp.blob();
    var url = URL.createObjectURL(blob);
    upd(img.id, { status: 'removed', removeResult: blob, removeUrl: url });
  } catch (e) {
    upd(img.id, { status: 'error', error: e.message });
  }
}

// ==================== Confidence Bar ====================
function ConfidenceBar({ value, label, color }) {
  var c = color || (value >= 70 ? 'bg-red-500' : value >= 40 ? 'bg-yellow-500' : 'bg-green-500');
  return (
    <div className="flex items-center gap-2">
      {label && <span className="text-xs text-gray-500 w-16 flex-shrink-0">{label}</span>}
      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
        <div className={'h-full rounded-full transition-all duration-500 ' + c} style={{ width: Math.min(100, value) + '%' }} />
      </div>
      <span className="text-xs text-gray-600 w-10 text-right">{Math.round(value)}%</span>
    </div>
  );
}

// ==================== Info Row ====================
function InfoRow({ label, value }) {
  if (value === undefined || value === null) return null;
  return (
    <div className="flex items-center justify-between">
      <span className="text-[11px] text-gray-400">{label}</span>
      <span className="text-[11px] text-gray-700 font-mono">{value}</span>
    </div>
  );
}

// ==================== Detail Value Renderer ====================
function DetailValue({ k, v, labels }) {
  if (v === undefined || v === null) return null;
  var label = (labels && labels[k]) || k;
  if (typeof v === 'object' && !Array.isArray(v)) {
    return (
      <div className="ml-3">
        <span className="text-[11px] text-gray-500 font-medium">{label}</span>
        <div className="ml-3 mt-0.5 space-y-0.5">
          {Object.keys(v).map(function (sk) {
            return (
              <div key={sk} className="flex items-center justify-between">
                <span className="text-[11px] text-gray-400">{sk}</span>
                <span className="text-[11px] text-gray-700 font-mono">{typeof v[sk] === 'number' ? v[sk].toFixed(4).replace(/\.?0+$/, '') : String(v[sk])}</span>
              </div>
            );
          })}
        </div>
      </div>
    );
  }
  var displayVal = typeof v === 'number' ? (Number.isInteger(v) ? String(v) : v.toFixed(4).replace(/\.?0+$/, '')) : String(v);
  return (
    <div className="flex items-center justify-between">
      <span className="text-[11px] text-gray-400">{label}</span>
      <span className="text-[11px] text-gray-700 font-mono">{displayVal}</span>
    </div>
  );
}

// ==================== Detection Result Card ====================
function DetectResultCard({ result }) {
  var [expanded, setExpanded] = useState({});
  if (!result) return null;
  var confidenceColor = result.confidence >= 70 ? 'text-red-500' : result.confidence >= 40 ? 'text-yellow-600' : 'text-green-500';

  var toggleExpand = function (key) {
    setExpanded(function (prev) {
      var next = Object.assign({}, prev);
      next[key] = !next[key];
      return next;
    });
  };

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="flex items-center gap-3 p-3 rounded-xl bg-white border border-gray-100 shadow-sm">
        <div className={'w-10 h-10 rounded-xl flex items-center justify-center ' + (result.has_watermark ? 'bg-red-50 text-red-500' : 'bg-green-50 text-green-500')}>
          {result.has_watermark ? <Alert /> : <Check />}
        </div>
        <div className="flex-1">
          <p className="text-sm font-semibold text-gray-800">{result.has_watermark ? '检测到水印' : '未检测到水印'}</p>
          <p className="text-xs text-gray-400">置信度 <span className={confidenceColor + ' font-medium'}>{Math.round(result.confidence)}%</span> &middot; 耗时 {(result.processing_time || 0).toFixed(2)}s</p>
        </div>
      </div>

      {result.image_info && (
        <div className="rounded-xl bg-white border border-gray-100 p-3">
          <p className="text-xs font-medium text-gray-600 mb-2">图片信息</p>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1">
            <InfoRow label="尺寸" value={result.image_info.width + ' x ' + result.image_info.height} />
            <InfoRow label="通道" value={result.image_info.channels + (result.image_info.has_alpha ? ' (含Alpha)' : '')} />
            <InfoRow label="总像素" value={result.image_info.total_pixels?.toLocaleString()} />
            <InfoRow label="文件大小" value={result.image_info.file_size_kb + ' KB'} />
          </div>
        </div>
      )}

      <div className="space-y-1.5">
        {DETECT_METHODS.map(function (m) {
          var d = result.details && result.details[m.key];
          if (!d) return null;
          var detected = d.detected;
          var isExpanded = expanded[m.key];
          var hasDetails = d.description || (d.technical_details && Object.keys(d.technical_details).length > 0);
          var labels = DETAIL_LABELS[m.key] || {};
          return (
            <div key={m.key} className="rounded-lg bg-white border border-gray-100 overflow-hidden">
              <div className={'flex items-center gap-3 px-3 py-2 cursor-pointer transition-colors ' + (hasDetails ? 'hover:bg-gray-50' : '')} onClick={hasDetails ? function () { toggleExpand(m.key) } : undefined}>
                <span className="text-base w-6 text-center">{m.icon}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-medium text-gray-700">{m.name}</span>
                    {detected && <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-50 text-red-500 font-medium">检出</span>}
                    {!detected && <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-50 text-green-500 font-medium">未检出</span>}
                  </div>
                  <ConfidenceBar value={d.confidence || 0} />
                </div>
                {hasDetails && (
                  <svg className={'w-4 h-4 text-gray-400 flex-shrink-0 transition-transform duration-200 ' + (isExpanded ? 'rotate-180' : '')} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="6 9 12 15 18 9" /></svg>
                )}
              </div>
              {hasDetails && (
                <div className={'overflow-hidden transition-all duration-200 ' + (isExpanded ? 'max-h-[500px] opacity-100' : 'max-h-0 opacity-0')}>
                  <div className="px-3 py-2 bg-gray-50 border-t border-gray-100 space-y-1">
                    {d.description && <p className="text-[11px] text-gray-500 mb-1.5">{d.description}</p>}
                    {d.technical_details && Object.keys(d.technical_details).map(function (k) {
                      return <DetailValue key={k} k={k} v={d.technical_details[k]} labels={labels} />;
                    })}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {result.visualization && (
        <div className="rounded-xl overflow-hidden border border-gray-100">
          <p className="text-xs font-medium text-gray-600 px-3 py-2 bg-gray-50">热力图可视化</p>
          <img src={'data:image/png;base64,' + result.visualization} alt="heatmap" className="w-full" />
        </div>
      )}
    </div>
  );
}

// ==================== Image Card (Sidebar) ====================
function ImageCard({ image, isActive, isSel }) {
  var statusNode = null;
  if (image.detectStatus === 'detecting' || image.status === 'removing')
    statusNode = <span className="w-3.5 h-3.5 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />;
  else if (image.status === 'watermark')
    statusNode = <span className="text-orange-500"><Alert /></span>;
  else if (image.status === 'clean')
    statusNode = <span className="text-green-500"><Check /></span>;
  else if (image.status === 'removed')
    statusNode = <span className="text-blue-500"><Check /></span>;
  else if (image.status === 'error')
    statusNode = <span className="text-red-400"><X /></span>;

  var statusText = null;
  if (image.detectStatus === 'detecting') statusText = <span className="text-xs text-blue-500">检测中</span>;
  else if (image.status === 'removing') statusText = <span className="text-xs text-blue-500">去除中</span>;
  else if (image.status === 'watermark') statusText = <span className="text-xs text-orange-500">有水印</span>;
  else if (image.status === 'clean') statusText = <span className="text-xs text-green-500">无水印</span>;
  else if (image.status === 'removed') statusText = <span className="text-xs text-blue-500">已去除</span>;
  else if (image.status === 'error') statusText = <span className="text-xs text-red-400">失败</span>;

  var activeCls = isActive ? 'bg-blue-50 border border-blue-200' : 'hover:bg-gray-50 border border-transparent';
  var selCls = isSel ? 'bg-blue-500 border-blue-500' : 'border-gray-300 hover:border-blue-400';

  return (
    <div className={'flex items-center gap-2 p-2 rounded-lg transition-colors group animate-fade-up cursor-pointer ' + activeCls} onClick={() => setActiveId(image.id)}>
      <div className={'sel-cb w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0 cursor-pointer transition-all ' + selCls} onClick={e => { e.stopPropagation(); toggleSel(image.id) }}>
        {isSel && <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3"><polyline points="20 6 9 17 4 12" /></svg>}
      </div>
      <div className="w-10 h-10 rounded-lg overflow-hidden bg-gray-100 flex-shrink-0 relative">
        <img src={image.thumb} alt="" loading="lazy" className="w-full h-full object-cover" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-gray-800 truncate">{image.name}</p>
        <div className="flex items-center gap-1.5 mt-0.5">
          <span className="text-xs text-gray-400">{fmt(image.size)}</span>
          {statusText}
        </div>
      </div>
      <div className="flex items-center gap-0.5 flex-shrink-0">
        {image.status === 'removed' && <button onClick={e => { e.stopPropagation(); downloadRemoved(image) }} className="p-1 rounded hover:bg-blue-50 text-gray-400 hover:text-blue-500 transition-all" title="下载"><Download /></button>}
        {image.detectStatus === 'error' && <button onClick={e => { e.stopPropagation(); detectSingle(image) }} className="p-1 rounded hover:bg-blue-50 text-gray-400 hover:text-blue-500 transition-all" title="重试"><Refresh /></button>}
        <button onClick={e => { e.stopPropagation(); rmImg(image.id) }} className="p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-400 transition-all" title="删除"><X /></button>
      </div>
    </div>
  );
}

function downloadRemoved(img) {
  if (!img.removeResult) return;
  var name = img.name.replace(/\.[^.]+$/, '') + '_cleaned.png';
  downloadFile(img.removeResult, name);
}

// ==================== Detect Tab ====================
function DetectTab({ activeImg }) {
  var { zoom, setZoom, pan, setPan, handleWheel, handlePanDown, handlePanMove, handlePanUp, handleZoomReset } = useZoomPan();
  var [showHeatmap, setShowHeatmap] = useState(false);

  useEffect(function () { setZoom(1); setPan({ x: 0, y: 0 }); setShowHeatmap(false); }, [activeImg?.id]);

  if (!activeImg) return <EmptyState icon={<Shield />} title="选择图片查看检测结果" description="从左侧列表选择一张图片" theme="blue" />;

  var imgUrl = activeImg.thumb;
  var imgStyle = {
    transform: 'scale(' + zoom + ') translate(' + pan.x + 'px,' + pan.y + 'px)',
    transformOrigin: 'center center',
    transition: 'transform 0.15s ease-out',
    maxWidth: '100%', maxHeight: '100%', objectFit: 'contain',
    cursor: zoom > 1 ? 'grab' : 'zoom-in',
  };

  if (activeImg.detectStatus === 'detecting') {
    return (
      <div className="flex-1 flex flex-col items-center justify-center">
        <div className="w-16 h-16 rounded-2xl bg-blue-50 flex items-center justify-center mx-auto mb-4">
          <span className="w-8 h-8 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
        </div>
        <p className="text-sm text-gray-500">正在检测水印，请稍候...</p>
      </div>
    );
  }

  if (activeImg.detectStatus === 'error') {
    return (
      <div className="flex-1 flex flex-col items-center justify-center">
        <div className="text-center max-w-sm">
          <div className="w-16 h-16 rounded-2xl bg-red-50 flex items-center justify-center mx-auto mb-4 text-red-400"><Alert /></div>
          <p className="text-sm text-red-500 mb-2">检测失败</p>
          <div className="bg-red-50 border border-red-100 rounded-lg px-3 py-2 mb-3 text-left">
            <p className="text-xs text-red-600 break-all">{activeImg.error || '未知错误'}</p>
          </div>
          <Btn variant="ghost" size="sm" theme="blue" onClick={() => detectSingle(activeImg)}><Refresh />重试</Btn>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex gap-4 overflow-hidden p-4">
      <div className="flex-1 flex flex-col items-center justify-center overflow-hidden relative rounded-xl bg-gray-50 border border-gray-100"
        onWheel={handleWheel} onMouseDown={handlePanDown} onMouseMove={handlePanMove} onMouseUp={handlePanUp} onMouseLeave={handlePanUp}>
        <div className="relative" style={{ maxWidth: '100%', maxHeight: '100%' }}>
          <img src={imgUrl} alt="" style={imgStyle} draggable={false} />
          {showHeatmap && activeImg.detectResult && activeImg.detectResult.visualization && (
            <img src={'data:image/png;base64,' + activeImg.detectResult.visualization} alt="heatmap"
              className="absolute inset-0 w-full h-full object-contain pointer-events-none"
              style={{ opacity: 0.5, mixBlendMode: 'multiply' }} />
          )}
        </div>
        <ZoomControls zoom={zoom} setZoom={setZoom} handleZoomReset={handleZoomReset} />
        {activeImg.detectResult && activeImg.detectResult.visualization && (
          <button onClick={() => setShowHeatmap(!showHeatmap)}
            className={'absolute top-3 right-3 px-2.5 py-1 rounded-lg text-xs font-medium border transition-all z-10 ' + (showHeatmap ? 'bg-blue-500 text-white border-blue-500' : 'bg-white text-gray-600 border-gray-200 hover:bg-blue-50')}>
            <Layers /> 热力图
          </button>
        )}
        <div className="absolute bottom-14 flex items-center gap-3">
          <span className="text-xs text-gray-400">{activeImg.name} ({fmt(activeImg.size)})</span>
        </div>
      </div>

      <div className="w-80 flex-shrink-0 overflow-y-auto space-y-3">
        {activeImg.detectResult ? (
          <DetectResultCard result={activeImg.detectResult} />
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-14 h-14 rounded-2xl bg-blue-50 flex items-center justify-center mx-auto mb-3 text-blue-400"><Search /></div>
            <p className="text-sm text-gray-500 mb-1">尚未检测</p>
            <p className="text-xs text-gray-400">点击下方按钮开始检测</p>
          </div>
        )}
        <Btn variant="primary" size="sm" theme="blue" className="w-full" onClick={() => detectSingle(activeImg)} loading={activeImg.detectStatus === 'detecting'}>
          <Search />{activeImg.detectResult ? '重新检测' : '开始检测'}
        </Btn>
      </div>
    </div>
  );
}

// ==================== Remove Tab ====================
function RemoveTab({ activeImg }) {
  var { zoom, setZoom, pan, setPan, handleWheel, handlePanDown, handlePanMove, handlePanUp, handleZoomReset } = useZoomPan();
  var [sliderPos, setSliderPos] = useState(50);
  var sliderDragging = useRef(false);

  useEffect(function () { setZoom(1); setPan({ x: 0, y: 0 }); setSliderPos(50); }, [activeImg?.id]);

  var handleSliderMove = useCallback(function (e) {
    if (!sliderDragging.current) return;
    var rect = e.currentTarget.getBoundingClientRect();
    var x = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
    setSliderPos(x / rect.width * 100);
  }, []);

  if (!activeImg) return <EmptyState icon={<Eraser />} title="选择图片进行水印去除" description="从左侧列表选择一张图片" theme="blue" />;

  if (activeImg.status === 'removing') {
    return (
      <div className="flex-1 flex flex-col items-center justify-center">
        <div className="w-16 h-16 rounded-2xl bg-blue-50 flex items-center justify-center mx-auto mb-4">
          <span className="w-8 h-8 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
        </div>
        <p className="text-sm text-gray-500">正在去除水印，请稍候...</p>
      </div>
    );
  }

  if (activeImg.status === 'error' && !activeImg.detectResult) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center">
        <div className="text-center max-w-sm">
          <div className="w-16 h-16 rounded-2xl bg-red-50 flex items-center justify-center mx-auto mb-4 text-red-400"><Alert /></div>
          <p className="text-sm text-red-500 mb-2">去除失败</p>
          <div className="bg-red-50 border border-red-100 rounded-lg px-3 py-2 mb-3 text-left">
            <p className="text-xs text-red-600 break-all">{activeImg.error || '未知错误'}</p>
          </div>
          <Btn variant="ghost" size="sm" theme="blue" onClick={() => removeSingle(activeImg)}><Refresh />重试</Btn>
        </div>
      </div>
    );
  }

  if (activeImg.removeUrl) {
    return (
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="flex-1 flex items-center justify-center overflow-hidden p-4 relative">
          <div className="relative w-full h-full max-w-3xl max-h-full select-none overflow-hidden rounded-xl"
            onMouseMove={handleSliderMove} onMouseUp={() => sliderDragging.current = false} onMouseLeave={() => sliderDragging.current = false}>
            <div className="absolute inset-0 flex items-center justify-center bg-gray-200">
              <img src={activeImg.removeUrl} alt="" className="max-w-full max-h-full object-contain" />
            </div>
            <div className="absolute inset-0 overflow-hidden" style={{ clipPath: 'inset(0 ' + (100 - sliderPos) + '% 0 0)' }}>
              <div className="w-full h-full flex items-center justify-center bg-gray-200">
                <img src={activeImg.thumb} alt="" className="max-w-full max-h-full object-contain" />
              </div>
            </div>
            <div className="absolute top-0 bottom-0 w-0.5 bg-white shadow-lg cursor-ew-resize" style={{ left: sliderPos + '%' }} onMouseDown={e => { e.preventDefault(); sliderDragging.current = true }}>
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-8 h-8 rounded-full bg-white shadow-lg flex items-center justify-center cursor-ew-resize">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#666" strokeWidth="2"><polyline points="15 18 9 12 15 6" /></svg>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#666" strokeWidth="2" style={{ marginLeft: -4 }}><polyline points="9 18 15 12 9 6" /></svg>
              </div>
            </div>
            <div className="absolute bottom-3 left-3 px-2 py-1 rounded bg-black/50 text-white text-xs">原图</div>
            <div className="absolute bottom-3 right-3 px-2 py-1 rounded bg-blue-500/80 text-white text-xs">去除结果</div>
          </div>
        </div>
        <div className="flex items-center justify-center gap-2 py-2">
          <Btn variant="primary" size="sm" theme="blue" onClick={() => downloadRemoved(activeImg)}><Download />下载结果</Btn>
          <Btn variant="ghost" size="sm" theme="blue" onClick={() => removeSingle(activeImg)}><Refresh />重新去除</Btn>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex gap-4 overflow-hidden p-4">
      <div className="flex-1 flex flex-col items-center justify-center overflow-hidden relative rounded-xl bg-gray-50 border border-gray-100"
        onWheel={handleWheel} onMouseDown={handlePanDown} onMouseMove={handlePanMove} onMouseUp={handlePanUp} onMouseLeave={handlePanUp}>
        <img src={activeImg.thumb} alt="" style={{
          transform: 'scale(' + zoom + ') translate(' + pan.x + 'px,' + pan.y + 'px)',
          transformOrigin: 'center center', transition: 'transform 0.15s ease-out',
          maxWidth: '100%', maxHeight: '100%', objectFit: 'contain', cursor: zoom > 1 ? 'grab' : 'zoom-in',
        }} draggable={false} />
        <ZoomControls zoom={zoom} setZoom={setZoom} handleZoomReset={handleZoomReset} />
        <div className="absolute bottom-14 flex items-center gap-3">
          <span className="text-xs text-gray-400">{activeImg.name} ({fmt(activeImg.size)})</span>
        </div>
      </div>

      <div className="w-80 flex-shrink-0 overflow-y-auto space-y-4">
        <div>
          <p className="text-xs font-medium text-gray-600 mb-2">去除方法</p>
          <div className="space-y-1">
            {REMOVE_METHODS.map(function (m) {
              return (
                <button key={m.key} onClick={() => setMethod(m.key)}
                  className={'w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-all ' + (_method === m.key ? 'bg-blue-50 border border-blue-200' : 'bg-white border border-gray-100 hover:bg-gray-50')}>
                  <div className={'w-4 h-4 rounded-full border-2 flex items-center justify-center flex-shrink-0 ' + (_method === m.key ? 'border-blue-500' : 'border-gray-300')}>
                    {_method === m.key && <div className="w-2 h-2 rounded-full bg-blue-500" />}
                  </div>
                  <div>
                    <p className="text-xs font-medium text-gray-700">{m.name}</p>
                    <p className="text-[10px] text-gray-400">{m.desc}</p>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs font-medium text-gray-600">强度</p>
            <span className="text-xs text-blue-500 font-medium">{_strength}</span>
          </div>
          <input type="range" min="1" max="10" value={_strength} onChange={e => setStrength(parseInt(e.target.value))}
            className="w-full h-1.5 accent-blue-500" />
          <div className="flex justify-between text-[10px] text-gray-400 mt-1">
            <span>轻微</span>
            <span>强力</span>
          </div>
        </div>

        {activeImg.status === 'error' && (
          <div className="bg-red-50 border border-red-100 rounded-lg px-3 py-2">
            <p className="text-xs text-red-600 break-all">{activeImg.error}</p>
          </div>
        )}

        <Btn variant="primary" size="sm" theme="blue" className="w-full" onClick={() => removeSingle(activeImg)} loading={activeImg.status === 'removing'}>
          <Eraser />{activeImg.status === 'removed' ? '重新去除' : '开始去除'}
        </Btn>
      </div>
    </div>
  );
}

// ==================== Main App ====================
function App() {
  var store = useStore();
  var images = store.images;
  var sel = store.sel;
  var activeId = store.activeId;
  var tab = store.tab;

  var [processing, setProcessing] = useState(false);
  var [sidebarW, setSidebarW] = useState(260);
  var containerRef = useRef(null);
  var batchAbortRef = useRef(null);

  var activeImg = images.find(i => i.id === activeId) || images[0] || null;
  var detectedCount = images.filter(i => i.detectStatus === 'done').length;
  var removedCount = images.filter(i => i.status === 'removed').length;
  var selCount = sel.size;

  useEffect(function () {
    function onKey(e) {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      if (e.key === '1') setTab('detect');
      else if (e.key === '2') setTab('remove');
    }
    document.addEventListener('keydown', onKey);
    return function () { document.removeEventListener('keydown', onKey); };
  }, []);

  var handleSidebarDrag = function (clientX) {
    if (!containerRef.current) return;
    var rect = containerRef.current.getBoundingClientRect();
    setSidebarW(Math.max(200, Math.min(clientX - rect.left, 400)));
  };

  var handleDetectAll = async function () {
    setProcessing(true);
    batchAbortRef.current = new AbortController();
    var pending = images.filter(i => i.detectStatus !== 'done');
    _batchProgress = { completed: 0, total: pending.length, type: 'detect' };
    notify();
    var workers = [];
    var queue = pending.slice();
    for (var w = 0; w < Math.min(3, queue.length); w++) {
      workers.push((async function () {
        while (queue.length) {
          if (batchAbortRef.current && batchAbortRef.current.signal.aborted) break;
          var img = queue.shift();
          if (!img) break;
          await detectSingle(img);
          _batchProgress.completed++;
          notify();
        }
      })());
    }
    await Promise.all(workers);
    _batchProgress = null;
    notify();
    toast('批量检测完成', 'ok');
    setProcessing(false);
  };

  var handleRemoveAll = async function () {
    setProcessing(true);
    batchAbortRef.current = new AbortController();
    var pending = images.filter(i => i.status === 'watermark' || i.detectStatus === 'done');
    _batchProgress = { completed: 0, total: pending.length, type: 'remove' };
    notify();
    var workers = [];
    var queue = pending.slice();
    for (var w = 0; w < Math.min(3, queue.length); w++) {
      workers.push((async function () {
        while (queue.length) {
          if (batchAbortRef.current && batchAbortRef.current.signal.aborted) break;
          var img = queue.shift();
          if (!img) break;
          await removeSingle(img);
          _batchProgress.completed++;
          notify();
        }
      })());
    }
    await Promise.all(workers);
    _batchProgress = null;
    notify();
    toast('批量去除完成', 'ok');
    setProcessing(false);
  };

  var handleDownloadAll = function () {
    images.filter(i => i.removeResult).forEach(function (img) {
      downloadRemoved(img);
    });
  };

  var handleDeleteSelected = function () {
    Array.from(sel).forEach(id => rmImg(id));
  };

  var actionBtns = null;
  if (images.length === 0) {
    actionBtns = <Btn variant="primary" size="sm" theme="blue" disabled><Shield />等待上传图片</Btn>;
  } else if (selCount > 1) {
    actionBtns = <>
      <Btn variant="primary" size="sm" theme="blue" onClick={handleDetectAll} disabled={processing} loading={processing && _batchProgress?.type === 'detect'}><Search />检测选中 ({selCount})</Btn>
      <Btn variant="ghost" size="sm" theme="blue" onClick={handleRemoveAll} disabled={processing} loading={processing && _batchProgress?.type === 'remove'}><Eraser />去除选中</Btn>
      {processing && <button onClick={function () { if (batchAbortRef.current) batchAbortRef.current.abort(); toast('已取消', 'info'); }} className="px-3 py-1.5 text-sm font-medium rounded-lg transition-all flex items-center gap-1.5 bg-red-500 hover:bg-red-600 text-white"><X />取消</button>}
    </>;
  } else {
    actionBtns = <>
      <Btn variant="primary" size="sm" theme="blue" onClick={handleDetectAll} disabled={processing} loading={processing && _batchProgress?.type === 'detect'}><Search />全部检测 ({images.length})</Btn>
      <Btn variant="ghost" size="sm" theme="blue" onClick={handleRemoveAll} disabled={processing} loading={processing && _batchProgress?.type === 'remove'}><Eraser />全部去除</Btn>
      {processing && <button onClick={function () { if (batchAbortRef.current) batchAbortRef.current.abort(); toast('已取消', 'info'); }} className="px-3 py-1.5 text-sm font-medium rounded-lg transition-all flex items-center gap-1.5 bg-red-500 hover:bg-red-600 text-white"><X />取消</button>}
    </>;
  }

  return (
    <div className="flex flex-col h-screen">
      <div className="flex items-center h-12 px-5 bg-white border-b border-gray-100 flex-shrink-0">
        <a href="../../" className="flex items-center gap-1 text-sm text-gray-400 hover:text-blue-500 transition-colors mr-4 no-underline">&larr; 工具箱</a>
        <div className="flex items-center gap-2.5">
          <div className="w-6 h-6 rounded bg-blue-500 flex items-center justify-center text-white"><Shield /></div>
          <span className="text-base font-semibold text-gray-700">暗水印检测与去除</span>
          <span className="text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-500 font-medium">AI</span>
        </div>
      </div>

      <div ref={containerRef} className="flex flex-1 overflow-hidden">
        {/* Left sidebar */}
        <div className="flex flex-col bg-white border-r border-gray-100 flex-shrink-0" style={{ width: sidebarW }}>
          <div className="flex items-center justify-between px-3 py-2.5 border-b border-gray-50">
            <div className="flex items-center gap-1.5">
              <span className="text-sm font-medium text-gray-700">图片列表</span>
              <span className="text-[11px] px-1.5 py-0.5 rounded bg-blue-50 text-blue-500 font-medium">{images.length}</span>
            </div>
            {images.length > 0 && <button onClick={clearAll} className="text-xs text-gray-400 hover:text-red-400 transition-colors flex items-center gap-0.5"><Trash />清空</button>}
          </div>

          {images.length > 0 && (
            <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-50">
              <button onClick={selCount === images.length ? deselAll : selAll} className="text-xs text-blue-500 hover:text-blue-700 font-medium">{selCount === images.length ? '取消全选' : '全选'}</button>
              {selCount > 0 && <span className="text-xs text-gray-400">已选 {selCount}/{images.length}</span>}
              {selCount > 0 && <div className="flex-1" />}
              {selCount > 0 && <button onClick={handleDeleteSelected} className="text-xs text-red-400 hover:text-red-600">删除选中</button>}
            </div>
          )}

          <div className="flex-1 overflow-y-auto p-1.5 space-y-0.5">
            {images.length === 0 ? <div className="p-1.5"><UploadZone theme="blue" onFiles={addImages} /></div> : images.map(img => <ImageCard key={img.id} image={img} isActive={img.id === activeId} isSel={sel.has(img.id)} />)}
          </div>

          {images.length > 0 && <div className="p-2 border-t border-gray-50"><UploadZone theme="blue" onFiles={addImages} isButton={true} /></div>}
        </div>

        <Divider theme="blue" onDrag={handleSidebarDrag} />

        {/* Right main panel */}
        <div className="flex-1 flex flex-col overflow-hidden min-w-0">
          <div className="px-4 py-3 bg-white border-b border-gray-100 flex-shrink-0">
            <div className="flex items-center gap-2">
              {actionBtns}
              {removedCount > 0 && <Btn variant="ghost" size="sm" theme="blue" onClick={handleDownloadAll}><Download />下载全部 ({removedCount})</Btn>}
              <div className="flex-1" />
              {/* Tab switch */}
              <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-0.5">
                <button onClick={() => setTab('detect')} className={'px-3 py-1 rounded-md text-xs font-medium transition-all ' + (tab === 'detect' ? 'bg-white text-gray-800 shadow-sm' : 'text-gray-500')}>检测</button>
                <button onClick={() => setTab('remove')} className={'px-3 py-1 rounded-md text-xs font-medium transition-all ' + (tab === 'remove' ? 'bg-white text-gray-800 shadow-sm' : 'text-gray-500')}>去除</button>
              </div>
            </div>
          </div>

          <div className="flex-1 flex overflow-hidden bg-gray-100">
            {tab === 'detect' ? <DetectTab activeImg={activeImg} /> : <RemoveTab activeImg={activeImg} />}
          </div>

          <div className="flex items-center justify-between px-4 py-2 bg-white border-t border-gray-100 flex-shrink-0">
            <div className="flex items-center gap-3 text-xs text-gray-400">
              {_batchProgress ? (
                <span className="text-blue-600 font-medium">
                  {_batchProgress.type === 'detect' ? '检测' : '去除'}中 {_batchProgress.completed}/{_batchProgress.total}
                </span>
              ) : (
                <>
                  <span>{images.length} 张图片</span>
                  {detectedCount > 0 && <span className="text-blue-500">{detectedCount} 已检测</span>}
                  {removedCount > 0 && <span className="text-green-500">{removedCount} 已去除</span>}
                  {images.filter(i => i.status === 'watermark').length > 0 && <span className="text-orange-500">{images.filter(i => i.status === 'watermark').length} 有水印</span>}
                  {images.filter(i => i.status === 'error').length > 0 && <span className="text-red-400">{images.filter(i => i.status === 'error').length} 失败</span>}
                  {selCount > 0 && <span className="text-blue-500">已选 {selCount}</span>}
                </>
              )}
            </div>
            <div className="flex items-center gap-1 text-xs text-gray-400"><div className="w-1.5 h-1.5 rounded-full bg-green-400" />就绪</div>
          </div>
        </div>
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
