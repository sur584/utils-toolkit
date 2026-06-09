import { useState, useEffect, useRef, useCallback } from 'react';
import ReactDOM from 'react-dom/client';
import { fmt, uid, isImg, resizeFile } from '../shared/utils.js';
import { Upload, Download, X, Trash, Check, Alert, Refresh } from '../shared/icons.jsx';
import { ZoomControls, Btn, UploadZone, Divider } from '../shared/components.jsx';
import { useZoomPan } from '../shared/hooks.js';
import { downloadOne as dlOne, downloadMultiple as dlMultiple } from '../shared/download.js';

// ==================== 全局状态管理 ====================
let _images = [], _ls = new Set(), _sel = new Set(), _activeId = null, _exportFormat = 'png', _inpaintMethod = 'telea', _dilateSize = 5, _dilateIter = 2, _expand = 3, _batchProgress = null;
const sub = fn => {_ls.add(fn); return () => _ls.delete(fn)};
const notify = () => _ls.forEach(fn => fn());

const addImages = files => {
  const v = Array.from(files).filter(isImg);
  if(!v.length) return;
  const n = v.map(f => ({id:uid(), file:f, name:f.name, size:f.size, thumb:URL.createObjectURL(f), status:'idle', resultBlob:null, resultUrl:null, error:null, textCount:null, processingTime:null}));
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
  return {images:_images, sel:_sel, activeId:_activeId, exportFormat:_exportFormat, inpaintMethod:_inpaintMethod, dilateSize:_dilateSize, dilateIter:_dilateIter, expand:_expand, batchProgress:_batchProgress};
};

// ==================== 工具专属图标 ====================
const I = {
  text:()=><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="4 7 4 4 20 4 20 7"/><line x1="9" y1="20" x2="15" y2="20"/><line x1="12" y1="4" x2="12" y2="20"/></svg>,
  settings:()=><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>,
};

// ==================== 空状态 ====================
function TextRemoverEmptyState(){
  return <div className="flex-1 flex items-center justify-center h-full animate-fade-up">
    <div className="text-center max-w-sm">
      <div className="w-20 h-20 rounded-2xl bg-rose-50 flex items-center justify-center mx-auto mb-5 text-rose-500"><I.text/></div>
      <h2 className="text-xl font-semibold text-gray-800 mb-2">拖入图片开始去文字</h2>
      <p className="text-sm text-gray-400 mb-5">AI 自动识别图片中的文字并智能去除，还原干净背景</p>
      <div className="flex items-center justify-center gap-5 mb-5 text-xs text-gray-400">
        <span className="flex items-center gap-1.5"><Upload/>拖拽</span>
        <span className="flex items-center gap-1.5">Ctrl+V</span>
        <span className="flex items-center gap-1.5">选择文件</span>
      </div>
      <UploadZone theme="rose" isButton={true} onFiles={addImages}/>
    </div>
  </div>;
}

// ==================== 图片卡片 ====================
function ImageCard({image, isActive, isSel}){
  var statusNode = null;
  if(image.status === 'processing') statusNode = <span className="w-3.5 h-3.5 border-2 border-rose-400 border-t-transparent rounded-full animate-spin"/>;
  else if(image.status === 'done') statusNode = <span className="text-green-500"><Check/></span>;
  else if(image.status === 'error') statusNode = <span className="text-red-400"><X/></span>;

  var statusText = null;
  if(image.status === 'processing') statusText = <span className="text-xs text-rose-500">{image.statusText || '处理中'}</span>;
  else if(image.status === 'done') statusText = <span className="text-xs text-green-500">{image.textCount || 0} 处文字 · 完成</span>;
  else if(image.status === 'error') statusText = <span className="text-xs text-red-400">失败</span>;

  var activeCls = isActive ? 'bg-rose-50 border border-rose-200' : 'hover:bg-gray-50 border border-transparent';
  var selCls = isSel ? 'bg-rose-500 border-rose-500' : 'border-gray-300 hover:border-rose-400';

  return <div className={'flex items-center gap-2 p-2 rounded-lg transition-colors group animate-fade-up cursor-pointer '+activeCls} onClick={() => setActiveId(image.id)}>
    <div className={'sel-cb w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0 cursor-pointer transition-all '+selCls} onClick={e => {e.stopPropagation(); toggleSel(image.id)}}>
      {isSel && <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg>}
    </div>
    <div className="w-10 h-10 rounded-lg overflow-hidden bg-gray-100 flex-shrink-0 relative">
      <img src={image.thumb} alt="" className="w-full h-full object-cover"/>
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
      {image.status==='done' && <button onClick={e => {e.stopPropagation(); dlOne(image, '_no_text', _exportFormat)}} className="p-1 rounded hover:bg-rose-50 text-gray-400 hover:text-rose-500 transition-all" title="下载"><Download/></button>}
      {image.status==='error' && <button onClick={e => {e.stopPropagation(); processSingle(image)}} className="p-1 rounded hover:bg-rose-50 text-gray-400 hover:text-rose-500 transition-all" title="重试"><Refresh/></button>}
      <button onClick={e => {e.stopPropagation(); rmImg(image.id)}} className="p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-400 transition-all" title="删除"><X/></button>
    </div>
  </div>;
}

