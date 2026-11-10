# FlowForm 二期设计（V2）

> 配套：`PRD-lowcode-form-approval.md`、`TECH-DESIGN.md`。
> 本文是二期的范围与实现依据，随里程碑推进增量修订。
> **当前状态：M7 已完成；M8 代码已完成，待补测试与真机验收。**

---

## 0. 二期目标与边界

### 0.1 主线

二期主线是**配置能力升级**：让设计者在不依赖研发的情况下，把流程和表单配得更清楚、更好看、更贴近真实业务。

两条产品线：

1. **流程可视化画布**：在现有流程 JSON 上增加自动布局画布，支持轻编辑。
2. **表单表现力与布局**：分区栅格、字段跨列、展示型控件、字段联动、打印与移动端适配。

### 0.2 里程碑顺序

| 里程碑 | 主题 | 交付 | 验收 |
|---|---|---|---|
| **M7** | 流程可视化画布 | 自动布局 + 轻编辑，和清单视图共用同一份流程 JSON | 请假/报销流程正确呈现；节点增删、同级拖拽排序、分支/并行组操作可用；保存重载与清单视图一致 |
| **M8** | 表单布局与展示控件 | 分区栅格、字段跨列、分区折叠；标题/说明/分割线/图片/受限富文本 | 老表单默认渲染不变；设计器可配置布局与展示控件；发起页/详情/预览/打印一致 |
| **M9** | 字段联动规则 | 按条件控制显隐/只读/必填，前端实时、服务端兜底 | 规则只加限制；节点权限的 hidden 不可被规则点亮；提交/处理无法绕过 |
| **M10** | 打印与移动端 + 打磨 | A4 打印样式、核心用户路径响应式、文档与演示更新 | 打印只输出单据内容；375px 宽可走完发起/审批核心流程 |

### 0.3 二期明确不做

- 自由画布、坐标持久化、任意连线；
- 完整表达式与条件编辑器增强（只抽取现有条件编辑器复用）；
- 选项联动、赋值联动；
- 模板库、版本对比与回滚、多人协作；
- 加签/转办/催办/超时；
- 部门级数据权限、报表统计、外部通知、多租户；
- 可配置打印模板；
- 全站管理端响应式（管理端只保证可用）。

---

## 1. M7：流程可视化画布

### 1.1 原则

- **不改变数据模型**：画布只是 `FlowDefinition` 的另一种呈现，不引入坐标、连线或新表。
- **单一事实源**：画布与清单编辑同一份 `definition`；保存、发布、校验、引擎全部复用现有路径。
- **布局是纯函数**：布局算法不依赖 DOM，可单测。
- **不做自由连线**：节点顺序、分支、并行组仍然由现有结构化 JSON 表达；画布只负责展示和轻编辑。

### 1.2 新增模块

```
frontend/src/components/flow-designer/
├─ canvas/
│  ├─ layout.ts            # FlowDefinition -> CanvasLayout（纯函数）
│  ├─ layout.spec.ts       # 布局单测
│  ├─ FlowCanvas.vue       # 画布容器：缩放/平移/选中/拖拽
│  ├─ CanvasNode.vue       # 节点卡片
│  ├─ CanvasGroup.vue      # 条件/并行组容器
│  └─ CanvasToolbar.vue    # 视图切换、缩放、适配、新增
├─ definitionOps.ts        # 节点查找/插入/删除/移动（纯函数）
└─ ConditionEditor.vue     # M9 新增；M7 不改条件编辑器
```

`FlowDesignerView.vue` 增加“清单 / 画布”切换；选中节点继续复用 `NodePropertyPanel.vue`。

### 1.3 布局算法

`buildCanvasLayout(definition: FlowDefinition): CanvasLayout`

输出：

```ts
interface CanvasLayout {
  width: number
  height: number
  nodes: CanvasNode[]      // 绝对坐标
  edges: CanvasEdge[]      // 折线路径
  groups: CanvasGroup[]    // 条件/并行容器框
}

interface CanvasNode {
  id: string
  kind: 'start' | 'approval' | 'fill' | 'parallel' | 'condition' | 'cc' | 'end'
  x: number
  y: number
  width: number
  height: number
  parentId?: string        // 所属分支/并行组
}
```

布局规则：

