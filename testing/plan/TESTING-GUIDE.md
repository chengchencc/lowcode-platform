# 测试编写与更新指南

> 本文回答一个具体问题：**新增需求、修改行为、修一个 bug 时，测试应该怎么动。**
> 测试战略见 [TEST-PLAN.md](TEST-PLAN.md)；G1 验收规则见 [../acceptance/README.md](../acceptance/README.md)；E2E 运行方式见 [../e2e/README.md](../e2e/README.md)。

---

## 1. 先决定加在哪一层

| 你要验证的东西 | 加在哪 | 典型例子 | 算验收证据吗 |
|---|---|---|---|
| 纯函数/算法/组件内部行为 | G0：pytest / vitest | 公式计算、画布布局、字段联动求值 | 否 |
| 业务规则、接口契约、权限、状态机 | G1：`../acceptance/*.md` + API 黑盒 | 驳回轮次、hidden 字段过滤、越权 403 | 是 |
| 真实角色、真实浏览器、真实操作时序 | G1/G2：`../e2e/specs/*.spec.ts` | 张三发起→李四审批→驳回重提 | 是 |
| 极端配置/随机动作序列下的不变量 | G3：属性/模型测试 | 任务守恒、幂等、快照一致 | 是 |
| 界面观感、打印排版、首次使用体验 | G4：手工/探索式 | 移动端布局、打印分页 | 是（UAT） |

**判断口诀**：如果缺陷只有在"某个角色、某个页面、某个真实操作顺序"下才出现，就不要只用单元测试证明它；反过来，纯计算规则也不值得用浏览器 E2E 去测。

---

## 2. 新增一个需求/功能（标准七步）

1. **先确认需求**：PRD/设计文档里写清楚行为；写不清楚的，先问产品负责人，不要从现有实现反推。
2. **登记矩阵**：在 [../acceptance/ACCEPTANCE-MATRIX.md](../acceptance/ACCEPTANCE-MATRIX.md) 加一行，分配 `CASE-ID`、需求来源、验收点、优先级。
3. **写用例**：按 [../acceptance/TEMPLATE.md](../acceptance/TEMPLATE.md) 写 Given/When/Then；新领域先用 [Spec Pack](../acceptance/SPEC-PACK.md) 做独立设计。
4. **确认期望**：P0 用例的"期望结果"由产品负责人确认；只确认期望，不需要审步骤细节。
5. **先写失败用例（能写的话）**：至少在实现完成前把用例落到自动化骨架里，避免"实现完再补一个刚好通过的测试"。
6. **在正确的层自动化**：API 黑盒或 E2E；打 `@p0`/`@p1` 标签；在矩阵填自动化位置。
7. **执行并回填**：`bash scripts/e2e.sh @p0 --headed` 先人工看一遍，再无头回归；更新状态和最近结果。

---

## 3. 新增/修改 G1 验收用例

- 文件放在 `../acceptance/<模块>.md`，ID 沿用 `TEST-PLAN.md` §6 的场景 ID。
- 一条用例只验证一个可判定的行为；期望结果必须能写成断言（文本、状态码、字段值、任务数、通知数、审计记录）。
- 需求来源必须真实存在。文档没定义的，写进"需求待确认项"，不要自己补规则。
- ID 一旦被自动化引用就不再改名；拆分场景用 `-a`/`-b` 新增，旧 ID 标 `N/A` 并注明替代者。
- 状态按 `TODO → DESIGNED → AUTOMATED → PASS/FAIL` 流转，**只以 `../acceptance/ACCEPTANCE-MATRIX.md` 为准**。

修改已有用例时：

- 行为**有意**变化：更新期望结果，并在用例里注明变更原因和关联需求变更。
- 行为**意外**变化：这是回归，先确认是实现 bug 还是用例过时；不要为了让测试变绿而改期望。

---

## 4. 新增/修改浏览器 E2E

### 位置与结构

- 用例：`../e2e/specs/<领域>.spec.ts`（如 `approve.spec.ts`、`permissions.spec.ts`）。
- 登录/造数：复用 [../e2e/fixtures/auth.ts](../e2e/fixtures/auth.ts) 的 `openAs` / `apiAs` / `loginViaApi`。
- 账号与组织：以 [../acceptance/TEST-DATA.md](../acceptance/TEST-DATA.md) 为准，不新增硬编码账号。

### 编写规则

