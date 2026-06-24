import { useState, useEffect, useRef, useCallback } from 'react';
import ReactDOM from 'react-dom/client';
import { fmt, ext, isImg, uid, showToast } from '../shared/utils.js';
import { Upload, Download, X, Trash, Plus, Refresh } from '../shared/icons.jsx';
import { Btn, UploadZone, Divider } from '../shared/components.jsx';

// ==================== 全局状态管理（简易 Store） ====================
let _images=[],_ls=new Set(),_tab='compress',_sel=new Set(),_preview=null,_previewImg=null,_cropResults=null;
const sub=fn=>{_ls.add(fn);return()=>_ls.delete(fn)};
const notify=()=>_ls.forEach(fn=>fn());
const addImages=files=>{
  const v=Array.from(files).filter(isImg);if(!v.length)return;
  const n=v.map(f=>({id:uid(),file:f,origFile:f,origUrl:URL.createObjectURL(f),name:f.name,size:f.size,origSize:f.size,type:f.type,w:0,h:0,thumb:URL.createObjectURL(f),status:'idle',blob:null,cSize:null,cUrl:null,progress:0}));
  n.forEach(img=>{const t=new Image();t.onload=()=>{img.w=t.naturalWidth;img.h=t.naturalHeight;URL.revokeObjectURL(t.src);notify()};t.src=URL.createObjectURL(img.file)});
  _images=[..._images,...n];notify();
};
const rmImg=id=>{const i=_images.find(x=>x.id===id);if(i){URL.revokeObjectURL(i.thumb);if(i.cUrl)URL.revokeObjectURL(i.cUrl)}_images=_images.filter(x=>x.id!==id);_sel.delete(id);notify()};
const clearAll=()=>{_images.forEach(i=>{URL.revokeObjectURL(i.thumb);if(i.cUrl)URL.revokeObjectURL(i.cUrl)});_images=[];_sel.clear();notify()};
const upd=(id,u)=>{_images=_images.map(i=>i.id===id?{...i,...u}:i);notify()};
const curFile=img=>img.blob||img.file;
const processedFile=(blob,name)=>new File([blob],name,{type:blob.type||'image/png'});
const toggleSel=id=>{_sel.has(id)?_sel.delete(id):_sel.add(id);notify()};
const selAll=()=>{_images.forEach(i=>_sel.add(i.id));notify()};
const deselAll=()=>{_sel.clear();notify()};
const setPreview=v=>{_preview=v;notify()};
const setPreviewImg=v=>{_previewImg=v;notify()};
const setCropResults=v=>{_cropResults=v;notify()};
const useStore=()=>{const[,t]=useState(0);useEffect(()=>{const u=sub(()=>t(x=>x+1));return u},[]);return{images:_images,tab:_tab,sel:_sel,preview:_preview,previewImg:_previewImg,cropResults:_cropResults,setPreviewImg}};

// Tool-specific icons (not in shared/icons.jsx)
const I={
  image:()=><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect width="18" height="18" x="3" y="3" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/></svg>,
  zap:()=><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>,
  scissors:()=><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="6" cy="6" r="3"/><path d="M8.12 8.12 12 12"/><path d="M20 4 8.12 15.88"/><circle cx="6" cy="18" r="3"/><path d="M14.8 14.8 20 20"/></svg>,
  arrow:()=><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>,
  crop:()=><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M6.13 1L6 16a2 2 0 0 0 2 2h15"/><path d="M1 6.13L16 6a2 2 0 0 1 2 2v15"/></svg>,
  folder:()=><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>,
  clipboard:()=><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect width="8" height="4" x="8" y="2" rx="1"/></svg>,
  chevDown:()=><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="6 9 12 15 18 9"/></svg>,
  trending:()=><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/></svg>,
  circle:()=><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/></svg>,
  square:()=><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2"/></svg>,
  roundedRect:()=><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="6"/></svg>,
  eye:()=><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>,
  droplet:()=><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 22a7 7 0 0 0 7-7c0-2-1-3.9-3-5.5s-3.5-4-4-6.5c-.5 2.5-2 4.9-4 6.5C6 11.1 5 13 5 15a7 7 0 0 0 7 7z"/></svg>,
  sparkle:()=><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3l1.912 5.813a2 2 0 0 0 1.275 1.275L21 12l-5.813 1.912a2 2 0 0 0-1.275 1.275L12 21l-1.912-5.813a2 2 0 0 0-1.275-1.275L3 12l5.813-1.912a2 2 0 0 0 1.275-1.275L12 3z"/></svg>,
  tag:()=><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20.59 13.41 11 3H4v7l9.59 9.59a2 2 0 0 0 2.82 0l4.18-4.18a2 2 0 0 0 0-2.82Z"/><circle cx="7.5" cy="7.5" r="1"/></svg>,
};

// ==================== 进度条组件 ====================
function Progress({value=0,label,className=''}){
  const v=Math.min(100,Math.max(0,value));
  return <div className={`w-full ${className}`}>
    {label&&<div className="flex items-center justify-between mb-1"><span className="text-xs text-gray-500">{label}</span><span className="text-xs text-gray-400">{Math.round(v)}%</span></div>}
    <div className="w-full h-1.5 rounded-full bg-gray-100 overflow-hidden"><div className="h-full rounded-full bg-blue-500 transition-all duration-500" style={{width:v+'%'}}/></div>
  </div>;
}

// ==================== 空状态占位 ====================
function EmptyState(){
  return <div className="flex-1 flex items-center justify-center h-full animate-fade-up">
    <div className="text-center max-w-sm">
      <div className="w-20 h-20 rounded-2xl bg-blue-50 flex items-center justify-center mx-auto mb-5 text-blue-500"><I.image/></div>
      <h2 className="text-xl font-semibold text-gray-800 mb-2">拖入图片开始处理</h2>
      <p className="text-sm text-gray-400 mb-5">支持 JPG、PNG、WEBP，可批量处理</p>
      <div className="flex items-center justify-center gap-5 mb-5 text-xs text-gray-400">
        <span className="flex items-center gap-1.5"><Upload/>拖拽</span>
        <span className="flex items-center gap-1.5"><I.clipboard/>Ctrl+V</span>
        <span className="flex items-center gap-1.5"><I.folder/>选择</span>
      </div>
      <UploadZone isButton onFiles={addImages} accept="image/jpeg,image/png,image/webp"/>
    </div>
  </div>;
}

// ==================== 图片卡片（左侧列表） ====================
function ImageCard({image,selected,isActive}){
  const s=image.cSize?((1-image.cSize/(image.origSize||image.size))*100).toFixed(0):null;
  return <div className={`flex items-center gap-2 p-2 rounded-lg transition-colors group animate-fade-up ${isActive?'bg-blue-50 border border-blue-200':'hover:bg-gray-50 border border-transparent'}`}>
    <div onClick={e=>{e.stopPropagation();toggleSel(image.id)}} className={`w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0 cursor-pointer transition-all ${selected?'bg-blue-500 border-blue-500':'border-gray-300 hover:border-blue-400'}`}>
      {selected&&<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg>}
    </div>
    <div onClick={()=>setPreviewImg(image)} className="flex items-center gap-2.5 flex-1 min-w-0 cursor-pointer">
      <div className="w-10 h-10 rounded-lg overflow-hidden bg-gray-100 flex-shrink-0"><img src={image.thumb} alt="" loading="lazy" className="w-full h-full object-cover"/></div>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-gray-800 truncate">{image.name}</p>
        <div className="flex items-center gap-1.5 mt-0.5">
          <span className="text-xs text-gray-400">{fmt(image.size)}</span>
          {s&&<span className="text-xs text-green-500">-{s}%</span>}
        </div>
      </div>
    </div>
    {image.status==='done'&&<span className="text-xs text-green-500">✓</span>}
    {image.status==='error'&&<span className="text-xs text-red-400">✗</span>}
    <button onClick={e=>{e.stopPropagation();rmImg(image.id)}} className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-red-50 text-gray-300 hover:text-red-400 transition-all"><X size={12}/></button>
  </div>;
}

