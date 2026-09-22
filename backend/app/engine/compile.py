"""流程定义 → 可执行形态（PRD §3.3）。

编译期做三件事：
1. 把树形结构（steps / branches / members）拍平成若干**有序列表**，
   并记录每个节点的 `Placement` —— 「这个节点走完之后去哪」由此变成查表
2. 校验 id 全局唯一（令牌定位依赖它）
3. 校验结构性约束（并行组内不能放条件、分支内不能嵌并行外的容器等）

编译是一次性的、纯计算的；引擎运行期只做查表与求值。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from app.engine.errors import FlowInvalid
from app.engine.types import CompiledFlow, NodeDef, Placement
from app.schemas.flow_definition import (
    Branch,
    CcNode,
    ConditionNode,
    EndNode,
    FlowDefinition,
    NodeBase,
    ParallelNode,
    StartNode,
)

#: 并行组内允许的成员类型（PRD：组内为多个审批/填写节点同时发起）
PARALLEL_MEMBER_TYPES = {"approval", "fill"}

#: 条件分支内允许出现的类型（V1 不允许分支内再嵌并行组之外的容器嵌套过深，
#: 但允许嵌套条件与并行组 —— 见 validate.py 的说明）
BRANCH_ALLOWED_TYPES = {"approval", "fill", "parallel", "condition", "cc"}


def _gate(condition_id: str, branch_id: str) -> str:
    return f"{condition_id}:{branch_id}"


def compile_flow(definition: FlowDefinition) -> CompiledFlow:
    """把流程定义编译成 `CompiledFlow`。结构非法时抛 `FlowInvalid`。"""
    nodes: dict[str, NodeDef] = {}
    root_list: list[str] = []
    branch_lists: dict[tuple[str, str], list[str]] = {}
    parallel_members: dict[str, list[str]] = {}
    condition_branches: dict[str, list[Branch]] = {}

    def register(
        node: NodeBase,
        placement: Placement,
        gates: tuple[str, ...],
    ) -> None:
        if node.id in nodes:
            raise FlowInvalid(f"节点标识 “{node.id}” 重复；节点标识必须全局唯一", node_id=node.id)
        if node.id in {"__start__", "__end__"}:
            raise FlowInvalid(f"节点标识 “{node.id}” 是保留字", node_id=node.id)
        nodes[node.id] = NodeDef(
            id=node.id,
            type=node.type,
            name=node.name,
            raw=node,
            placement=placement,
            gates=gates,
        )

    def walk(
        steps: Iterable[NodeBase],
        *,
        container_kind: str,
        condition_id: str | None,
        branch_id: str | None,
        parallel_id: str | None,
        gates: tuple[str, ...],
    ) -> list[str]:
        """把一层步骤登记成有序列表，返回该列表的节点 id 顺序。"""
        order: list[str] = []
        for index, node in enumerate(steps):
            # 注：start/end 不可能出现在这里 —— StepNode 的联合类型不含它们，
            # pydantic 在解析阶段就会拒绝。这里不重复检查（死代码）。
            placement = Placement(
                kind=container_kind,  # type: ignore[arg-type]
                index=index,
                condition_id=condition_id,
                branch_id=branch_id,
                parallel_id=parallel_id,
            )
            register(node, placement, gates)
            order.append(node.id)

            if isinstance(node, ConditionNode):
                if not node.branches:
                    raise FlowInvalid(f"条件节点 “{node.name}” 没有任何分支", node_id=node.id)
                else_count = sum(1 for b in node.branches if b.when is None)
                if else_count > 1:
                    raise FlowInvalid(
                        f"条件节点 “{node.name}” 有多个「否则」分支，最多只能有一个",
                        node_id=node.id,
                    )
                if else_count == 1 and node.branches[-1].when is not None:
                    raise FlowInvalid(
                        f"条件节点 “{node.name}” 的「否则」分支必须排在最后",
                        node_id=node.id,
                    )
                condition_branches[node.id] = list(node.branches)

                seen_branch_ids: set[str] = set()
                for branch in node.branches:
                    if branch.id in seen_branch_ids:
                        raise FlowInvalid(
                            f"条件节点 “{node.name}” 的分支标识 “{branch.id}” 重复",
                            node_id=node.id,
                        )
                    seen_branch_ids.add(branch.id)
                    for inner in branch.steps:
                        if inner.type not in BRANCH_ALLOWED_TYPES:
                            raise FlowInvalid(
                                f"分支 “{branch.id}” 里不能放 “{inner.type}” 类型的节点",
                                node_id=inner.id,
                            )
                    branch_lists[(node.id, branch.id)] = walk(
                        branch.steps,
                        container_kind="branch",
                        condition_id=node.id,
                        branch_id=branch.id,
                        parallel_id=None,
                        gates=(*gates, _gate(node.id, branch.id)),
                    )

            elif isinstance(node, ParallelNode):
                if not node.members:
                    raise FlowInvalid(f"并行组 “{node.name}” 没有任何成员", node_id=node.id)
                if node.mode not in {"all", "any"}:
                    raise FlowInvalid(
                        f"并行组 “{node.name}” 的聚合模式只能是 all(会签) 或 any(或签)",
                        node_id=node.id,
                    )
                # 成员类型由 ParallelNode.members 的联合类型（ApprovalNode | FillNode）
                # 在 pydantic 解析阶段约束，这里只查 id 重复 —— 那是类型系统表达不了的
                seen_member_ids: set[str] = set()
                for member in node.members:
                    if member.id in seen_member_ids:
                        raise FlowInvalid(
                            f"并行组 “{node.name}” 的成员标识 “{member.id}” 重复",
                            node_id=node.id,
                        )
                    seen_member_ids.add(member.id)

                parallel_members[node.id] = walk(
                    node.members,
                    container_kind="parallel",
                    condition_id=None,
                    branch_id=None,
                    parallel_id=node.id,
                    gates=gates,
                )

        return order

    root_list = walk(
        definition.steps,
        container_kind="root",
        condition_id=None,
        branch_id=None,
        parallel_id=None,
        gates=(),
    )

    start_raw = definition.start if isinstance(definition.start, StartNode) else StartNode(id="start", name="发起")
    end_raw = definition.end if isinstance(definition.end, EndNode) else EndNode(id="end", name="结束")

    if start_raw.id in nodes:
        raise FlowInvalid(f"节点标识 “{start_raw.id}” 与发起节点冲突", node_id=start_raw.id)
    if end_raw.id in nodes:
        raise FlowInvalid(f"节点标识 “{end_raw.id}” 与结束节点冲突", node_id=end_raw.id)
    if start_raw.id == end_raw.id:
        raise FlowInvalid("发起节点与结束节点不能同名")

    # 首尾节点不参与「位置」体系，但仍登记进 nodes 以便按 id 查找
    nodes[start_raw.id] = NodeDef(
        id=start_raw.id, type="start", name=start_raw.name, raw=start_raw,
        placement=Placement(kind="root", index=-1), gates=(),
    )
    nodes[end_raw.id] = NodeDef(
        id=end_raw.id, type="end", name=end_raw.name, raw=end_raw,
        placement=Placement(kind="root", index=len(root_list)), gates=(),
    )

    return CompiledFlow(
        definition=definition,
        start=nodes[start_raw.id],
        end=nodes[end_raw.id],
        nodes=nodes,
        root_list=root_list,
        branch_lists=branch_lists,
        parallel_members=parallel_members,
        condition_branches=condition_branches,
    )


def parse_flow_definition(raw: Mapping[str, Any] | FlowDefinition) -> FlowDefinition:
    """把存库的 JSON 解析成模型；形状非法时抛 `FlowInvalid`。"""
    if isinstance(raw, FlowDefinition):
        return raw
    try:
        return FlowDefinition.model_validate(raw)
    except Exception as exc:  # noqa: BLE001 - pydantic 的 ValidationError
        raise FlowInvalid(f"流程定义结构不合法：{exc}") from exc


def compile_definition(raw: Mapping[str, Any] | FlowDefinition) -> CompiledFlow:
    """一步到位：解析 + 编译。"""
    return compile_flow(parse_flow_definition(raw))


__all__ = [
    "BRANCH_ALLOWED_TYPES",
    "PARALLEL_MEMBER_TYPES",
    "compile_definition",
    "compile_flow",
    "parse_flow_definition",
    # 便于其他模块从这里取类型
    "CcNode",
    "ConditionNode",
    "ParallelNode",
]
