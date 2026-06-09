"""
打包 utils-toolkit 为免安装便携版
下载 Python embeddable 包 + 预装所有依赖 + 复制项目文件
生成一个可直接拷贝到新设备运行的文件夹

用法：python build_portable.py [--output D:\output] [--skip-models]
"""

import os
import sys
import shutil
import subprocess
import zipfile
import urllib.request
import argparse
import tempfile
from pathlib import Path

# ── 配置 ──────────────────────────────────────────────────
PYTHON_VERSION = "3.11.9"
PYTHON_EMBED_URL = (
    f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
)
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.resolve()

# 需要复制的项目文件/目录
COPY_ITEMS = [
    "backend/",
    "tools/",
    "models/",
    "assets/",
    "src/",
    "launcher.py",
    "requirements.txt",
    "index.html",
    "404.html",
]

# 生成的便携版文件夹名
PORTABLE_NAME = f"utils-toolkit-portable"


def download_file(url, dest, desc=""):
    """下载文件，显示进度"""
    print(f"  下载 {desc or url} ...")
    try:
        urllib.request.urlretrieve(url, dest)
        size_mb = os.path.getsize(dest) / 1024 / 1024
        print(f"  完成 ({size_mb:.1f} MB)")
    except Exception as e:
        print(f"  下载失败: {e}")
        print(f"  请手动下载: {url}")
        print(f"  保存到: {dest}")
        sys.exit(1)