// ==================== 处理逻辑 ====================
async function processSingle(img, retryCount){
  retryCount = retryCount || 0;
  upd(img.id, {status:'processing', statusText:'检测文字中...', error:null});
  try {
    var uploadFile = await resizeFile(img.file, 2048);
    upd(img.id, {statusText:'去除文字中...'});
    var formData = new FormData();
    formData.append('file', uploadFile, img.file.name);
    formData.append('method', _inpaintMethod);
    formData.append('dilate_size', _dilateSize);
    formData.append('dilate_iter', _dilateIter);
    formData.append('expand', _expand);
    formData.append('format', _exportFormat);
    var resp = await fetch('/api/text-remove', {method:'POST', body:formData});
    if(!resp.ok){
      var err = await resp.json().catch(function(){return {}});
      throw new Error(err.detail || ('HTTP ' + resp.status));
    }
    var blob = await resp.blob();
    var url = URL.createObjectURL(blob);
    var textCount = resp.headers.get('X-Text-Count') || '0';
    var processingTime = resp.headers.get('X-Processing-Time-Ms') || null;
    upd(img.id, {status:'done', statusText:null, resultBlob:blob, resultUrl:url, textCount:parseInt(textCount), processingTime:processingTime});
  } catch(e) {
    if(retryCount < 2){
      upd(img.id, {statusText:'重试中 (' + (retryCount+1) + '/2)...'});
      return processSingle(img, retryCount + 1);
    }
    upd(img.id, {status:'error', statusText:null, error:e.message});
  }
}

function doDownloadOne(img){
  dlOne(img, '_no_text', _exportFormat);
}

function doDownloadMultiple(imgs){
  dlMultiple(imgs, '_no_text', _exportFormat, 'text_removed.zip');
}