- 主轴**自上而下**：start → steps → end。
- 顺序节点纵向排列，垂直间距 56。
- 条件节点：条件卡片下方按分支横向分泳道；每条泳道内顺序节点纵向排列；泳道结束后汇回下一个主线节点。
- 并行组：组容器内成员横向分泳道；容器下方接下一个主线节点。
- 节点尺寸：start/end 160×56；审批/填写/抄送/条件 220×76；并行/条件容器按内容计算。
- 边用正交折线：从父节点底部中点出发，向下到分支汇合点，再进入子节点顶部中点。
- 画布内边距 48；泳道间距 40；组内边距 24。
- 同一份定义多次布局结果必须完全一致（确定性，无随机）。

### 1.4 编辑操作

`definitionOps.ts` 提供纯函数，画布与清单共用：

| 操作 | 语义 |
|---|---|
| `findNode(definition, id)` | 在任意层级查找节点 |
| `removeNode(definition, id)` | 删除节点；删除条件/并行组时级联删除子节点 |
| `moveSibling(definition, id, delta)` | 同级上移/下移 |
| `insertAfter(definition, id, node)` | 在指定节点后插入（同级） |
| `addBranch(definition, conditionId)` | 给条件节点增加一条分支 |
| `addParallelMember(definition, parallelId)` | 给并行组增加成员 |
| `moveToContainer(definition, id, targetContainerId)` | 移入条件分支/并行组（M7 支持拖入空容器或组末尾） |

画布交互：

- 点击节点：选中并打开右侧属性面板。
- 节点上的“+”热点：在节点后插入新节点，弹出类型菜单（审批/填写/条件/并行/抄送）。
- 删除按钮：确认后删除；条件/并行组删除时提示会级联删除。
- **同级拖拽排序**：按住节点卡片拖动，显示插入位置指示线，松手后调用 `moveSibling`。
- **拖入分支/并行组**：拖动节点到分支泳道或并行组容器，松手后调用 `moveToContainer`。
- 条件节点提供“添加分支”；每个条件泳道提供“+”直接向该分支插入节点；并行组提供“+ 成员”。
- 缩放范围 0.4–1.6，支持适配视图；画布背景拖动平移。
- 所有编辑操作后沿用现有 1.5 秒防抖自动保存。
- 清单视图保留，作为小屏与精确编辑的兜底。

### 1.5 画布与现有组件的边界

- `NodePropertyPanel.vue` 不改交互，只由画布传入当前选中节点。
- `FlowDesignerView.vue` 继续负责加载、保存、发布、返回目标刷新；画布只发出“选中/定义已变更”事件。
- 发布校验、`validate.py`、引擎编译全部不动。

### 1.6 M7 测试与验收

**单测（不依赖 DOM）**：

- `layout.spec.ts`：线性流程、条件分支、嵌套条件、并行组、条件+并行混合、空流程、确定性。
- `definitionOps.spec.ts`：查找、删除（含级联）、同级移动、插入、加分支/成员、跨容器移动后的结构不变式。

**组件测试**：

- 挂载画布，断言节点卡片与边渲染、无未注册组件告警；
- 选中节点、点击“+”插入、删除、拖拽排序会修改 definition；
- 清单/画布切换后选中态与数据一致。

**验收**：

- 请假、报销两条示例流程在画布中结构正确；
- 在画布上完成一次节点新增、删除、同级拖拽排序、分支/并行组编辑；
- 保存后刷新页面，画布与清单视图显示一致；
- 发布校验与现有流程完全一致；
- 原有流程配置器测试全绿。

---

## 2. M8：表单布局与展示控件

### 2.1 Schema 扩展

全部为可选字段，旧 schema 原样可读；**不强制升级 `model_version`**。

```jsonc
{
  "layout": { "label_position": "top", "columns": 2 },
  "sections": [
    {
      "key": "sec_apply",
      "title": "申请信息",
      "columns": 3,              // 新增：分区级列数，1..4；缺省用 layout.columns
      "collapsible": true,       // 已有字段，M8 真正生效
      "fields": [
        {
          "key": "amount",
          "label": "金额",
          "type": "number",
          "span": 8,             // 新增：1..24，缺省按控件类型自动决定
          "display": null
        },
        {
          "key": "intro",
          "label": "填表说明",
          "type": "rich_text",   // 展示型控件
          "display": { "markdown": "请如实填写，**金额单位：元**。" }
        }
      ]
    }
  ]
}
```

