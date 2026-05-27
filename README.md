# 小小工具箱

一个轻量级的多功能在线工具集，包含视频解析下载、图片批量处理等实用工具。

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

## 使用方式

### 双击运行（推荐）

1. 双击 `app.bat`
2. 自动安装依赖并启动 FastAPI 服务
3. 自动打开浏览器

### 手动启动

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

## 环境要求

- **图片处理**：无需任何环境，直接浏览器打开
- **视频解析下载**：需要 Python 3.10+，首次运行自动安装依赖（yt-dlp、fastapi、uvicorn、httpx）

## 项目结构

```
utils-toolkit/
├── index.html                 # 工具箱主页
├── app.bat                    # Windows 启动脚本
├── launcher.py                # Python 启动器
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
│   ├── video-tool/            # 视频解析下载
│   │   ├── index.html
│   │   ├── css/style.css
│   │   └── js/app.js
│   └── image-tool/            # 图片批量处理
│       └── index.html
```

## 技术栈

- **后端**：FastAPI + uvicorn
- **前端**：原生 HTML/CSS/JS（视频工具）、React 18（图片工具）
- **视频解析**：自定义多平台解析器
- **视频下载**：yt-dlp

## License

MIT
