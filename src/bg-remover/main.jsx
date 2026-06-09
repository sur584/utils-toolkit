import { useState, useEffect, useRef, useCallback } from 'react';
import ReactDOM from 'react-dom/client';
import { fmt, uid, isImg, toast, resizeFile } from '../shared/utils.js';
import { Download, X, Trash, Check, Alert, Refresh } from '../shared/icons.jsx';
import { ZoomControls, Btn, UploadZone, Divider, EmptyState } from '../shared/components.jsx';
import { useZoomPan } from '../shared/hooks.js';
import { downloadOne as dlOne, downloadMultiple as dlMultiple } from '../shared/download.js';

// 开发者模式点击计数
var _devModeClicks = 0, _devModeTimer = null;

// ==================== 全局状态管理 ====================
let _images = [], _ls = new Set(), _sel = new Set(), _activeId = null, _exportFormat = 'png', _devMode = false, _batchProgress = null;
const sub = fn => {_ls.add(fn); return () => _ls.delete(fn)};
const notify = () => _ls.forEach(fn => fn());

const addImages = files => {
  const v = Array.from(files).filter(isImg);
  if(!v.length) return;
  const n = v.map(f => ({id:uid(), file:f, name:f.name, size:f.size, thumb:URL.createObjectURL(f), status:'idle', resultBlob:null, resultUrl:null, error:null}));
  _images = [..._images, ...n];
  if(!_activeId && n.length) _activeId = n[0].id;
  notify();
};
const rmImg = id => {
  const i = _images.find(x => x.id===id);
  if(i){URL.revokeObjectURL(i.thumb); if(i.resultUrl) URL.revokeObjectURL(i.resultUrl)}
  _images = _images.filter(x => x.id!==id);
  _sel.delete(id);
  if(_activeId===id) _activeId = _images[0]?.id || null;
  notify();
};
const clearAll = () => {
  _images.forEach(i => {URL.revokeObjectURL(i.thumb); if(i.resultUrl) URL.revokeObjectURL(i.resultUrl)});
  _images = []; _sel.clear(); _activeId = null; notify();
};
const upd = (id, u) => {_images = _images.map(i => i.id===id ? {...i,...u} : i); notify()};
const setActiveId = id => {_activeId = id; notify()};
const toggleSel = id => {_sel.has(id) ? _sel.delete(id) : _sel.add(id); notify()};
const selAll = () => {_images.forEach(i => _sel.add(i.id)); notify()};
const deselAll = () => {_sel.clear(); notify()};
const useStore = () => {
  const [,t] = useState(0);
  useEffect(() => {const u = sub(() => t(x => x+1)); return u}, []);
  return {images:_images, sel:_sel, activeId:_activeId, exportFormat:_exportFormat, devMode:_devMode, batchProgress:_batchProgress};
};

// ==================== 工具专属图标 ====================
var Scissors = function(){return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="6" cy="6" r="3"/><path d="M8.12 8.12 12 12"/><path d="M20 4 8.12 15.88"/><circle cx="6" cy="18" r="3"/><path d="M14.8 14.8 20 20"/></svg>};


// ==================== 图片卡片（左侧列表项） ====================
function ImageCard({image, isActive, isSel}){
  var statusNode = null;
  if(image.status === 'processing') statusNode = <span className="w-3.5 h-3.5 border-2 border-purple-400 border-t-transparent rounded-full animate-spin"/>;
  else if(image.status === 'done') statusNode = <span className="text-green-500"><Check/></span>;
  else if(image.status === 'error') statusNode = <span className="text-red-400"><X/></span>;

  var statusText = null;
  if(image.status === 'processing') statusText = <span className="text-xs text-purple-500">{image.statusText || '处理中'}</span>;
  else if(image.status === 'done') {
    var clsLabel = image.classification ? ({product:'商品',portrait:'人物',pet:'宠物',general:'通用'}[image.classification] || '') : '';
    statusText = <span className="text-xs text-green-500">{clsLabel ? clsLabel + ' · ' : ''}完成</span>;
  }
  else if(image.status === 'error') statusText = <span className="text-xs text-red-400">失败</span>;

  var activeCls = isActive ? 'bg-purple-50 border border-purple-200' : 'hover:bg-gray-50 border border-transparent';
  var selCls = isSel ? 'bg-purple-500 border-purple-500' : 'border-gray-300 hover:border-purple-400';

  return <div className={'flex items-center gap-2 p-2 rounded-lg transition-colors group animate-fade-up cursor-pointer '+activeCls} onClick={() => setActiveId(image.id)}>
    <div className={'sel-cb w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0 cursor-pointer transition-all '+selCls} onClick={e => {e.stopPropagation(); toggleSel(image.id)}}>
      {isSel && <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg>}
    </div>
    <div className="w-10 h-10 rounded-lg overflow-hidden bg-gray-100 flex-shrink-0 relative">
      <img src={image.thumb} alt="" loading="lazy" className="w-full h-full object-cover"/>
      {image.status==='done' && <div className="absolute inset-0 bg-green-500/20 flex items-center justify-center"><span className="text-green-600"><Check/></span></div>}
    </div>
    <div className="flex-1 min-w-0">
      <p className="text-sm text-gray-800 truncate">{image.name}</p>
      <div className="flex items-center gap-1.5 mt-0.5">
        <span className="text-xs text-gray-400">{fmt(image.size)}</span>
        {statusText}
      </div>
    </div>
    <div className="flex items-center gap-0.5 flex-shrink-0">
      {image.status==='done' && <button onClick={e => {e.stopPropagation(); dlOne(image, '_remove', _exportFormat)}} className="p-1 rounded hover:bg-purple-50 text-gray-400 hover:text-purple-500 transition-all" title="下载"><Download/></button>}
      {image.status==='error' && <button onClick={e => {e.stopPropagation(); processSingle(image)}} className="p-1 rounded hover:bg-purple-50 text-gray-400 hover:text-purple-500 transition-all" title="重试"><Refresh/></button>}
      <button onClick={e => {e.stopPropagation(); rmImg(image.id)}} className="p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-400 transition-all" title="删除"><X/></button>
    </div>
  </div>;
}