// ==================== 压缩面板 ====================
function CompressPanel(){
  const{images,sel}=useStore();
  const[ts,setTs]=useState(500);const[unit,setUnit]=useState('KB');const[fmt2,setFmt2]=useState('keep');const[proc,setProc]=useState(false);
  const targets=sel.size>0?images.filter(i=>sel.has(i.id)):images;
  const tot=targets.reduce((a,i)=>a+(i.origSize||i.size),0);const comp=targets.reduce((a,i)=>a+(i.cSize||0),0);
  const dn=targets.filter(i=>i.status==='done').length;const sv=comp>0?((1-comp/tot)*100).toFixed(1):0;

  const compressFile=(file,targetBytes,maxW)=>new Promise((resolve,reject)=>{
    const img=new Image();
    img.onload=()=>{
      let w=img.naturalWidth,h=img.naturalHeight;
      if(maxW&&w>maxW){h=Math.round(h*maxW/w);w=maxW}
      const canvas=document.createElement('canvas');
      canvas.width=w;canvas.height=h;
      const ctx=canvas.getContext('2d');
      ctx.drawImage(img,0,0,w,h);
      let lo=0.1,hi=0.95,best=null;
      const outType=fmt2==='png'?'image/png':fmt2==='webp'?'image/webp':'image/jpeg';
      const tryQ=(q)=>{
        canvas.toBlob(b=>{
          if(!b){reject(new Error('canvas toBlob failed'));return}
          if(b.size<=targetBytes||lo>=hi){resolve(b);return}
          if(b.size>targetBytes){hi=q-(hi-lo)/2}else{lo=q+(hi-lo)/2}
          if(hi-lo<0.02){resolve(b);return}
          tryQ((lo+hi)/2);
        },outType,q);
      };
      tryQ(0.76);
    };
    img.onerror=reject;
    img.src=URL.createObjectURL(file);
  });

  const compress=async()=>{
    setProc(true);const tb=unit==='MB'?ts*1024*1024:ts*1024;
    const pending=targets;
    const CONC=3;const results=[];
    let idx=0;
    const worker=async()=>{
      while(idx<pending.length){
        const img=pending[idx++];if(!img)break;
        const input=curFile(img);const inputSize=input.size||img.size;
        const origState={name:img.name,file:img.file,blob:img.blob,thumb:img.thumb,size:img.size,cSize:img.cSize,cUrl:img.cUrl,status:img.status,progress:img.progress};
        upd(img.id,{status:'compressing',progress:30});
        try{
          const sizeRatio=tb/inputSize;
          const maxW=sizeRatio<0.15?1200:sizeRatio<0.3?1920:sizeRatio<0.5?2560:99999;
          const c=await compressFile(input,tb,maxW);
          const url=URL.createObjectURL(c);
          const newFile=processedFile(c,img.name);
          if(img.cUrl)URL.revokeObjectURL(img.cUrl);
          upd(img.id,{name:newFile.name,file:newFile,blob:c,thumb:url,size:c.size,cSize:c.size,cUrl:url,status:'done',progress:100});
          results.push({name:img.name,origUrl:origState.thumb||img.origUrl,resultUrl:url,origSize:inputSize,resultSize:c.size,blob:c,saving:((1-c.size/inputSize)*100).toFixed(0)+'%',imgId:img.id,newFile,newBlob:c,newThumb:url,newCSize:c.size,newCUrl:url,origState});
        }catch(e){upd(img.id,{status:'error'})}
      }
    };
    await Promise.all(Array.from({length:Math.min(CONC,pending.length)},()=>worker()));
    setProc(false);
    if(results.length)setPreview({type:'compress',items:results});
  };
  return <div className="h-full flex flex-col p-4 gap-3 animate-fade-up overflow-hidden">
    <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm flex-shrink-0">
      <div className="flex items-center justify-between mb-3"><p className="text-base font-medium text-gray-700">压缩设置</p>{sel.size>0&&<span className="text-xs text-blue-500">已选 {sel.size} 张</span>}</div>
      <div className="grid grid-cols-2 gap-3">
        <div><label className="text-xs text-gray-500 mb-1 block">目标大小</label><div className="flex items-center gap-1.5"><input type="number" value={ts} onChange={e=>setTs(Number(e.target.value))} className="flex-1 h-9 px-2.5 rounded-lg bg-gray-50 border border-gray-200 text-sm text-gray-800 outline-none focus:border-blue-400 transition-all"/><button onClick={()=>setUnit(u=>u==='KB'?'MB':'KB')} className="h-9 px-2.5 rounded-lg bg-gray-50 border border-gray-200 text-xs text-gray-600 hover:bg-gray-100 transition-colors font-medium min-w-[52px] flex items-center justify-center gap-0.5">{unit}<I.chevDown/></button></div></div>
        <div><label className="text-xs text-gray-500 mb-1 block">输出格式</label><select value={fmt2} onChange={e=>setFmt2(e.target.value)} className="w-full h-9 px-2.5 rounded-lg bg-gray-50 border border-gray-200 text-sm text-gray-600 outline-none cursor-pointer hover:bg-gray-100 transition-colors"><option value="keep">保持原格式</option><option value="jpg">JPG</option><option value="png">PNG</option><option value="webp">WEBP</option></select></div>
      </div>
    </div>
    {dn>0&&<div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm animate-fade-up flex-shrink-0">
      <div className="flex items-center gap-1.5 mb-2.5"><span className="text-green-500"><I.trending/></span><p className="text-base font-medium text-gray-700">压缩统计</p></div>
      <div className="grid grid-cols-3 gap-3"><div><p className="text-xs text-gray-400">原始</p><p className="text-base font-semibold text-gray-800">{fmt(tot)}</p></div><div><p className="text-xs text-gray-400">压缩后</p><p className="text-base font-semibold text-blue-500">{fmt(comp)}</p></div><div><p className="text-xs text-gray-400">节省</p><p className="text-base font-semibold text-green-500">{sv}%</p></div></div>
      <Progress value={dn/targets.length*100} label={`${dn}/${targets.length}`} className="mt-2.5"/>
    </div>}
    <div className="flex-1 min-h-0 overflow-y-auto space-y-1 pr-1">
      <p className="text-xs text-gray-400 mb-1">图片列表 ({targets.length})</p>
      {targets.map((img,i)=><div key={img.id} className="flex items-center gap-2.5 p-2 rounded-lg bg-white border border-gray-100 hover:border-gray-200 transition-all animate-fade-up" style={{animationDelay:`${i*25}ms`}}>
        <div className="w-10 h-10 rounded-lg overflow-hidden bg-gray-100 flex-shrink-0"><img src={img.thumb} alt="" loading="lazy" className="w-full h-full object-cover"/></div>
        <div className="flex-1 min-w-0"><p className="text-sm text-gray-700 truncate">{img.name}</p><div className="flex items-center gap-1.5 mt-0.5"><span className="text-xs text-gray-400">{fmt(img.size)}</span>{img.cSize&&<><span className="text-xs text-gray-300">→</span><span className="text-xs text-blue-500">{fmt(img.cSize)}</span></>}</div></div>
        {img.status==='compressing'&&<Progress value={img.progress||0} className="w-16"/>}
        {img.status==='done'&&<span className="text-xs text-green-500 font-medium">完成</span>}
        {img.status==='error'&&<span className="text-xs text-red-400 font-medium">失败</span>}
      </div>)}
    </div>
    <div className="flex items-center gap-2 pt-1 flex-shrink-0 flex-wrap"><Btn variant="primary" className="flex-1 min-w-0" onClick={compress} disabled={!targets.length||proc} loading={proc}><I.zap/>{sel.size>0?`压缩选中 (${sel.size})`:'开始压缩'}</Btn><Btn variant="ghost" onClick={clearAll} disabled={!images.length}>清空</Btn></div>
  </div>;
}

// ==================== 去水印面板 ====================
function WatermarkPanel(){
  const{images,sel}=useStore();
  const[sensitivity,setSensitivity]=useState('medium');
  const[method,setMethod]=useState('telea');
  const[proc,setProc]=useState(false);
  const[progress,setProgress]=useState(0);
  const[procCount,setProcCount]=useState(0);
  const targets=sel.size>0?images.filter(i=>sel.has(i.id)):images;
  const dn=targets.filter(i=>i.status==='done').length;

  const processSingle=async(img)=>{
    const fd=new FormData();
    fd.append('file',curFile(img));
    fd.append('sensitivity',sensitivity);
    fd.append('method',method);
    const res=await fetch('/api/watermark-removal',{method:'POST',body:fd});
    if(!res.ok)throw new Error(`HTTP ${res.status}`);
    const blob=await res.blob();
    return blob;
  };

  const processBatch=async()=>{
    setProc(true);setProgress(0);setProcCount(0);
    const pending=targets;
    if(pending.length===0){setProc(false);return}

    const results=[];
    const doOne=async(img)=>{
      const input=curFile(img);const inputSize=input.size||img.size;
      const origState={name:img.name,file:img.file,blob:img.blob,thumb:img.thumb,size:img.size,cSize:img.cSize,cUrl:img.cUrl,status:img.status,progress:img.progress};
      upd(img.id,{status:'processing',progress:50});
      const blob=await processSingle(img);
      const url=URL.createObjectURL(blob);
      const newFile=processedFile(blob,img.name.replace(/\.[^.]+$/,'')+'_nowm.png');
      if(img.cUrl)URL.revokeObjectURL(img.cUrl);
      upd(img.id,{name:newFile.name,file:newFile,blob,thumb:url,size:blob.size,cSize:blob.size,cUrl:url,status:'done',progress:100});
      results.push({name:newFile.name,origUrl:origState.thumb||img.origUrl,resultUrl:url,origSize:inputSize,resultSize:blob.size,blob,imgId:img.id,origState});
    };

    if(pending.length===1){
      try{await doOne(pending[0]);setProcCount(1)}catch(e){upd(pending[0].id,{status:'error'});console.error('Watermark removal failed:',e)}
      setProc(false);
      if(results.length)setPreview({type:'watermark',items:results});
      return;
    }

    // 批量并发处理
    const CONC=3;let idx=0;let doneCount=0;
    const worker=async()=>{
      while(idx<pending.length){
        const img=pending[idx++];if(!img)break;
        try{await doOne(img)}catch(e){upd(img.id,{status:'error'});console.error('Watermark removal failed:',e)}
        doneCount++;
        setProcCount(doneCount);
        setProgress(Math.round(doneCount/pending.length*100));
      }
    };
    await Promise.all(Array.from({length:Math.min(CONC,pending.length)},()=>worker()));
    setProc(false);
    if(results.length)setPreview({type:'watermark',items:results});
  };

  return <div className="h-full flex flex-col p-4 gap-3 animate-fade-up overflow-hidden">
    <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm flex-shrink-0">
      <div className="flex items-center justify-between mb-3"><p className="text-base font-medium text-gray-700">去水印设置</p>{sel.size>0&&<span className="text-xs text-blue-500">已选 {sel.size} 张</span>}</div>
      <div className="grid grid-cols-2 gap-3">
        <div><label className="text-xs text-gray-500 mb-1 block">灵敏度</label><select value={sensitivity} onChange={e=>setSensitivity(e.target.value)} className="w-full h-9 px-2.5 rounded-lg bg-gray-50 border border-gray-200 text-sm text-gray-600 outline-none cursor-pointer hover:bg-gray-100 transition-colors"><option value="low">低 - 轻微水印</option><option value="medium">中 - 普通水印</option><option value="high">高 - 重度水印</option></select></div>
        <div><label className="text-xs text-gray-500 mb-1 block">修复方法</label><select value={method} onChange={e=>setMethod(e.target.value)} className="w-full h-9 px-2.5 rounded-lg bg-gray-50 border border-gray-200 text-sm text-gray-600 outline-none cursor-pointer hover:bg-gray-100 transition-colors"><option value="telea">Telea - 速度快</option><option value="ns">NS - 质量高</option></select></div>
      </div>
    </div>
    {proc&&<div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm animate-fade-up flex-shrink-0">
      <div className="flex items-center gap-1.5 mb-2.5"><span className="text-blue-500"><I.droplet/></span><p className="text-base font-medium text-gray-700">处理进度</p></div>
      <Progress value={progress} label={`${procCount}/${targets.length}`} className="mt-1"/>
    </div>}
    {dn>0&&!proc&&<div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm animate-fade-up flex-shrink-0">
      <div className="flex items-center gap-1.5 mb-2.5"><span className="text-green-500"><I.trending/></span><p className="text-base font-medium text-gray-700">处理统计</p></div>
      <div className="grid grid-cols-2 gap-3"><div><p className="text-xs text-gray-400">已完成</p><p className="text-base font-semibold text-blue-500">{dn} / {targets.length}</p></div><div><p className="text-xs text-gray-400">成功率</p><p className="text-base font-semibold text-green-500">{Math.round(dn/targets.length*100)}%</p></div></div>
    </div>}
    <div className="flex-1 min-h-0 overflow-y-auto space-y-1 pr-1">
      <p className="text-xs text-gray-400 mb-1">图片列表 ({targets.length})</p>
      {targets.map((img,i)=><div key={img.id} className="flex items-center gap-2.5 p-2 rounded-lg bg-white border border-gray-100 hover:border-gray-200 transition-all animate-fade-up" style={{animationDelay:`${i*25}ms`}}>
        <div className="w-10 h-10 rounded-lg overflow-hidden bg-gray-100 flex-shrink-0"><img src={img.thumb} alt="" loading="lazy" className="w-full h-full object-cover"/></div>
        <div className="flex-1 min-w-0"><p className="text-sm text-gray-700 truncate">{img.name}</p><div className="flex items-center gap-1.5 mt-0.5"><span className="text-xs text-gray-400">{fmt(img.size)}</span>{img.cSize&&<><span className="text-xs text-gray-300">→</span><span className="text-xs text-blue-500">{fmt(img.cSize)}</span></>}</div></div>
        {img.status==='processing'&&<Progress value={img.progress||0} className="w-16"/>}
        {img.status==='done'&&<span className="text-xs text-green-500 font-medium">完成</span>}
        {img.status==='error'&&<span className="text-xs text-red-400 font-medium">失败</span>}
      </div>)}
    </div>
    <div className="flex items-center gap-2 pt-1 flex-shrink-0 flex-wrap"><Btn variant="primary" className="flex-1 min-w-0" onClick={processBatch} disabled={!targets.length||proc} loading={proc}><I.droplet/>{sel.size>0?`去水印 (${sel.size})`:'开始去水印'}</Btn><Btn variant="ghost" onClick={clearAll} disabled={!images.length}>清空</Btn></div>
  </div>;
}

