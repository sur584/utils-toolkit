# 小小工具箱

一个轻量级的多功能在线工具集，包含视频解析下载、图片批量处理、AI 智能抠图、溶图合成等实用工具。

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
- AI 自动识别主体，一键去除图片背景，生成透明 PNG
- 基于 rembg + ONNX Runtime，支持 5 种深度学习模型可选
- 手动编辑画笔（擦除/恢复），支持缩放、对比预览
- 批量处理、结果缓存、速度/质量双模式
- 详见 [抠图工具](/tools/bg-remover/)

### 🎨 溶图合成
- 上传底图和多张透明产品主图，拖拽调整位置
- 批量套用模板，一键导出合成图片
- 适用于电商产品图、社交媒体配图等场景
- 详见 [溶图工具](/tools/image-composite/)

## 使用方式

### 双击运行（推荐，无需任何环境）

1. 双击 `app.bat`
2. **自动检测并安装 Python**（无需手动安装，会下载便携版 Python 到项目目录）
3. 自动安装依赖并启动服务
4. 自动打开浏览器

> `app.bat` 会自动处理一切：检测 Python → 下载安装 → 安装依赖 → 启动服务。双击即可使用。

### 手动启动（已安装 Python 的用户）

```bash
python launcher.py
```

## 访问地址

| 地址 | 内容 |
|------|------|
| `http://127.0.0.1:5001/` | 自动跳转到工具箱首页 |
| `http://127.0.0.1:5001/tools/` | 工具箱首页 |
| `http://127.0.0.1:5001/tools/video-tool/` | 视频解析下载 |
| `http://127.0.0.1:5001/tools/image-tool/` | 图片批量处理 |
| `http://127.0.0.1:5001/tools/bg-remover/` | 智能抠图 |
| `http://127.0.0.1:5001/tools/image-composite/` | 溶图合成 |

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
├── app.bat                    # Windows 启动脚本（自动安装 Python + 依赖）
├── launcher.py                # Python 启动器
├── requirements.txt           # Python 依赖清单
├── python/                    # 便携版 Python（自动下载，无需手动操作）
├── models/                    # AI 模型文件（自动下载）
├── .gitignore
├── backend/                   # 后端服务
│   ├── main.py                # FastAPI 应用
│   ├── decrypt.py             # 微信视频号解密
│   └── parsers/               # 多平台视频解析器
│       ├── __init__.py        # 统一入口
│       ├── _utils.py          # 共用函数
│       ├── douyin.py          # 抖音
│       ├── bilibili.py        # B站
│       └── ...                # 共 10 个平台
├── tools/
│   ├── libs/                  # 公共前端库
│   │   ├── tailwind.js
│   │   ├── react.production.min.js
│   │   ├── react-dom.production.min.js
│   │   ├── babel.min.js
│   │   ├── jszip.min.js
│   │   └── FileSaver.min.js
│   ├── video-tool/            # 视频解析下载
│   │   ├── index.html
│   │   ├── css/style.css
│   │   └── js/app.js
│   ├── image-tool/            # 图片批量处理
│   │   └── index.html
│   ├── bg-remover/            # AI 智能抠图
│   │   └── index.html
│   └── image-composite/       # 溶图合成
│       └── index.html
└── docs/
    └── feature-image-composite-requirements.md
```

## 技术栈

- **后端**：FastAPI + uvicorn
- **前端**：原生 HTML/CSS/JS（视频工具）、React 18（图片工具、抠图工具、溶图工具）
- **视频解析**：自定义多平台解析器 + yt-dlp
- **AI 抠图**：rembg + ONNX Runtime（支持 u2netp / u2net / isnet-general-use / u2net_human_seg / silueta 五种模型）
- **图片处理**：Pillow (PIL)

## License

MIT