// ==================== 处理逻辑（全局函数，供组件调用） ====================
var _processingRef = {current: false};
var _batchAbortController = null;
var _batchCancelled = false;

async function processSingle(img, retryCount){
  retryCount = retryCount || 0;
  if(_batchAbortController && _batchAbortController.signal.aborted) return;
  upd(img.id, {status:'processing', statusText:'分析中...', error:null});
  try {
    var uploadFile = await resizeFile(img.file, 2048);
    upd(img.id, {statusText:'处理中...'});
    var formData = new FormData();
    formData.append('file', uploadFile, img.file.name);
    formData.append('model', 'auto');
    formData.append('format', _exportFormat);
    var fetchOpts = {method:'POST', body:formData};
    if(_batchAbortController) fetchOpts.signal = _batchAbortController.signal;
    var resp = await fetch('/api/bg-remove', fetchOpts);
    if(!resp.ok){
      var err = await resp.json().catch(function(){return {}});
      throw new Error(err.detail || ('HTTP ' + resp.status));
    }
    var blob = await resp.blob();
    var url = URL.createObjectURL(blob);
    var classification = resp.headers.get('X-Image-Classification') || null;
    var modelUsed = resp.headers.get('X-Model-Used') || null;
    var cacheHit = resp.headers.get('X-Cache-Hit') === 'true';
    var processingTime = resp.headers.get('X-Processing-Time-Ms') || null;
    upd(img.id, {status:'done', statusText:null, resultBlob:blob, resultUrl:url,
                  classification:classification, modelUsed:modelUsed, cacheHit:cacheHit, processingTime:processingTime});
  } catch(e) {
    if(_batchAbortController && _batchAbortController.signal.aborted) return;
    if(retryCount < 2){
      upd(img.id, {statusText:'重试中 (' + (retryCount+1) + '/2)...'});
      return processSingle(img, retryCount + 1);
    }
    upd(img.id, {status:'error', statusText:null, error:e.message});
  }
}