// ==================== 高清化面板 ====================
function UpscalePanel(){
  const{images,sel}=useStore();
  const[scale,setScale]=useState(2);
  const[proc,setProc]=useState(false);
  const[progress,setProgress]=useState(0);
  const[procCount,setProcCount]=useState(0);
  const targets=sel.size>0?images.filter(i=>sel.has(i.id)):images;
  const dn=targets.filter(i=>i.status==='done').length;

  const processSingle=async(img)=>{
    const fd=new FormData();
    fd.append('file',curFile(img));
    fd.append('scale',String(scale));
    const res=await fetch('/api/upscale',{method:'POST',body:fd});
    if(!res.ok)throw new Error(`HTTP ${res.status}`);
    const blob=await res.blob();
    return blob;
  };

  const processBatch=async()=>{
    setProc(true);setProgress(0);setProcCount(0);
    const pending=targets;
    if(pending.length===0){setProc(false);return}

    const results=[];
    const doOne=async(img)=>{
      const input=curFile(img);const inputSize=input.size||img.size;
      const origState={name:img.name,file:img.file,blob:img.blob,thumb:img.thumb,size:img.size,cSize:img.cSize,cUrl:img.cUrl,status:img.status,progress:img.progress};
      upd(img.id,{status:'processing',progress:50});
      const blob=await processSingle(img);
      const url=URL.createObjectURL(blob);
      const newFile=processedFile(blob,img.name.replace(/\.[^.]+$/,'')+'_'+scale+'x.png');
      if(img.cUrl)URL.revokeObjectURL(img.cUrl);
      upd(img.id,{name:newFile.name,file:newFile,blob,thumb:url,size:blob.size,cSize:blob.size,cUrl:url,status:'done',progress:100});
      results.push({name:newFile.name,origUrl:origState.thumb||img.origUrl,resultUrl:url,origSize:inputSize,resultSize:blob.size,blob,imgId:img.id,origState});
    };

    if(pending.length===1){
      try{await doOne(pending[0]);setProcCount(1)}catch(e){upd(pending[0].id,{status:'error'});console.error('Upscale failed:',e)}
      setProc(false);
      if(results.length)setPreview({type:'upscale',items:results});
      return;
    }

    // 批量并发处理
    const CONC=3;let idx=0;let doneCount=0;
    const worker=async()=>{
      while(idx<pending.length){
        const img=pending[idx++];if(!img)break;
        try{await doOne(img)}catch(e){upd(img.id,{status:'error'});console.error('Upscale failed:',e)}
        doneCount++;
        setProcCount(doneCount);
        setProgress(Math.round(doneCount/pending.length*100));
      }
    };
    await Promise.all(Array.from({length:Math.min(CONC,pending.length)},()=>worker()));
    setProc(false);
    if(results.length)setPreview({type:'upscale',items:results});
  };

  return <div className="h-full flex flex-col p-4 gap-3 animate-fade-up overflow-hidden">
    <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm flex-shrink-0">
      <div className="flex items-center justify-between mb-3"><p className="text-base font-medium text-gray-700">高清化设置</p>{sel.size>0&&<span className="text-xs text-blue-500">已选 {sel.size} 张</span>}</div>
      <div className="grid grid-cols-2 gap-3">
        <div><label className="text-xs text-gray-500 mb-1 block">放大倍数</label><div className="flex items-center gap-1.5">
          {[{l:'2x',v:2},{l:'4x',v:4}].map(p=><button key={p.v} onClick={()=>setScale(p.v)} className={`flex-1 h-9 px-3 rounded-lg text-sm font-medium transition-all border ${scale===p.v?'bg-blue-50 text-blue-600 border-blue-200':'text-gray-500 border-gray-200 hover:bg-gray-50'}`}>{p.l}</button>)}
        </div></div>
      </div>
    </div>
    {proc&&<div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm animate-fade-up flex-shrink-0">
      <div className="flex items-center gap-1.5 mb-2.5"><span className="text-purple-500"><I.sparkle/></span><p className="text-base font-medium text-gray-700">处理进度</p></div>
      <Progress value={progress} label={`${procCount}/${targets.length}`} className="mt-1"/>
    </div>}
    {dn>0&&!proc&&<div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm animate-fade-up flex-shrink-0">
      <div className="flex items-center gap-1.5 mb-2.5"><span className="text-green-500"><I.trending/></span><p className="text-base font-medium text-gray-700">处理统计</p></div>
      <div className="grid grid-cols-2 gap-3"><div><p className="text-xs text-gray-400">已完成</p><p className="text-base font-semibold text-blue-500">{dn} / {targets.length}</p></div><div><p className="text-xs text-gray-400">成功率</p><p className="text-base font-semibold text-green-500">{Math.round(dn/targets.length*100)}%</p></div></div>
    </div>}
    <div className="flex-1 min-h-0 overflow-y-auto space-y-1 pr-1">
      <p className="text-xs text-gray-400 mb-1">图片列表 ({targets.length})</p>
      {targets.map((img,i)=><div key={img.id} className="flex items-center gap-2.5 p-2 rounded-lg bg-white border border-gray-100 hover:border-gray-200 transition-all animate-fade-up" style={{animationDelay:`${i*25}ms`}}>
        <div className="w-10 h-10 rounded-lg overflow-hidden bg-gray-100 flex-shrink-0"><img src={img.thumb} alt="" loading="lazy" className="w-full h-full object-cover"/></div>
        <div className="flex-1 min-w-0"><p className="text-sm text-gray-700 truncate">{img.name}</p><div className="flex items-center gap-1.5 mt-0.5"><span className="text-xs text-gray-400">{fmt(img.size)}</span>{img.cSize&&<><span className="text-xs text-gray-300">→</span><span className="text-xs text-blue-500">{fmt(img.cSize)}</span></>}</div></div>
        {img.status==='processing'&&<Progress value={img.progress||0} className="w-16"/>}
        {img.status==='done'&&<span className="text-xs text-green-500 font-medium">完成</span>}
        {img.status==='error'&&<span className="text-xs text-red-400 font-medium">失败</span>}
      </div>)}
    </div>
    <div className="flex items-center gap-2 pt-1 flex-shrink-0 flex-wrap"><Btn variant="primary" className="flex-1 min-w-0" onClick={processBatch} disabled={!targets.length||proc} loading={proc}><I.sparkle/>{sel.size>0?`高清化 (${sel.size})`:'开始高清化'}</Btn><Btn variant="ghost" onClick={clearAll} disabled={!images.length}>清空</Btn></div>
  </div>;
}

// ==================== CROP PANEL ====================
const RATIO_PRESETS=[
  {l:'自由',v:null},{l:'1:1',v:1},{l:'4:3',v:4/3},{l:'3:4',v:3/4},
  {l:'16:9',v:16/9},{l:'9:16',v:9/16},{l:'4:5',v:4/5},{l:'5:4',v:5/4},
  {l:'3:2',v:3/2},{l:'2:3',v:2/3},{l:'2:1',v:2},{l:'1:2',v:0.5},
];
const SOCIAL_PRESETS=[
  {l:'Instagram 帖子',w:1080,h:1080},{l:'Instagram 故事',w:1080,h:1920},{l:'Instagram 横幅',w:1080,h:566},
  {l:'Facebook 帖子',w:1200,h:630},{l:'Facebook 封面',w:820,h:312},{l:'Twitter 帖子',w:1200,h:675},
  {l:'YouTube 缩略图',w:1280,h:720},{l:'YouTube 横幅',w:2560,h:1440},{l:'LinkedIn 帖子',w:1200,h:627},
  {l:'TikTok',w:1080,h:1920},{l:'小红书',w:1080,h:1440},{l:'微信朋友圈',w:1080,h:1080},
];
const SHAPE_OPTS=[{l:'矩形',v:'rect',icon:I.square},{l:'圆角',v:'rounded',icon:I.roundedRect},{l:'圆形',v:'circle',icon:I.circle}];

