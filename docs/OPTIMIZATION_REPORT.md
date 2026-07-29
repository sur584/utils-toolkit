# utils-toolkit 优化修复报告

> 日期：2026-07-27 ｜ 基线：`docs/BUG_REPORT.md`（2 严重 / 4 高 / 8 中 / 8 低）
> 执行方式：多 Agent 并行修复（Fix-A 后端安全健壮性 / Fix-B 依赖与前端）+ 独立验证代理整体回归
> 状态：**全部修复项已落地并通过回归验证**（改动未提交，待人工 review 后 commit）

---

## 一、修复清单

### 🔴 严重

| # | 缺陷 | 修复 |
|---|------|------|
| S1 | `rapidocr_onnxruntime>=1.3.0` 在 Py≥3.12 无解，requirements.txt 整体不可安装 | 降界为 `>=1.2.3,<2`；`pip install --dry-run -r requirements.txt` 解析成功 ✅ |
| S2 | `simple_lama_inpainting` 在 Py3.13 无法安装（依赖 numpy<2 无轮子） | 移入 **`requirements-optional.txt`**（附英文说明：需 Py≤3.12 或有 C 编译器）；代码本为惰性导入，不影响服务启动，仅"文字移除"功能需按需安装 |

### 🟠 高

| # | 缺陷 | 修复 |
|---|------|------|
| H1 | 21 处 `verify=False` 关闭 TLS 校验 + 6 处 yt-dlp `nocheckcertificate: True` | `backend/config.py` 新增 **`SSL_VERIFY`** 开关（env `UT_SSL_VERIFY`，**默认开启校验**；MITM 代理环境可设 `UT_SSL_VERIFY=0`）。21 处 httpx `verify=SSL_VERIFY`、6 处 yt-dlp `nocheckcertificate=not SSL_VERIFY` 全部联动（其中 5 处为独立验证发现的漏改，已补齐，全库复查 0 残留） |
| H2 | 服务绑定 `0.0.0.0` 无认证 | `backend/main.py` 与 `launcher.py` 改为读取 env **`UT_HOST`**（绑定地址可配置），launcher 端口探测 socket 同步联动。**默认值保持 `0.0.0.0`**（用户实际需要局域网访问）；如需仅限本机可设 `UT_HOST=127.0.0.1` |
| H3 | npm HIGH 漏洞 postcss 8.5.15（GHSA-r28c-9q8g-f849 路径穿越） | `npm audit fix` → postcss 8.5.23，`npm audit` **0 vulnerabilities**（仅 lockfile 变更） |
| H4 | numpy 被 6 处直接 import 却未声明 | requirements.txt 显式声明 `numpy>=1.24,<3`（另补 `ctranslate2>=4.0,<5`） |

### 🟡 中

| # | 缺陷 | 修复 |
|---|------|------|
| M1 | `transcript.py:238/350` fire-and-forget 任务未存引用 | 模块级 `_background_tasks` 集合保存引用 + `add_done_callback` 自动清理 |
| M2 | `image_classifier.py:40` 模型下载中断残留半截文件致永久故障 | 下载到 `.tmp` 临时文件，成功后 `os.replace`，失败清理临时文件后 re-raise |
| M3 | 前端 `image-composite/main.jsx:698/709` Promise 无 `.catch` | 两处补 `.catch`，复用组件既有 toast 报错 + 恢复 generating 状态 |
| M5 | `/api/history/list` 返回 405（误匹配动态路由） | `routers/history.py` 为同一 handler 叠加 `GET /api/history/list` 别名（注册于动态路由之前），实测 **200 并返回真实 JSON** |
| M7 | 依赖全部无上界，已实证漂移到 OpenCV 5 / NumPy 2 | 全量补上界（fastapi<1、opencv-python-headless<5、pydantic<3、Pillow<14 等；yt-dlp 日历版不加）；`aiofiles` 死依赖删除；pytest 移入新增 `requirements-dev.txt` |

### 🟢 低

- `disk_cache.py` 5 处 `except Exception: pass` → 加 `logger.warning`（行为不变，不再静默）
- `tests/test_douyin_profile_pagination.py:40` `asyncio.get_event_loop()` → `asyncio.run()`，DeprecationWarning 消除（`-W error::DeprecationWarning` 下仍 62 passed）
- `image-tool/main.jsx:739` `new Promise(async...)` 反模式 → 标准等价改写，消除悬挂 Promise 风险

### 未处理项（有意保留）

| 项 | 原因 |
|---|------|
| M4 异步路由内阻塞 `open()`（4 处） | 性能类问题，本地单用户场景影响小；改造需引入 aiofiles/线程池，留待后续 |
| 约 130 条 ruff 质量项（F401/B904/F541 等） | 纯风格问题，建议单独一次 `ruff --fix` 批量处理，避免与本次功能性修复混在同一 diff |
| 测试覆盖率低（仅 2 个测试文件） | 属工程建设项，不在本次缺陷修复范围 |

---

## 二、回归验证结果（独立验证代理，fresh eyes）

| 验证项 | 期望 | 实际 |
|---|---|---|
| 抖音分页测试 | 62 passed 且无 DeprecationWarning | ✅ 62 passed（`-W error` 复跑仍通过） |
| SRT 管道测试 | 17 passed | ✅ 17 passed |
| requirements dry-run 解析 | 成功 | ✅ exit 0，无 ResolutionImpossible |
| 三个 requirements 文件编码 | 纯 ASCII / 无 BOM / 全 CRLF | ✅ 全部通过 |
| npm audit | 0 vulnerabilities | ✅ |
| vite build | exit 0 | ✅ 43 modules |
| 后端启动 | 监听 **127.0.0.1**:5001，日志无 ERROR | ✅（rmbg 模型预加载 ~13s） |
| 路由探活 | `/`307、`/docs`200、`/tools/`200、`/api/history`200、`/api/cache/stats`200 | ✅ 全部符合 |
| **`/api/history/list`** | **200（原 405）** | ✅ 200，返回真实 JSON |
| 全库 `verify=False` 残留 | 0 | ✅ 0 |
| `nocheckcertificate` 联动 | 6/6 | ⚠️ 首轮 1/6 → **补修后 6/6** ✅（import OK、62 用例复测通过） |
| 验证后进程清理 | 端口释放、无残留 | ✅ |

---

## 三、新增配置项

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `UT_SSL_VERIFY` | `1`（开启校验） | 设 `0`/`false` 可关闭出站 TLS 证书校验（仅限可信 MITM 代理环境） |
| `UT_HOST` | `0.0.0.0`（局域网可访问） | 服务绑定地址；需仅限本机时设 `127.0.0.1` |

## 四、变更文件清单

- **后端（23 个修改）**：`backend/config.py`、`main.py`、`launcher.py`、`parsers/`（_utils/bilibili/douyin/profile/tiktok/twitter/wechat_channels/weibo/xigua/youtube）、`routers/`（video/transcript/history）、`services/`（download_service/disk_cache/image_classifier）、`tests/test_douyin_profile_pagination.py`
- **依赖**：`requirements.txt`（重构）、`requirements-optional.txt`（新增）、`requirements-dev.txt`（新增）、`package-lock.json`（postcss 升级）
- **前端**：`src/image-composite/main.jsx`、`src/image-tool/main.jsx`
- 所有改动**未提交**，`git status` 可查看完整 diff，review 后可 commit。