// ==================== 手动编辑画笔 ====================
function EditCanvas({resultUrl, thumbUrl, zoom, pan, editMode, brushSize, onSave, onCancel}){
  var canvasRef = useRef(null);
  var sourceRef = useRef(null);  // 缩放后的原图（用于恢复笔刷）
  var drawingRef = useRef(false);
  var lastPosRef = useRef(null);  // 上一个画笔位置，用于连线
  var historyRef = useRef([]);
  var cursorRef = useRef({x:-100, y:-100, visible:false});

  // 初始化：加载结果图到 canvas，加载原图到 source
  useEffect(function(){
    if(!resultUrl || !canvasRef.current) return;
    var canvas = canvasRef.current;
    var ctx = canvas.getContext('2d');
    var container = canvas.parentElement;
    var img = new Image();
    img.onload = function(){
      var cW = container ? container.clientWidth : img.naturalWidth;
      var cH = container ? container.clientHeight : img.naturalHeight;
      var scale = Math.min(cW / img.naturalWidth, cH / img.naturalHeight, 1);
      var dw = Math.round(img.naturalWidth * scale);
      var dh = Math.round(img.naturalHeight * scale);
      canvas.width = dw;
      canvas.height = dh;
      ctx.clearRect(0, 0, dw, dh);
      ctx.drawImage(img, 0, 0, dw, dh);
      historyRef.current = [ctx.getImageData(0, 0, dw, dh)];
    };
    img.src = resultUrl;

    // 加载原图（用于恢复笔刷）- 缩放到与 canvas 相同尺寸
    var srcImg = new Image();
    srcImg.onload = function(){
      // 创建一个缩放后的原图 canvas，尺寸与 result canvas 一致
      var scaledCanvas = document.createElement('canvas');
      scaledCanvas.width = canvas.width;
      scaledCanvas.height = canvas.height;
      scaledCanvas.getContext('2d').drawImage(srcImg, 0, 0, canvas.width, canvas.height);
      sourceRef.current = scaledCanvas;
    };
    srcImg.src = thumbUrl;
  }, [resultUrl, thumbUrl]);

  // 获取 canvas 坐标（考虑缩放和平移，transformOrigin: center center）
  function getCanvasXY(e){
    var canvas = canvasRef.current;
    if(!canvas) return null;
    var container = canvas.parentElement;
    var rect = container.getBoundingClientRect();
    var displayW = rect.width, displayH = rect.height;
    var mouseX = e.clientX - rect.left;
    var mouseY = e.clientY - rect.top;
    // canvas 在容器中居中，计算 canvas 的实际显示位置
    var cw = canvas.offsetWidth || canvas.width;
    var ch = canvas.offsetHeight || canvas.height;
    var ox = (displayW - cw) / 2;
    var oy = (displayH - ch) / 2;
    // 逆向 transform: translate(-50%,-50%) + scale(zoom) translate(pan)
    var localX = (mouseX - displayW/2) / zoom + displayW/2 - pan.x - ox;
    var localY = (mouseY - displayH/2) / zoom + displayH/2 - pan.y - oy;
    // local → canvas pixel
    var cx = localX * (canvas.width / cw);
    var cy = localY * (canvas.height / ch);
    if(cx < 0 || cy < 0 || cx >= canvas.width || cy >= canvas.height) return null;
    return {x:cx, y:cy};
  }

  function applyBrush(e){
    var pos = getCanvasXY(e);
    if(!pos) return;
    var canvas = canvasRef.current;
    var ctx = canvas.getContext('2d');
    var displayW = canvas.offsetWidth || 1;
    var r = brushSize * (canvas.width / displayW) / zoom;
    var last = lastPosRef.current;

    if(editMode === 'erase'){
      ctx.globalCompositeOperation = 'destination-out';
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.lineWidth = r * 2;
      if(last){
        ctx.beginPath();
        ctx.moveTo(last.x, last.y);
        ctx.lineTo(pos.x, pos.y);
        ctx.stroke();
      }
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, r, 0, Math.PI * 2);
      ctx.fill();
    } else if(editMode === 'restore' && sourceRef.current){
      // 从原图恢复画笔区域（clip 到画笔路径）
      // sourceRef.current 已经是缩放到 canvas 尺寸的原图
      ctx.save();
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, r, 0, Math.PI * 2);
      if(last){
        ctx.moveTo(last.x, last.y - r);
        ctx.lineTo(pos.x, pos.y - r);
        ctx.moveTo(last.x, last.y + r);
        ctx.lineTo(pos.x, pos.y + r);
      }
      ctx.clip();
      ctx.globalCompositeOperation = 'source-over';
      // 直接绘制已缩放的原图
      ctx.drawImage(sourceRef.current, 0, 0);
      ctx.restore();
    }
    lastPosRef.current = pos;
  }

  function saveSnapshot(){
    var canvas = canvasRef.current;
    if(!canvas) return;
    var ctx = canvas.getContext('2d');
    historyRef.current.push(ctx.getImageData(0, 0, canvas.width, canvas.height));
    if(historyRef.current.length > 30) historyRef.current.shift();
  }

  function handlePointerDown(e){
    if(editMode === 'none') return;
    e.preventDefault();
    saveSnapshot();
    drawingRef.current = true;
    lastPosRef.current = null;
    applyBrush(e);
  }
  function handlePointerMove(e){
    // 更新画笔光标位置
    var canvas = canvasRef.current;
    if(!canvas) return;
    var container = canvas.parentElement;
    var rect = container.getBoundingClientRect();
    cursorRef.current = {
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
      visible: true
    };
    // 重绘光标
    var cursorEl = container.querySelector('.brush-cursor');
    if(cursorEl){
      var dispR = brushSize * (canvas.width / (canvas.offsetWidth || 1)) / zoom;
      var size = Math.max(dispR * 2, 4);
      cursorEl.style.width = size + 'px';
      cursorEl.style.height = size + 'px';
      cursorEl.style.left = cursorRef.current.x + 'px';
      cursorEl.style.top = cursorRef.current.y + 'px';
      cursorEl.style.opacity = cursorRef.current.visible ? '1' : '0';
      cursorEl.style.borderColor = editMode === 'erase' ? '#ef4444' : '#22c55e';
      cursorEl.style.backgroundColor = editMode === 'erase' ? 'rgba(239,68,68,0.15)' : 'rgba(34,197,94,0.15)';
    }
    if(!drawingRef.current) return;
    applyBrush(e);
  }
  function handlePointerUp(){
    drawingRef.current = false;
  }
  function handlePointerLeave(){
    drawingRef.current = false;
    cursorRef.current.visible = false;
    var canvas = canvasRef.current;
    if(canvas){
      var cursorEl = canvas.parentElement.querySelector('.brush-cursor');
      if(cursorEl) cursorEl.style.opacity = '0';
    }
  }

  function handleUndo(){
    if(historyRef.current.length <= 1) return;
    historyRef.current.pop();
    var prev = historyRef.current[historyRef.current.length - 1];
    var canvas = canvasRef.current;
    var ctx = canvas.getContext('2d');
    ctx.putImageData(prev, 0, 0);
    lastPosRef.current = null;
  }

  function handleSave(){
    var canvas = canvasRef.current;
    if(!canvas) return;
    canvas.toBlob(function(blob){
      if(!blob) return;
      var url = URL.createObjectURL(blob);
      onSave(blob, url);
    }, 'image/png');
  }

  useEffect(function(){
    return function(){ drawingRef.current = false; lastPosRef.current = null; };
  }, [editMode]);

  // 全局 pointermove：工具栏区域内隐藏画笔光标
  useEffect(function(){
    if(editMode === 'none') return;
    function onDocMove(e){
      var canvas = canvasRef.current;
      if(!canvas) return;
      var container = canvas.parentElement;
      var toolbar = container ? container.parentElement.querySelector('.edit-toolbar') : null;
      var cursorEl = container ? container.querySelector('.brush-cursor') : null;
      if(!cursorEl) return;
      if(toolbar && toolbar.contains(e.target)){
        cursorEl.style.opacity = '0';
      } else if(cursorRef.current.visible){
        cursorEl.style.opacity = '1';
      }
    }
    document.addEventListener('pointermove', onDocMove);
    return function(){ document.removeEventListener('pointermove', onDocMove); };
  }, [editMode]);

  return <>
    <div className="absolute inset-0 z-20" style={{cursor:'none'}}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerLeave={handlePointerLeave}>
      <div className="brush-cursor" style={{
        position:'absolute', pointerEvents:'none', borderRadius:'50%',
        border: editMode==='restore' ? '2px solid #22c55e' : '2px solid #ef4444',
        backgroundColor: editMode==='restore' ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
        transform:'translate(-50%,-50%)', opacity:0, transition:'width 0.1s, height 0.1s, border-color 0.2s, background-color 0.2s', zIndex:30
      }}/>
    </div>
    <canvas ref={canvasRef} className="absolute pointer-events-none" style={{
      top: '50%', left: '50%',
      transform: 'translate(-50%,-50%) scale('+zoom+') translate('+pan.x+'px,'+pan.y+'px)',
      transformOrigin: 'center center',
      imageRendering: zoom > 2 ? 'pixelated' : 'auto',
      maxWidth: '100%', maxHeight: '100%',
    }}/>
    {/* 编辑工具栏 */}
    <div className="edit-toolbar absolute top-3 left-3 flex items-center gap-1.5 px-2 py-1.5 rounded-lg bg-white/90 backdrop-blur-sm shadow-lg z-30 select-none" style={{cursor:'auto'}}>
      <span className="text-[11px] text-gray-500 font-medium mr-1">画笔:</span>
      <button onClick={function(){onCancel('erase')}} className={'px-2 py-1 rounded text-xs font-medium transition-all '+(editMode==='erase'?'bg-red-100 text-red-600':'text-gray-500 hover:bg-red-50')} title="擦除画笔">擦除</button>
      <button onClick={function(){onCancel('restore')}} className={'px-2 py-1 rounded text-xs font-medium transition-all '+(editMode==='restore'?'bg-green-100 text-green-600':'text-gray-500 hover:bg-green-50')} title="恢复画笔">恢复</button>
      <div className="w-px h-4 bg-gray-200 mx-0.5"/>
      <input type="range" min="5" max="100" value={brushSize} onChange={function(e){onCancel('size', parseInt(e.target.value))}} className="w-16 h-1 accent-purple-500" title={'画笔大小: ' + brushSize + 'px'}/>
      <span className="text-[10px] text-gray-400 w-7">{brushSize}</span>
      <div className="w-px h-4 bg-gray-200 mx-0.5"/>
      <button onClick={handleUndo} className="px-2 py-1 rounded text-xs text-gray-500 hover:bg-gray-100 transition-all" title="撤销">↩</button>
      <button onClick={handleSave} className="px-2.5 py-1 rounded text-xs font-medium bg-purple-500 text-white hover:bg-purple-600 transition-all">完成</button>
      <button onClick={function(){onCancel('cancel')}} className="px-2.5 py-1 rounded text-xs text-gray-500 hover:bg-gray-100 transition-all">取消</button>
    </div>
  </>;
}