展示型控件：

| type | 配置 | 说明 |
|---|---|---|
| `heading` | `display.text`, `display.level` (1..3) | 标题 |
| `paragraph` | `display.text` | 说明文字，支持换行 |
| `divider` | `display.text?` | 分割线，可带标题 |
| `image_view` | `display.url`, `display.alt?` | 图片/横幅（只读展示，不是上传控件） |
| `rich_text` | `display.markdown` | 受限 Markdown；前后端白名单清洗，禁止任意 HTML |

约束：

- 展示控件**不绑定数据**：不进入 `current_data`、快照、CSV 导出、值校验、字段权限矩阵的编辑项。
- 展示控件不能配置 required、options、formula、cascader、validators、columns；不能出现在子表行内。
- 展示控件仍需要 key（用于渲染、定位和唯一性校验），但不参与公式与条件引用。
- 权限：展示控件跟随分区/节点权限的可见性，永远只读、不必填；设计器不把它们列进字段权限矩阵。

### 2.2 渲染器

- `SectionBlock.vue` 读取列数：`section.columns ?? schema.layout.columns ?? 2`。
- 字段宽度：`field.span ?? autoSpan(field, columns)`；宽字段（子表、多行文本、附件、图片上传）默认整行。
- 响应式：小屏一律单列，`xs=24`。
- 分区折叠：`collapsible=true` 时显示折叠开关；默认展开。
- 展示控件走独立的 `DisplayBlock.vue`，不包 `<a-form-item>`，不显示标签与校验态。
- 渲染器仍是单一渲染树，`edit / readonly / preview / print` 共用。

### 2.3 设计器

- 控件面板新增“展示”分组：标题、说明、分割线、图片、富文本。
- 属性面板新增：
  - 展示控件属性（文本、级别、图片地址、Markdown）；
  - 字段跨列（整行 / 1/2 / 1/3 / 1/4）；
  - 分区属性（列数、折叠）；
  - 表单全局布局（标签位置、默认列数）。
- 实时预览复用 `FormRenderer`，不再另做一套。

### 2.4 后端

- `core/constants.py` 增加 `DISPLAY_FIELD_TYPES`，并明确 `SUBTABLE_COLUMN_TYPES` 不含展示控件。
- `schemas/form_schema.py`：
  - `FieldDef.span`、`FieldDef.display`；
  - `SectionDef.columns`；
  - `FormLayout.columns` 扩展到 1..4；
  - 校验展示控件配置与禁用项；
  - 公式、条件、值规则跳过展示控件；引用展示控件时给出明确错误。
- `engine/permissions.py`：展示控件按正常分层求可见性，但强制 `editable=False, required=False`。
- `engine/fields.py`、`engine/value_rules.py`、快照与导出：只处理数据字段。
- `services/form_service.py`：预览示例数据跳过展示控件。

### 2.5 M8 测试与验收

- 后端：schema 形状/语义校验、旧 schema 兼容、展示控件不进入数据/快照/导出、权限只读、子表拒绝展示控件。
- 前端：布局列数与 span、分区折叠、五类展示控件渲染、设计器属性面板、预览一致性。
- 验收：老表单默认渲染不变；设计器可配置 1–4 列、字段跨列、分区折叠、展示控件；发起页/详情/预览/打印一致。

### 2.6 M8 实现状态

代码已完成，提交在 `feat/phase2-m7-flow-canvas` 分支：

- 后端：`FieldDef.span`、`SectionDef.columns`、`FormLayout.columns(1–4)`，五类展示控件；
  展示控件不进入数据/快照/CSV/值校验/权限矩阵，公式与条件引用会被发布校验拦下。
- 前端：`DisplayBlock`、栅格列数/字段跨列、分区折叠、标签位置、设计器展示分组与属性面板、
  受限 Markdown 渲染。
- **测试待补**：按用户要求，M8 的 pytest/vitest 回归与真机验收统一在后续一起跑。

---

## 3. M9：字段联动规则

### 3.1 规则模型

表单 schema 根增加 `rules`，条件复用 `ConditionGroup`：