// ==================== 预览面板 ====================
function PreviewPanel({activeImg, viewMode, setViewMode, sliderPos, setSliderPos, sliderDragging, handleSliderMove, zoom, setZoom, pan, setPan, panDragging, handleWheel, handlePanDown, handlePanMove, handlePanUp, handleZoomReset}){
  if(!activeImg) return <TextRemoverEmptyState/>;

  // 处理中
  if(activeImg.status === 'processing'){
    return <div className="text-center">
      <div className="w-16 h-16 rounded-2xl bg-rose-50 flex items-center justify-center mx-auto mb-4"><span className="w-8 h-8 border-2 border-rose-400 border-t-transparent rounded-full animate-spin"/></div>
      <p className="text-sm text-gray-500 mb-1">{activeImg.statusText || '正在去除文字，请稍后'}</p>
    </div>;
  }

  // 处理失败
  if(activeImg.status === 'error'){
    var errText = activeImg.error || '未知错误';
    var tipText = '';
    if(errText.indexOf('未检测到文字') >= 0) tipText = '图片中未识别到文字，请确认图片包含可见文字';
    else if(errText.indexOf('无法识别') >= 0 || errText.indexOf('格式') >= 0) tipText = '请确认文件是图片格式（JPG/PNG/WebP/BMP）';
    else if(errText.indexOf('OCR') >= 0 || errText.indexOf('paddle') >= 0) tipText = 'OCR 模型加载失败，请重启服务后重试';
    else tipText = '支持 JPG、PNG、WebP、BMP 格式，建议尺寸不超过 4096px';

    return <div className="text-center max-w-sm">
      <div className="w-16 h-16 rounded-2xl bg-red-50 flex items-center justify-center mx-auto mb-4 text-red-400"><Alert/></div>
      <p className="text-sm text-red-500 mb-2">处理失败</p>
      <div className="bg-red-50 border border-red-100 rounded-lg px-3 py-2 mb-2 text-left">
        <p className="text-xs text-red-600 break-all leading-relaxed">{errText}</p>
      </div>
      <p className="text-xs text-gray-400 mb-3">{tipText}</p>
      <Btn variant="ghost" size="sm" theme="rose" onClick={() => processSingle(activeImg)}><Refresh/>重试</Btn>
    </div>;
  }

  // 对比模式
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
      <div className="absolute bottom-3 right-3 px-2 py-1 rounded bg-rose-500/80 text-white text-xs">去文字结果</div>
    </div>;
  }

  var imgUrl = activeImg.resultUrl || activeImg.thumb;
  var imgStyle = {
    transform: 'scale('+zoom+') translate('+pan.x+'px,'+pan.y+'px)',
    transformOrigin: 'center center',
    transition: panDragging.current ? 'none' : 'transform 0.15s ease-out',
    maxWidth: '100%',
    maxHeight: '100%',
    objectFit: 'contain',
    cursor: zoom > 1 ? (panDragging.current ? 'grabbing' : 'grab') : 'zoom-in',
  };
  var checkerCls = activeImg.resultUrl ? ' checkerboard' : '';

  if(activeImg.resultUrl){
    return <div className="relative w-full h-full flex flex-col items-center justify-center overflow-hidden rounded-xl">
      <div className={'flex-1 flex items-center justify-center w-full overflow-hidden p-4'+checkerCls}
        onWheel={handleWheel}
        onMouseDown={handlePanDown}
        onMouseMove={handlePanMove}
        onMouseUp={handlePanUp}
        onMouseLeave={handlePanUp}>
        <img src={activeImg.resultUrl} alt="" style={imgStyle} draggable={false}/>
      </div>
      <ZoomControls zoom={zoom} setZoom={setZoom} handleZoomReset={handleZoomReset}/>
      <button onClick={() => doDownloadOne(activeImg)} className="absolute top-3 right-3 px-3 py-1.5 rounded-lg bg-rose-500 text-white text-xs font-medium hover:bg-rose-600 shadow-lg flex items-center gap-1.5 z-10 transition-all"><Download/>下载结果</button>
      {activeImg.processingTime && <div className="absolute top-3 left-3 px-2 py-1 rounded bg-black/50 text-white text-[11px] z-10">耗时 {activeImg.processingTime}ms</div>}
    </div>;
  }

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