// ==================== 预览面板（右侧） ====================
function PreviewPanel({activeImg, viewMode, setViewMode, sliderPos, setSliderPos, sliderDragging, handleSliderMove, zoom, setZoom, pan, setPan, handleWheel, handlePanDown, handlePanMove, handlePanUp, handleZoomReset, editMode, brushSize, onEditAction}){
  if(!activeImg) return <EmptyState icon={<Scissors/>} title="拖入图片开始抠图" description="AI 自动识别主体，一键去除背景，生成透明 PNG" theme="purple"/>;

  // 处理中
  if(activeImg.status === 'processing'){
    return <div className="text-center">
      <div className="w-16 h-16 rounded-2xl bg-purple-50 flex items-center justify-center mx-auto mb-4"><span className="w-8 h-8 border-2 border-purple-400 border-t-transparent rounded-full animate-spin"/></div>
      <p className="text-sm text-gray-500 mb-1">{activeImg.statusText || '正在抠图中，请稍后'}</p>
    </div>;
  }

  // 处理失败
  if(activeImg.status === 'error'){
    var errText = activeImg.error || '未知错误';
    var tipText = '';
    if(errText.indexOf('无法识别') >= 0 || errText.indexOf('格式') >= 0) tipText = '请确认文件是图片格式（JPG/PNG/WebP/BMP），而非 .psd/.svg/.gif 等格式';
    else if(errText.indexOf('损坏') >= 0 || errText.indexOf('无法读取') >= 0) tipText = '文件可能已损坏，请用其他软件重新导出为 PNG 或 JPG 后再试';
    else if(errText.indexOf('颜色模式') >= 0) tipText = '请用图片编辑软件将颜色模式转为 RGB 后再试';
    else if(errText.indexOf('太小') >= 0) tipText = '图片分辨率太小，请使用更大的图片';
    else if(errText.indexOf('超时') >= 0) tipText = '处理时间过长，请切换到「速度优先」模式，或缩小图片尺寸';
    else if(errText.indexOf('内存不足') >= 0) tipText = '图片太大导致内存不足，请将图片缩小到 2048px 以内';
    else if(errText.indexOf('模型') >= 0) tipText = '请尝试切换其他模型，或重启服务';
    else tipText = '支持 JPG、PNG、WebP、BMP 格式，建议尺寸不超过 4096px';

    return <div className="text-center max-w-sm">
      <div className="w-16 h-16 rounded-2xl bg-red-50 flex items-center justify-center mx-auto mb-4 text-red-400"><Alert/></div>
      <p className="text-sm text-red-500 mb-2">处理失败</p>
      <div className="bg-red-50 border border-red-100 rounded-lg px-3 py-2 mb-2 text-left">
        <p className="text-xs text-red-600 break-all leading-relaxed">{errText}</p>
      </div>
      <p className="text-xs text-gray-400 mb-3">{tipText}</p>
      <Btn variant="ghost" size="sm" theme="purple" onClick={() => processSingle(activeImg)}><Refresh/>重试</Btn>
    </div>;
  }

  // 对比模式（有结果时）— 不支持缩放，保留滑块交互
  if(viewMode === 'compare' && activeImg.resultUrl){
    return <div className="relative w-full h-full max-w-3xl max-h-full select-none overflow-hidden rounded-xl" onMouseMove={handleSliderMove} onMouseUp={() => sliderDragging.current=false} onMouseLeave={() => sliderDragging.current=false}>
      <div className="absolute inset-0 flex items-center justify-center checkerboard">
        <img src={activeImg.resultUrl} alt="" className="max-w-full max-h-full object-contain"/>
      </div>
      <div className="absolute inset-0 overflow-hidden" style={{clipPath:'inset(0 '+(100-sliderPos)+'% 0 0)'}}>
        <div className="w-full h-full flex items-center justify-center bg-gray-200">
          <img src={activeImg.thumb} alt="" className="max-w-full max-h-full object-contain"/>
        </div>
      </div>
      <div className="absolute top-0 bottom-0 w-0.5 bg-white shadow-lg cursor-ew-resize" style={{left:sliderPos+'%'}} onMouseDown={e => {e.preventDefault(); sliderDragging.current=true}}>
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-8 h-8 rounded-full bg-white shadow-lg flex items-center justify-center cursor-ew-resize">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#666" strokeWidth="2"><polyline points="15 18 9 12 15 6"/></svg>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#666" strokeWidth="2" style={{marginLeft:-4}}><polyline points="9 18 15 12 9 6"/></svg>
        </div>
      </div>
      <div className="absolute bottom-3 left-3 px-2 py-1 rounded bg-black/50 text-white text-xs">原图</div>
      <div className="absolute bottom-3 right-3 px-2 py-1 rounded bg-purple-500/80 text-white text-xs">抠图结果</div>
    </div>;
  }

  // 获取要显示的图片 URL
  var imgUrl = activeImg.resultUrl || activeImg.thumb;
  var imgStyle = {
    transform: 'scale('+zoom+') translate('+pan.x+'px,'+pan.y+'px)',
    transformOrigin: 'center center',
    transition: 'transform 0.15s ease-out',
    maxWidth: '100%',
    maxHeight: '100%',
    objectFit: 'contain',
    cursor: zoom > 1 ? 'grab' : 'zoom-in',
  };
  var checkerCls = activeImg.resultUrl ? ' checkerboard' : '';

  // 有结果时：显示抠图结果（支持缩放）
  if(activeImg.resultUrl){
    var inEdit = editMode !== 'none';
    return <div className={'relative w-full h-full flex flex-col items-center justify-center overflow-hidden rounded-xl'+(inEdit?' editing':'')}>
      <div className={'flex-1 flex items-center justify-center w-full overflow-hidden p-4'+checkerCls}
        onWheel={handleWheel}
        onMouseDown={inEdit ? undefined : handlePanDown}
        onMouseMove={inEdit ? undefined : handlePanMove}
        onMouseUp={inEdit ? undefined : handlePanUp}
        onMouseLeave={inEdit ? undefined : handlePanUp}>
        <img src={activeImg.resultUrl} alt="" style={{...imgStyle, display: inEdit ? 'none' : undefined}} draggable={false}/>
        {inEdit && <EditCanvas resultUrl={activeImg.resultUrl} thumbUrl={activeImg.thumb} zoom={zoom} pan={pan} editMode={editMode} brushSize={brushSize} onSave={function(blob,url){upd(activeImg.id,{resultBlob:blob,resultUrl:url}); onEditAction('done');}} onCancel={onEditAction}/>}
      </div>
      <ZoomControls zoom={zoom} setZoom={setZoom} handleZoomReset={handleZoomReset}/>
      {!inEdit && <button onClick={() => dlOne(activeImg, '_remove', _exportFormat)} className="absolute top-3 right-3 px-3 py-1.5 rounded-lg bg-purple-500 text-white text-xs font-medium hover:bg-purple-600 shadow-lg flex items-center gap-1.5 z-10 transition-all"><Download/>下载 PNG</button>}
      {!inEdit && _devMode && activeImg.classification && <div className="absolute top-14 right-3 px-3 py-2 rounded-lg bg-black/70 backdrop-blur-sm text-white text-[11px] space-y-1 z-10">
        <div>分类: {activeImg.classification}</div>
        <div>模型: {activeImg.modelUsed || '-'}</div>
        <div>缓存: {activeImg.cacheHit ? '命中' : '未命中'}</div>
        <div>耗时: {activeImg.processingTime ? activeImg.processingTime+'ms' : '-'}</div>
      </div>}
    </div>;
  }

  // 等待处理 - 显示原图预览（支持缩放）
  return <div className="relative w-full h-full flex flex-col items-center justify-center overflow-hidden">
    <div className="flex-1 flex items-center justify-center w-full overflow-hidden p-4"
      onWheel={handleWheel}
      onMouseDown={handlePanDown}
      onMouseMove={handlePanMove}
      onMouseUp={handlePanUp}
      onMouseLeave={handlePanUp}>
      <img src={activeImg.thumb} alt="" style={imgStyle} draggable={false}/>
    </div>
    <ZoomControls zoom={zoom} setZoom={setZoom} handleZoomReset={handleZoomReset}/>
    <div className="absolute bottom-14 flex items-center gap-3">
      <span className="text-xs text-gray-400">{activeImg.name} ({fmt(activeImg.size)})</span>
    </div>
  </div>;
}