// ==================== 裁剪面板 ====================
function CropPanel(){
  const{images,sel,previewImg,setPreviewImg}=useStore();
  const[mode,setMode]=useState('manual');
  const[ratio,setRatio]=useState(null);
  const[shape,setShape]=useState('rect');
  const[borderRadius,setBorderRadius]=useState(20);
  const[pctW,setPctW]=useState(100);const[pctH,setPctH]=useState(100);
  const[pxW,setPxW]=useState(800);const[pxH,setPxH]=useState(600);
  const[socialPreset,setSocialPreset]=useState(null);
  const[batchMode,setBatchMode]=useState('uniform');
  const[idx,setIdx]=useState(0);
  const[processing,setProcessing]=useState(false);
  const containerRef=useRef(null);const imgRef=useRef(null);
  const[cropBox,setCropBox]=useState({x:0,y:0,w:0,h:0});
  const[dragging,setDragging]=useState(null);
  const ds=useRef({mx:0,my:0,cx:0,cy:0,cw:0,ch:0});

  useEffect(()=>{
    if(previewImg){
      const i=images.findIndex(x=>x.id===previewImg.id);
      if(i>=0) setIdx(i);
    }
  },[previewImg]);

  const img=images[idx];

  const getImgRect=()=>{
    const imgEl=imgRef.current,cont=containerRef.current;
    if(!imgEl||!cont||!imgEl.naturalWidth)return null;
    const cw=cont.clientWidth,ch=cont.clientHeight;
    const nw=imgEl.naturalWidth,nh=imgEl.naturalHeight;
    const s=Math.min(cw/nw,ch/nh);
    const w=nw*s,h=nh*s;
    return{x:(cw-w)/2,y:(ch-h)/2,w,h};
  };

  useEffect(()=>{
    if(!imgRef.current||!containerRef.current)return;
    const update=()=>{
      const ir=getImgRect();if(!ir)return;
      let cw,ch;
      if(mode==='pixels'){const s=Math.min(ir.w/pxW,ir.h/pxH);cw=pxW*s;ch=pxH*s}
      else if(mode==='social'&&socialPreset){const s=Math.min(ir.w/socialPreset.w,ir.h/socialPreset.h);cw=socialPreset.w*s;ch=socialPreset.h*s}
      else if(mode==='percentage'){cw=ir.w*pctW/100;ch=ir.h*pctH/100}
      else{cw=ir.w*0.8;ch=ir.h*0.8;if(ratio){if(cw/ch>ratio)ch=cw/ratio;else cw=ch*ratio;if(cw>ir.w){cw=ir.w;ch=cw/ratio}if(ch>ir.h){ch=ir.h;cw=ch*ratio}}}
      setCropBox({x:(ir.w-cw)/2,y:(ir.h-ch)/2,w:cw,h:ch});
    };
    const imgEl=imgRef.current;
    if(imgEl.complete)update();else imgEl.onload=update;
    return()=>{imgEl.onload=null};
  },[img,idx,mode,ratio,shape,socialPreset,pctW,pctH,pxW,pxH]);

  const getCropCoords=()=>{const r=getImgRect()||{x:0,y:0,w:1,h:1};return{x:cropBox.x/r.w,y:cropBox.y/r.h,w:cropBox.w/r.w,h:cropBox.h/r.h}};

  const calcCropForImage=(imgW,imgH)=>{
    let ar=ratio||(mode==='social'&&socialPreset?socialPreset.w/socialPreset.h:null);
    if(mode==='pixels'){const s=Math.min(imgW/pxW,imgH/pxH);return{x:(imgW-pxW*s)/(2*imgW),y:(imgH-pxH*s)/(2*imgH),w:(pxW*s)/imgW,h:(pxH*s)/imgH}}
    if(mode==='social'&&socialPreset){const s=Math.min(imgW/socialPreset.w,imgH/socialPreset.h);return{x:(imgW-socialPreset.w*s)/(2*imgW),y:(imgH-socialPreset.h*s)/(2*imgH),w:(socialPreset.w*s)/imgW,h:(socialPreset.h*s)/imgH}}
    if(mode==='percentage'){return{x:(1-pctW/100)/2,y:(1-pctH/100)/2,w:pctW/100,h:pctH/100}}
    let cw=imgW*0.8,ch=imgH*0.8;
    if(ar){if(cw/ch>ar)ch=cw/ar;else cw=ch*ar;if(cw>imgW){cw=imgW;ch=cw/ar}if(ch>imgH){ch=imgH;cw=ch*ar}}
    return{x:(imgW-cw)/(2*imgW),y:(imgH-ch)/(2*imgH),w:cw/imgW,h:ch/imgH};
  };

  const handleDown=(e,type)=>{
    e.preventDefault();e.stopPropagation();setDragging(type);
    ds.current={mx:e.clientX,my:e.clientY,cx:cropBox.x,cy:cropBox.y,cw:cropBox.w,ch:cropBox.h};
  };

  useEffect(()=>{
    if(!dragging)return;
    const onMove=e=>{
      const ir=getImgRect();if(!ir)return;
      const dx=e.clientX-ds.current.mx,dy=e.clientY-ds.current.my;
      const{cx,cy,cw,ch}=ds.current;
      if(dragging==='move'){setCropBox(b=>({...b,x:Math.max(0,Math.min(ir.w-b.w,cx+dx)),y:Math.max(0,Math.min(ir.h-b.h,cy+dy))}));return}
      const ar=ratio||(mode==='social'&&socialPreset?socialPreset.w/socialPreset.h:null);
      let nw,nh,nx=cx,ny=cy;
      if(dragging==='se'){nw=Math.max(20,cw+dx);nh=ar?nw/ar:ch+dy}
      else if(dragging==='sw'){nw=Math.max(20,cw-dx);nh=ar?nw/ar:ch+dy;nx=cx+(cw-nw)}
      else if(dragging==='ne'){nw=Math.max(20,cw+dx);nh=ar?nw/ar:ch-dy;ny=cy+(ch-nh)}
      else if(dragging==='nw'){nw=Math.max(20,cw-dx);nh=ar?nw/ar:ch-dy;nx=cx+(cw-nw);ny=cy+(ch-nh)}
      else return;
      if(ar&&nh>ir.h){nh=ir.h;nw=nh*ar}
      if(nw>ir.w){nw=ir.w;if(ar)nh=nw/ar}
      nx=Math.max(0,Math.min(ir.w-nw,nx));ny=Math.max(0,Math.min(ir.h-nh,ny));
      if(nx+nw>ir.w)nw=ir.w-nx;if(ny+nh>ir.h)nh=ir.h-ny;
      setCropBox({x:nx,y:ny,w:nw,h:nh});
    };
    const onUp=()=>setDragging(null);
    document.addEventListener('mousemove',onMove);document.addEventListener('mouseup',onUp);
    return()=>{document.removeEventListener('mousemove',onMove);document.removeEventListener('mouseup',onUp)};
  },[dragging,ratio,mode,socialPreset]);

  const doCrop=async(srcFile,customCoords)=>{
    const bmp=await createImageBitmap(srcFile);
    const c=customCoords||getCropCoords();
    const sx=Math.round(c.x*bmp.width),sy=Math.round(c.y*bmp.height);
    const dw=Math.round(c.w*bmp.width),dh=Math.round(c.h*bmp.height);
    const canvas=document.createElement('canvas');
    canvas.width=dw;canvas.height=dh;
    const ctx=canvas.getContext('2d');
    if(shape==='circle'){ctx.beginPath();ctx.ellipse(dw/2,dh/2,dw/2,dh/2,0,0,Math.PI*2);ctx.clip()}
    else if(shape==='rounded'){const r=borderRadius*Math.min(dw,dh)/200;ctx.beginPath();ctx.roundRect(0,0,dw,dh,r);ctx.clip()}
    ctx.drawImage(bmp,sx,sy,dw,dh,0,0,dw,dh);
    const outType=shape!=='rect'?'image/png':(srcFile.type||'image/jpeg');
    const cropped=await new Promise(r=>canvas.toBlob(r,outType,outType==='image/png'?1:0.95));
    bmp.close();
    return cropped;
  };

  const applyCropDirect=async()=>{
    if(!img)return;setProcessing(true);
    try{
      const cropped=await doCrop(curFile(img));
      saveAs(cropped, img.name);
      showToast('裁剪完成，已下载 ' + img.name, 'ok');
    }catch(e){console.error('Crop failed:',e);showToast('裁剪失败: ' + e.message, 'err')}
    setProcessing(false);
  };

  const applyCropAllDirect=async()=>{
    setProcessing(true);
    const targets=sel.size>0?images.filter(i=>sel.has(i.id)):images;
    if(targets.length===1){
      const t=targets[0];
      try{
        const cropped=await doCrop(curFile(t));
        saveAs(cropped, t.name);
      }catch(e){}
    } else if(targets.length>1){
      const zip=new JSZip();
      for(const t of targets){
        try{
          const input=curFile(t);
          const bmp=await createImageBitmap(input);
          const cc=calcCropForImage(bmp.width,bmp.height);
          bmp.close();
          const cropped=await doCrop(input,cc);
          zip.file(t.name, cropped);
        }catch(e){}
      }
      saveAs(await zip.generateAsync({type:'blob'}), 'cropped_images.zip');
      showToast('批量裁剪完成，共处理 ' + targets.length + ' 张图片', 'ok');
    }
    setProcessing(false);
  };

  const previewCropSingle=async()=>{
    if(!img)return;setProcessing(true);
    try{
      const origState={name:img.name,file:img.file,blob:img.blob,thumb:img.thumb,size:img.size,cSize:img.cSize,cUrl:img.cUrl,status:img.status,progress:img.progress};
      const cropped=await doCrop(curFile(img));
      if(img.cUrl)URL.revokeObjectURL(img.cUrl);
      const newFile=new File([cropped],img.name,{type:cropped.type});
      const url=URL.createObjectURL(cropped);
      upd(img.id,{name:newFile.name,file:newFile,blob:cropped,thumb:url,size:cropped.size,cSize:cropped.size,cUrl:url,status:'done',progress:100});
      setCropResults([{name:img.name,origUrl:origState.thumb||img.origUrl,resultUrl:url,origSize:img.size,resultSize:cropped.size,blob:cropped,saving:((1-cropped.size/img.size)*100).toFixed(0)+'%',imgId:img.id,newFile,newBlob:cropped,newThumb:url,newCSize:cropped.size,newCUrl:url,origState}]);
    }catch(e){console.error('Crop preview failed:',e)}
    setProcessing(false);
  };

  const previewCropAll=async()=>{
    setProcessing(true);
    const targets=sel.size>0?images.filter(i=>sel.has(i.id)):images;
    const results=[];
    for(const img of targets){
      try{
        const origState={name:img.name,file:img.file,blob:img.blob,thumb:img.thumb,size:img.size,cSize:img.cSize,cUrl:img.cUrl,status:img.status,progress:img.progress};
        const bmp=await createImageBitmap(curFile(img));
        const cc=calcCropForImage(bmp.width,bmp.height);
        bmp.close();
        const cropped=await doCrop(curFile(img),cc);
        if(img.cUrl)URL.revokeObjectURL(img.cUrl);
        const newFile=new File([cropped],img.name,{type:cropped.type});
        const url=URL.createObjectURL(cropped);
        upd(img.id,{name:newFile.name,file:newFile,blob:cropped,thumb:url,size:cropped.size,cSize:cropped.size,cUrl:url,status:'done',progress:100});
        results.push({name:img.name,origUrl:origState.thumb||img.origUrl,resultUrl:url,origSize:img.size,resultSize:cropped.size,blob:cropped,saving:((1-cropped.size/img.size)*100).toFixed(0)+'%',imgId:img.id,newFile,newBlob:cropped,newThumb:url,newCSize:cropped.size,newCUrl:url,origState});
      }catch(e){}
    }
    if(results.length)setCropResults(results);
    setProcessing(false);
  };

  const handleApplyCrop=batchMode==='uniform'?applyCropAllDirect:applyCropDirect;
  const handlePreviewCrop=batchMode==='uniform'?previewCropAll:previewCropSingle;

  const resetCrop=()=>{
    const imgEl=imgRef.current,cont=containerRef.current;
    if(!imgEl||!cont)return;
    setCropResults(null);
    if(batchMode==='uniform'&&sel.size>1){
      const targets=images.filter(i=>sel.has(i.id));
      targets.forEach(t=>{
        if(t.origFile&&t.file!==t.origFile){
          if(t.cUrl)URL.revokeObjectURL(t.cUrl);
          const newUrl=URL.createObjectURL(t.origFile);
          upd(t.id,{name:t.origFile.name,file:t.origFile,blob:null,thumb:newUrl,size:t.origSize||t.origFile.size,cSize:null,cUrl:null,status:'idle',progress:0});
        }
      });
      return;
    }
    if(img.origFile&&img.file!==img.origFile){
      if(img.cUrl)URL.revokeObjectURL(img.cUrl);
      const newUrl=URL.createObjectURL(img.origFile);
      upd(img.id,{name:img.origFile.name,file:img.origFile,blob:null,thumb:newUrl,size:img.origSize||img.origFile.size,cSize:null,cUrl:null,status:'idle',progress:0});
      return;
    }
    const doReset=()=>{
      if(!imgEl.naturalWidth){requestAnimationFrame(doReset);return}
      const cw=cont.clientWidth,ch=cont.clientHeight;
      const nw=imgEl.naturalWidth,nh=imgEl.naturalHeight;
      if(!nw||!nh||!cw||!ch)return;
      const s=Math.min(cw/nw,ch/nh);
      const iw=nw*s,ih=nh*s;
      let bw=iw*0.8,bh=ih*0.8;
      if(ratio){if(bw/bh>ratio)bh=bw/ratio;else bw=bh*ratio;if(bw>iw){bw=iw;bh=bw/ratio}if(bh>ih){bh=ih;bw=bh/ratio}}
      setCropBox({x:(iw-bw)/2,y:(ih-bh)/2,w:bw,h:bh});
    };
    doReset();
  };

  if(!img)return<EmptyState/>;

  const isCircle=shape==='circle';
  const ir=getImgRect()||{x:0,y:0,w:0,h:0};
  const bx=ir.x+cropBox.x,by=ir.y+cropBox.y;
  const boxStyle={left:bx,top:by,width:cropBox.w,height:cropBox.h,borderRadius:isCircle?'50%':shape==='rounded'?borderRadius+'px':'0'};

  return <div className="h-full flex flex-col overflow-hidden animate-fade-up">
    <div className="flex items-center gap-1 px-4 py-2.5 bg-white border-b border-gray-100 flex-shrink-0">
      {[{id:'manual',l:'手动'},{id:'percentage',l:'百分比'},{id:'pixels',l:'像素'},{id:'social',l:'社媒'},{id:'shape',l:'形状'}].map(m=>
        <button key={m.id} onClick={()=>setMode(m.id)} className={`px-3.5 py-2 rounded-lg text-sm font-medium transition-all ${mode===m.id?'bg-blue-500 text-white':'text-gray-500 hover:bg-gray-100'}`}>{m.l}</button>
      )}
      <div className="flex-1"/>
      <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-0.5">
        <button onClick={()=>setBatchMode('uniform')} className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${batchMode==='uniform'?'bg-white text-gray-800 shadow-sm':'text-gray-500'}`}>统一裁剪</button>
        <button onClick={()=>setBatchMode('individual')} className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${batchMode==='individual'?'bg-white text-gray-800 shadow-sm':'text-gray-500'}`}>单独裁剪</button>
      </div>
    </div>

    <div className="px-4 py-3 bg-white border-b border-gray-100 flex-shrink-0">
      {mode==='manual'&&<div className="flex flex-wrap gap-1.5">
        {RATIO_PRESETS.map(p=><button key={p.l} onClick={()=>setRatio(p.v)} className={`px-3 py-2 rounded-lg text-sm font-medium transition-all border ${ratio===p.v?'bg-blue-50 text-blue-600 border-blue-200':'text-gray-500 border-gray-200 hover:bg-gray-50'}`}>{p.l}</button>)}
      </div>}
      {mode==='percentage'&&<div className="flex items-center gap-4">
        <div className="flex items-center gap-2 flex-1"><span className="text-xs text-gray-500 w-8">宽%</span><input type="range" min="1" max="100" value={pctW} onChange={e=>setPctW(Number(e.target.value))} className="flex-1"/><input type="number" value={pctW} onChange={e=>setPctW(Math.min(100,Math.max(1,Number(e.target.value))))} className="w-16 h-8 px-2 rounded-lg bg-gray-50 border border-gray-200 text-xs text-gray-700 outline-none text-center"/></div>
        <div className="flex items-center gap-2 flex-1"><span className="text-xs text-gray-500 w-8">高%</span><input type="range" min="1" max="100" value={pctH} onChange={e=>setPctH(Number(e.target.value))} className="flex-1"/><input type="number" value={pctH} onChange={e=>setPctH(Math.min(100,Math.max(1,Number(e.target.value))))} className="w-16 h-8 px-2 rounded-lg bg-gray-50 border border-gray-200 text-xs text-gray-700 outline-none text-center"/></div>
      </div>}
      {mode==='pixels'&&<div className="flex items-center gap-4">
        <div className="flex items-center gap-2"><span className="text-xs text-gray-500">宽</span><input type="number" value={pxW} onChange={e=>setPxW(Math.min(10000,Math.max(1,Number(e.target.value))))} className="w-20 h-8 px-2 rounded-lg bg-gray-50 border border-gray-200 text-xs text-gray-700 outline-none text-center"/><span className="text-xs text-gray-400">px</span></div>
        <span className="text-gray-300">×</span>
        <div className="flex items-center gap-2"><span className="text-xs text-gray-500">高</span><input type="number" value={pxH} onChange={e=>setPxH(Math.min(10000,Math.max(1,Number(e.target.value))))} className="w-20 h-8 px-2 rounded-lg bg-gray-50 border border-gray-200 text-xs text-gray-700 outline-none text-center"/><span className="text-xs text-gray-400">px</span></div>
      </div>}
      {mode==='social'&&<div className="grid grid-cols-4 gap-1.5 max-h-24 overflow-y-auto">
        {SOCIAL_PRESETS.map(p=><button key={p.l} onClick={()=>setSocialPreset(p)} className={`px-2.5 py-2 rounded-lg text-xs font-medium transition-all border text-left ${socialPreset?.l===p.l?'bg-blue-50 text-blue-600 border-blue-200':'text-gray-500 border-gray-200 hover:bg-gray-50'}`}><div>{p.l}</div><div className="text-[11px] text-gray-400">{p.w}×{p.h}</div></button>)}
      </div>}
      {mode==='shape'&&<div className="flex items-center gap-4">
        <div className="flex items-center gap-1.5">{SHAPE_OPTS.map(s=><button key={s.v} onClick={()=>setShape(s.v)} className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-all border ${shape===s.v?'bg-blue-50 text-blue-600 border-blue-200':'text-gray-500 border-gray-200 hover:bg-gray-50'}`}><s.icon/>{s.l}</button>)}</div>
        {shape==='rounded'&&<div className="flex items-center gap-2 flex-1"><span className="text-xs text-gray-500">圆角</span><input type="range" min="5" max="100" value={borderRadius} onChange={e=>setBorderRadius(Number(e.target.value))} className="flex-1"/><span className="text-xs text-gray-500 w-8">{borderRadius}px</span></div>}
      </div>}
    </div>

    <div ref={containerRef} className="flex-1 relative bg-gray-100 m-3 rounded-xl overflow-hidden select-none">
      <img ref={imgRef} src={img.thumb} alt="" className="absolute inset-0 m-auto max-w-full max-h-full object-contain pointer-events-none"/>
      <div className="absolute inset-0 pointer-events-none" style={{background:isCircle
        ?`radial-gradient(ellipse ${cropBox.w/2}px ${cropBox.h/2}px at ${bx+cropBox.w/2}px ${by+cropBox.h/2}px, transparent 60%, rgba(0,0,0,.5) 100%)`
        :`linear-gradient(to right, rgba(0,0,0,.5) ${bx}px, transparent ${bx}px, transparent ${bx+cropBox.w}px, rgba(0,0,0,.5) ${bx+cropBox.w}px)`}}/>
      {!isCircle&&<><div className="absolute pointer-events-none" style={{left:0,right:0,top:0,height:by,background:'rgba(0,0,0,.5)'}}/><div className="absolute pointer-events-none" style={{left:0,right:0,top:by+cropBox.h,bottom:0,background:'rgba(0,0,0,.5)'}}/></>}
      <div className="absolute border-2 border-white cursor-move" style={boxStyle} onMouseDown={e=>handleDown(e,'move')}>
        {!isCircle&&<div className="absolute inset-0 pointer-events-none">
          <div className="absolute left-1/3 top-0 bottom-0 w-px bg-white/40"/><div className="absolute left-2/3 top-0 bottom-0 w-px bg-white/40"/>
          <div className="absolute top-1/3 left-0 right-0 h-px bg-white/40"/><div className="absolute top-2/3 left-0 right-0 h-px bg-white/40"/>
        </div>}
        {[{t:'nw',c:'-top-1.5 -left-1.5 cursor-nw-resize'},{t:'ne',c:'-top-1.5 -right-1.5 cursor-ne-resize'},{t:'sw',c:'-bottom-1.5 -left-1.5 cursor-sw-resize'},{t:'se',c:'-bottom-1.5 -right-1.5 cursor-se-resize'}].map(h=>
          !isCircle&&<div key={h.t} className={`absolute w-2.5 h-2.5 bg-white rounded-sm shadow border border-gray-300 ${h.c}`} style={{transform:'translate(-50%,-50%)'}} onMouseDown={e=>handleDown(e,h.t)}/>
        )}
        <div className="absolute -top-5 left-1/2 -translate-x-1/2 px-1.5 py-0.5 rounded bg-black/60 text-white text-[10px] whitespace-nowrap">{Math.round(cropBox.w)}×{Math.round(cropBox.h)}</div>
      </div>
    </div>

    <div className="flex items-center justify-between px-4 py-3 flex-wrap gap-2">
      <div className="flex items-center gap-2">
        <Btn variant="ghost" size="sm" onClick={()=>{const i=Math.max(0,idx-1);setIdx(i);setPreviewImg(images[i])}} disabled={idx===0}>上一张</Btn>
        <span className="text-xs text-gray-500">{idx+1}/{images.length}</span>
        <Btn variant="ghost" size="sm" onClick={()=>{const i=Math.min(images.length-1,idx+1);setIdx(i);setPreviewImg(images[i])}} disabled={idx===images.length-1}>下一张</Btn>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        <Btn variant="ghost" size="sm" onClick={resetCrop}><Refresh/>重置</Btn>
        <Btn variant="ghost" size="sm" onClick={handlePreviewCrop} disabled={processing} loading={processing}><I.eye/>预览效果</Btn>
        <Btn variant="primary" size="sm" onClick={handleApplyCrop} disabled={processing} loading={processing}><Download/>{batchMode==='uniform'&&sel.size>0?`应用裁剪 (${sel.size})`:'应用裁剪'}</Btn>
      </div>
    </div>
  </div>;
}

// ==================== 重命名/转格式面板 ====================
function RenameConvertPanel(){
  const{images,sel}=useStore();
  const[outFmt,setOutFmt]=useState('keep');const[quality,setQuality]=useState(0.92);const[mode,setMode]=useState('keep');
  const[baseName,setBaseName]=useState('image');const[findStr,setFindStr]=useState('');const[replaceStr,setReplaceStr]=useState('');
  const[prefix,setPrefix]=useState('');const[suffix,setSuffix]=useState('');const[seq,setSeq]=useState(true);const[seqStart,setSeqStart]=useState(1);const[seqPad,setSeqPad]=useState(3);const[proc,setProc]=useState(false);
  const targets=sel.size>0?images.filter(i=>sel.has(i.id)):images;
  const mimeMap={jpg:'image/jpeg',png:'image/png',webp:'image/webp'};
  const splitName=name=>{const dot=name.lastIndexOf('.');return dot>0?{stem:name.slice(0,dot),ext:name.slice(dot+1).toLowerCase()}:{stem:name,ext:''}};
  const targetExt=img=>outFmt==='keep'?(splitName(img.name).ext||ext(img.type)):outFmt;
  const safeStem=v=>(v||'image').trim().replace(/[\\/:*?"<>|]+/g,'-')||'image';
  const dedupeName=(name,used)=>{
    if(!used.has(name)){used.add(name);return name}
    const dot=name.lastIndexOf('.');const stem=dot>0?name.slice(0,dot):name;const ex=dot>0?name.slice(dot):'';
    let n=2,next=`${stem}_${n}${ex}`;
    while(used.has(next)){n++;next=`${stem}_${n}${ex}`}
    used.add(next);return next;
  };
  const makeRawName=(img,i)=>{
    const parts=splitName(img.name);let stem=parts.stem;
    if(mode==='base')stem=baseName;
    if(mode==='replace'&&findStr)stem=stem.split(findStr).join(replaceStr);
    let next=safeStem(`${prefix}${stem}${suffix}`);
    if(seq)next+=String(Math.max(0,Number(seqStart)||0)+i).padStart(Math.max(1,Number(seqPad)||1),'0');
    return `${next}.${targetExt(img)}`;
  };
  const targetIds=new Set(targets.map(i=>i.id));const usedNames=new Set(images.filter(i=>!targetIds.has(i.id)).map(i=>i.name));
  const previewNames=new Map();targets.forEach((img,i)=>previewNames.set(img.id,dedupeName(makeRawName(img,i),usedNames)));
  const convertFile=(file,mime)=>new Promise(async(resolve,reject)=>{
    let bmp=null;
    try{
      bmp=await createImageBitmap(file);
      const canvas=document.createElement('canvas');canvas.width=bmp.width;canvas.height=bmp.height;
      const ctx=canvas.getContext('2d');
      if(mime==='image/jpeg'){ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height)}
      ctx.drawImage(bmp,0,0);
      canvas.toBlob(b=>b?resolve(b):reject(new Error('canvas toBlob failed')),mime,mime==='image/png'?undefined:quality);
    }catch(e){reject(e)}finally{if(bmp)bmp.close()}
  });
  const apply=async()=>{
    if(!targets.length)return;setProc(true);
    const planned=targets.map(img=>({img,name:previewNames.get(img.id)||makeRawName(img,0),ex:targetExt(img)}));
    let ok=0;
    for(const item of planned){
      const{img,name,ex}=item;const mime=mimeMap[ex]||img.type;const needConvert=outFmt!=='keep'&&img.type!==mime;
      try{
        if(!needConvert){upd(img.id,{name});ok++;continue}
        const input=curFile(img);upd(img.id,{status:'processing',progress:40});
        const blob=await convertFile(input,mime);const url=URL.createObjectURL(blob);const newFile=processedFile(blob,name);
        if(img.cUrl)URL.revokeObjectURL(img.cUrl);
        if(img.thumb&&img.thumb!==img.origUrl&&img.thumb!==img.cUrl)URL.revokeObjectURL(img.thumb);
        upd(img.id,{name,file:newFile,blob,type:mime,thumb:url,size:blob.size,cSize:blob.size,cUrl:url,status:'done',progress:100});
        ok++;
      }catch(e){upd(img.id,{status:'error',progress:0})}
    }
    setProc(false);showToast(`已处理 ${ok}/${planned.length} 张`,ok===planned.length?'ok':'info');
  };
  const downloadZip=async()=>{
    if(!targets.length)return;
    setProc(true);
    const zip=new JSZip();const used=new Set();
    try{
      for(const img of targets){
        const name=dedupeName(previewNames.get(img.id)||img.name,used);const ex=targetExt(img);const mime=mimeMap[ex]||img.type;
        const file=outFmt!=='keep'&&img.type!==mime?await convertFile(curFile(img),mime):curFile(img);
        zip.file(name,file);
      }
      saveAs(await zip.generateAsync({type:'blob'}),outFmt==='keep'?'renamed_images.zip':'converted_images.zip');
    }finally{setProc(false)}
  };
  return <div className="h-full flex flex-col p-4 gap-3 animate-fade-up overflow-hidden">
    <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm flex-shrink-0">
      <div className="flex items-center justify-between mb-3"><p className="text-base font-medium text-gray-700">重命名 / 转格式</p>{sel.size>0&&<span className="text-xs text-blue-500">已选 {sel.size} 张</span>}</div>
      <div className="grid grid-cols-2 gap-3 mb-3">
        <div><label className="text-xs text-gray-500 mb-1 block">输出格式</label><select value={outFmt} onChange={e=>setOutFmt(e.target.value)} className="w-full h-9 px-2.5 rounded-lg bg-gray-50 border border-gray-200 text-sm text-gray-600 outline-none cursor-pointer hover:bg-gray-100 transition-colors"><option value="keep">保持原格式</option><option value="jpg">JPG</option><option value="png">PNG</option><option value="webp">WEBP</option></select></div>
        <div><label className="text-xs text-gray-500 mb-1 block">质量 {Math.round(quality*100)}%</label><input type="range" min="0.4" max="1" step="0.01" value={quality} onChange={e=>setQuality(Number(e.target.value))} disabled={outFmt==='png'||outFmt==='keep'} className="w-full h-9 disabled:opacity-30"/></div>
      </div>
      <div className="grid grid-cols-3 gap-2 mb-3">
        {[['keep','保留原名'],['base','统一基名'],['replace','查找替换']].map(([id,label])=><button key={id} onClick={()=>setMode(id)} className={`h-9 rounded-lg text-sm font-medium transition-all ${mode===id?'bg-blue-500 text-white':'bg-gray-50 text-gray-500 hover:bg-gray-100'}`}>{label}</button>)}
      </div>
      {mode==='base'&&<div className="mb-3"><label className="text-xs text-gray-500 mb-1 block">统一基名</label><input value={baseName} onChange={e=>setBaseName(e.target.value)} className="w-full h-9 px-2.5 rounded-lg bg-gray-50 border border-gray-200 text-sm text-gray-800 outline-none focus:border-blue-400 transition-all" placeholder="image"/></div>}
      {mode==='replace'&&<div className="grid grid-cols-2 gap-3 mb-3">
        <div><label className="text-xs text-gray-500 mb-1 block">查找</label><input value={findStr} onChange={e=>setFindStr(e.target.value)} className="w-full h-9 px-2.5 rounded-lg bg-gray-50 border border-gray-200 text-sm text-gray-800 outline-none focus:border-blue-400 transition-all" placeholder="原文字"/></div>
        <div><label className="text-xs text-gray-500 mb-1 block">替换为</label><input value={replaceStr} onChange={e=>setReplaceStr(e.target.value)} className="w-full h-9 px-2.5 rounded-lg bg-gray-50 border border-gray-200 text-sm text-gray-800 outline-none focus:border-blue-400 transition-all" placeholder="新文字"/></div>
      </div>}
      <div className="grid grid-cols-2 gap-3 mb-3">
        <div><label className="text-xs text-gray-500 mb-1 block">前缀</label><input value={prefix} onChange={e=>setPrefix(e.target.value)} className="w-full h-9 px-2.5 rounded-lg bg-gray-50 border border-gray-200 text-sm text-gray-800 outline-none focus:border-blue-400 transition-all" placeholder="可选"/></div>
        <div><label className="text-xs text-gray-500 mb-1 block">后缀</label><input value={suffix} onChange={e=>setSuffix(e.target.value)} className="w-full h-9 px-2.5 rounded-lg bg-gray-50 border border-gray-200 text-sm text-gray-800 outline-none focus:border-blue-400 transition-all" placeholder="可选"/></div>
      </div>
      <div className="flex items-end gap-3 flex-wrap">
        <button onClick={()=>setSeq(v=>!v)} className={`h-9 px-3 rounded-lg text-sm font-medium transition-all ${seq?'bg-blue-50 text-blue-500':'bg-gray-50 text-gray-400'}`}>{seq?'追加序号':'不加序号'}</button>
        <div className="w-24"><label className="text-xs text-gray-500 mb-1 block">起始</label><input type="number" value={seqStart} onChange={e=>setSeqStart(Number(e.target.value))} className="w-full h-9 px-2.5 rounded-lg bg-gray-50 border border-gray-200 text-sm text-gray-800 outline-none focus:border-blue-400 transition-all"/></div>
        <div className="w-24"><label className="text-xs text-gray-500 mb-1 block">位数</label><input type="number" min="1" value={seqPad} onChange={e=>setSeqPad(Number(e.target.value))} className="w-full h-9 px-2.5 rounded-lg bg-gray-50 border border-gray-200 text-sm text-gray-800 outline-none focus:border-blue-400 transition-all"/></div>
      </div>
    </div>
    <div className="flex-1 min-h-0 overflow-y-auto space-y-1 pr-1">
      <p className="text-xs text-gray-400 mb-1">实时预览 ({targets.length})</p>
      {targets.map((img,i)=>{const next=previewNames.get(img.id)||img.name;const ex=targetExt(img);const converting=outFmt!=='keep'&&img.type!==(mimeMap[ex]||img.type);return <div key={img.id} className="flex items-center gap-2.5 p-2 rounded-lg bg-white border border-gray-100 hover:border-gray-200 transition-all animate-fade-up" style={{animationDelay:`${i*25}ms`}}>
        <div className="w-10 h-10 rounded-lg overflow-hidden bg-gray-100 flex-shrink-0"><img src={img.thumb} alt="" loading="lazy" className="w-full h-full object-cover"/></div>
        <div className="flex-1 min-w-0"><p className="text-sm text-gray-700 truncate">{img.name}</p><div className="flex items-center gap-1.5 mt-0.5 min-w-0"><span className="text-xs text-gray-300">→</span><span className="text-xs text-blue-500 truncate">{next}</span></div></div>
        <div className="text-right flex-shrink-0"><p className="text-xs font-medium text-gray-600 uppercase">{ex}</p><p className="text-[11px] text-gray-400">{fmt(img.size)}</p></div>
        {img.status==='processing'&&<Progress value={img.progress||0} className="w-16"/>}
        {img.status==='error'?<span className="text-xs text-red-400 font-medium">失败</span>:converting&&<span className="text-xs text-blue-500 font-medium">转码</span>}
      </div>})}
    </div>
    <div className="flex items-center gap-2 pt-1 flex-shrink-0 flex-wrap"><Btn variant="primary" className="flex-1 min-w-0" onClick={apply} disabled={!targets.length||proc} loading={proc}><I.tag/>{sel.size>0?`处理选中 (${sel.size})`:'应用处理'}</Btn><Btn variant="ghost" onClick={downloadZip} disabled={!targets.length||proc}><Download/>打包下载</Btn><Btn variant="ghost" onClick={clearAll} disabled={!images.length}>清空</Btn></div>
  </div>;
}

// ==================== 下载面板 ====================
function DownloadPanel(){
  const{images}=useStore();
  const proc=images.filter(i=>i.blob);const tot=images.reduce((a,i)=>a+(i.origSize||i.size),0);
  const comp=proc.reduce((a,i)=>a+(i.cSize||i.size),0);const sv=comp>0?((1-comp/tot)*100).toFixed(1):0;
  const dl=img=>{const b=curFile(img);saveAs(b,img.name)};
  const dlAll=async()=>{if(!proc.length)return;const zip=new JSZip();proc.forEach(img=>{const b=curFile(img);zip.file(img.name,b)});saveAs(await zip.generateAsync({type:'blob'}),'images.zip')};
  return <div className="h-full flex flex-col p-4 gap-3 overflow-y-auto animate-fade-up">
    <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
      <p className="text-base font-medium text-gray-700 mb-2.5">下载概览</p>
      <div className="grid grid-cols-3 gap-3"><div><p className="text-xs text-gray-400">总图片</p><p className="text-xl font-semibold text-gray-800">{images.length}</p></div><div><p className="text-xs text-gray-400">已处理</p><p className="text-xl font-semibold text-blue-500">{proc.length}</p></div><div><p className="text-xs text-gray-400">压缩率</p><p className="text-xl font-semibold text-green-500">{sv}%</p></div></div>
    </div>
    <div className="flex-1">
      <div className="flex items-center px-3 py-2 text-xs text-gray-400 font-medium border-b border-gray-100"><span className="flex-1">文件名</span><span className="w-16 text-right">原始</span><span className="w-16 text-right">处理后</span><span className="w-12 text-right">节省</span><span className="w-12 text-right">操作</span></div>
      <div className="space-y-0.5">{images.map((img,i)=>{const has=!!img.blob;const baseSize=img.origSize||img.size;const s=has&&img.cSize?((1-img.cSize/baseSize)*100).toFixed(0):null;return<div key={img.id} className="flex items-center px-3 py-2.5 rounded-lg hover:bg-gray-50 transition-colors animate-fade-up" style={{animationDelay:`${i*20}ms`}}>
        <div className="flex-1 flex items-center gap-2 min-w-0"><div className="w-8 h-8 rounded-lg overflow-hidden bg-gray-100 flex-shrink-0"><img src={img.thumb} alt="" loading="lazy" className="w-full h-full object-cover"/></div><span className="text-sm text-gray-700 truncate">{img.name}</span></div>
        <span className="w-16 text-right text-xs text-gray-400">{fmt(baseSize)}</span>
        <span className="w-16 text-right text-xs text-gray-500">{has?fmt(img.cSize||img.size):'-'}</span>
        <span className="w-12 text-right text-xs text-green-500 font-medium">{s?s+'%':'-'}</span>
        <div className="w-16 text-right flex items-center justify-end gap-1">
          {has&&<button onClick={()=>dl(img)} className="text-xs text-blue-500 hover:text-blue-700 font-medium">下载</button>}
          <button onClick={()=>rmImg(img.id)} className="p-1 rounded hover:bg-red-50 text-gray-300 hover:text-red-400 transition-colors"><X size={12}/></button>
        </div>
      </div>})}
      </div>
    </div>
    <div className="flex items-center gap-2"><Btn variant="primary" className="flex-1" onClick={dlAll} disabled={!proc.length}><Download/>下载全部 (ZIP)</Btn><Btn variant="ghost" onClick={clearAll} disabled={!images.length}><Trash size={12}/>清空全部</Btn></div>
  </div>;
}

// ==================== 图片放大查看器 ====================
function ZoomViewer({url, label, onClose}){
  const[zoom,setZoom]=useState(1);
  const[pan,setPan]=useState({x:0,y:0});
  const dragging=useRef(false);
  const start=useRef({x:0,y:0,px:0,py:0});
  useEffect(()=>{
    function onKey(e){if(e.key==='Escape')onClose()}
    document.addEventListener('keydown',onKey);
    return()=>document.removeEventListener('keydown',onKey);
  },[onClose]);
  const handleWheel=e=>{e.preventDefault();setZoom(z=>Math.max(0.2,Math.min(10,z+(e.deltaY>0?-0.3:0.3))))};
  const handleDown=e=>{e.preventDefault();dragging.current=true;start.current={x:e.clientX,y:e.clientY,px:pan.x,py:pan.y}};
  const handleMove=e=>{if(!dragging.current)return;setPan({x:start.current.px+(e.clientX-start.current.x),y:start.current.py+(e.clientY-start.current.y)})};
  const handleUp=()=>{dragging.current=false};
  return <div className="fixed inset-0 z-[60] bg-black/80 flex flex-col" onClick={onClose}>
    <div className="flex items-center justify-between px-5 py-3 text-white flex-shrink-0">
      <span className="text-sm font-medium">{label}</span>
      <div className="flex items-center gap-2">
        <button onClick={e=>{e.stopPropagation();setZoom(z=>Math.max(0.2,z-0.5))}} className="px-2 py-1 rounded bg-white/10 hover:bg-white/20 text-sm">-</button>
        <span className="text-sm w-12 text-center">{Math.round(zoom*100)}%</span>
        <button onClick={e=>{e.stopPropagation();setZoom(z=>Math.min(10,z+0.5))}} className="px-2 py-1 rounded bg-white/10 hover:bg-white/20 text-sm">+</button>
        <button onClick={e=>{e.stopPropagation();setZoom(1);setPan({x:0,y:0})}} className="px-2 py-1 rounded bg-white/10 hover:bg-white/20 text-xs">重置</button>
        <button onClick={e=>{e.stopPropagation();onClose()}} className="p-1 rounded hover:bg-white/20"><X size={16}/></button>
      </div>
    </div>
    <div className="flex-1 overflow-hidden cursor-grab active:cursor-grabbing" onClick={e=>e.stopPropagation()}
      onWheel={handleWheel} onMouseDown={handleDown} onMouseMove={handleMove} onMouseUp={handleUp} onMouseLeave={handleUp}>
      <img src={url} alt="" className="max-w-none select-none" draggable={false}
        style={{position:'absolute',top:'50%',left:'50%',transform:`translate(-50%,-50%) scale(${zoom}) translate(${pan.x/zoom}px,${pan.y/zoom}px)`,maxWidth:zoom<=1?'100%':'none',maxHeight:zoom<=1?'100%':'none',objectFit:'contain'}}/>
    </div>
    <div className="flex items-center justify-center px-5 py-2 text-white/60 text-xs flex-shrink-0">滚轮缩放 · 拖拽平移 · 点击空白关闭</div>
  </div>;
}

// ==================== 压缩/裁剪结果预览弹窗 ====================
function PreviewModal(){
  const{preview}=useStore();
  const[removed,setRemoved]=useState(new Set());
  const[names,setNames]=useState(()=>preview?preview.items.map(it=>it.name):[]);
  const[zoomTarget,setZoomTarget]=useState(null);
  useEffect(()=>{if(preview)setNames(preview.items.map(it=>it.name))},[preview]);
  if(!preview)return null;
  const{items,type}=preview;
  const keptIdx=items.map((_,i)=>i).filter(i=>!removed.has(i));
  const close=()=>{
    items.forEach((item,i)=>{
      if(removed.has(i)&&item.imgId&&item.origState){
        upd(item.imgId,item.origState);
      }
    });
    setPreview(null);
  };
  const toggleRemove=i=>setRemoved(s=>{const n=new Set(s);n.has(i)?n.delete(i):n.add(i);return n});
  const updateName=(i,v)=>setNames(prev=>{const n=[...prev];n[i]=v;return n});
  const typeLabel={compress:'压缩结果',crop:'裁剪结果',watermark:'去水印结果',upscale:'高清化结果'}[type]||'处理结果';
  const afterLabel={compress:'压缩后',crop:'裁剪后',watermark:'去水印后',upscale:'高清化后'}[type]||'处理后';
  return <>
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 animate-fade-up" onClick={close}>
      <div className="bg-white rounded-2xl shadow-2xl max-w-4xl w-full mx-4 max-h-[85vh] flex flex-col overflow-hidden" onClick={e=>e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
          <h3 className="text-base font-semibold text-gray-800">{typeLabel} ({keptIdx.length}/{items.length} 保留)</h3>
          <button onClick={close} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"><X size={12}/></button>
        </div>
        <div className="flex-1 overflow-y-auto p-5">
          <div className="grid grid-cols-2 gap-4">
            {items.map((item,i)=>{
              const isOff=removed.has(i);
              return <div key={i} className={`relative bg-gray-50 rounded-xl p-3 animate-fade-up transition-all ${isOff?'opacity-40 grayscale':'hover:shadow-md'}`} style={{animationDelay:`${i*60}ms`}}>
                <button onClick={()=>toggleRemove(i)} className={`absolute top-2 right-2 z-10 w-6 h-6 rounded-full flex items-center justify-center text-white text-xs transition-all ${isOff?'bg-gray-400 hover:bg-gray-500':'bg-red-400 hover:bg-red-500'}`} title={isOff?'恢复此图':'移除此结果'}><X size={12}/></button>
                <input type="text" value={names[i]||item.name} onChange={e=>updateName(i,e.target.value)}
                  className={`w-full text-sm font-medium mb-2 px-2 py-1.5 rounded border bg-white outline-none transition-all ${isOff?'text-gray-400 line-through border-transparent':'text-gray-700 border-gray-200 focus:border-blue-400'}`}/>
                <div className="flex gap-3 mb-3">
                  <div className="flex-1 relative rounded-lg overflow-hidden bg-gray-200 cursor-pointer group/img" onClick={()=>setZoomTarget({url:item.origUrl,label:'原图'})}>
                    <img src={item.origUrl} alt="" className="w-full h-40 object-contain transition-transform group-hover/img:scale-105"/>
                    <span className="absolute bottom-1.5 left-1.5 px-1.5 py-0.5 rounded bg-black/50 text-white text-[11px]">原图</span>
                    <span className="absolute inset-0 flex items-center justify-center bg-black/0 group-hover/img:bg-black/10 transition-colors"><span className="opacity-0 group-hover/img:opacity-100 text-white text-xs bg-black/50 px-2 py-1 rounded transition-opacity">点击放大</span></span>
                  </div>
                  <div className="flex-1 relative rounded-lg overflow-hidden bg-gray-200 cursor-pointer group/img" onClick={()=>setZoomTarget({url:item.resultUrl,label:afterLabel})}>
                    <img src={item.resultUrl} alt="" className="w-full h-40 object-contain transition-transform group-hover/img:scale-105"/>
                    <span className="absolute bottom-1.5 left-1.5 px-1.5 py-0.5 rounded bg-blue-500/80 text-white text-[11px]">{afterLabel}</span>
                    <span className="absolute inset-0 flex items-center justify-center bg-black/0 group-hover/img:bg-black/10 transition-colors"><span className="opacity-0 group-hover/img:opacity-100 text-white text-xs bg-black/50 px-2 py-1 rounded transition-opacity">点击放大</span></span>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-2 text-center">
                  <div><p className="text-[11px] text-gray-400">原始大小</p><p className="text-xs font-semibold text-gray-700">{fmt(item.origSize)}</p></div>
                  <div><p className="text-[11px] text-gray-400">处理后</p><p className="text-xs font-semibold text-blue-500">{fmt(item.resultSize)}</p></div>
                  <div><p className="text-[11px] text-gray-400">节省空间</p><p className="text-xs font-semibold text-green-500">{item.saving}</p></div>
                </div>
              </div>;
            })}
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-gray-100">
          <Btn variant="ghost" size="sm" onClick={close}>关闭</Btn>
          <Btn variant="primary" size="sm" disabled={!keptIdx.length} onClick={async()=>{
            if(keptIdx.length===1){const i=keptIdx[0];saveAs(items[i].blob,names[i]||items[i].name)}
            else{const zip=new JSZip();keptIdx.forEach(i=>zip.file(names[i]||items[i].name,items[i].blob));const zipNames={compress:'compressed',crop:'cropped',watermark:'nowatermark',upscale:'upscaled'};saveAs(await zip.generateAsync({type:'blob'}),(zipNames[type]||'processed')+'_images.zip')}
            close()
          }}><Download/>下载保留项 ({keptIdx.length})</Btn>
        </div>
      </div>
    </div>
    {zoomTarget&&<ZoomViewer url={zoomTarget.url} label={zoomTarget.label} onClose={()=>setZoomTarget(null)}/>}
  </>;
}

// ==================== 裁剪结果预览面板（右侧） ====================
function CropResultsPanel(){
  const{cropResults}=useStore();
  const[removed,setRemoved]=useState(new Set());
  const[names,setNames]=useState(()=>cropResults?cropResults.map(it=>it.name):[]);
  useEffect(()=>{if(cropResults)setNames(cropResults.map(it=>it.name))},[cropResults]);
  if(!cropResults||!cropResults.length)return null;
  const keptIdx=cropResults.map((_,i)=>i).filter(i=>!removed.has(i));
  const toggleRemove=i=>setRemoved(s=>{const n=new Set(s);n.has(i)?n.delete(i):n.add(i);return n});
  const updateName=(i,v)=>setNames(prev=>{const n=[...prev];n[i]=v;return n});
  const downloadAll=async()=>{
    if(keptIdx.length===1){const i=keptIdx[0];saveAs(cropResults[i].blob,names[i]||cropResults[i].name);return}
    if(keptIdx.length>1){const zip=new JSZip();keptIdx.forEach(i=>zip.file(names[i]||cropResults[i].name,cropResults[i].blob));saveAs(await zip.generateAsync({type:'blob'}),'images.zip')}
  };
  return <div className="flex-1 flex flex-col bg-[#f5f7fa] overflow-hidden">
    <div className="flex items-center justify-between px-4 py-2.5 bg-white border-b border-gray-100 flex-shrink-0">
      <div className="flex items-center gap-2">
        <span className="text-base font-medium text-gray-700">裁剪预览</span>
        <span className="text-xs text-gray-400">{keptIdx.length}/{cropResults.length} 保留</span>
      </div>
      <button onClick={()=>setCropResults(null)} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"><X size={12}/></button>
    </div>
    <div className="flex-1 overflow-y-auto p-4 space-y-3">
      {cropResults.map((item,i)=>{
        const isOff=removed.has(i);
        return <div key={i} className={`bg-white rounded-xl border border-gray-100 p-3 transition-all ${isOff?'opacity-40 grayscale':'hover:shadow-md'}`}>
          <div className="flex items-center gap-2 mb-2">
            <input type="text" value={names[i]||item.name} onChange={e=>updateName(i,e.target.value)}
              className={`flex-1 min-w-0 text-sm font-medium px-2 py-1.5 rounded border bg-white outline-none transition-all ${isOff?'text-gray-400 line-through border-transparent':'text-gray-700 border-gray-200 focus:border-blue-400'}`}/>
            <button onClick={()=>toggleRemove(i)} className={`p-1 rounded-full transition-colors flex-shrink-0 ${isOff?'bg-gray-200 text-gray-400 hover:bg-gray-300':'bg-red-50 text-red-400 hover:bg-red-100'}`} title={isOff?'恢复此图':'移除此结果'}>
              {isOff?<Plus/>:<X size={12}/>}
            </button>
          </div>
          <div className="flex gap-2 mb-2">
            <div className="flex-1 relative rounded-lg overflow-hidden bg-gray-100">
              <img src={item.origUrl} alt="" className="w-full h-32 object-contain"/>
              <span className="absolute bottom-1 left-1 px-1.5 py-0.5 rounded bg-black/50 text-white text-[11px]">原图</span>
            </div>
            <div className="flex-1 relative rounded-lg overflow-hidden bg-gray-100">
              <img src={item.resultUrl} alt="" className="w-full h-32 object-contain"/>
              <span className="absolute bottom-1 left-1 px-1.5 py-0.5 rounded bg-blue-500/80 text-white text-[11px]">裁剪后</span>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2 text-center">
            <div><p className="text-[11px] text-gray-400">原始</p><p className="text-xs font-semibold text-gray-700">{fmt(item.origSize)}</p></div>
            <div><p className="text-[11px] text-gray-400">裁剪后</p><p className="text-xs font-semibold text-blue-500">{fmt(item.resultSize)}</p></div>
            <div><p className="text-[11px] text-gray-400">节省</p><p className="text-xs font-semibold text-green-500">{item.saving}</p></div>
          </div>
        </div>;
      })}
    </div>
    <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-gray-100 bg-white flex-shrink-0">
      <Btn variant="ghost" size="sm" onClick={()=>setCropResults(null)}>关闭</Btn>
      <Btn variant="primary" size="sm" disabled={!keptIdx.length} onClick={downloadAll}><Download/>一键下载 ({keptIdx.length})</Btn>
    </div>
  </div>;
}

// ==================== IMAGE PREVIEW ====================
function ImagePreview(){
  const{images,previewImg,cropResults}=useStore();
  if(cropResults&&cropResults.length)return <CropResultsPanel/>;
  const current=previewImg?images.find(i=>i.id===previewImg.id):null;
  if(!current)return <div className="flex-1 flex items-center justify-center bg-[#f5f7fa]"><p className="text-base text-gray-400">点击左侧图片进行预览</p></div>;
  const baseSize=current.origSize||current.size;
  const s=current.cSize?((1-current.cSize/baseSize)*100).toFixed(0):null;
  return <div className="flex-1 flex flex-col bg-[#f5f7fa] overflow-hidden">
    <div className="flex items-center justify-between px-4 py-2.5 bg-white border-b border-gray-100 flex-shrink-0">
      <div className="flex items-center gap-2 min-w-0">
        <span className="text-base font-medium text-gray-700 truncate">{current.name}</span>
        <span className="text-xs text-gray-400 flex-shrink-0">{fmt(baseSize)}</span>
        {current.cSize&&<span className="text-xs text-green-500 flex-shrink-0">→ {fmt(current.cSize)} ({s}%)</span>}
      </div>
      <div className="flex items-center gap-1.5 flex-shrink-0">
        {current.w>0&&<span className="text-xs text-gray-400">{current.w}×{current.h}</span>}
        <span className="text-xs text-gray-400 uppercase">{ext(current.type)}</span>
      </div>
    </div>
    <div className="flex-1 flex items-center justify-center p-4 overflow-hidden">
      <img src={current.thumb} alt="" className="max-w-full max-h-full object-contain rounded-lg shadow-sm"/>
    </div>
  </div>;
}

// ==================== 主应用组件 ====================
function App(){
  const{images,tab,sel,preview,previewImg}=useStore();
  const has=images.length>0;
  const tabs=[{id:'compress',l:'压缩',icon:I.zap},{id:'watermark',l:'去水印',icon:I.droplet},{id:'upscale',l:'高清化',icon:I.sparkle},{id:'crop',l:'裁剪',icon:I.scissors},{id:'rename',l:'重命名/转格式',icon:I.tag},{id:'download',l:'下载',icon:Download}];
  const tot=images.reduce((a,i)=>a+i.size,0);const comp=images.reduce((a,i)=>a+(i.cSize||0),0);
  const selCount=sel.size;

  const [isMobile,setIsMobile]=useState(window.innerWidth<=900);
  useEffect(()=>{
    const onResize=()=>setIsMobile(window.innerWidth<=900);
    window.addEventListener('resize',onResize);
    return()=>window.removeEventListener('resize',onResize);
  },[]);

  const [sidebarW,setSidebarW]=useState(isMobile?window.innerWidth:256);
  const [rightW,setRightW]=useState(420);
  const containerRef=useRef(null);
  const handleSidebarDrag=(clientX)=>{
    if(!containerRef.current)return;
    const rect=containerRef.current.getBoundingClientRect();
    setSidebarW(Math.max(200,Math.min(clientX-rect.left,400)));
  };
  const handleRightDrag=(clientX)=>{
    if(!containerRef.current)return;
    const rect=containerRef.current.getBoundingClientRect();
    setRightW(Math.max(300,Math.min(rect.right-clientX,600)));
  };

  return <div className="flex flex-col h-screen">
    <div className="flex items-center h-12 px-5 bg-white border-b border-gray-100 flex-shrink-0">
      <a href="../../" className="flex items-center gap-1 text-sm text-gray-400 hover:text-blue-500 transition-colors mr-4 no-underline">← 工具箱</a>
      <div className="flex items-center gap-2.5"><div className="w-6 h-6 rounded bg-blue-500 flex items-center justify-center text-white"><I.image/></div><span className="text-base font-semibold text-gray-700">图片批量处理</span></div>
    </div>
    <div ref={containerRef} className="flex flex-1 overflow-hidden">
      <div className="flex flex-col bg-white border-r border-gray-100 flex-shrink-0" style={{width:sidebarW}}>
        <div className="flex items-center justify-between px-3 py-2.5 border-b border-gray-50">
          <div className="flex items-center gap-1.5"><span className="text-sm font-medium text-gray-700">图片列表</span><span className="text-[11px] px-1.5 py-0.5 rounded bg-blue-50 text-blue-500 font-medium">{images.length}</span></div>
          {images.length>0&&<button onClick={clearAll} className="text-xs text-gray-400 hover:text-red-400 transition-colors flex items-center gap-0.5"><Trash size={12}/>清空</button>}
        </div>
        {images.length>0&&<div className="flex items-center gap-2 px-3 py-2 border-b border-gray-50">
          <button onClick={selCount===images.length?deselAll:selAll} className="text-xs text-blue-500 hover:text-blue-700 font-medium">{selCount===images.length?'取消全选':'全选'}</button>
          {selCount>0&&<span className="text-xs text-gray-400">已选 {selCount}/{images.length}</span>}
        </div>}
        <div className="flex-1 overflow-y-auto p-1.5 space-y-0.5">{images.length===0?<div className="p-1.5"><UploadZone onFiles={addImages} accept="image/jpeg,image/png,image/webp"/></div>:images.map(img=><ImageCard key={img.id} image={img} selected={sel.has(img.id)} isActive={previewImg?.id===img.id}/>)}</div>
        {images.length>0&&<div className="p-2 border-t border-gray-50"><UploadZone isButton onFiles={addImages} accept="image/jpeg,image/png,image/webp"/></div>}
      </div>
      {!isMobile&&<Divider onDrag={handleSidebarDrag}/>}
      <div className="flex-1 flex overflow-hidden" style={{background:'var(--bg-primary, #f5f7fa)'}}>
        <div className="flex-1 flex flex-col overflow-hidden min-w-0">
          <div className="flex items-center gap-1 px-4 py-2.5 bg-white border-b border-gray-100 flex-shrink-0">
            {tabs.map(t=><button key={t.id} onClick={()=>{_tab=t.id;notify()}} className={`flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm font-medium transition-all ${tab===t.id?'bg-blue-500 text-white':'text-gray-500 hover:bg-gray-100'}`}><t.icon/>{t.l}</button>)}
          </div>
          <div className="flex-1 overflow-hidden">{!has?<EmptyState/>:<div key={tab} className="h-full">{tab==='compress'&&<CompressPanel/>}{tab==='watermark'&&<WatermarkPanel/>}{tab==='upscale'&&<UpscalePanel/>}{tab==='crop'&&<CropPanel/>}{tab==='rename'&&<RenameConvertPanel/>}{tab==='download'&&<DownloadPanel/>}</div>}</div>
        </div>
        {has&&!isMobile&&<>
          <Divider onDrag={handleRightDrag}/>
          <div className="overflow-hidden flex flex-col flex-shrink-0" style={{width:rightW}}><ImagePreview/></div>
        </>}
      </div>
    </div>
    <div className="flex items-center justify-between h-7 px-5 bg-white border-t border-gray-100 flex-shrink-0">
      <div className="flex items-center gap-3 text-xs text-gray-400"><span>{images.length} 张</span><span>{fmt(tot)}</span>{comp>0&&<span className="text-blue-500">压缩后 {fmt(comp)} ({((1-comp/tot)*100).toFixed(1)}% 节省)</span>}</div>
      <div className="flex items-center gap-1 text-xs text-gray-400"><div className="w-1.5 h-1.5 rounded-full bg-green-400"/>就绪</div>
    </div>
    {preview&&<PreviewModal/>}
  </div>;
}

ReactDOM.createRoot(document.getElementById('root')).render(<App/>);