```jsonc
{
  "rules": [
    {
      "id": "r_travel",
      "name": "出差才显示明细",
      "when": {
        "op": "and",
        "conditions": [{ "field": "is_travel", "cmp": "==", "value": true }]
      },
      "effects": [
        { "target": "travel_detail", "effect": "hidden" },
        { "target": "travel_amount", "effect": "required" }
      ],
      "clear_when_hidden": true
    }
  ]
}
```

- `effect` 仅支持 `hidden` / `readonly` / `required`。
- **只加限制**：不能把节点权限已隐藏的字段重新点亮，不能把只读字段改成可编辑。
- 同一字段多条规则命中时：`hidden > readonly > required`，不依赖声明顺序。
- `required` 只在字段可见且可编辑时生效；只读字段上的 required 在发布时给 warning。
- `clear_when_hidden`：规则隐藏字段时是否清空其值；默认 `false`（保留旧值）。

### 3.2 条件模型复用

- 后端抽出 `app/schemas/conditions.py`，`Condition` / `ConditionGroup` 由流程定义与表单规则共用；`flow_definition.py` 保留 re-export，避免调用点大改。
- 前端抽出 `src/types/conditions.ts`，流程类型与表单类型共同引用。
- 不为表单规则扩展新的比较符或表达式能力。

### 3.3 求值顺序

```
节点权限矩阵（L0–L5）
        ↓
规则求值（只看基础权限，只允许收紧）
        ↓
最终 FieldPermission（visible / editable / required）
```

- 基础权限来自 `resolve_field_permissions` 或 `resolve_view_permissions`，扩展字段（机制 C）也先叠加。
- 规则求值不改变 `reason` 的既有层级，追加 `→ R{rule_id}:{effect}` 便于排查。
- 归档视角（终态全可见只读）不应用表单规则：**归档一律全可见只读**，避免历史单据出现字段消失。

### 3.4 服务端执行

- 新增 `backend/app/engine/form_rules.py` 纯函数：
  - `apply_form_rules(base_permissions, schema, values) -> dict[str, FieldPermission]`
  - `clean_hidden_values(schema, values) -> dict`（仅在 `clear_when_hidden` 时移除键）
- `render_instance` 下发：
  - `permissions`：基础权限（不含表单规则）；
  - `form_rules`：规则定义。
  - 前端用同一套 TS 规则实现，随输入实时重算。
- 提交 / 处理：
  - 先用合并后的数据计算公式字段；
  - 再求值规则，得到有效权限；
  - 按有效权限执行必填校验与字段 patch 过滤；
  - 隐藏字段的非法修改不落库；`clear_when_hidden` 命中时移除该键；
  - 与现有幂等、快照、字段来源追踪逻辑保持同一事务。
- 前后端共享 `docs/form-rule-test-vectors.json`，任何一侧语义漂移都会让测试变红。

### 3.5 发布校验

- 目标字段必须存在，且不是展示控件/扩展字段；
- 条件引用的字段必须存在，且不是展示控件；
- 禁止规则直接或间接依赖自身目标（构建依赖图，检测环），报 `RULE_CYCLE`；
- `required` 指向永远只读的字段时给 warning；
- 规则数量、表达式长度设上限，避免发布出不可维护的定义。

### 3.6 设计器

- 从 `NodePropertyPanel.vue` 抽出 `ConditionEditor.vue`，流程条件与表单规则共用。
- 新增“联动规则”面板：规则列表、增删、启用/停用、条件编辑、效果行、字段选择器、循环/冲突提示。
- 设计器预览使用示例值实时展示规则效果。

### 3.7 M9 测试与验收

- 纯函数：条件命中、三种效果、只加限制、hidden 优先、required 只在可编辑时生效、展示控件排除、循环检测。
- 服务端：render 契约、提交/处理时的规则兜底、隐藏字段篡改被拒、`clear_when_hidden`、必填由规则触发。
- 前端：规则实时重算、共享测试向量、设计器挂载与编辑。
- 验收：配一条“是否出差 → 显示/必填出差明细”的规则；切换值即时生效；绕过前端提交被服务端拦截。

---

## 4. M10：打印与移动端

### 4.1 打印

- 实例详情页用只读渲染器生成打印文档：
  - 顶部：标题、单号、状态、发起人、提交时间；
  - 中部：分区表单（只读，展示控件保留）；
  - 底部：处理历史（可选，默认包含）。
