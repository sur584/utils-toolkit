# 小小工具箱

一个轻量级的多功能在线工具集，包含视频解析下载、图片批量处理、AI 智能抠图、溶图合成、视频文案提取等实用工具。

## 包含工具

### 🎬 视频解析下载
- 支持抖音、B站、小红书、TikTok、YouTube、Instagram、Twitter/X、微博、西瓜视频、微信视频号等 10+ 平台
- 粘贴分享文本自动提取链接并解析
- 支持视频下载、复制直链、在线预览、批量解析、历史记录
- 详见 [视频工具](/tools/video-tool/)

### 🖼️ 图片批量处理
- 图片压缩（Canvas 压缩，二分法查找最佳质量）
- 图片裁剪（支持多种比例、形状、社交媒体尺寸预设）
- 批量处理、格式转换
- 详见 [图片工具](/tools/image-tool/)

### ✂️ 智能抠图
- AI 自动识别图片类型（商品/人物/宠物/通用），自动选择最佳模型
- 基于 rembg + ONNX Runtime，支持 rmbg-2.0 / ISNet / U2Net 三种模型
- 图片类型识别：MobileNetV3 ONNX 推理分类
- 智能模型路由：根据图片类型、CPU 负载、批量大小自动选模型
- 并发批量处理（ThreadPoolExecutor），磁盘持久化缓存（300条，7天TTL）
- 边缘优化：高斯羽化、Alpha 优化、去白边
- 手动编辑画笔（擦除/恢复），支持缩放、对比预览
- 支持 PNG / WebP 导出，批量 ZIP 打包
- 详见 [抠图工具](/tools/bg-remover/)

### 🎨 溶图合成
- 上传底图和多张透明产品主图，拖拽调整位置
- 批量套用模板，一键导出合成图片
- 适用于电商产品图、社交媒体配图等场景
- 详见 [溶图工具](/tools/image-composite/)

### 📝 视频文案提取
- 粘贴视频链接自动提取文案，支持字幕提取 + AI 语音识别（faster-whisper）
- 支持抖音、B站、YouTube、TikTok 等主流平台
- 支持本地 GPU 加速和云端 ASR 回退
- 详见 [视频文案提取](/tools/transcript/)

## 使用方式

### 双击运行（推荐，无需任何环境）

1. 双击 `app.bat`
2. 自动安装依赖
3. 首次运行自动构建前端，后续跳过
4. 启动服务并打开浏览器

> `app.bat` 会自动处理一切：检测 Python → 安装依赖 → 构建前端 → 启动服务。双击即可使用。

### 手动启动（已安装 Python 的用户）

```bash
python launcher.py
```

### 重新构建前端 （白屏）

修改了 `src/` 下的前端源码后，双击 `rebuild.bat` 或运行：

```bash
npx vite build
```

## 访问地址

| 地址 | 内容 |
|------|------|
| `http://127.0.0.1:5001/` | 自动跳转到工具箱首页 |


## 环境要求

- **图片处理**：无需任何环境，直接浏览器打开即可使用
- **智能抠图**：需要 Python 3.10+，rembg、onnxruntime、Pillow
- **视频解析下载**：需要 Python 3.10+，yt-dlp
  - **无 Python 环境？** 直接双击 `app.bat`，会自动下载便携版 Python 到项目 `python/` 目录，无需管理员权限
  - 已有 Python？`app.bat` 会自动检测并跳过安装，直接启动

## 项目结构

