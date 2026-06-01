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

## 方式四：AI 模型驱动工具（V3.0 架构）

适用于需要 AI 模型推理的工具（如智能抠图）。参考 `bg-remover` 实现。

### 后端架构（services 层）

V3.0 将 AI 工具拆分为独立服务模块，位于 `backend/services/`：

| 模块 | 职责 |
|------|------|
| `model_manager.py` | 模型注册、加载、Session 缓存、线程安全 |
| `image_classifier.py` | 图片类型分类（MobileNetV3 ONNX） |
| `model_router.py` | 根据分类+负载自动选模型 |
| `image_optimizer.py` | 模型相关图片预处理（尺寸、颜色模式） |
| `post_processor.py` | 边缘优化（高斯羽化、Alpha 优化、去白边） |
| `task_queue.py` | ThreadPoolExecutor 并发批量处理 |
| `disk_cache.py` | 磁盘持久化 LRU 缓存（300条，7天TTL） |

### 后端要点

1. **模型管理**：`ModelManager` 类集中管理模型生命周期
   ```python
   model_manager = ModelManager()
   session = model_manager.get_session("bria-rmbg")
   ```

2. **智能路由**：`ModelRouter` 根据图片分类自动选模型
   ```python
   model = model_router.select_model(classification="product", batch_size=10)
   ```

3. **磁盘缓存**：`DiskCache` 替代内存缓存，支持 TTL 和容量限制
   ```python
   disk_cache = DiskCache(cache_dir="cache", max_entries=300, ttl_days=7)
   disk_cache.put(key, png_bytes, metadata={"model": "bria-rmbg"})
   ```

4. **并发处理**：`TaskQueue` 使用 ThreadPoolExecutor
   ```python
   results = await task_queue.process_batch(tasks, process_fn)
   ```

5. **API 设计**：
   - `GET /api/{tool}/models` — 返回可用模型列表
   - `POST /api/{tool}` — 单张处理（FormData 上传）
   - `POST /api/{tool}-batch` — 批量并发处理
   - `POST /api/{tool}-batch-stream` — SSE 实时进度
   - 响应头携带元数据：`X-Image-Classification`, `X-Model-Used`, `X-Cache-Hit`

### 前端要点

1. **上传区**：支持拖拽、点击、`Ctrl+V` 粘贴
2. **客户端预缩放**：上传前用 Canvas 缩放，减少传输体积
3. **自动重试**：失败自动重试 2 次
4. **并发批量**：前端 3 路 worker 并发处理，实时进度显示
5. **预览对比**：支持原图/结果/对比三种视图模式
6. **手动编辑**：Canvas 画笔擦除/恢复，支持撤销历史
7. **导出格式**：PNG / WebP 可选，批量 ZIP 打包
8. **开发者模式**：三击版本徽章显示分类/模型/缓存/耗时信息

### 新增依赖

在 `requirements.txt` 中添加：
```
rembg>=2.0.50
onnxruntime>=1.16.0
opencv-python-headless>=4.8.0
psutil>=5.9.0
scipy>=1.11.0
Pillow>=10.0.0
```

在 `launcher.py` 的 `optional` 列表中注册可选依赖：
```python
optional = [
    ('yt_dlp', 'yt-dlp'),
    ('rembg', 'rembg'),
    ('cv2', 'opencv-python-headless'),
    ('psutil', 'psutil'),
    ('scipy', 'scipy'),
]
```
