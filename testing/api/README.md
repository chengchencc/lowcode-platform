# G1 API 黑盒验收

用真实 HTTP 调运行中的后端，**不 import `backend.app` 的业务实现**。对应测试方案里的 G1 需求验收层。

## 运行

```bash
# 重置 E2E 独立库 → 起后端 → 跑全部
bash scripts/api.sh

# 只跑某个文件 / 某个关键字
bash scripts/api.sh test_auth.py
bash scripts/api.sh -k hidden

# 保留 testing/.runtime/e2e 数据
bash scripts/api.sh --no-reset

# 复用已启动的 8000 服务（不会重置库）
bash scripts/api.sh --no-server
```

依赖：后端 `.venv`（含 pytest/httpx），不需要 Playwright 或前端。

## 目录

```text
testing/api/
├─ pytest.ini
├─ conftest.py          # 登录客户端、种子数据、临时用户
├─ support/
│  ├─ client.py         # ApiClient（HTTP + token + X-Request-Id）
│  └─ factories.py      # 建用户/部门/角色、草稿/提交/审批/渲染
├─ test_auth.py         # 登录、失效 token、登出
├─ test_org.py          # 部门主管向上查找、无主管兜底、组织越权
├─ test_initiate.py     # 开始页、草稿、提交、幂等、必填校验
├─ test_tasks.py        # 同意、越权处理、重复处理、并行会签 + 填写节点
└─ test_permissions.py  # 无关人/设计者可见性、hidden 字段、归档可见
```

## 约定

- 所有数据通过 API 创建，名称带 `E2E-` / `e2e_` 前缀；测试之间不共享可变数据。
- 断言用户可观察的 HTTP 结果：状态码、`detail.code`、实例状态、任务数量、字段可见性。
- 不把“当前实现怎么返回”当期望；期望来自 `testing/acceptance/P0-CASES-*.md` 与 `P0-DECISIONS.md`。
- 新增用例时先确认矩阵里的 `CASE-ID` 与需求来源，再落到对应 `test_*.py`。
- 失败按 `docs/TEST-PLAN.md` §11 分类：实现 bug / 需求歧义 / 用例错误。

## 数据隔离

- 数据库：`testing/.runtime/e2e/e2e.db`
- 附件：`testing/.runtime/e2e/storage/`
- 启动日志：`testing/.runtime/e2e/api-backend.log`
- 绝不对开发库 `backend/flowform.db` 或生产库运行。