- `@media print`：
  - 隐藏导航、侧边栏、按钮、筛选、操作区；
  - A4、页边距 16mm；
  - 分区/字段尽量不跨页；子表表头重复；
  - 附件只打印文件名，不嵌入二进制。
- 不做可配置打印模板；继续用浏览器“另存为 PDF”。

### 4.2 移动端

范围：登录、发起中心、填写页、工作台、实例详情、消息中心；管理端保证可用。

- 断点：`<= 768px`。
- 主框架：侧边菜单变抽屉，顶部栏压缩。
- 表单：强制单列、标签置顶、分区标题紧凑。
- 实例详情：头部堆叠、进度条纵向/紧凑、操作栏吸底。
- 工作台：待办/已办在小屏切卡片列表；管理端表格横向滚动。
- 发起中心/消息中心：卡片单列。

### 4.3 M10 测试与验收

- 前端：打印模式渲染测试、移动端布局类名/条件渲染测试（mock `matchMedia`）。
- 手工验收：Chrome/Edge 打印预览无导航与按钮；375px 宽完成发起 → 审批 → 查看详情。
- 更新 `docs/DEMO.md`、README 与 TECH-DESIGN 的里程碑状态。

---

## 5. 兼容与迁移

- M7–M10 **不新增数据库表，不需要 Alembic 迁移**。
- 表单/流程定义的新字段全部可选；历史 `form_versions` 与 `flow_versions` 原样可读。
- `model_version` 只在破坏性变更时升级；二期不升级。
- 现有实例、快照、导出格式不受影响；展示控件不进入数据，规则只影响求值结果。

---

## 6. 测试策略

| 层 | 内容 |
|---|---|
| 纯函数 | 画布布局、节点操作、表单规则、展示控件语义 |
| 后端集成 | schema 校验、render 契约、提交/处理规则兜底、发布校验 |
| 前端组件 | 画布交互、布局渲染、展示控件、规则实时重算、打印/移动端类名 |
| 共享向量 | `docs/formula-test-vectors.json`（已有）+ `docs/form-rule-test-vectors.json`（M9 新增） |
| 端到端 | 每条里程碑补只走 HTTP 的场景测试；打印/移动端由用户在浏览器验收 |
| 收尾 | `bash scripts/check.sh` 全量五项 |

---

## 7. 风险与应对

| 风险 | 应对 |
|---|---|
| 画布拖拽与缩放坐标系复杂 | 先落纯函数布局与按钮式操作，再叠加拖拽；清单视图始终保留 |
| 嵌套过深导致画布过宽 | 横向滚动 + 适配视图，不压缩节点 |
| 表单规则前后端语义漂移 | 共享测试向量；服务端为最终权威；规则只加限制，语义面小 |
| 展示控件影响现有权限/快照/导出 | 集中 `is_data_field` 判定；默认行为对旧 schema 不变；补回归测试 |
| 移动端管理页回归 | 范围限定核心用户路径；管理端只保证可用；用户浏览器验收 |
| 打印排版差异 | 独立打印样式；Chrome/Edge 手工验收；不引入 PDF 库 |
| 富文本 XSS | 只支持受限 Markdown，前后端白名单清洗，禁止任意 HTML |

---

## 8. M7 完成定义（DoD）

- [x] 画布可在清单/画布间切换，选中态同步。
- [x] 自动布局覆盖 start/end、顺序、条件、嵌套条件、并行组、抄送。
- [x] 节点新增、删除、同级拖拽排序、拖入分支/并行组可用。
- [x] 条件分支与并行成员的增删可用。
- [x] 保存后刷新，画布与清单显示一致；发布校验与现有流程一致。
- [x] 布局与节点操作纯函数单测、画布组件测试通过。
- [x] `bash scripts/check.sh` 全量通过。
- [x] README / TECH-DESIGN / 本文档状态同步。

**M7 实际测试**：布局纯函数 6 项、定义操作 11 项、画布组件 8 项、完整设计器集成 2 项；
全量校验为 407 项 pytest + 115 项前端测试，`ruff` / `vue-tsc` / `vite build` 全绿。
真机验收中修掉一个指针捕获导致的按钮点击 bug，并补上条件泳道/并行组的直接添加入口，
详见 `TECH-DESIGN.md` §8。
