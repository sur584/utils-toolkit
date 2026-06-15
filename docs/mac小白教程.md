# Mac 新手配置指南

本教程面向**无任何开发经验**的 Mac 用户，手把手教你运行小小工具箱。

---

## 目录

- [1. 打开终端](#1-打开终端)
- [2. 安装 Homebrew](#2-安装-homebrew)
- [3. 安装 Python](#3-安装-python)
- [4. 安装 ffmpeg](#4-安装-ffmpeg)
- [5. 获取项目](#5-获取项目)
- [6. 启动工具箱](#6-启动工具箱)
- [7. 常见问题](#7-常见问题)

---

## 1. 打开终端

终端是 Mac 上运行命令的地方，后续所有操作都在这里完成。

1. 点击屏幕右上角的 **放大镜图标**（Spotlight 搜索）
2. 输入 `终端`
3. 点击 **终端.app**（或按回车）

你会看到一个黑底白字的窗口，这就是终端。后面所有带 `$` 开头的命令，都是在终端里输入的（`$` 本身不需要输入）。

---

## 2. 安装 Homebrew

Homebrew 是 Mac 的包管理器，用来安装 Python 和其他工具。

### 2.1 安装 Xcode Command Line Tools

在终端粘贴以下命令，按回车：

```bash
xcode-select --install
```

会弹出一个窗口，点击 **"安装"**，等待完成（约 5-10 分钟）。

### 2.2 安装 Homebrew

在终端粘贴以下命令，按回车：

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

过程中会提示按回车继续，输入你的 Mac 密码（输入时屏幕不会显示字符，这是正常的），然后等待安装完成（约 5-15 分钟，取决于网速）。

> **如果遇到网络问题**：中国大陆用户可以使用国内镜像源安装。如果上述命令超时或报错，改用：
>
> ```bash
> /bin/bash -c "$(curl -fsSL https://gitee.com/ineo6/homebrew-install/raw/master/install.sh)"
> ```

### 2.3 验证安装

```bash
brew --version
```

如果显示版本号（如 `Homebrew 4.x.x`），说明安装成功。

---

## 3. 安装 Python

```bash
brew install python@3.12
```

等进度条跑完即可，约 3-10 分钟。

验证安装：

```bash
python3 --version
```

应输出 `Python 3.12.x`。

---

## 4. 安装 ffmpeg

ffmpeg 是视频/音频处理工具，部分功能需要它：

```bash
brew install ffmpeg
```

验证安装：

```bash
ffmpeg -version
```

---

## 5. 获取项目

### 方式一：下载 ZIP（推荐新手）

1. 打开浏览器，访问项目地址
2. 点击 **Code** → **Download ZIP**
3. 解压 ZIP 文件，得到 `utils-toolkit-main` 文件夹
4. **重命名**为 `utils-toolkit`（去掉 `-main`）
5. 将这个文件夹放到 **文稿** 或你喜欢的任意位置

### 方式二：git clone（如果你会使用 git）

```bash
cd ~/Documents
git clone <项目地址>
cd utils-toolkit
```

---

## 6. 启动工具箱

### 一键启动（推荐）

在终端中，**先进入项目目录**（将下面的路径替换成你实际放的位置）：

```bash
cd ~/Documents/utils-toolkit
```

然后启动：

```bash
python3 launcher.py
```

首次启动会自动安装依赖（约 5-20 分钟，取决于网速），之后会自动打开浏览器。

**关键步骤说明：**

| 步骤 | 说明 | 预估时间 |
|------|------|----------|
| 检查依赖 | 自动检测已安装/未安装的包 | 几秒钟 |
| 安装依赖 | 自动 pip install 所有需要的库 | 5-20 分钟 |
| 检查前端构建 | 构建前端页面（仅首次） | 1-2 分钟 |
| 启动服务 | 在端口 5001 启动服务器 | 2-3 秒 |

看到以下界面表示启动成功：

```
==================================================
  小小工具箱 3.0.0
  视频解析下载 | 图片批量处理 | AI 智能抠图
==================================================

[1/4] 检查依赖...
  [OK] httpx
  [OK] fastapi
  ...

[2/4] 检查前端构建...
  [OK] 前端构建完成

[3/4] 启动服务...

  本机访问: http://127.0.0.1:5001/tools/
  局域网:   http://192.168.x.x:5001/tools/

  视频:   http://127.0.0.1:5001/tools/video-tool/
  图片:   http://127.0.0.1:5001/tools/image-tool/
  ...

  按 Ctrl+C 停止服务
==================================================
```

### 停止服务

在终端中按 `Ctrl + C` 即可停止。

---

## 7. 常见问题

### Q: `python3` 命令找不到？

确保 Python 已正确安装：

```bash
brew list python@3.12
```

如果没安装，重新执行：

```bash
brew install python@3.12
```

安装后需要让 Homebrew 的 Python 生效（一般 brew 会自动处理，如果不行）：

```bash
export PATH="/opt/homebrew/bin:$PATH"
```

然后把上面这行加到 `~/.zshrc` 中（这样每次打开终端都生效）：

```bash
echo 'export PATH="/opt/homebrew/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### Q: 安装依赖很慢或卡住？

原因是网络问题。可以改用国内镜像源：

```bash
python3 -m pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/
```

然后重新运行 `python3 launcher.py`。

如果还是慢，可以手动分段安装：

```bash
# 先装核心依赖
python3 -m pip install fastapi uvicorn httpx yt-dlp pydantic python-multipart aiofiles

# 再装图片处理相关
python3 -m pip install rembg onnxruntime opencv-python-headless Pillow scipy psutil

# 最后装视频文案提取相关
python3 -m pip install faster-whisper opencc-python-reimplemented python-dotenv
```

### Q: 端口被占用

默认端口是 5001，如果被占用可以指定其他端口：

```bash
python3 launcher.py --port 5002
```

### Q: 浏览器没有自动打开

手动在浏览器地址栏输入：

```
http://127.0.0.1:5001/tools/
```

### Q: 视频解析/下载功能报错 "ffmpeg not found"

确认 ffmpeg 已安装：

```bash
brew install ffmpeg
```

安装后重新启动工具箱。

### Q: 智能抠图功能安装失败

rembg 和 onnxruntime 体积较大，在某些 Mac 机型上（特别是 Apple Silicon），onnxruntime 需要额外配置：

```bash
# 卸载 CPU 版本
python3 -m pip uninstall onnxruntime

# 安装 Apple Silicon 优化版
python3 -m pip install onnxruntime-silicon
```

### Q: 视频文案提取（faster-whisper）运行很慢？

首次运行 faster-whisper 会自动下载模型文件（几百 MB），后续使用会更快。如果你有 GPU（Apple Silicon M 系列芯片），faster-whisper 会自动利用 GPU 加速。

如果想先用小模型测试，可以在 `transcript-config.json` 中配置，或暂时跳过 faster-whisper 的安装。

---

## 附录：需要的软件一览

| 软件 | 用途 | 安装方式 | 大小 |
|------|------|----------|------|
| Xcode CLI Tools | 编译工具 | `xcode-select --install` | ~1.5 GB |
| Homebrew | 包管理器 | 脚本安装 | ~500 MB |
| Python 3.12 | 运行环境 | `brew install python@3.12` | ~50 MB |
| ffmpeg | 视频处理 | `brew install ffmpeg` | ~100 MB |
| Python 依赖库 | 项目功能 | `pip install` 自动完成 | ~1-2 GB |

**总计约 3-4 GB 磁盘空间**，大部分是 Xcode CLI Tools 和 pip 包。

## 附录：目录结构说明

```
utils-toolkit/
├── launcher.py          # 启动脚本（双击或 python3 运行）
├── requirements.txt     # Python 依赖清单
├── app.sh               # Mac/Linux 一键启动脚本
├── backend/             # 后端服务（FastAPI）
├── tools/               # 前端页面（可直接访问）
├── transcript-config.json # 视频文案提取配置
└── docs/                # 文档
```

日常使用只需关注 `launcher.py`，其他文件会自动处理。
