# 新增工具指南

## 方式一：纯前端工具

适用于不需要后端服务的工具（图片处理、文本转换等）。

1. **创建工具目录**：`tools/my-tool/index.html`

2. **在 `index.html`（主页）添加卡片**：
   ```html
   <a class="tool-card" href="my-tool/" data-color="blue" data-kw="关键词1 关键词2">
       <div class="card-head">
           <div class="card-icon" style="background:rgba(59,130,246,0.12)">🔧</div>
           <div class="card-meta">
               <h4>我的工具</h4>
               <span class="badge">简要说明</span>
           </div>
       </div>
       <div class="card-body">工具描述。</div>
       <div class="card-foot">
           <span class="tag tag-blue">标签1</span>
       </div>
   </a>
   ```

3. `data-color` 支持：`blue`、`green`、`purple`、`orange`、`pink`

## 方式二：前后端工具

适用于需要后端处理的工具。

1. 创建前端页面 `tools/my-tool/index.html`

2. 在 `backend/main.py` 添加 API：
   ```python
   @app.post("/api/my-tool/action")
   async def my_action(req: MyRequest):
       return {"success": True, "data": result}
   ```

3. 如需挂载静态文件，在 `backend/main.py` 末尾添加：
   ```python
   MY_TOOL_DIR = PROJECT_DIR / "tools" / "my-tool"
   if MY_TOOL_DIR.exists():
       app.mount("/tools/my-tool", StaticFiles(directory=str(MY_TOOL_DIR), html=True), name="my-tool")
   ```

## 方式三：新增视频平台解析器

1. 创建 `backend/parsers/myplatform.py`：
   ```python
   DOMAINS = ["myplatform.com"]

   async def parse(url: str) -> dict:
       return {"success": True, "data": {"platform": "myplatform", "title": "...", ...}}
   ```

2. 在 `backend/parsers/__init__.py` 的 `PLATFORM_MAP` 注册：
   ```python
   "myplatform": (myplatform.DOMAINS, myplatform.parse),
   ```

## 方式四：AI 模型驱动工具

适用于需要 AI 模型推理的工具（如智能抠图）。参考 `bg-remover` 实现。

### 后端要点

1. **模型管理**：在 `backend/main.py` 中定义模型字典和加载函数
   ```python
   BG_MODELS = {
       "model_name": "模型描述",
   }
   
   def _get_bg_session(model_name: str = None):
       # 按需加载模型，全局缓存 session
       ...
   ```

2. **结果缓存**：使用 LRU 缓存相同输入的结果，避免重复计算
   ```python
   _bg_cache = OrderedDict()
   _BG_CACHE_MAX = 50
   
   def _cache_key(data: bytes, model: str, quality: str) -> str:
       h = hashlib.md5(data).hexdigest()
       return f"{h}_{model}_{quality}"
   ```

3. **图片预处理**：统一颜色模式、限制尺寸、检测损坏文件
   ```python
   def _preprocess_image(data: bytes, fast: bool = False) -> "Image.Image":
       from PIL import Image
       img = Image.open(io.BytesIO(data))
       img.load()  # 强制解码，检测损坏
       # 统一颜色模式、限制尺寸...
   ```

4. **API 设计**：
   - `GET /api/{tool}/models` — 返回可用模型列表
   - `POST /api/{tool}` — 单张处理（FormData 上传）
   - 异步处理 + 超时保护（`asyncio.wait_for` + `asyncio.to_thread`）

### 前端要点

1. **上传区**：支持拖拽、点击、`Ctrl+V` 粘贴
2. **客户端预缩放**：上传前用 Canvas 缩放，减少传输体积
3. **预览对比**：支持原图/结果/对比三种视图模式
4. **手动编辑**：Canvas 画笔擦除/恢复，支持撤销历史
5. **批量操作**：逐张调用 API，支持全选/批量下载 ZIP

### 新增依赖

在 `requirements.txt` 中添加 AI 相关依赖：
```
rembg>=2.0.50
onnxruntime>=1.16.0
```

在 `launcher.py` 的 `optional` 列表中注册可选依赖：
```python
optional = [
    ('yt_dlp', 'yt-dlp'),
    ('rembg', 'rembg'),
]
```
