"""
Utils Toolkit Launcher
自动启动 FastAPI 服务并打开浏览器
用法：python launcher.py [--port 5001] [--no-browser]
"""
import sys
import os
import time
import subprocess
import threading
import webbrowser
import argparse

# 切换到脚本所在目录
os.chdir(os.path.dirname(os.path.abspath(__file__)))


def check_and_install_deps():
    """检查并安装依赖（核心依赖必须，其余可选）"""
    required = [
        ('httpx', 'httpx'),
        ('fastapi', 'fastapi'),
        ('uvicorn', 'uvicorn'),
        ('pydantic', 'pydantic'),
        ('multipart', 'python-multipart'),
    ]
    optional = [
        ('yt_dlp', 'yt-dlp'),
        ('rembg', 'rembg'),
        ('cv2', 'opencv-python-headless'),
        ('psutil', 'psutil'),
        ('scipy', 'scipy'),
        ('rapidocr_onnxruntime', 'rapidocr-onnxruntime'),
        ('simple_lama_inpainting', 'simple-lama-inpainting'),
        # 视频文案提取（transcript）
        ('opencc', 'opencc-python-reimplemented'),
        ('dotenv', 'python-dotenv'),
        ('aiofiles', 'aiofiles'),
        ('faster_whisper', 'faster-whisper'),
    ]

    missing_req = []
    missing_opt = []

    for import_name, pip_name in required:
        try:
            __import__(import_name)
            print(f'  [OK] {pip_name}')
        except ImportError:
            missing_req.append(pip_name)

    for import_name, pip_name in optional:
        try:
            __import__(import_name)
            print(f'  [OK] {pip_name}')
        except ImportError:
            missing_opt.append(pip_name)

    if not missing_req and not missing_opt:
        return

    if missing_req:
        print(f'  [...] 缺少核心依赖: {", ".join(missing_req)}')
    if missing_opt:
        print(f'  [...] 缺少可选依赖: {", ".join(missing_opt)}（视频/抠图功能将不可用）')

    # 分离安装：核心依赖必须成功，可选依赖失败不影响启动
    if missing_req:
        print(f'  [...] 正在安装核心依赖: {", ".join(missing_req)} ...')
        try:
            subprocess.check_call(
                [sys.executable, '-m', 'pip', 'install'] + missing_req,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            print(f'  [OK] 核心依赖安装完成')
        except Exception:
            env = os.environ.copy()
            for k in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
                env.pop(k, None)
            try:
                subprocess.check_call(
                    [sys.executable, '-m', 'pip', 'install', '--no-proxy'] + missing_req,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
                )
                print(f'  [OK] 核心依赖安装完成（无代理模式）')
            except Exception as e2:
                print(f'  [ERROR] 核心依赖安装失败: {e2}')
                print(f'         请手动执行: {sys.executable} -m pip install {" ".join(missing_req)}')
                sys.exit(1)

    if missing_opt:
        print(f'  [...] 正在安装可选依赖: {", ".join(missing_opt)} ...')
        try:
            subprocess.check_call(
                [sys.executable, '-m', 'pip', 'install'] + missing_opt,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            print(f'  [OK] 可选依赖安装完成')
        except Exception:
            print(f'  [WARN] 可选依赖安装失败（抠图/去文字功能将不可用）')


def get_lan_ip():
    """获取本机局域网 IP"""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def find_free_port(start_port):
    """从 start_port 开始寻找可用端口"""
    import socket
    for port in range(start_port, start_port + 10):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(('0.0.0.0', port))
            s.close()
            return port
        except OSError:
            continue
    return start_port


def build_frontend():
    """自动构建前端（仅在构建产物不存在时）"""
    import shutil
    if not shutil.which('node'):
        return  # 无 Node.js，跳过

    tools_dir = os.path.join(os.getcwd(), 'tools')
    for tool in ['bg-remover', 'image-tool', 'text-remover', 'image-composite', 'watermark-tool']:
        if not os.path.exists(os.path.join(tools_dir, tool, 'index.html')):
            print('  [...] 首次运行，正在构建前端...')
            try:
                subprocess.check_call(
                    ['npx', 'vite', 'build'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                print('  [OK] 前端构建完成')
            except Exception as e:
                print(f'  [WARN] 前端构建失败: {e}')
            return
    # 已构建过，跳过


def start_server(port):
    """启动 FastAPI 服务"""
    try:
        import uvicorn
        uvicorn.run("backend.main:app", host="0.0.0.0", port=port, log_level="info")
    except OSError as e:
        if 'Address already in use' in str(e) or '10048' in str(e):
            print(f'[ERROR] 端口 {port} 已被占用！')
            print(f'        请关闭占用该端口的程序，或使用 --port 指定其他端口')
        else:
            print(f'[ERROR] 服务启动失败: {e}')
    except Exception as e:
        print(f'[ERROR] 服务启动失败: {e}')


def main():
    parser = argparse.ArgumentParser(description='小小工具箱启动器')
    parser.add_argument('--port', type=int, default=5001, help='服务端口号（默认 5001）')
    parser.add_argument('--no-browser', action='store_true', help='不自动打开浏览器')
    parser.add_argument('--check-deps-only', action='store_true', help='仅检查并安装依赖，不启动服务')
    args = parser.parse_args()

    if args.check_deps_only:
        check_and_install_deps()
        sys.exit(0)

    port = find_free_port(args.port)

    print('=' * 50)
    print('  小小工具箱 3.0.0')
    print('  视频解析下载 | 图片批量处理 | AI 智能抠图')
    print('=' * 50)
    print()

    print('[1/4] 检查依赖...')
    check_and_install_deps()
    print()

    print('[2/4] 检查前端构建...')
    build_frontend()
    print()

    print(f'[3/4] 启动服务 (端口 {port})...')
    server_thread = threading.Thread(target=start_server, args=(port,), daemon=True)
    server_thread.start()
    time.sleep(2)

    # 验证服务
    import urllib.request
    url = f'http://127.0.0.1:{port}/'
    server_ok = False
    for _ in range(5):
        try:
            urllib.request.urlopen(url + 'api/health', timeout=3)
            server_ok = True
            break
        except Exception:
            time.sleep(1)

    if server_ok:
        print(f'  [OK] 服务已启动')
    else:
        print('  [WARN] 服务可能还在启动中，正在打开浏览器...')

    # 打开浏览器
    if not args.no_browser:
        print('[4/4] 打开浏览器...')
        try:
            webbrowser.open(url)
        except Exception:
            pass
    else:
        print('[4/4] 跳过浏览器（使用 --no-browser）')

    lan_ip = get_lan_ip()
    print()
    print(f'  本机访问: {url}tools/')
    if lan_ip != "127.0.0.1":
        print(f'  局域网:   http://{lan_ip}:{port}/tools/')
    print()
    print(f'  视频:   {url}tools/video-tool/')
    print(f'  图片:   {url}tools/image-tool/')
    print(f'  抠图:   {url}tools/bg-remover/')
    print(f'  溶图:   {url}tools/image-composite/')
    print(f'  去文字: {url}tools/text-remover/')
    print(f'  水印:   {url}tools/watermark-tool/')
    print()
    print('  按 Ctrl+C 停止服务')
    print('=' * 50)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print('\n正在关闭服务...')
        sys.exit(0)


if __name__ == '__main__':
    main()