// ==================== 主应用组件 ====================
function App(){
  var store = useStore();
  var images = store.images;
  var sel = store.sel;
  var activeId = store.activeId;

  var [processing, setProcessing] = useState(false);
  var [viewMode, setViewMode] = useState('result');
  var [sliderPos, setSliderPos] = useState(50);
  var sliderDragging = useRef(false);
  var [sidebarW, setSidebarW] = useState(260);
  var containerRef = useRef(null);
  var { zoom, setZoom, pan, setPan, handleWheel, handlePanDown, handlePanMove, handlePanUp, handleZoomReset } = useZoomPan();
  var [editMode, setEditMode] = useState('none');
  var [brushSize, setBrushSize] = useState(30);

  // 切换图片时重置缩放和编辑模式
  useEffect(function(){ setZoom(1); setPan({x:0,y:0}); setEditMode('none'); }, [activeId]);

  var activeImg = images.find(i => i.id===activeId) || images[0] || null;
  var doneCount = images.filter(i => i.status==='done').length;
  var selCount = sel.size;

  var handleSidebarDrag = function(clientX){
    if(!containerRef.current) return;
    var rect = containerRef.current.getBoundingClientRect();
    setSidebarW(Math.max(200, Math.min(clientX-rect.left, 400)));
  };

  var handleSliderMove = useCallback(function(e){
    if(!sliderDragging.current) return;
    var rect = e.currentTarget.getBoundingClientRect();
    var x = Math.max(0, Math.min(e.clientX-rect.left, rect.width));
    setSliderPos(x/rect.width*100);
  }, []);

  // 编辑模式操作（来自 EditCanvas 回调）
  var handleEditAction = useCallback(function(action, data){
    if(action === 'erase'){ setEditMode('erase'); }
    else if(action === 'restore'){ setEditMode('restore'); }
    else if(action === 'size'){ setBrushSize(data); }
    else if(action === 'undo'){
      // 触发 EditCanvas 内部的 undo（通过 force update）
      setBrushSize(function(s){ return s; }); // force re-render
    }
    else if(action === 'done'){ setEditMode('none'); }
    else if(action === 'cancel'){
      if(typeof data === 'string') setEditMode(data); // 'erase'/'restore'
      else setEditMode('none');
    }
  }, []);

  var handleProcessAll = async function(){
    setProcessing(true);
    var pending = images.filter(function(i){return i.status!=='done'});
    await processBatch(pending);
    setProcessing(false);
  };

  var handleProcessSelected = async function(){
    setProcessing(true);
    var pending = images.filter(function(i){return sel.has(i.id) && i.status!=='done'});
    await processBatch(pending);
    setProcessing(false);
  };

  var processBatch = async function(pending){
    if(!pending.length) return;
    _batchAbortController = new AbortController();
    _batchCancelled = false;
    var total = pending.length;
    var completed = 0;
    var startTime = Date.now();
    var concurrency = Math.min(3, total);
    var queue = pending.slice();
    _batchProgress = {completed:0, total:total, speed:'-', eta:'-', cancelled:false};
    notify();

    var workers = [];
    for(var w=0; w<concurrency; w++){
      workers.push((async function worker(){
        while(queue.length > 0){
          if(_batchAbortController.signal.aborted) break;
          var img = queue.shift();
          if(!img) break;
          await processSingle(img);
          if(_batchAbortController.signal.aborted) break;
          completed++;
          var elapsed = (Date.now() - startTime) / 1000;
          var speed = (elapsed / completed).toFixed(1);
          var remaining = total - completed;
          var eta = remaining > 0 ? Math.round(remaining * elapsed / completed) : 0;
          _batchProgress = {completed:completed, total:total, speed:speed+'s/img', eta:eta+'s', cancelled:false};
          notify();
        }
      })());
    }
    await Promise.all(workers);
    if(_batchAbortController && _batchAbortController.signal.aborted){
      _batchProgress = {completed:completed, total:total, speed:'-', eta:'-', cancelled:true};
    } else {
      _batchProgress = null;
      toast('批处理完成，共处理 ' + total + ' 张图片', 'ok');
    }
    _batchAbortController = null;
    notify();
  };

  var handleDownloadAll = function(){
    var done = images.filter(i => i.status==='done' && i.resultBlob);
    dlMultiple(done, '_remove', _exportFormat, 'removed_images.zip');
  };

  var handleDownloadSelected = function(){
    var done = images.filter(i => sel.has(i.id) && i.status==='done' && i.resultBlob);
    dlMultiple(done, '_remove', _exportFormat, 'removed_images.zip');
  };

  var handleDeleteSelected = function(){
    var ids = Array.from(sel);
    ids.forEach(id => rmImg(id));
  };

  // 操作栏按钮
  var actionBtns = null;
  if(images.length === 0){
    actionBtns = <Btn variant="primary" size="sm" theme="purple" disabled={true}><Scissors/>等待上传图片</Btn>;
  } else if(selCount > 1){
    actionBtns = <>
      <Btn variant="primary" size="sm" theme="purple" onClick={handleProcessSelected} disabled={processing} loading={processing}><Scissors/>抠图选中 ({selCount})</Btn>
      <Btn variant="ghost" size="sm" theme="purple" onClick={handleDownloadSelected} disabled={processing}><Download/>下载选中</Btn>
      {processing && <button onClick={function(){if(_batchAbortController) _batchAbortController.abort(); _batchCancelled = true; toast('已取消批处理', 'info');}} className="px-3 py-1.5 text-sm font-medium rounded-lg transition-all flex items-center gap-1.5 bg-red-500 hover:bg-red-600 text-white"><X/>取消</button>}
    </>;
  } else if(activeImg){
    actionBtns = <>
      <Btn variant="primary" size="sm" theme="purple" onClick={() => processSingle(activeImg)} disabled={processing} loading={processing}><Scissors/>{activeImg.status==='done'?'重新抠图':'一键抠图'}</Btn>
      {activeImg.status==='done' && <Btn variant="ghost" size="sm" theme="purple" onClick={() => dlOne(activeImg, '_remove', _exportFormat)} disabled={processing}><Download/>下载 PNG</Btn>}
      {processing && <button onClick={function(){if(_batchAbortController) _batchAbortController.abort(); _batchCancelled = true; toast('已取消批处理', 'info');}} className="px-3 py-1.5 text-sm font-medium rounded-lg transition-all flex items-center gap-1.5 bg-red-500 hover:bg-red-600 text-white"><X/>取消</button>}
    </>;
  } else {
    actionBtns = <>
      <Btn variant="primary" size="sm" theme="purple" onClick={handleProcessAll} disabled={processing||!images.length} loading={processing}><Scissors/>批量抠图全部 ({images.length})</Btn>
      {processing && <button onClick={function(){if(_batchAbortController) _batchAbortController.abort(); _batchCancelled = true; toast('已取消批处理', 'info');}} className="px-3 py-1.5 text-sm font-medium rounded-lg transition-all flex items-center gap-1.5 bg-red-500 hover:bg-red-600 text-white"><X/>取消</button>}
    </>;
  }

  // 视图切换按钮
  var viewBtns = null;
  if(activeImg && activeImg.status==='done'){
    viewBtns = <>
      <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-0.5">
        <button onClick={() => {setViewMode('original'); setEditMode('none');}} className={'px-2.5 py-1 rounded-md text-xs font-medium transition-all '+(viewMode==='original'?'bg-white text-gray-800 shadow-sm':'text-gray-500')}>原图</button>
        <button onClick={() => {setViewMode('result'); setEditMode('none');}} className={'px-2.5 py-1 rounded-md text-xs font-medium transition-all '+(viewMode==='result'?'bg-white text-gray-800 shadow-sm':'text-gray-500')}>抠图</button>
        <button onClick={() => {setViewMode('compare'); setEditMode('none');}} className={'px-2.5 py-1 rounded-md text-xs font-medium transition-all '+(viewMode==='compare'?'bg-white text-gray-800 shadow-sm':'text-gray-500')}>对比</button>
      </div>
      {viewMode==='result' && <button onClick={() => setEditMode(editMode==='none'?'erase':'none')} className={'px-2.5 py-1 rounded-lg text-xs font-medium border transition-all '+(editMode!=='none'?'bg-orange-50 border-orange-300 text-orange-600':'border-gray-200 text-gray-500 hover:bg-orange-50 hover:text-orange-500 hover:border-orange-300')}>手动编辑</button>}
    </>;
  }

  return <div className="flex flex-col h-screen">
    <div className="flex items-center h-12 px-5 bg-white border-b border-gray-100 flex-shrink-0">
      <a href="../../" className="flex items-center gap-1 text-sm text-gray-400 hover:text-purple-500 transition-colors mr-4 no-underline">← 工具箱</a>
      <div className="flex items-center gap-2.5">
        <div className="w-6 h-6 rounded bg-purple-500 flex items-center justify-center text-white"><Scissors/></div>
        <span className="text-base font-semibold text-gray-700">智能抠图</span>
        <span className="text-xs px-2 py-0.5 rounded-full bg-purple-50 text-purple-500 font-medium cursor-pointer select-none" onClick={function(){
          _devModeClicks = (_devModeClicks || 0) + 1;
          if(_devModeClicks >= 3){_devMode = !_devMode; _devModeClicks = 0; notify();}
          clearTimeout(_devModeTimer);
          _devModeTimer = setTimeout(function(){_devModeClicks = 0}, 1000);
        }} title="三击切换开发者模式">AI</span>
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-400 font-medium">V3.0</span>
      </div>
    </div>

    <div ref={containerRef} className="flex flex-1 overflow-hidden">
      {/* 左侧图片列表 */}
      <div className="flex flex-col bg-white border-r border-gray-100 flex-shrink-0" style={{width:sidebarW}}>
        <div className="flex items-center justify-between px-3 py-2.5 border-b border-gray-50">
          <div className="flex items-center gap-1.5">
            <span className="text-sm font-medium text-gray-700">图片列表</span>
            <span className="text-[11px] px-1.5 py-0.5 rounded bg-purple-50 text-purple-500 font-medium">{images.length}</span>
          </div>
          {images.length>0 && <button onClick={clearAll} className="text-xs text-gray-400 hover:text-red-400 transition-colors flex items-center gap-0.5"><Trash/>清空</button>}
        </div>

        {images.length>0 && <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-50">
          <button onClick={selCount===images.length ? deselAll : selAll} className="text-xs text-purple-500 hover:text-purple-700 font-medium">{selCount===images.length ? '取消全选' : '全选'}</button>
          {selCount>0 && <span className="text-xs text-gray-400">已选 {selCount}/{images.length}</span>}
          {selCount>0 && <div className="flex-1"/>}
          {selCount>0 && <button onClick={handleDeleteSelected} className="text-xs text-red-400 hover:text-red-600">删除选中</button>}
        </div>}

        <div className="flex-1 overflow-y-auto p-1.5 space-y-0.5">
          {images.length===0 ? <div className="p-1.5"><UploadZone theme="purple" onFiles={addImages}/></div> : images.map(img => <ImageCard key={img.id} image={img} isActive={img.id===activeId} isSel={sel.has(img.id)}/>)}
        </div>

        {images.length>0 && <div className="p-2 border-t border-gray-50"><UploadZone theme="purple" onFiles={addImages} isButton={true}/></div>}
      </div>

      <Divider theme="purple" onDrag={handleSidebarDrag}/>

      {/* 右侧主面板 */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <div className="px-4 py-3 bg-white border-b border-gray-100 flex-shrink-0">
          <div className="flex items-center gap-2">
            {actionBtns}
            {doneCount>1 && <Btn variant="ghost" size="sm" theme="purple" onClick={handleDownloadAll} disabled={processing}><Download/>下载全部 ({doneCount})</Btn>}
            <div className="flex-1"/>
            {images.some(function(i){return i.status==='error'}) && <Btn variant="ghost" size="sm" theme="purple" onClick={function(){
              var failed = images.filter(function(i){return i.status==='error'});
              failed.forEach(function(img){processSingle(img)});
            }}><Refresh/>重试失败 ({images.filter(function(i){return i.status==='error'}).length})</Btn>}
            <div className="flex items-center gap-0.5 bg-gray-100 rounded-lg p-0.5">
              <button onClick={function(){_exportFormat='png'; notify()}} className={'px-2 py-1 rounded-md text-xs font-medium transition-all '+(_exportFormat==='png'?'bg-white text-gray-800 shadow-sm':'text-gray-500')}>PNG</button>
              <button onClick={function(){_exportFormat='webp'; notify()}} className={'px-2 py-1 rounded-md text-xs font-medium transition-all '+(_exportFormat==='webp'?'bg-white text-gray-800 shadow-sm':'text-gray-500')}>WebP</button>
            </div>
            {viewBtns}
          </div>
        </div>

        <div className="flex-1 flex items-center justify-center p-4 overflow-hidden bg-gray-100">
          <PreviewPanel activeImg={activeImg} viewMode={viewMode} setViewMode={setViewMode} sliderPos={sliderPos} setSliderPos={setSliderPos} sliderDragging={sliderDragging} handleSliderMove={handleSliderMove} zoom={zoom} setZoom={setZoom} pan={pan} setPan={setPan} handleWheel={handleWheel} handlePanDown={handlePanDown} handlePanMove={handlePanMove} handlePanUp={handlePanUp} handleZoomReset={handleZoomReset} editMode={editMode} brushSize={brushSize} onEditAction={handleEditAction}/>
        </div>

        <div className="flex items-center justify-between px-4 py-2 bg-white border-t border-gray-100 flex-shrink-0">
          <div className="flex items-center gap-3 text-xs text-gray-400">
            {_batchProgress ? (
              _batchProgress.cancelled ? (
                <span className="text-orange-500 font-medium">已取消 (已完成 {_batchProgress.completed}/{_batchProgress.total})</span>
              ) : (
                <span className="text-purple-600 font-medium">处理中 {_batchProgress.completed}/{_batchProgress.total} | {_batchProgress.speed} | 预计剩余 {_batchProgress.eta}</span>
              )
            ) : (
              <>
                <span>{images.length} 张图片</span>
                {doneCount>0 && <span className="text-green-500">{doneCount} 张完成</span>}
                {images.some(function(i){return i.status==='error'}) && <span className="text-red-400">{images.filter(function(i){return i.status==='error'}).length} 张失败</span>}
                {selCount>0 && <span className="text-purple-500">已选 {selCount}</span>}
              </>
            )}
          </div>
          <div className="flex items-center gap-1 text-xs text-gray-400"><div className="w-1.5 h-1.5 rounded-full bg-green-400"/>就绪</div>
        </div>
      </div>
    </div>
  </div>;
}

ReactDOM.createRoot(document.getElementById('root')).render(<App/>);
