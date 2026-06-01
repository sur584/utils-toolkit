"""
Utils Toolkit Launcher
自动启动 FastAPI 服务并打开浏览器
用法：python launcher.py
"""
import sys
import os
import time
import subprocess
import threading
import webbrowser

# 切换到脚本所在目录
os.chdir(os.path.dirname(os.path.abspath(__file__)))


def check_and_install_deps():
    """检查并安装依赖（核心依赖必须，其余可选）"""
    # 核心依赖（缺少则无法启动）
    required = [
        ('httpx', 'httpx'),
        ('fastapi', 'fastapi'),
        ('uvicorn', 'uvicorn'),
        ('pydantic', 'pydantic'),
    ]
    # 可选依赖（缺少不影响启动，功能按需加载）
    optional = [
        ('yt_dlp', 'yt-dlp'),
        ('rembg', 'rembg'),
    ]

    missing_req = []
    missing_opt = []

    for import_name, pip_name in required:
        try:
            __import__(import_name)
            print(f'[OK] {pip_name}')
        except ImportError:
            missing_req.append(pip_name)

    for import_name, pip_name in optional:
        try:
            __import__(import_name)
            print(f'[OK] {pip_name}')
        except ImportError:
            missing_opt.append(pip_name)

    all_missing = missing_req + missing_opt
    if not all_missing:
        return

    if missing_req:
        print(f'[...] 缺少核心依赖: {", ".join(missing_req)}')
    if missing_opt:
        print(f'[...] 缺少可选依赖: {", ".join(missing_opt)}（视频/抠图功能将不可用）')

    print(f'[...] 正在安装: {", ".join(all_missing)} ...')
    try:
        subprocess.check_call(
            [sys.executable, '-m', 'pip', 'install'] + all_missing,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f'[OK] 依赖安装完成')
    except Exception:
        # 代理问题：去掉代理环境变量重试
        print(f'[...] 安装失败，尝试去掉代理重试...')
        env = os.environ.copy()
        for k in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
            env.pop(k, None)
        try:
            subprocess.check_call(
                [sys.executable, '-m', 'pip', 'install', '--no-proxy'] + all_missing,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
            )
            print(f'[OK] 依赖安装完成（无代理模式）')
        except Exception as e2:
            print(f'[WARN] 自动安装失败: {e2}')
            print(f'       请手动执行: {sys.executable} -m pip install {" ".join(all_missing)}')
            if missing_req:
                print(f'[ERROR] 核心依赖缺失，无法启动服务')
                sys.exit(1)


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


def start_server():
    """启动 FastAPI 服务"""
    try:
        import uvicorn
        uvicorn.run("backend.main:app", host="0.0.0.0", port=5001, log_level="info")
    except OSError as e:
        if 'Address already in use' in str(e) or '10048' in str(e):
            print('[ERROR] Port 5001 already in use!')
            print('        Close other services using this port, or restart.')
        else:
            print(f'[ERROR] Server failed: {e}')
    except Exception as e:
        print(f'[ERROR] Server failed: {e}')


def main():
    print('=' * 50)
    print('  小小工具箱')
    print('  视频解析下载 | 图片批量处理')
    print('=' * 50)
    print()

    check_and_install_deps()

    # 启动服务
    print('[...] Starting server ...')
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    time.sleep(2)

    # 验证服务
    import urllib.request
    url = 'http://127.0.0.1:5001/'
    server_ok = False
    for _ in range(5):
        try:
            urllib.request.urlopen(url + 'api/health', timeout=3)
            server_ok = True
            break
        except Exception:
            time.sleep(1)

    if server_ok:
        print(f'[OK] Server running: {url}')
    else:
        print('[WARN] Server may not be running yet, opening browser anyway ...')

    # 打开浏览器
    print('[OK] Opening browser ...')
    try:
        webbrowser.open(url)
    except Exception:
        pass

    lan_ip = get_lan_ip()
    print()
    print(f'  本机访问: {url}tools/')
    if lan_ip != "127.0.0.1":
        print(f'  局域网:   http://{lan_ip}:5001/tools/')
    print()
    print(f'  视频:   {url}tools/video-tool/')
    print(f'  图片:   {url}tools/image-tool/')
    print(f'  抠图:   {url}tools/bg-remover/')
    print()
    print('Press Ctrl+C to stop.')
    print('=' * 50)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print('\nShutting down ...')
        sys.exit(0)


if __name__ == '__main__':
    main()
