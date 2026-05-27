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
    """检查并安装依赖"""
    deps = {
        'yt_dlp': 'yt-dlp',
        'httpx': 'httpx',
        'fastapi': 'fastapi',
        'uvicorn': 'uvicorn',
        'pydantic': 'pydantic',
    }
    for import_name, pip_name in deps.items():
        try:
            __import__(import_name)
            print(f'[OK] {pip_name} installed')
        except ImportError:
            print(f'[...] {pip_name} not found, installing...')
            try:
                subprocess.check_call(
                    [sys.executable, '-m', 'pip', 'install', pip_name],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                print(f'[OK] {pip_name} installed')
            except Exception as e:
                print(f'[WARN] Failed to install {pip_name}: {e}')


def start_server():
    """启动 FastAPI 服务"""
    try:
        import uvicorn
        uvicorn.run("backend.main:app", host="127.0.0.1", port=5001, log_level="info")
    except OSError as e:
        if 'Address already in use' in str(e) or '10048' in str(e):
            print('[ERROR] Port 5001 already in use! Please close other services on this port.')
        else:
            print(f'[ERROR] Server failed: {e}')
    except Exception as e:
        print(f'[ERROR] Server failed: {e}')


def main():
    print('==================================================')
    print('  小小工具箱')
    print('  视频解析下载 | 图片批量处理')
    print('==================================================')

    check_and_install_deps()

    # 启动服务
    print('[...] Starting server...')
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    time.sleep(3)

    # 验证服务
    import urllib.request
    url = 'http://127.0.0.1:5001/'
    try:
        urllib.request.urlopen(url + 'api/health', timeout=3)
        print(f'[OK] Server running: {url}')
    except Exception:
        print('[WARN] Server may not be running. Try: pip install fastapi uvicorn httpx')

    # 打开浏览器
    print(f'[OK] Opening browser...')
    try:
        if sys.platform == 'win32':
            os.startfile(url)
        else:
            subprocess.Popen(['xdg-open', url])
    except Exception:
        webbrowser.open(url)

    print()
    print(f'  工具箱: {url}tools/')
    print(f'  视频:   {url}tools/video-tool/')
    print(f'  图片:   {url}tools/image-tool/')
    print()
    print('Press Ctrl+C to stop.')
    print('==================================================')

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print('\nShutting down...')
        sys.exit(0)


if __name__ == '__main__':
    main()