- 一个测试只走一条业务旅程；需要多角色时用多个 `browser.newContext()`。
- 共享同一实例的多角色用例用 `test.describe.serial`；其余用例不依赖执行顺序。
- 定位器优先 `getByRole` / `getByLabel` / `getByPlaceholder` / `getByText`；动态表格可加 `data-testid`，**禁止**依赖 antd 内部 class。
- 权限类用例同时断言 UI 不显示 + API 返回 403/404。
- 造数尽量走 API，UI 只走被验证的关键交互；不要用 UI 去准备前置数据。
- 所有自建数据带 `E2E-<runId>-` 前缀；跑在 `testing/.runtime/e2e/` 独立库，绝不连开发库。
- 新增用例先 `bash scripts/e2e.sh @p0 --headed` 人工看一遍，再跑无头；flaky 用例必须修，不能靠 retry。
- 完成后把 `../e2e/specs/xxx.spec.ts` 填回矩阵的"自动化位置"。

### 常用命令

```bash
bash scripts/e2e.sh @p0 --headed     # 可见执行，前期必看
bash scripts/e2e.sh @p0              # 无头回归
bash scripts/e2e.sh --ui             # 交互式单步调试
bash scripts/e2e.sh --no-reset       # 保留 testing/.runtime/e2e 数据
bash scripts/e2e.sh --no-server      # 复用已启动的 8000/5173
```

---

## 5. 修一个 bug

1. 按 [TEST-PLAN.md](TEST-PLAN.md) §11 记录：环境、角色、步骤、**期望结果（引用需求）**、实际结果、证据。
2. 先写一条**按期望行为**的失败用例（API 或 E2E），确认它当前失败。
3. 再改代码；用例转绿后才算修复完成。
4. 在矩阵登记缺陷 ID 和回归用例 ID。
5. 如果根因是需求歧义：先更新 PRD/设计文档，再改用例和代码。

---

## 6. 需求变更时怎么更新测试

1. 在 `../acceptance/ACCEPTANCE-MATRIX.md` 里按需求编号搜索受影响的用例。
2. 更新用例的期望结果，注明变更原因；不要静默删除旧 ID。
3. 重新跑受影响的子集；发布前跑全量 `@p0`。
4. 需求文档变了就重新生成 Spec Pack：

   ```bash
   bash scripts/build-spec-pack.sh
   ```

---

## 7. 提交前检查清单

- [ ] 矩阵已更新（新用例/状态/缺陷/自动化位置）
- [ ] 每条用例都有需求来源；没有来源的已列入"需求待确认"
- [ ] 新增 E2E 已 `--headed` 人工看过一次
- [ ] 无头回归通过，且没有新增 flaky
- [ ] 没有把测试数据写进 `backend/flowform.db` 或生产库
- [ ] 行为变化同步更新了 PRD/设计文档
- [ ] 期望结果不是从当前实现反推出来的

---

## 8. 为什么 `testing/.runtime/spec-pack/` 不入库

`testing/.runtime/spec-pack/` 是 `scripts/build-spec-pack.sh` 生成的工作目录，不是源文件：

- **避免重复与漂移**：它里面的产品文档是 `docs/` 的副本，测试模板/测试数据来自 `testing/`，OpenAPI 是从代码导出的。提交进仓库后，源文档一改、代码一改，副本就会过期，读者分不清哪个是权威版本。
- **保持单一事实来源**：需求的权威版本始终是 `docs/` 下的原文，测试规范的权威版本是 `testing/` 下的原文；接口契约始终是当前代码导出的 OpenAPI。
- **按轮次重新生成**：每轮独立用例设计前重新构建，确保设计者看到的是当前需求与契约。
- **隔离性**：目录里只放需求/设计/业务文档和 OpenAPI，明确不含源码；生成物不入库也避免有人误把它当源码目录维护。
- **可复现**：构建脚本、源文档、模板都在仓库里，随时可以重建；真正需要保留的是产出的用例（`../acceptance/`）和矩阵，而不是输入副本。

如果以后需要审计"某轮设计用的是哪版资料"，建议在测试报告里记录构建时间与文档 commit，而不是提交整个生成目录。

---

## 9. 文档地图

| 文档 | 用途 |
|---|---|
| [TEST-PLAN.md](TEST-PLAN.md) | 总体测试战略、四道闸门、退出标准 |
| [../acceptance/ACCEPTANCE-MATRIX.md](../acceptance/ACCEPTANCE-MATRIX.md) | 需求→用例→结果，唯一验收口径 |
| [../acceptance/README.md](../acceptance/README.md) | G1 用例规则、状态流转 |
| [../acceptance/SPEC-PACK.md](../acceptance/SPEC-PACK.md) | 独立用例设计流程与 Prompt |
| [../acceptance/TEMPLATE.md](../acceptance/TEMPLATE.md) | 单条用例模板 |
| [../acceptance/TEST-DATA.md](../acceptance/TEST-DATA.md) | 测试账号、组织、种子数据 |
| [../e2e/README.md](../e2e/README.md) | E2E 运行、定位器、产物 |
| [../README.md](../README.md) | testing/ 总入口 |
| 本文 | 新增/修改/回归测试的操作手册 |
