"""小红书 x-s 签名生成（调用 vendored node 脚本）

小红书 user_posted 等接口需要 x-s / x-t / x-s-common 签名头，签名算法由
前端混淆 JS 计算，无法用纯 Python 复刻。这里通过 node 子进程运行 vendored
的签名 JS（backend/parsers/xhs_sign/），输入 (api, a1, data, method)，
输出 {xs, xt, xs_common, xray}。

安全：日志只打 api 路径与 a1 长度，绝不打 cookie / a1 明文。
"""

import os
import json
import shutil
import asyncio
import logging
from typing import Dict

logger = logging.getLogger(__name__)

_SIGN_DIR = os.path.join(os.path.dirname(__file__), "xhs_sign")
_SIGN_JS = os.path.join(_SIGN_DIR, "sign.js")

_BEGIN = "__XHS_SIGN_BEGIN__"
_END = "__XHS_SIGN_END__"

_SIGN_TIMEOUT = 15.0


def _node_bin() -> str:
    return shutil.which("node") or "node"


def _extract_payload(stdout: str) -> Dict[str, str]:
    """从 node 输出中提取哨兵包裹的 JSON（签名 JS 会在补环境阶段污染 stdout）。"""
    start = stdout.find(_BEGIN)
    end = stdout.find(_END, start + 1) if start != -1 else -1
    if start == -1 or end == -1:
        raise RuntimeError("签名脚本未返回有效结果")
    raw = stdout[start + len(_BEGIN):end]
    return json.loads(raw)


async def sign(api: str, a1: str, data: str = "", method: str = "GET") -> Dict[str, str]:
    """生成小红书签名头。

    Args:
        api: 拼好 query 的接口路径，如 /api/sns/web/v1/user_posted?num=30&...
        a1: cookie 中的 a1 字段值
        data: POST body（GET 传空串）
        method: HTTP 方法
    Returns:
        {"xs", "xt", "xs_common"}
    """
    if not os.path.isfile(_SIGN_JS):
        raise RuntimeError("缺少签名脚本 sign.js")

    payload = json.dumps({"api": api, "a1": a1, "data": data, "method": method})
    logger.info("xhs sign: api=%s a1_len=%d method=%s", api.split("?", 1)[0], len(a1), method)

    try:
        proc = await asyncio.create_subprocess_exec(
            _node_bin(), _SIGN_JS, payload,
            cwd=_SIGN_DIR,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        raise RuntimeError("未找到 node，可从 nodejs.org 安装后重试")

    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=_SIGN_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()  # 回收子进程，避免 Windows 下遗留句柄
        raise RuntimeError("签名超时")

    if proc.returncode != 0:
        msg = (err or b"").decode("utf-8", "ignore").strip()[:200]
        raise RuntimeError(f"签名失败：{msg or '未知错误'}")

    ret = _extract_payload((out or b"").decode("utf-8", "ignore"))
    if not ret.get("xs") or not ret.get("xs_common"):
        raise RuntimeError("签名结果为空")
    return ret
