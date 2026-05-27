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