```
utils-toolkit/
├── index.html                 # 工具箱主页
├── app.bat / app.sh           # 一键启动脚本
├── launcher.py                # Python 启动器（统一依赖管理）
├── rebuild.bat                # 重新构建前端（修改源码后双击）
├── build.bat                  # 构建前端脚本
├── build_portable.py          # 便携版打包脚本
├── vite.config.js             # Vite 构建配置（多页面 + 构建后处理）
├── tailwind.config.js         # Tailwind CSS 配置
├── requirements.txt           # Python 依赖清单
├── transcript-config.json     # 云端 ASR 提供商配置
├── models/                    # AI 模型文件（自动下载）
├── cache/                     # 缓存目录
├── .gitignore
│
├── src/                       # 前端源码（Vite 构建）
│   ├── shared/                # 共享模块（消除工具间）
│   │   ├── icons.jsx          # 共享 SVG 图标组件
│   │   ├── components.jsx     # 共享 UI 组件（Btn, UploadZone, Divider, EmptyState, ZoomControls）
│   │   ├── hooks.js           # 共享 hooks（useZoomPan）
│   │   ├── download.js        # 共享下载辅助函数
│   │   ├── utils.js           # 共享工具函数
│   │   └── store.js           # 共享状态管理工厂
│   ├── bg-remover/main.jsx    # AI 智能抠图
│   ├── text-remover/main.jsx  # 智能去文字
│   ├── image-tool/main.jsx    # 图片批处理
│   ├── watermark-tool/main.jsx # 视频去水印
│   └── image-composite/main.jsx # 溶图合成
│
├── backend/                   # 后端服务
│   ├── main.py                # FastAPI 入口（精简版，~100 行）
│   ├── config.py              # 路径常量、日志配置
│   ├── deps.py                # 共享依赖、Pydantic 模型
│   ├── decrypt.py             # 微信视频号解密
│   ├── routers/               # 路由模块（从 main.py 拆分）
│   │   ├── video.py           # 视频解析路由
│   │   ├── bg_remove.py       # 抠图路由
│   │   ├── text_remove.py     # 去字路由
│   │   ├── transcript.py      # 文案提取 API 路由
│   │   ├── watermark.py       # 去水印路由
│   │   ├── history.py         # 历史记录路由
│   │   └── static.py          # 静态文件 + 首页路由
│   ├── parsers/               # 多平台视频解析器（10 个平台）
│   ├── transcript/            # 文案提取后端模块
│   │   ├── pipeline.py        # 文案提取管线
│   │   ├── cloud_asr.py       # 云端 ASR 接入
│   │   ├── cloud_config.py    # 云端配置管理
│   │   ├── settings.py        # 设置管理
│   │   ├── ytdlp_utils.py     # yt-dlp 工具函数
│   │   ├── temp_manager.py    # 临时文件管理
│   │   ├── asr/               # ASR 模块
│   │   └── platforms/         # 平台适配器
│   └── services/              # 业务服务层
│       ├── bg_remove_service.py  # 抠图管线服务
│       ├── download_service.py   # 下载策略服务
│       ├── model_manager.py      # 模型管理器
│       ├── image_classifier.py   # 图片分类（MobileNetV3）
│       ├── model_router.py       # 智能模型路由
│       ├── image_optimizer.py    # 图片预处理
│       ├── post_processor.py     # 边缘优化
│       ├── task_queue.py         # 并发任务队列
│       └── disk_cache.py         # 磁盘缓存
│
├── tools/                     # 构建产物 + 静态前端
│   ├── libs/                  # 公共前端库
│   ├── video-tool/            # 视频解析下载（vanilla JS）
│   ├── image-tool/            # 图片批处理（构建产物）
│   ├── bg-remover/            # AI 智能抠图（构建产物）
│   ├── text-remover/          # 智能去文字（构建产物）
│   ├── image-composite/       # 溶图合成（构建产物）
│   ├── watermark-tool/        # 视频去水印（构建产物）
│   └── transcript/            # 视频文案提取（前端页面）
│
└── docs/
    ├── TOOLS_GUIDE.md         # 开发者指南
    └── feature-image-composite-requirements.md
```

## 技术栈

- **后端**：FastAPI + uvicorn
- **前端**：原生 HTML/CSS/JS（视频工具）、React 18 + Vite（图片工具、抠图工具、去字工具、溶图工具）
- **视频解析**：自定义多平台解析器 + yt-dlp
- **AI 抠图**：rembg + ONNX Runtime + MobileNetV3（自动选择 rmbg-2.0 / isnet-general-use / u2net）
- **语音识别**：faster-whisper（本地 GPU 加速）+ 云端 ASR 回退
- **图片处理**：Pillow (PIL)

## 常见问题

### 图片处理工具白屏

**现象**：访问"智能抠图"、"图片批处理"等工具页面时，页面一片空白，但服务器没有报错。

**原因**：浏览器在加载工具的 JavaScript 文件时，因为缺少一个安全标记（CORS 头），浏览器会静默拒绝执行脚本，导致页面无法渲染。

**一键修复**：双击 `app.bat` 或运行 `python launcher.py` 即可。

首次运行会自动构建前端，后续启动直接跳过。修改了前端源码后，双击 `rebuild.bat` 重新构建。

## 最近更新

### 2025-06-15
- **新增** 视频文案提取工具：支持多平台视频链接文案提取，集成 faster-whisper 本地识别与云端 ASR 回退
- **新增** 视频去水印工具（WebUI）
- **优化** 项目结构，新增 transcript 后端模块

### 2025-06-05
- **新增** 溶图合成功能
- **优化** 智能抠图边缘处理与批量导出

### 2025-06-01
- **重构** 后端架构，拆分为 routers / services 模块
- **新增** AI 智能抠图，支持 rmbg-2.0 / ISNet / U2Net 三种模型

## License

MIT