def setup_python_embed(work_dir, portable_dir):
    """下载并配置 Python embeddable 包"""
    python_dir = portable_dir / "python"
    python_dir.mkdir(parents=True, exist_ok=True)

    zip_path = work_dir / "python-embed.zip"

    # 1. 下载 Python embeddable 包
    print(f"\n[1/5] 下载 Python {PYTHON_VERSION} embeddable 包...")
    download_file(PYTHON_EMBED_URL, zip_path, f"Python {PYTHON_VERSION}")

    # 2. 解压
    print("  解压中...")
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(python_dir)
    zip_path.unlink()

    # 3. 修改 ._pth 文件以启用 import site
    pth_files = list(python_dir.glob("python*._pth"))
    if pth_files:
        pth = pth_files[0]
        content = pth.read_text(encoding="utf-8")
        # 取消注释 import site
        content = content.replace("#import site", "import site")
        # 添加 Lib/site-packages 路径
        if "Lib/site-packages" not in content:
            content += "\nLib/site-packages\n"
        pth.write_text(content, encoding="utf-8")
        print(f"  已配置 {pth.name}")
    else:
        print("  [WARN] 未找到 ._pth 文件")
        sys.exit(1)

    # 4. 安装 pip
    print("  安装 pip...")
    get_pip_path = work_dir / "get-pip.py"
    download_file(GET_PIP_URL, get_pip_path, "get-pip.py")

    result = subprocess.run(
        [str(python_dir / "python.exe"), str(get_pip_path)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  pip 安装失败:\n{result.stderr}")
        sys.exit(1)
    get_pip_path.unlink()
    print("  pip 安装完成")

    # 5. 配置 pip 使用清华镜像（可选，加速国内下载）
    pip_conf = python_dir / "Lib" / "site-packages" / "pip" / "_internal" / "configuration"
    # 不写死镜像，让用户自行决定

    return python_dir


def install_deps(python_dir):
    """安装 Python 依赖"""
    print("\n[2/5] 安装 Python 依赖...")
    req_file = PROJECT_ROOT / "requirements.txt"

    # 设置环境变量确保正确安装
    env = os.environ.copy()
    env["PYTHONPATH"] = ""

    # 使用 --target 安装到 python/Lib/site-packages
    site_packages = python_dir / "Lib" / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)

    # 先升级 pip（embeddable 包的 pip 可能较旧）
    subprocess.run(
        [str(python_dir / "python.exe"), "-m", "pip", "install", "--upgrade", "pip"],
        capture_output=True
    )

    # 安装依赖
    cmd = [
        str(python_dir / "python.exe"), "-m", "pip", "install",
        "-r", str(req_file),
        "-i", "https://pypi.tuna.tsinghua.edu.cn/simple",
    ]
    print(f"  执行: pip install -r requirements.txt")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  [WARN] 部分依赖安装失败:")
        print(result.stderr[-500:] if len(result.stderr) > 500 else result.stderr)
        print("  将继续打包，缺失功能在目标设备上可手动安装")
    else:
        print("  所有依赖安装完成")

    # 显示已安装包数量
    result = subprocess.run(
        [str(python_dir / "python.exe"), "-m", "pip", "list", "--format=columns"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        lines = result.stdout.strip().split("\n")
        print(f"  共安装 {len(lines) - 2} 个包")


def copy_project(portable_dir, skip_models=False):
    """复制项目文件到便携目录"""
    print("\n[3/5] 复制项目文件...")
    app_dir = portable_dir / "app"
    app_dir.mkdir(parents=True, exist_ok=True)

    for item in COPY_ITEMS:
        src = PROJECT_ROOT / item
        dst = app_dir / item

        if not src.exists():
            print(f"  [SKIP] {item} 不存在")
            continue

        if skip_models and item == "models/":
            print(f"  [SKIP] models/ (跳过模型)")
            dst.mkdir(parents=True, exist_ok=True)
            continue

        if src.is_dir():
            print(f"  复制 {item} ({_dir_size(src)})...")
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            print(f"  复制 {item}...")
            shutil.copy2(src, dst)

    print("  项目文件复制完成")


def create_launchers(portable_dir):
    """创建启动脚本"""
    print("\n[4/5] 创建启动脚本...")

    # Windows bat 启动器
    bat_content = f'''@echo off
chcp 65001 >nul
title Utils Toolkit v3.0

set "PYTHON_DIR=%~dp0python"
set "APP_DIR=%~dp0app"
set "PATH=%PYTHON_DIR%;%PYTHON_DIR%\\Scripts;%PATH%"
set "PYTHONHOME=%PYTHON_DIR%"
set "PYTHONPATH=%APP_DIR%"

cd /d "%APP_DIR%"

echo ========================================
echo   Utils Toolkit v3.0
echo   Video | Image | Background Remover
echo ========================================
echo.

"%PYTHON_DIR%\\python.exe" launcher.py %*

echo.
echo 服务已停止，按任意键退出...
pause >nul
'''
    bat_path = portable_dir / "启动工具箱.bat"
    bat_path.write_text(bat_content, encoding="utf-8")
    print(f"  创建 {bat_path.name}")

    # 也创建一个不自动打开浏览器的版本
    bat_content2 = bat_content.replace(
        'launcher.py %*',
        'launcher.py --no-browser %*'
    )
    bat_path2 = portable_dir / "启动工具箱(不打开浏览器).bat"
    bat_path2.write_text(bat_content2, encoding="utf-8")
    print(f"  创建 {bat_path2.name}")

    # 依赖检查脚本
    bat_check = f'''@echo off
chcp 65001 >nul
set "PYTHON_DIR=%~dp0python"
set "PATH=%PYTHON_DIR%;%PYTHON_DIR%\\Scripts;%PATH%"
set "PYTHONHOME=%PYTHON_DIR%"
set "PYTHONPATH=%~dp0app"
cd /d "%~dp0app"
"%PYTHON_DIR%\\python.exe" launcher.py --check-deps-only
echo.
pause
'''
    check_path = portable_dir / "检查依赖.bat"
    check_path.write_text(bat_check, encoding="utf-8")
    print(f"  创建 {check_path.name}")


def _dir_size(path):
    """计算目录大小的可读字符串"""
    total = 0
    for f in Path(path).rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    if total > 1024 * 1024 * 1024:
        return f"{total / 1024 / 1024 / 1024:.1f} GB"
    elif total > 1024 * 1024:
        return f"{total / 1024 / 1024:.1f} MB"
    else:
        return f"{total / 1024:.0f} KB"


def create_readme(portable_dir):
    """创建使用说明"""
    readme = f'''# Utils Toolkit v3.0 - 便携版

## 使用方法

### Windows
双击 `启动工具箱.bat` 即可启动

### 首次运行
1. 启动后会自动安装缺失的 Python 依赖（约 1-3 分钟）
2. 首次使用抠图功能时，会自动下载 AI 模型（约 1.4GB）
3. 之后再启动就是秒开

## 功能列表

| 工具 | 说明 | 依赖 |
|------|------|------|
| 视频工具 | 视频解析下载 | yt-dlp |
| 图片工具 | 图片批量处理 | - |
| 抠图工具 | AI 智能抠图 | rembg, onnxruntime |
| 溢图工具 | 图片合成 | - |
| 去文字 | 图片去文字/水印 | rapidocr, simple-lama |

## 需要的环境

- Windows 10/11
- Python 3.10+ (已内置，无需安装)
- 首次运行需联网（安装依赖和下载模型）

## 端口

默认 5001，可通过 `--port 8080` 修改

## 文件结构

```
utils-toolkit-portable/
├── python/          # 免安装 Python（内置）
├── app/             # 项目文件
│   ├── backend/     # 后端服务
│   ├── tools/       # 前端页面
│   ├── models/      # AI 模型
│   ├── assets/      # 前端资源
│   └── launcher.py  # 启动器
├── 启动工具箱.bat    # 启动脚本
└── README.md        # 本文件
```
'''
    readme_path = portable_dir / "README.md"
    readme_path.write_text(readme.strip(), encoding="utf-8")
    print(f"  创建 README.md")


def main():
    parser = argparse.ArgumentParser(description="打包 utils-toolkit 为便携版")
    parser.add_argument("--output", "-o", default=str(PROJECT_ROOT.parent),
                        help="输出目录（默认：项目父目录）")
    parser.add_argument("--skip-models", action="store_true",
                        help="跳过复制模型文件（节省空间，模型需单独下载）")
    args = parser.parse_args()

    output_base = Path(args.output)
    portable_dir = output_base / PORTABLE_NAME

    print("=" * 50)
    print("  Utils Toolkit 便携版打包工具")
    print("=" * 50)

    # 清理旧的打包目录
    if portable_dir.exists():
        print(f"\n  清理旧目录: {portable_dir}")
        shutil.rmtree(portable_dir)

    with tempfile.TemporaryDirectory() as work_dir:
        work_path = Path(work_dir)

        # 1. 下载配置 Python embeddable
        python_dir = setup_python_embed(work_path, portable_dir)

        # 2. 安装依赖
        install_deps(python_dir)

        # 3. 复制项目文件
        copy_project(portable_dir, skip_models=args.skip_models)

        # 4. 创建启动器
        create_launchers(portable_dir)

        # 5. 创建说明
        create_readme(portable_dir)

    # 统计最终大小
    total_size = _dir_size(portable_dir)
    print(f"\n[5/5] 打包完成！")
    print(f"  输出目录: {portable_dir}")
    print(f"  总大小: {total_size}")
    print(f"  Python: {PYTHON_VERSION} embeddable")
    print(f"\n将整个 {PORTABLE_NAME} 文件夹拷贝到目标设备即可使用")
    print(f"双击 启动工具箱.bat 启动")


if __name__ == "__main__":
    main()