// ==================== 设置面板 ====================
function SettingsPanel({show, onClose}){
  if(!show) return null;
  return <div className="absolute top-12 right-4 z-30 bg-white rounded-xl shadow-xl border border-gray-100 p-4 w-72 animate-fade-up">
    <div className="flex items-center justify-between mb-3">
      <span className="text-sm font-semibold text-gray-700">修复设置</span>
      <button onClick={onClose} className="p-1 rounded hover:bg-gray-100 text-gray-400"><X/></button>
    </div>
    <div className="space-y-3">
      <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-rose-50 border border-rose-100">
        <span className="text-rose-500 text-sm font-bold">LaMa</span>
        <span className="text-[11px] text-rose-600">深度学习修复引擎</span>
      </div>
      <div>
        <label className="text-xs text-gray-500 font-medium mb-1 block">文字外扩: {_expand}px</label>
        <input type="range" min="0" max="10" value={_expand} onChange={e => {_expand=parseInt(e.target.value); notify()}} className="w-full h-1.5 accent-rose-500"/>
      </div>
      <div>
        <label className="text-xs text-gray-500 font-medium mb-1 block">遮罩膨胀: {_dilateSize}px x {_dilateIter}次</label>
        <input type="range" min="1" max="15" value={_dilateSize} onChange={e => {_dilateSize=parseInt(e.target.value); notify()}} className="w-full h-1.5 accent-rose-500"/>
      </div>
      <div className="pt-1 text-[11px] text-gray-400 leading-relaxed">
        LaMa 是基于深度学习的图像修复模型，能理解图像语义，修复复杂背景效果远优于传统算法。
      </div>
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
  var { zoom, setZoom, pan, setPan, panDragging, handleWheel, handlePanDown, handlePanMove, handlePanUp, handleZoomReset } = useZoomPan();
  var [showSettings, setShowSettings] = useState(false);

  useEffect(function(){ handleZoomReset(); }, [activeId]);

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
    var total = pending.length;
    var completed = 0;
    var startTime = Date.now();
    var concurrency = Math.min(3, total);
    var queue = pending.slice();
    _batchProgress = {completed:0, total:total, speed:'-', eta:'-'};
    notify();

    var workers = [];
    for(var w=0; w<concurrency; w++){
      workers.push((async function worker(){
        while(queue.length > 0){
          var img = queue.shift();
          if(!img) break;
          await processSingle(img);
          completed++;
          var elapsed = (Date.now() - startTime) / 1000;
          var speed = (elapsed / completed).toFixed(1);
          var remaining = total - completed;
          var eta = remaining > 0 ? Math.round(remaining * elapsed / completed) : 0;
          _batchProgress = {completed:completed, total:total, speed:speed+'s/img', eta:eta+'s'};
          notify();
        }
      })());
    }
    await Promise.all(workers);
    _batchProgress = null;
    notify();
  };

  var handleDownloadAll = function(){
    var done = images.filter(i => i.status==='done' && i.resultBlob);
    doDownloadMultiple(done);
  };

  var handleDownloadSelected = function(){
    var done = images.filter(i => sel.has(i.id) && i.status==='done' && i.resultBlob);
    doDownloadMultiple(done);
  };

  var handleDeleteSelected = function(){
    var ids = Array.from(sel);
    ids.forEach(id => rmImg(id));
  };

  var actionBtns = null;
  if(images.length === 0){
    actionBtns = <Btn variant="primary" size="sm" theme="rose" disabled={true}><I.text/>等待上传图片</Btn>;
  } else if(selCount > 1){
    actionBtns = <>
      <Btn variant="primary" size="sm" theme="rose" onClick={handleProcessSelected} disabled={processing} loading={processing}><I.text/>去文字选中 ({selCount})</Btn>
      <Btn variant="ghost" size="sm" onClick={handleDownloadSelected} disabled={processing}><Download/>下载选中</Btn>
    </>;
  } else if(activeImg){
    actionBtns = <>
      <Btn variant="primary" size="sm" theme="rose" onClick={() => processSingle(activeImg)} disabled={processing} loading={processing}><I.text/>{activeImg.status==='done'?'重新处理':'一键去文字'}</Btn>
      {activeImg.status==='done' && <Btn variant="ghost" size="sm" onClick={() => doDownloadOne(activeImg)} disabled={processing}><Download/>下载结果</Btn>}
    </>;
  } else {
    actionBtns = <Btn variant="primary" size="sm" theme="rose" onClick={handleProcessAll} disabled={processing||!images.length} loading={processing}><I.text/>批量去文字 ({images.length})</Btn>;
  }

  var viewBtns = null;
  if(activeImg && activeImg.status==='done'){
    viewBtns = <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-0.5">
      <button onClick={() => setViewMode('original')} className={'px-2.5 py-1 rounded-md text-xs font-medium transition-all '+(viewMode==='original'?'bg-white text-gray-800 shadow-sm':'text-gray-500')}>原图</button>
      <button onClick={() => setViewMode('result')} className={'px-2.5 py-1 rounded-md text-xs font-medium transition-all '+(viewMode==='result'?'bg-white text-gray-800 shadow-sm':'text-gray-500')}>结果</button>
      <button onClick={() => setViewMode('compare')} className={'px-2.5 py-1 rounded-md text-xs font-medium transition-all '+(viewMode==='compare'?'bg-white text-gray-800 shadow-sm':'text-gray-500')}>对比</button>
    </div>;
  }

  return <div className="flex flex-col h-screen">
    <div className="flex items-center h-12 px-5 bg-white border-b border-gray-100 flex-shrink-0">
      <a href="../../" className="flex items-center gap-1 text-sm text-gray-400 hover:text-rose-500 transition-colors mr-4 no-underline">← 工具箱</a>
      <div className="flex items-center gap-2.5">
        <div className="w-6 h-6 rounded bg-rose-500 flex items-center justify-center text-white"><I.text/></div>
        <span className="text-base font-semibold text-gray-700">智能去文字</span>
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-400 font-medium">AI</span>
      </div>
    </div>

    <div ref={containerRef} className="flex flex-1 overflow-hidden">
      {/* 左侧图片列表 */}
      <div className="flex flex-col bg-white border-r border-gray-100 flex-shrink-0" style={{width:sidebarW}}>
        <div className="flex items-center justify-between px-3 py-2.5 border-b border-gray-50">
          <div className="flex items-center gap-1.5">
            <span className="text-sm font-medium text-gray-700">图片列表</span>
            <span className="text-[11px] px-1.5 py-0.5 rounded bg-rose-50 text-rose-500 font-medium">{images.length}</span>
          </div>
          {images.length>0 && <button onClick={clearAll} className="text-xs text-gray-400 hover:text-red-400 transition-colors flex items-center gap-0.5"><Trash/>清空</button>}
        </div>

        {images.length>0 && <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-50">
          <button onClick={selCount===images.length ? deselAll : selAll} className="text-xs text-rose-500 hover:text-rose-700 font-medium">{selCount===images.length ? '取消全选' : '全选'}</button>
          {selCount>0 && <span className="text-xs text-gray-400">已选 {selCount}/{images.length}</span>}
          {selCount>0 && <div className="flex-1"/>}
          {selCount>0 && <button onClick={handleDeleteSelected} className="text-xs text-red-400 hover:text-red-600">删除选中</button>}
        </div>}

        <div className="flex-1 overflow-y-auto p-1.5 space-y-0.5">
          {images.length===0 ? <div className="p-1.5"><UploadZone theme="rose" onFiles={addImages}/></div> : images.map(img => <ImageCard key={img.id} image={img} isActive={img.id===activeId} isSel={sel.has(img.id)}/>)}
        </div>

        {images.length>0 && <div className="p-2 border-t border-gray-50"><UploadZone theme="rose" isButton={true} onFiles={addImages}/></div>}
      </div>

      <Divider theme="rose" onDrag={handleSidebarDrag}/>

      {/* 右侧主面板 */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <div className="px-4 py-3 bg-white border-b border-gray-100 flex-shrink-0 relative">
          <div className="flex items-center gap-2">
            {actionBtns}
            {doneCount>1 && <Btn variant="ghost" size="sm" onClick={handleDownloadAll} disabled={processing}><Download/>下载全部 ({doneCount})</Btn>}
            <div className="flex-1"/>
            {images.some(function(i){return i.status==='error'}) && <Btn variant="ghost" size="sm" onClick={function(){
              var failed = images.filter(function(i){return i.status==='error'});
              failed.forEach(function(img){processSingle(img)});
            }}><Refresh/>重试失败 ({images.filter(function(i){return i.status==='error'}).length})</Btn>}
            <div className="flex items-center gap-0.5 bg-gray-100 rounded-lg p-0.5">
              <button onClick={function(){_exportFormat='png'; notify()}} className={'px-2 py-1 rounded-md text-xs font-medium transition-all '+(_exportFormat==='png'?'bg-white text-gray-800 shadow-sm':'text-gray-500')}>PNG</button>
              <button onClick={function(){_exportFormat='webp'; notify()}} className={'px-2 py-1 rounded-md text-xs font-medium transition-all '+(_exportFormat==='webp'?'bg-white text-gray-800 shadow-sm':'text-gray-500')}>WebP</button>
            </div>
            <button onClick={() => setShowSettings(!showSettings)} className={'p-1.5 rounded-lg border transition-all '+(showSettings?'bg-rose-50 border-rose-200 text-rose-500':'border-gray-200 text-gray-400 hover:bg-gray-50 hover:text-gray-600')} title="修复设置"><I.settings/></button>
            {viewBtns}
          </div>
          <SettingsPanel show={showSettings} onClose={() => setShowSettings(false)}/>
        </div>

        <div className="flex-1 flex items-center justify-center p-4 overflow-hidden bg-gray-100">
          <PreviewPanel activeImg={activeImg} viewMode={viewMode} setViewMode={setViewMode} sliderPos={sliderPos} setSliderPos={setSliderPos} sliderDragging={sliderDragging} handleSliderMove={handleSliderMove} zoom={zoom} setZoom={setZoom} pan={pan} setPan={setPan} panDragging={panDragging} handleWheel={handleWheel} handlePanDown={handlePanDown} handlePanMove={handlePanMove} handlePanUp={handlePanUp} handleZoomReset={handleZoomReset}/>
        </div>

        <div className="flex items-center justify-between px-4 py-2 bg-white border-t border-gray-100 flex-shrink-0">
          <div className="flex items-center gap-3 text-xs text-gray-400">
            {_batchProgress ? (
              <span className="text-rose-600 font-medium">处理中 {_batchProgress.completed}/{_batchProgress.total} | {_batchProgress.speed} | 预计剩余 {_batchProgress.eta}</span>
            ) : (
              <>
                <span>{images.length} 张图片</span>
                {doneCount>0 && <span className="text-green-500">{doneCount} 张完成</span>}
                {images.some(function(i){return i.status==='error'}) && <span className="text-red-400">{images.filter(function(i){return i.status==='error'}).length} 张失败</span>}
                {selCount>0 && <span className="text-rose-500">已选 {selCount}</span>}
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
