# lark-plat 阶段1 集成测试 harness（A~E 用例集）

- 作者: 集成测试工程师 (agt_h6a2iy9qfpg6pa)
- 入库: master（架构 seq2140 item4，add-only；原离线稿 `work/stage1-integration`）
- 覆盖: US-01 认证 / US-02 RBAC / US-03 数据权限 / US-11 审计 / WS-token 归属

## 环境

- Python 3.12 + pytest + httpx（后端 venv）
- `LARK_PLAT_API_BASE`：API 基地址（如 `http://localhost:8000/api/v1`）。
  **只有显式设置该变量才会启用 `live`/`seed` 用例**；未设置时全部 skip，
  因此普通 `pytest`（CI／后端单测门禁）保持离线、确定性、不触网不触库。
- `OPENAPI_PATH`：静态契约基线 openapi.json（默认 `stage1/fixtures/openapi.json`，
  为阶段1 冻结快照 66 paths；仓库现行契约为 `docs/openapi.json`，二者用途不同）
- `LARK_PLAT_REPO`：`差异A` 源码断言所用仓库根（默认按本文件位置自动推导）
- 种子账号（module-design §12）：admin（`admin/admin@larkplat`）；
  operator/viewer 由 `app.db.seed` 预置（可用 `LARK_ADMIN_USER` 等覆盖）

## 收集范围（与单测互不污染）

- `backend/pyproject.toml` 已加 `norecursedirs = ["tests/integration"]`：
  裸 `pytest`（CI／后端单测门禁）**只收集 `backend/tests/` 单测＋锁**，不误收本 live harness。
- 本 harness 须**显式路径**独立跑（独立 `pytest.ini` 注册 `live`/`seed`/`openapi` 标记）。

```powershell
# 裸单测（离线）：只含 backend/tests/**，不含本 harness
cd backend; pytest

# 静态契约基线（离线，不依赖后端）
pytest tests/integration/stage1 -m openapi -v

# 离线全量（live 部分在未启用/不可达/种子缺失时自动 skip）
pytest tests/integration/stage1 -v

# live 全量（须先播种，见下）
$env:LARK_PLAT_API_BASE="http://localhost:8000/api/v1"
pytest tests/integration/stage1 -v
```

## 种子播种 / 清理

`live` 的 WS-token 用例需要 operator 本人拥有的 exec 任务：

```powershell
python tests/integration/stage1/tools/stage1_seed.py --ensure   # 建种子（幂等）
python tests/integration/stage1/tools/stage1_seed.py --status   # 查种子
python tests/integration/stage1/tools/stage1_seed.py --clean    # 清种子（级联）
```

`阶段1 种子清理`（清理历史 e2e 残留主机，恢复 groupA/B 基线）：

```powershell
python tests/integration/stage1/tools/cleanup_stage1_seeds.py            # dry-run
python tests/integration/stage1/tools/cleanup_stage1_seeds.py --apply    # 执行
```

## 分组

- `-m openapi` 静态契约基线（66 paths / Result 信封 / snake_case / 路由顺序 / securitySchemes / 差异A·B）
- `-m live` 需可达 API
- `-m seed` 需种子数据（三角色 + 组A/B 主机 + `it-ws-seed` exec 任务）

## 覆盖（对照 kb/tasks/lark-plat-stage1-cases.md）

- `tests/test_contract_baseline.py` — §6 断言基线【**测试维护**：P2-ID `e45a19c`
  抽取 `issue_tokens()` 后，差异A 源断言跟随铸发点；可观测契约未变，代码reviewer seq2136】
- `tests/test_auth.py` — US-01 A1~A12（+a6b 单活跃会话）
- `tests/test_rbac.py` — US-02 B1~B11
- `tests/test_datascope.py` — US-03 C1~C7（c2 动态派生：对共享库种子累积免疫）
- `tests/test_audit.py` — US-11 D1~D6
- `tests/test_ws_token.py` — WS-token E1~E4（E1 走 `it-ws-seed`，不再 skip）

## 关联离线锁（随批入库，非本 harness）

- `backend/tests/test_p2_3_identity_lock.py` — P2-ID 契约锁（15/15，绑 `e45a19c`）
- `backend/tests/test_us03_datascope_lock.py` — US-03 离线**等价/兜底**锁
  （11/11；**不得冒充 live 绿**，不替代本 harness 的 live 主路径 c2）
