"""引擎事务编排（PRD §3.5.2 / §3.5.3 / §3.5.4）。

这是引擎**唯一**的写入口：所有状态变化都经过这里，且遵循同一个骨架：

    锁实例 → 状态机 guard → 幂等检查 → 计算令牌操作 → 落库
          → 写 action/snapshot → 生成通知 → 提交

本模块**允许** import db/models —— 它是编排层，不是纯核心。
分层约束针对的是 compile/conditions/expressions/permissions/aggregate/machine/router
那几个模块（它们必须能脱离数据库单测）。
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.clock import utcnow
from app.core.constants import (
    INSTANCE_STATUS_LABELS,
    TERMINAL_STATUSES,
    AggregateMode,
    AssignmentResult,
    AssignmentStatus,
    CancelReason,
    InstanceStatus,
    SnapshotKind,
    TaskStatus,
    TaskType,
)
from app.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnprocessableError,
)
from app.engine import notify
from app.engine import snapshot as snapshot_mod
from app.engine.aggregate import (
    group_state,
    next_sequential_seq,
    node_state,
    normalize_mode,
    should_cancel_siblings_on_pass,
)
from app.engine.approvers import (
    ApproverContext,
    ApproverProvider,
    initial_status_for_mode,
    order_by_mode,
    resolve_approvers,
    resolve_cc,
)
from app.engine.compile import compile_definition
from app.engine.errors import FlowInvalid, IllegalTransition
from app.engine.ext_fields import (
    ExtFieldSpec,
    make_field_key,
    merge_ext_fields,
    normalize_spec,
)
from app.engine.fields import FieldDiff, apply_field_patch, field_label_index
from app.engine.form_rules import apply_form_rules, hidden_clear_keys
from app.engine.machine import (
    EVENT_ABANDON,
    EVENT_FINISH,
    EVENT_REJECT,
    EVENT_RESUBMIT,
    EVENT_SUBMIT,
    EVENT_TERMINATE,
    EVENT_WITHDRAW,
    assert_transition,
)
from app.engine.permissions import (
    ExtFieldView,
    FieldPermission,
    apply_ext_fields,
    editable_keys,
    resolve_field_permissions,
)
from app.engine.router import (
    allowed_return_targets,
    cancel_set_for_return,
    plan_after_group,
    plan_after_node,
    plan_start,
)
from app.engine.types import (
    AssignmentView,
    CompiledFlow,
    Cursor,
    EngineResult,
    NotificationDraft,
    TaskView,
    TokenOp,
)
from app.engine.value_rules import validate_values
from app.models import (
    DataSnapshot,
    FlowInstance,
    FlowVersion,
    FormVersion,
    InstanceAction,
    InstanceExtField,
    Notification,
    Task,
    TaskAssignment,
    User,
)
from app.schemas.form_schema import parse_form_schema

#: 字段 diff 的追溯信息上限，避免超大表单把 JSON 撑爆
_MAX_CHANGED_FIELDS = 200


class EngineService:
    """一次引擎事件 = 一个事务。"""

    def __init__(
        self,
        db: Session,
        *,
        provider: ApproverProvider,
        clock=utcnow,
    ) -> None:
        self.db = db
        self.provider = provider
        self.clock = clock

    # ==================================================================== 公开事件

    def submit(
        self,
        *,
        instance: FlowInstance,
        actor: User,
        data: Mapping[str, Any],
        note: str | None = None,
        attachment_ids: Sequence[int] = (),
        assignee_picks: Mapping[str, Sequence[int]] | None = None,
        request_id: str | None = None,
    ) -> EngineResult:
        """首次提交（PRD F3.4）。DRAFT → RUNNING。"""
        self._lock(instance.id)
        if instance.status != InstanceStatus.DRAFT:
            raise IllegalTransition(instance.status, EVENT_SUBMIT)

        # 发起人指定审批人的选择结果，作为特殊字段并入数据
        values_in = dict(data)
        if assignee_picks:
            values_in["__initiator_select__"] = self._flatten_picks(assignee_picks)

        return self._start_round(
            instance=instance,
            actor=actor,
            values_in=values_in,
            note=note,
            attachment_ids=attachment_ids,
            event=EVENT_SUBMIT,
            kind=SnapshotKind.SUBMIT,
            request_id=request_id,
        )

    def resubmit(
        self,
        *,
        instance: FlowInstance,
        actor: User,
        data: Mapping[str, Any],
        note: str | None = None,
        attachment_ids: Sequence[int] = (),
        assignee_picks: Mapping[str, Sequence[int]] | None = None,
        request_id: str | None = None,
    ) -> EngineResult:
        """驳回后重新提交（PRD F3.6）：轮次 +1，从头重走。"""
        self._lock(instance.id)
        if instance.status != InstanceStatus.REJECTED:
            raise IllegalTransition(instance.status, EVENT_RESUBMIT)

        # 清理上一轮残留的令牌（理论上驳回时已全取消，这里兜底）
        self._cancel_pending(instance, CancelReason.RESUBMITTED)
        instance.round += 1

        values_in = dict(data)
        if assignee_picks:
            values_in["__initiator_select__"] = self._flatten_picks(assignee_picks)

        return self._start_round(
            instance=instance,
            actor=actor,
            values_in=values_in,
            note=note,
            attachment_ids=attachment_ids,
            event=EVENT_RESUBMIT,
            kind=SnapshotKind.SUBMIT,
            request_id=request_id,
        )

    def act(
        self,
        *,
        assignment_id: int,
        actor: User,
        action: str,
        opinion: str | None = None,
        attachment_ids: Sequence[int] = (),
        field_patch: Mapping[str, Any] | None = None,
        return_target: str | None = None,
        expected_version: int | None = None,
        request_id: str | None = None,
    ) -> EngineResult:
        """统一动作入口（PRD F4.3）：同意 / 驳回 / 退回 / 提交。"""
        assignment = self.db.get(TaskAssignment, assignment_id)
        if assignment is None:
            raise NotFoundError("任务不存在", code="ASSIGNMENT_NOT_FOUND")

        instance = self._lock(assignment.instance_id)
        task = self.db.get(Task, assignment.task_id)
        assert task is not None

        self._assert_can_act(instance, task, assignment, actor, expected_version)

        compiled = self._compiled(instance)
        node = compiled.nodes.get(task.node_key)
        if node is None:
            raise FlowInvalid(f"流程定义里没有节点 “{task.node_key}”", node_id=task.node_key)

        cursor = Cursor(task.node_key, tuple(task.gates), task.round)

        # ---- 字段写入 ----
        form_schema = self._schema_for(instance)
        permissions = self._permissions_for(
            instance, compiled, task.node_key, gates=task.gates, round_no=task.round
        )
        values, diffs, permissions = self._apply_patch_with_rules(
            instance=instance,
            form_schema=form_schema,
            base_permissions=permissions,
            patch=dict(field_patch or {}),
        )
        self._assert_required(permissions, values, form_schema, partial=True)
        self._assert_values_valid(form_schema, values, permissions, editable_only=True)

        # ---- 意见 / 附件必填（可在节点上配置） ----
        self._assert_opinion_and_attachment(node, action, opinion, attachment_ids)

        # ---- 校验动作合法性 ----
        self._assert_action_allowed(node, action, return_target, compiled, cursor)

        now = self.clock()
        action_row = self._write_action(
            instance=instance,
            task=task,
            assignment=assignment,
            actor=actor,
            action=action,
            opinion=opinion,
            attachment_ids=attachment_ids,
            changed_fields=diffs,
            request_id=request_id,
            to_status=None,
        )

        assignment.status = AssignmentStatus.DONE
        assignment.result = action
        assignment.opinion = opinion
        assignment.attachments = list(attachment_ids)
        assignment.action_id = action_row.id
        assignment.acted_at = now

        instance.current_data = values
        instance.field_meta = self._update_field_meta(
            instance.field_meta, diffs, node_key=task.node_key, actor_id=actor.id,
            action_id=action_row.id, round_no=instance.round,
        )
        instance.last_action_at = now

        result = EngineResult(instance_status=instance.status)
        result.changed_fields = [d.to_dict() for d in diffs[:_MAX_CHANGED_FIELDS]]
        result.action_id = action_row.id

        if action == AssignmentResult.REJECT:
            self._handle_reject(instance, task, actor, opinion, result)
        elif action == AssignmentResult.RETURN:
            self._handle_return(instance, compiled, task, cursor, return_target, actor, result)
        else:
            self._handle_pass(instance, compiled, task, cursor, node, actor, result)

        # ---- 快照 + 通知落库 ----
        snap = self._write_snapshot(
            instance=instance,
            kind=SnapshotKind.ACTION,
            actor_id=actor.id,
            action_id=action_row.id,
        )
        action_row.snapshot_id = snap.id
        action_row.to_status = instance.status
        result.snapshot_id = snap.id

        self._persist_notifications(result.notifications)
        self.db.commit()
        self.db.refresh(instance)
        result.instance_status = instance.status
        return result

    def withdraw(
        self,
        *,
        instance: FlowInstance,
        actor: User,
        reason: str | None = None,
        request_id: str | None = None,
    ) -> EngineResult:
        """撤回（PRD §3.5.4）：**尚无任何任务被处理过**时才能撤。"""
        self._lock(instance.id)
        self._assert_can_withdraw(instance)

        result = EngineResult(instance_status=instance.status)
        now = self.clock()

        action_row = self._write_action(
            instance=instance, task=None, assignment=None, actor=actor,
            action="WITHDRAW", opinion=reason, attachment_ids=(), changed_fields=[],
            request_id=request_id, to_status=None,
        )
        cancelled = self._cancel_pending(instance, CancelReason.WITHDRAWN)
        instance.status = assert_transition(instance.status, EVENT_WITHDRAW)
        instance.finished_at = now
        action_row.to_status = instance.status

        self._notify_cancelled(instance, cancelled, "发起人已撤回", result)
        result.notifications.extend(
            notify.instance_status_changed(
                instance_id=instance.id,
                instance_title=instance.title,
                status=instance.status,
                recipients=[instance.initiator_id],
            )
        )

        snap = self._write_snapshot(
            instance=instance, kind=SnapshotKind.ACTION, actor_id=actor.id, action_id=action_row.id
        )
        action_row.snapshot_id = snap.id
        result.snapshot_id = snap.id
        result.action_id = action_row.id

        self._persist_notifications(result.notifications)
        self.db.commit()
        return result

    def abandon(
        self, *, instance: FlowInstance, actor: User, request_id: str | None = None
    ) -> EngineResult:
        """撤销（PRD §3.5.4）：REJECTED → WITHDRAWN，放弃本轮申请。"""
        self._lock(instance.id)
        if instance.initiator_id != actor.id:
            raise UnprocessableError("只有发起人可以撤销", code="NOT_INITIATOR")

        result = EngineResult(instance_status=instance.status)
        action_row = self._write_action(
            instance=instance, task=None, assignment=None, actor=actor,
            action="ABANDON", opinion=None, attachment_ids=(), changed_fields=[],
            request_id=request_id, to_status=None,
        )
        instance.status = assert_transition(instance.status, EVENT_ABANDON)
        instance.finished_at = self.clock()
        action_row.to_status = instance.status

        result.action_id = action_row.id
        self._persist_notifications(result.notifications)
        self.db.commit()
        return result

    def terminate(
        self,
        *,
        instance: FlowInstance,
        actor: User,
        reason: str,
        request_id: str | None = None,
    ) -> EngineResult:
        """管理员强制终止（PRD §3.5.4）。reason 必填并写入审计。"""
        self._lock(instance.id)
        if not reason or not reason.strip():
            raise UnprocessableError("终止必须填写原因", code="TERMINATE_REASON_REQUIRED")

        result = EngineResult(instance_status=instance.status)
        now = self.clock()

        action_row = self._write_action(
            instance=instance, task=None, assignment=None, actor=actor,
            action="TERMINATE", opinion=reason, attachment_ids=(), changed_fields=[],
            request_id=request_id, to_status=None,
        )
        cancelled = self._cancel_pending(instance, CancelReason.TERMINATED)
        instance.status = assert_transition(instance.status, EVENT_TERMINATE)
        instance.terminated_reason = reason
        instance.finished_at = now
        action_row.to_status = instance.status

        self._notify_cancelled(instance, cancelled, "管理员终止了流程", result)
        result.notifications.extend(
            notify.instance_status_changed(
                instance_id=instance.id,
                instance_title=instance.title,
                status=instance.status,
                recipients=self._participants(instance),
                extra=f"终止原因：{reason}",
            )
        )

        snap = self._write_snapshot(
            instance=instance, kind=SnapshotKind.TERMINATE, actor_id=actor.id, action_id=action_row.id
        )
        action_row.snapshot_id = snap.id
        result.snapshot_id = snap.id
        result.action_id = action_row.id

        self._persist_notifications(result.notifications)
        self.db.commit()
        return result

    def mark_cc_read(
        self, *, assignment_id: int, actor: User
    ) -> None:
        """抄送已读（抄送不占令牌，无状态变化）。"""
        assignment = self.db.get(TaskAssignment, assignment_id)
        if assignment is None:
            raise NotFoundError("任务不存在", code="ASSIGNMENT_NOT_FOUND")
        if assignment.user_id != actor.id:
            raise UnprocessableError("只能标记自己的抄送", code="NOT_ASSIGNEE")
        task = self.db.get(Task, assignment.task_id)
        if task is None or task.node_type != TaskType.CC:
            raise UnprocessableError("只有抄送可以标记已读", code="NOT_CC_TASK")

        if not assignment.is_read:
            assignment.is_read = True
            assignment.read_at = self.clock()
            assignment.result = AssignmentResult.READ
            self._write_action(
                instance=self.db.get(FlowInstance, assignment.instance_id),
                task=task, assignment=assignment, actor=actor,
                action="CC_READ", opinion=None, attachment_ids=(), changed_fields=[],
                request_id=None, to_status=None,
            )
        self.db.commit()

    # ==================================================================== 机制 C：动态追加字段

    def add_ext_field(
        self,
        *,
        instance: FlowInstance,
        actor: User,
        spec: ExtFieldSpec,
        request_id: str | None = None,
    ) -> EngineResult:
        """运行中给**该实例**追加一个字段（PRD §3.4 机制 C）。

        只作用于该实例、不入模板；默认只读，仅目标节点可编辑；
        追加点之前的节点不可见。追加行为本身进审计与快照。
        """
        self._lock(instance.id)
        if instance.status in TERMINAL_STATUSES:
            raise UnprocessableError(
                f"实例已是{_status_label(instance.status)}，不能再追加字段",
                code="EXT_FIELD_NOT_ALLOWED",
            )

        normalized = normalize_spec(spec)

        # 可编辑节点：没指定就用**当前待办节点**（PRD：「默认当前待办节点」）
        active_nodes = self._active_node_keys(instance.id)
        target_nodes = list(normalized.editable_node_ids) or active_nodes
        if not target_nodes:
            raise UnprocessableError(
                "实例当前没有待办节点，无法确定可编辑节点",
                code="NO_ACTIVE_NODE",
            )

        # 可见起点：追加点所在节点。它之前的节点看不到这个字段
        visible_from = active_nodes[0] if active_nodes else target_nodes[0]

        instance.ext_field_seq += 1
        field_key = make_field_key(instance.ext_field_seq, normalized.label)

        row = InstanceExtField(
            instance_id=instance.id,
            field_key=field_key,
            label=normalized.label,
            type=normalized.type,
            section_key=normalized.section_key,
            config={
                **(normalized.config or {}),
                **({"placeholder": normalized.placeholder} if normalized.placeholder else {}),
            }
            or None,
            required=normalized.required,
            editable_node_ids=target_nodes,
            visible_from_node_id=visible_from,
            status="ACTIVE",
            source_node_key=visible_from,
            seq=instance.ext_field_seq,
            created_by=actor.id,
        )
        self.db.add(row)
        self.db.flush()

        # 并入实例 schema：渲染时不必区分模板字段与扩展字段
        instance.data_schema = self._schema_for(instance).model_dump(mode="json")

        now = self.clock()
        action_row = self._write_action(
            instance=instance, task=None, assignment=None, actor=actor,
            action="ADD_EXT_FIELD",
            opinion=f"追加字段「{normalized.label}」",
            attachment_ids=(), changed_fields=[],
            request_id=request_id, to_status=instance.status,
        )
        instance.last_action_at = now

        result = EngineResult(instance_status=instance.status)
        result.action_id = action_row.id
        result.events.append(
            self._event("EXT_FIELD_ADDED", instance, visible_from, {
                "field_key": field_key,
                "label": normalized.label,
                "type": normalized.type,
                "editable_nodes": target_nodes,
            })
        )

        # 通知当前处理人：他要多填一个字段
        handlers = [
            a.user_id for t in self._pending_tasks(instance.id) for a in t.assignments
            if a.status == AssignmentStatus.PENDING
        ]
        node_name = None
        if visible_from and visible_from in self._compiled(instance).nodes:
            node_name = self._compiled(instance).nodes[visible_from].name
        result.notifications.extend(
            notify.ext_field_added(
                instance_id=instance.id,
                instance_title=instance.title,
                field_key=field_key,
                label=normalized.label,
                node_name=node_name,
                recipients=handlers,
            )
        )

        snap = self._write_snapshot(
            instance=instance, kind=SnapshotKind.EXT_FIELD,
            actor_id=actor.id, action_id=action_row.id,
        )
        action_row.snapshot_id = snap.id
        result.snapshot_id = snap.id

        self._persist_notifications(result.notifications)
        self.db.commit()
        self.db.refresh(instance)
        return result

    def disable_ext_field(
        self,
        *,
        instance: FlowInstance,
        actor: User,
        field_key: str,
        request_id: str | None = None,
    ) -> EngineResult:
        """停用动态字段。

        **不可物理删除**（PRD F5.3）—— 历史快照里还有它的值，
        删掉定义会让那些快照渲染不出来。停用后界面上消失，但数据与定义都留着。
        """
        self._lock(instance.id)
        if instance.status in TERMINAL_STATUSES:
            raise UnprocessableError(
                f"实例已是{_status_label(instance.status)}，不能再改动字段",
                code="EXT_FIELD_NOT_ALLOWED",
            )

        row = self.db.scalar(
            select(InstanceExtField).where(
                InstanceExtField.instance_id == instance.id,
                InstanceExtField.field_key == field_key,
            )
        )
        if row is None:
            raise NotFoundError("动态字段不存在", code="EXT_FIELD_NOT_FOUND")
        if row.status != "ACTIVE":
            raise ConflictError("该字段已经停用", code="EXT_FIELD_ALREADY_DISABLED")

        row.status = "DISABLED"
        self.db.flush()

        instance.data_schema = self._schema_for(instance).model_dump(mode="json")

        action_row = self._write_action(
            instance=instance, task=None, assignment=None, actor=actor,
            action="DISABLE_EXT_FIELD",
            opinion=f"停用字段「{row.label}」",
            attachment_ids=(), changed_fields=[],
            request_id=request_id, to_status=instance.status,
        )
        instance.last_action_at = self.clock()

        result = EngineResult(instance_status=instance.status)
        result.action_id = action_row.id
        result.events.append(
            self._event("EXT_FIELD_DISABLED", instance, row.visible_from_node_id, {
                "field_key": field_key,
            })
        )

        snap = self._write_snapshot(
            instance=instance, kind=SnapshotKind.EXT_FIELD,
            actor_id=actor.id, action_id=action_row.id,
        )
        action_row.snapshot_id = snap.id
        result.snapshot_id = snap.id

        self.db.commit()
        self.db.refresh(instance)
        return result

    def _active_node_keys(self, instance_id: int) -> list[str]:
        """当前活跃令牌所在的节点 key（按激活顺序）。"""
        self.db.flush()
        rows = self.db.execute(
            select(Task.node_key)
            .where(
                Task.instance_id == instance_id,
                Task.status == TaskStatus.PENDING,
                Task.blocks_flow.is_(True),
            )
            .order_by(Task.id)
        ).all()
        seen: list[str] = []
        for (key,) in rows:
            if key not in seen:
                seen.append(key)
        return seen

    # ==================================================================== 提交链路

    def _start_round(
        self,
        *,
        instance: FlowInstance,
        actor: User,
        values_in: dict[str, Any],
        note: str | None,
        attachment_ids: Sequence[int],
        event: str,
        kind: str,
        request_id: str | None,
    ) -> EngineResult:
        """提交与重提的公共部分：校验 → 写值 → 派发首节点。"""
        form_schema = self._schema_for(instance)
        compiled = self._compiled(instance)

        # 走到这里可能是「退回给发起人后重填」—— 那期间追加的动态字段此时可写，
        # 所以发起节点的权限同样要过一遍 L5
        permissions = self._permissions_for(
            instance, compiled, compiled.definition.start.id
        )
        values, diffs, permissions = self._apply_patch_with_rules(
            instance=instance,
            form_schema=form_schema,
            base_permissions=permissions,
            patch=values_in,
        )
        # 提交是「整单提交」，必填要全量校验（动作处理时只做增量校验）
        self._assert_required(permissions, values, form_schema)
        # 谁填的值谁负责：只校验发起阶段可编辑的那些字段
        self._assert_values_valid(form_schema, values, permissions, editable_only=True)

        now = self.clock()
        from_status = instance.status
        instance.current_data = values
        instance.status = assert_transition(instance.status, event)
        instance.started_at = instance.started_at or now
        instance.last_action_at = now

        action_row = self._write_action(
            instance=instance, task=None, assignment=None, actor=actor,
            action="SUBMIT" if event == EVENT_SUBMIT else "RESUBMIT",
            opinion=note, attachment_ids=attachment_ids, changed_fields=diffs,
            request_id=request_id, to_status=None,
        )
        action_row.from_status = from_status
        action_row.round = instance.round

        result = EngineResult(instance_status=instance.status)
        result.changed_fields = [d.to_dict() for d in diffs[:_MAX_CHANGED_FIELDS]]
        result.action_id = action_row.id

        # 快照要在派发**之前**写：它记录的是「提交那一刻的数据」，
        # 而且 seq 顺序必须与时间顺序一致（先提交、后节点动作）。
        snap = self._write_snapshot(
            instance=instance, kind=kind, actor_id=actor.id, action_id=action_row.id
        )
        action_row.snapshot_id = snap.id
        result.snapshot_id = snap.id

        cursors = plan_start(compiled, values)
        self._dispatch(instance, compiled, cursors, actor, result)
        action_row.to_status = instance.status

        self._persist_notifications(result.notifications)
        self.db.commit()
        self.db.refresh(instance)
        result.instance_status = instance.status
        return result

    # ==================================================================== 派发

    def _dispatch(
        self,
        instance: FlowInstance,
        compiled: CompiledFlow,
        cursors: Sequence[Cursor],
        actor: User,
        result: EngineResult,
        *,
        reactivate: bool = False,
    ) -> None:
        """把一批游标变成任务。

        `reactivate`：退回重派时为 True，会让同节点的 activation_seq +1
        （用于区分「同一节点的第二次激活」，历史任务保留）。
        """
        if not cursors:
            return

        values = instance.current_data or {}
        group_ids: dict[str, str] = {}
        finished = False

        for cursor in cursors:
            node = compiled.nodes.get(cursor.node_key)
            if node is None:
                raise FlowInvalid(f"流程定义里没有节点 “{cursor.node_key}”", node_id=cursor.node_key)

            # 到达结束节点 → 实例通过
            if node.type == "end":
                if not finished:
                    self._finish(instance, actor, result)
                    finished = True
                continue

            group_id: str | None = None
            if node.placement.kind == "parallel" and node.placement.parallel_id:
                # 同一次激活的组内成员共享一个 group_id（PRD §3.3.2 的并行容器）
                group_id = group_ids.setdefault(node.placement.parallel_id, uuid.uuid4().hex)

            self._spawn(instance, compiled, cursor, node_id=node.id, group_id=group_id,
                        actor=actor, result=result, reactivate=reactivate)

            # 抄送不占令牌、不阻塞主线：派发知会后**立即从它之后继续**
            # （PRD §3.3.2「抄送节点 | 无 | 生成抄送给我；不阻塞主线」）
            if node.type == "cc":
                self._dispatch(
                    instance, compiled,
                    plan_after_node(compiled, cursor, values),
                    actor, result, reactivate=reactivate,
                )

        self._sync_current_nodes(instance, compiled)

    def _spawn(
        self,
        instance: FlowInstance,
        compiled: CompiledFlow,
        cursor: Cursor,
        *,
        node_id: str,
        group_id: str | None,
        actor: User,
        result: EngineResult,
        reactivate: bool,
    ) -> Task | None:
        node = compiled.nodes[node_id]
        now = self.clock()

        activation_seq = self._next_activation_seq(instance.id, node_id, instance.round)

        task = Task(
            instance_id=instance.id,
            node_key=node_id,
            node_name=node.name,
            node_type=self._task_type(node.type),
            status=TaskStatus.PENDING,
            round=instance.round,
            activation_seq=activation_seq,
            gates=list(cursor.gates),
            group_id=group_id,
            node_def_snapshot=node.raw.model_dump(mode="json"),
            blocks_flow=node.is_blocking,
            activated_at=now,
        )

        # ---- 抄送：不占令牌，派发后主线立即继续 ----
        if node.type == "cc":
            resolution = resolve_cc(
                node.raw.cc_to, self._approver_context(instance, compiled), self.provider
            )
            if not resolution.user_ids:
                # 抄送没解析到人不是异常 —— 不打扰管理员，只是没人收到知会
                task.status = TaskStatus.COMPLETED
                task.completed_at = now
                self.db.add(task)
                return task
            task.assignee_mode = None
            self.db.add(task)
            self.db.flush()
            for user_id in resolution.user_ids:
                self.db.add(
                    TaskAssignment(
                        task_id=task.id, instance_id=instance.id, user_id=user_id,
                        seq=0, status=AssignmentStatus.PENDING,
                    )
                )
            self.db.flush()
            result.spawned.append(TokenOp(kind="spawn", node_key=node_id, gates=cursor.gates))
            result.events.append(self._event("CC_SENT", instance, node_id, {"count": len(resolution.user_ids)}))
            result.notifications.extend(
                notify.cc_received(
                    instance_id=instance.id,
                    instance_title=instance.title,
                    node_name=node.name,
                    assignments=self._assignment_pairs(task),
                )
            )
            return task

        # ---- 审批 / 填写：解析审批人 ----
        rule = getattr(node.raw, "assignee", None)
        resolution = resolve_approvers(
            rule, self._approver_context(instance, compiled), self.provider
        )
        if resolution.abnormal:
            task.abnormal = True
            task.abnormal_reason = (resolution.reason or "")[:128]
            instance.abnormal = True
            result.notifications.extend(
                notify.abnormal_assignment(
                    instance_id=instance.id,
                    instance_title=instance.title,
                    node_name=node.name,
                    admin_ids=resolution.fallback_admin_ids,
                    reason=resolution.reason or "未解析到审批人",
                )
            )

        assignee_ids = order_by_mode(rule.mode if rule else AggregateMode.SINGLE, resolution.resolved_ids)
        task.assignee_mode = rule.mode if rule else AggregateMode.SINGLE
        task.approver_resolved = resolution.by_source or None

        self.db.add(task)
        self.db.flush()

        for index, user_id in enumerate(assignee_ids):
            self.db.add(
                TaskAssignment(
                    task_id=task.id,
                    instance_id=instance.id,
                    user_id=user_id,
                    seq=index,
                    status=initial_status_for_mode(task.assignee_mode, index),
                )
            )
        self.db.flush()

        result.spawned.append(
            TokenOp(
                kind="spawn",
                node_key=node_id,
                gates=cursor.gates,
                group_id=group_id,
                assignee_ids=tuple(assignee_ids),
                abnormal=resolution.abnormal,
                abnormal_reason=resolution.reason,
            )
        )
        result.events.append(
            self._event(
                "NODE_SPAWNED",
                instance,
                node_id,
                {
                    "assignees": assignee_ids,
                    "mode": task.assignee_mode,
                    "group_id": group_id,
                    "activation_seq": activation_seq,
                },
            )
        )
        result.notifications.extend(
            notify.task_created(
                instance_id=instance.id,
                instance_title=instance.title,
                node_name=node.name,
                assignments=self._assignment_pairs(task),
                round_no=instance.round,
            )
        )
        self._sync_current_nodes(instance, compiled)
        return task

    def _finish(self, instance: FlowInstance, actor: User, result: EngineResult) -> None:
        """走到结束节点 → APPROVED（PRD §3.5.1）。"""
        instance.status = assert_transition(instance.status, EVENT_FINISH)
        instance.finished_at = self.clock()
        result.events.append(self._event("INSTANCE_FINISHED", instance, None, {}))

        snap = self._write_snapshot(
            instance=instance, kind=SnapshotKind.ARCHIVE, actor_id=actor.id, action_id=None
        )
        result.snapshot_id = snap.id
        result.notifications.extend(
            notify.instance_status_changed(
                instance_id=instance.id,
                instance_title=instance.title,
                status=instance.status,
                recipients=self._participants(instance),
            )
        )

    # ==================================================================== 动作分支

    def _handle_pass(
        self,
        instance: FlowInstance,
        compiled: CompiledFlow,
        task: Task,
        cursor: Cursor,
        node: Any,
        actor: User,
        result: EngineResult,
    ) -> None:
        """同意 / 提交：聚合后决定节点是否走完。"""
        mode = task.assignee_mode or AggregateMode.SINGLE
        views = self._assignment_views(task)
        state = node_state(mode, views)

        if state == "FAILED":
            # 只可能由并发/异常造成（进入这个方法时本次动作是「通过」）
            raise ConflictError("任务状态与预期不符，请刷新后重试", code="STALE_ASSIGNMENT")

        if state == "OPEN":
            # 依次审批：激活下一个
            next_seq = next_sequential_seq(views)
            if next_seq is not None:
                self._activate_assignment(task, next_seq, instance, result)
            return

        # ---- 节点通过 ----
        task.status = TaskStatus.COMPLETED
        task.completed_at = self.clock()
        result.events.append(self._event("NODE_COMPLETED", instance, node.id, {}))

        if should_cancel_siblings_on_pass(mode):
            self._cancel_assignments(
                task,
                reason=CancelReason.ANY_SIGN_DONE,
                instance=instance,
                result=result,
                notify_users=True,
            )

        # ---- 并行组：等组内全部完成 ----
        if task.group_id:
            members = self._group_member_tasks(task)
            container_id = self._container_of_member(compiled, node.id)
            container_cursor = Cursor(container_id, cursor.gates, cursor.round)
            group_mode = self._group_mode(compiled, container_id)
            gs = group_state(group_mode, [TaskView(m.id, m.node_key, m.node_type, m.status) for m in members])

            if gs == "FAILED":
                self._fail_group(instance, task, members, actor, result)
                return
            if gs == "OPEN":
                self._sync_current_nodes(instance, compiled)
                return
            # JOINED → 从容器位置继续
            result.events.append(
                self._event("GROUP_JOINED", instance, container_id, {"members": [m.id for m in members]})
            )
            if normalize_mode(group_mode) == AggregateMode.ANY:
                # 或签：组已因某人通过而汇合 → 其余成员的待办作废（PRD §3.5.3）
                now_mark = self.clock()
                for member in members:
                    if member.id == task.id or member.status != TaskStatus.PENDING:
                        continue
                    member.status = TaskStatus.CANCELLED
                    member.cancelled_at = now_mark
                    member.cancel_reason = CancelReason.ANY_SIGN_DONE
                    self._cancel_assignments(
                        member, reason=CancelReason.ANY_SIGN_DONE, instance=instance,
                        result=result, notify_users=True,
                    )
            next_cursors = plan_after_group(compiled, container_cursor, instance.current_data or {})
        else:
            next_cursors = plan_after_node(compiled, cursor, instance.current_data or {})

        self._dispatch(instance, compiled, next_cursors, actor, result)
        self._sync_current_nodes(instance, compiled)

    def _handle_reject(
        self,
        instance: FlowInstance,
        task: Task,
        actor: User,
        opinion: str | None,
        result: EngineResult,
    ) -> None:
        """驳回至发起人（PRD §3.5.4）：实例 → REJECTED，任务全取消。"""
        task.status = TaskStatus.CANCELLED
        task.cancelled_at = self.clock()
        task.cancel_reason = CancelReason.REJECTED

        cancelled = self._cancel_pending(instance, CancelReason.REJECTED, exclude_task_id=task.id)
        instance.status = assert_transition(instance.status, EVENT_REJECT)

        self._notify_cancelled(instance, cancelled, "发起人已被驳回", result)
        result.events.append(self._event("INSTANCE_REJECTED", instance, task.node_key, {"opinion": opinion}))
        result.notifications.extend(
            notify.instance_status_changed(
                instance_id=instance.id,
                instance_title=instance.title,
                status=instance.status,
                recipients=[instance.initiator_id],
                node_name=task.node_name,
                extra=opinion,
            )
        )
        instance.current_node_keys = []

    def _handle_return(
        self,
        instance: FlowInstance,
        compiled: CompiledFlow,
        task: Task,
        cursor: Cursor,
        return_target: str | None,
        actor: User,
        result: EngineResult,
    ) -> None:
        """退回到指定节点（PRD §3.5.4）：实例**仍为 RUNNING**，只重派令牌。"""
        if not return_target:
            raise UnprocessableError("退回必须指定目标节点", code="RETURN_TARGET_REQUIRED")

        target_node = compiled.nodes.get(return_target)
        if target_node is None:
            raise UnprocessableError(f"退回目标 “{return_target}” 不存在", code="RETURN_TARGET_INVALID")

        allowed = {t.id for t in allowed_return_targets(compiled, cursor)}
        if return_target not in allowed:
            raise UnprocessableError(
                f"不能退回到「{target_node.name}」—— 它不是本节点的前序审批/填写节点",
                code="RETURN_TARGET_NOT_ALLOWED",
            )

        now = self.clock()
        task.status = TaskStatus.CANCELLED
        task.cancelled_at = now
        task.cancel_reason = CancelReason.RETURNED

        # 取消目标之后的全部令牌（含并行组、或签其余）
        pending_cursors = [
            Cursor(t.node_key, tuple(t.gates), t.round)
            for t in self._pending_tasks(instance.id, exclude_task_id=task.id)
        ]
        target_cursor = Cursor(return_target, target_node.gates, instance.round)
        to_cancel = cancel_set_for_return(compiled, pending_cursors, target_cursor)
        cancel_keys = {(c.node_key, c.gates) for c in to_cancel}
        for pending_task in self._pending_tasks(instance.id, exclude_task_id=task.id):
            if (pending_task.node_key, tuple(pending_task.gates)) in cancel_keys:
                pending_task.status = TaskStatus.CANCELLED
                pending_task.cancelled_at = now
                pending_task.cancel_reason = CancelReason.RETURNED
                self._cancel_assignments(
                    pending_task, reason=CancelReason.RETURNED, instance=instance,
                    result=result, notify_users=True,
                )
                result.cancelled.append(
                    TokenOp(kind="cancel", node_key=pending_task.node_key,
                            gates=tuple(pending_task.gates), reason=CancelReason.RETURNED)
                )

        # 在目标节点重新派发（activation_seq 自然 +1，历史任务保留）
        result.events.append(
            self._event("NODE_RETURNED", instance, task.node_key, {
                "from": task.node_key, "to": return_target,
            })
        )
        self._dispatch(
            instance, compiled, [target_cursor], actor, result, reactivate=True
        )
        result.notifications.extend(
            notify.returned(
                instance_id=instance.id,
                instance_title=instance.title,
                from_node=task.node_name,
                to_node=target_node.name,
                recipients=self._node_assignees(target_node.id, instance.id) or [instance.initiator_id],
            )
        )
        # **注意：实例状态不变（仍 RUNNING）**，字段数据也不回滚（PRD §3.5.4）
        self._sync_current_nodes(instance, compiled)

    def _fail_group(
        self,
        instance: FlowInstance,
        failing_task: Task,
        members: Sequence[Task],
        actor: User,
        result: EngineResult,
    ) -> None:
        """并行组失败：取消组内其余成员，然后按失败动作处理整实例。

        V1 的组失败一律按「驳回至发起人」处理 —— 会签任一人驳回即整单驳回
        （PRD §3.5.3「任一子任务驳回/退回 → 组失败」）。
        """
        now = self.clock()
        for member in members:
            if member.id == failing_task.id or member.status != TaskStatus.PENDING:
                continue
            member.status = TaskStatus.CANCELLED
            member.cancelled_at = now
            member.cancel_reason = CancelReason.GROUP_FAILED
            self._cancel_assignments(
                member, reason=CancelReason.GROUP_FAILED, instance=instance,
                result=result, notify_users=True,
            )
            result.cancelled.append(
                TokenOp(kind="cancel", node_key=member.node_key,
                        gates=tuple(member.gates), reason=CancelReason.GROUP_FAILED)
            )
        self._handle_reject(instance, failing_task, actor, None, result)

    # ==================================================================== 取消

    def _cancel_pending(
        self,
        instance: FlowInstance,
        reason: str,
        *,
        exclude_task_id: int | None = None,
    ) -> list[Task]:
        """取消实例上全部待办令牌。抄送 task 不占令牌，顺带一起取消。"""
        now = self.clock()
        cancelled: list[Task] = []
        for task in self._pending_tasks(instance.id, exclude_task_id=exclude_task_id):
            task.status = TaskStatus.CANCELLED
            task.cancelled_at = now
            task.cancel_reason = reason
            self._cancel_assignments(task, reason=reason, instance=instance, result=None, notify_users=False)
            cancelled.append(task)
        instance.current_node_keys = []
        return cancelled

    def _cancel_assignments(
        self,
        task: Task,
        *,
        reason: str,
        instance: FlowInstance,
        result: EngineResult | None,
        notify_users: bool,
    ) -> None:
        now = self.clock()
        pairs: list[tuple[int, int]] = []
        for assignment in task.assignments:
            if assignment.status not in {AssignmentStatus.PENDING, AssignmentStatus.WAITING}:
                continue
            # 待办中的才通知 —— 已经被取消/已处理的不再打扰
            pairs.append((assignment.user_id, assignment.id))
            assignment.status = AssignmentStatus.CANCELLED
            assignment.cancelled_at = now
            assignment.cancel_reason = reason
        if notify_users and result is not None and pairs:
            result.notifications.extend(
                notify.task_cancelled(
                    instance_id=instance.id,
                    instance_title=instance.title,
                    node_name=task.node_name,
                    assignment_ids=pairs,
                    reason=self._reason_label(reason),
                )
            )

    def _notify_cancelled(
        self,
        instance: FlowInstance,
        cancelled: Iterable[Task],
        reason: str,
        result: EngineResult,
    ) -> None:
        for task in cancelled:
            pairs = [(a.user_id, a.id) for a in task.assignments]
            if pairs:
                result.notifications.extend(
                    notify.task_cancelled(
                        instance_id=instance.id,
                        instance_title=instance.title,
                        node_name=task.node_name,
                        assignment_ids=pairs,
                        reason=reason,
                    )
                )

    def _activate_assignment(
        self, task: Task, seq: int, instance: FlowInstance, result: EngineResult
    ) -> None:
        for assignment in task.assignments:
            if assignment.seq == seq and assignment.status == AssignmentStatus.WAITING:
                assignment.status = AssignmentStatus.PENDING
                if task.assignee_mode == AggregateMode.SEQUENTIAL:
                    # 依次审批：只通知刚被激活的那一个
                    result.notifications.extend(
                        notify.task_created(
                            instance_id=instance.id,
                            instance_title=instance.title,
                            node_name=task.node_name,
                            assignments=[(assignment.user_id, assignment.id)],
                            round_no=instance.round,
                        )
                    )
                return

    # ==================================================================== 持久化

    def _write_action(
        self,
        *,
        instance: FlowInstance | None,
        task: Task | None,
        assignment: TaskAssignment | None,
        actor: User,
        action: str,
        opinion: str | None,
        attachment_ids: Sequence[int],
        changed_fields: Sequence[Any],
        request_id: str | None,
        to_status: str | None,
    ) -> InstanceAction:
        """写一条动作记录。幂等键由 DDL 的唯一约束兜底。"""
        assert instance is not None
        action_seq = self._next_action_seq(instance.id, task.id if task else 0, actor.id)
        row = InstanceAction(
            instance_id=instance.id,
            task_id=task.id if task else 0,
            assignment_id=assignment.id if assignment else None,
            node_key=task.node_key if task else None,
            node_name=task.node_name if task else None,
            actor_id=actor.id,
            action=action,
            action_seq=action_seq,
            round=instance.round,
            from_status=instance.status,
            to_status=to_status,
            opinion=opinion,
            attachments=list(attachment_ids) or None,
            changed_fields=[d.to_dict() if hasattr(d, "to_dict") else d for d in changed_fields] or None,
            request_id=request_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _write_snapshot(
        self, *, instance: FlowInstance, kind: str, actor_id: int, action_id: int | None
    ) -> DataSnapshot:
        ext = [
            {
                "field_key": f.field_key, "label": f.label, "type": f.type,
                "required": f.required, "status": f.status,
                "editable_node_ids": f.editable_node_ids,
                "visible_from_node_id": f.visible_from_node_id,
            }
            for f in instance.ext_fields
        ]
        payload = snapshot_mod.build_snapshot_payload(instance.current_data or {}, ext)
        seq = self._next_snapshot_seq(instance.id)
        snap = DataSnapshot(
            instance_id=instance.id,
            round=instance.round,
            seq=seq,
            kind=kind,
            data=payload,
            data_hash=snapshot_mod.hash_values(instance.current_data or {}),
            action_id=action_id,
            created_by=actor_id,
        )
        self.db.add(snap)
        self.db.flush()
        return snap

    def _persist_notifications(self, drafts: Sequence[NotificationDraft]) -> None:
        """落库。dedup_key 唯一索引让重复通知被静默忽略（幂等延伸到通知层）。"""
        if not drafts:
            return
        seen: set[str] = set()
        for draft in drafts:
            if draft.dedup_key:
                if draft.dedup_key in seen:
                    continue
                seen.add(draft.dedup_key)
        existing = set()
        keys = [d.dedup_key for d in drafts if d.dedup_key]
        if keys:
            existing = {
                row[0]
                for row in self.db.execute(
                    select(Notification.dedup_key).where(Notification.dedup_key.in_(keys))
                ).all()
            }
        for draft in drafts:
            if draft.dedup_key and draft.dedup_key in existing:
                continue
            self.db.add(
                Notification(
                    user_id=draft.user_id,
                    type=draft.type,
                    title=draft.title,
                    content=draft.content,
                    payload=draft.payload or None,
                    link=draft.link,
                    dedup_key=draft.dedup_key,
                )
            )
        self.db.flush()

    # ==================================================================== 查询辅助

    def _lock(self, instance_id: int) -> FlowInstance:
        """按 id 锁定实例行 —— 所有令牌变更在持锁期间完成。

        MySQL 上 with_for_update() 会发 SELECT ... FOR UPDATE；
        SQLite 忽略它（单写者模型下写事务本身已串行化）。
        """
        locked = self.db.execute(
            select(FlowInstance).where(FlowInstance.id == instance_id).with_for_update()
        ).scalar_one_or_none()
        if locked is None:
            raise NotFoundError("流程实例不存在", code="INSTANCE_NOT_FOUND")
        return locked

    def _form_schema(self, instance: FlowInstance):
        version = self.db.get(FormVersion, instance.form_version_id)
        if version is None:
            raise NotFoundError("表单版本不存在", code="FORM_VERSION_NOT_FOUND")
        return parse_form_schema(version.schema)

    def _compiled(self, instance: FlowInstance) -> CompiledFlow:
        version = self.db.get(FlowVersion, instance.flow_version_id)
        if version is None:
            raise NotFoundError("流程版本不存在", code="FLOW_VERSION_NOT_FOUND")
        return compile_definition(version.definition)

    def _permissions_for(
        self,
        instance: FlowInstance,
        compiled: CompiledFlow,
        node_key: str,
        *,
        gates: Sequence[str] = (),
        round_no: int | None = None,
    ) -> dict[str, FieldPermission]:
        """某节点上「谁能写谁只读」。

        **写入路径的唯一准入依据** —— 机制 C 的动态字段也必须在这里放行，
        否则处理人填的值会被 `apply_field_patch` 静默丢弃。
        """
        node = compiled.nodes.get(node_key)
        rule = None
        node_type = "approval"
        if node is not None:
            node_type = node.type
            if node.type == "start":
                rule = compiled.definition.start.fields_permission
            else:
                rule = getattr(node.raw, "fields_permission", None)
        permissions = resolve_field_permissions(
            form_schema=self._schema_for(instance),
            node_type=node_type,
            rule=rule,
            values=instance.current_data or {},
        )
        if node is None:
            return permissions
        # L5：动态字段叠加在模板权限之上（最后求值，覆盖 L0–L4）
        return apply_ext_fields(
            permissions,
            self._ext_views(instance),
            node_id=node_key,
            node_ancestors=compiled.ancestors(
                Cursor(node_key, tuple(gates), round_no or instance.round)
            ),
        )

    def _apply_patch_with_rules(
        self,
        *,
        instance: FlowInstance,
        form_schema: Any,
        base_permissions: Mapping[str, FieldPermission],
        patch: Mapping[str, Any],
    ) -> tuple[dict[str, Any], list[FieldDiff], dict[str, FieldPermission]]:
        """应用字段补丁，再用联动规则收紧权限并校验。

        规则可能依赖本次提交的新值（例如「是否出差」刚被改成是），所以先用
        「当前值 + 本次补丁」求一次权限，再吸收补丁；公式/清值可能再次改变
        条件命中，最多再迭代两轮。
        """
        current = instance.current_data or {}
        candidate = {**current, **patch}
        effective = apply_form_rules(base_permissions, form_schema, candidate)
        values, diffs = apply_field_patch(
            current=current,
            patch=patch,
            permissions=effective,
            form_schema=form_schema,
        )

        for _ in range(2):
            next_effective = apply_form_rules(base_permissions, form_schema, values)
            if next_effective == effective:
                break
            effective = next_effective
            values, diffs = apply_field_patch(
                current=current,
                patch=patch,
                permissions=effective,
                form_schema=form_schema,
            )

        clear_keys = hidden_clear_keys(base_permissions, form_schema, values)
        if clear_keys:
            labels = field_label_index(form_schema)
            cleared = False
            for key in clear_keys:
                permission = effective.get(key)
                if permission is None or permission.visible:
                    continue
                if key in values and values.get(key) not in (None, "", []):
                    diffs.append(FieldDiff(key, labels.get(key, key), values.get(key), None))
                    values.pop(key, None)
                    cleared = True
            if cleared:
                # 清值可能影响公式，公式再重算一遍
                values, formula_diffs = apply_field_patch(
                    current=values,
                    patch={},
                    permissions=effective,
                    form_schema=form_schema,
                )
                diffs.extend(formula_diffs)

        return values, diffs, effective

    def _ext_views(self, instance: FlowInstance) -> list[ExtFieldView]:
        return [
            ExtFieldView(
                field_key=f.field_key,
                label=f.label,
                type=f.type,
                required=bool(f.required),
                editable_node_ids=tuple(f.editable_node_ids or ()),
                visible_from_node_id=f.visible_from_node_id,
            )
            for f in instance.ext_fields
            if f.status == "ACTIVE"
        ]

    def _schema_for(self, instance: FlowInstance):
        """模板 schema ⊕ 机制 C 的动态字段（写入与渲染共用同一份视图）。"""
        return merge_ext_fields(self._form_schema(instance), list(instance.ext_fields))

    def _approver_context(self, instance: FlowInstance, compiled: CompiledFlow) -> ApproverContext:
        completed = list(
            self.db.scalars(
                select(Task)
                .where(Task.instance_id == instance.id, Task.status == TaskStatus.COMPLETED)
                .order_by(Task.completed_at)
            ).all()
        )
        prev_actors: dict[str, list[int]] = {}
        for task in completed:
            prev_actors.setdefault(task.node_key, []).extend(
                a.user_id
                for a in task.assignments
                if a.status == AssignmentStatus.DONE
                and a.result in {AssignmentResult.AGREE, AssignmentResult.SUBMIT}
            )
        return ApproverContext(
            initiator_id=instance.initiator_id,
            initiator_dept_id=instance.initiator_dept_id,
            values=instance.current_data or {},
            prev_actors=prev_actors,
            last_completed_node_id=completed[-1].node_key if completed else None,
        )

    def _pending_tasks(self, instance_id: int, *, exclude_task_id: int | None = None) -> list[Task]:
        # 会话是 autoflush=False，查询看不到本事务里尚未 flush 的改动 ——
        # 而聚合判定恰恰要读「刚刚改过的 task 状态」，所以这里必须显式 flush。
        self.db.flush()
        stmt = (
            select(Task)
            .where(Task.instance_id == instance_id, Task.status == TaskStatus.PENDING)
            .options(selectinload(Task.assignments))
            .order_by(Task.id)
        )
        tasks = list(self.db.scalars(stmt).all())
        if exclude_task_id is not None:
            tasks = [t for t in tasks if t.id != exclude_task_id]
        return tasks

    def _group_member_tasks(self, task: Task) -> list[Task]:
        if not task.group_id:
            return [task]
        # 同上：组聚合要看到刚标记为 COMPLETED 的自己
        self.db.flush()
        return list(
            self.db.scalars(select(Task).where(Task.group_id == task.group_id).order_by(Task.id)).all()
        )

    @staticmethod
    def _container_of_member(compiled: CompiledFlow, node_id: str) -> str:
        placement = compiled.nodes[node_id].placement
        if placement.kind == "parallel" and placement.parallel_id:
            return placement.parallel_id
        return node_id

    @staticmethod
    def _group_mode(compiled: CompiledFlow, container_id: str) -> str:
        node = compiled.nodes.get(container_id)
        if node is None:
            return AggregateMode.ALL
        return getattr(node.raw, "mode", AggregateMode.ALL)

    @staticmethod
    def _assignment_views(task: Task) -> list[AssignmentView]:
        return [
            AssignmentView(user_id=a.user_id, status=a.status, result=a.result, seq=a.seq)
            for a in task.assignments
        ]

    @staticmethod
    def _assignment_pairs(task: Task) -> list[tuple[int, int]]:
        return [
            (a.user_id, a.id)
            for a in task.assignments
            if a.status in {AssignmentStatus.PENDING, AssignmentStatus.WAITING}
        ]

    def _participants(self, instance: FlowInstance) -> list[int]:
        """实例的所有参与者：发起人 + 历任处理人。"""
        rows = self.db.execute(
            select(TaskAssignment.user_id)
            .where(TaskAssignment.instance_id == instance.id)
            .distinct()
        ).all()
        return list(dict.fromkeys([instance.initiator_id, *(r[0] for r in rows)]))

    def _node_assignees(self, node_key: str, instance_id: int) -> list[int]:
        rows = self.db.execute(
            select(TaskAssignment.user_id)
            .join(Task, Task.id == TaskAssignment.task_id)
            .where(Task.instance_id == instance_id, Task.node_key == node_key)
            .distinct()
        ).all()
        return [r[0] for r in rows]

    def _sync_current_nodes(self, instance: FlowInstance, compiled: CompiledFlow) -> None:
        """维护实例上的活跃节点冗余列（列表页展示用）。"""
        pending = self._pending_tasks(instance.id)
        instance.current_node_keys = [
            compiled.nodes[t.node_key].name if t.node_key in compiled.nodes else t.node_key
            for t in pending
            if t.blocks_flow
        ]

    # ==================================================================== 计数器

    def _next_action_seq(self, instance_id: int, task_id: int, actor_id: int) -> int:
        from sqlalchemy import func

        current = self.db.scalar(
            select(func.max(InstanceAction.action_seq)).where(
                InstanceAction.instance_id == instance_id,
                InstanceAction.task_id == task_id,
                InstanceAction.actor_id == actor_id,
            )
        )
        return (current or 0) + 1

    def _next_snapshot_seq(self, instance_id: int) -> int:
        from sqlalchemy import func

        current = self.db.scalar(
            select(func.max(DataSnapshot.seq)).where(DataSnapshot.instance_id == instance_id)
        )
        return (current or 0) + 1

    def _next_activation_seq(self, instance_id: int, node_key: str, round_no: int) -> int:
        from sqlalchemy import func

        current = self.db.scalar(
            select(func.max(Task.activation_seq)).where(
                Task.instance_id == instance_id,
                Task.node_key == node_key,
                Task.round == round_no,
            )
        )
        return (current or 0) + 1

    # ==================================================================== 断言

    def _assert_can_act(
        self,
        instance: FlowInstance,
        task: Task,
        assignment: TaskAssignment,
        actor: User,
        expected_version: int | None,
    ) -> None:
        if expected_version is not None and instance.version != expected_version:
            raise ConflictError(
                "数据已被他人修改，请刷新后重试",
                code="STALE_VERSION",
                extra={"expected": expected_version, "actual": instance.version},
            )
        if assignment.user_id != actor.id:
            # 授权失败而不是业务规则失败 —— 前端据此走「无权限」而非「重试」分支
            raise ForbiddenError("这不是分配给你的任务", code="NOT_ASSIGNEE")
        if assignment.status != AssignmentStatus.PENDING:
            raise ConflictError(
                "该任务已处理或已取消，请刷新后重试", code="ASSIGNMENT_NOT_PENDING"
            )
        if task.round != instance.round:
            raise ConflictError("该任务属于上一轮，已被作废", code="STALE_ROUND")
        if instance.status != InstanceStatus.RUNNING:
            raise IllegalTransition(instance.status, "处理任务")

    def _assert_can_withdraw(self, instance: FlowInstance) -> None:
        if instance.status != InstanceStatus.RUNNING:
            raise IllegalTransition(instance.status, EVENT_WITHDRAW)
        handled = self.db.scalar(
            select(TaskAssignment.id)
            .join(Task, Task.id == TaskAssignment.task_id)
            .where(
                TaskAssignment.instance_id == instance.id,
                TaskAssignment.status == AssignmentStatus.DONE,
                # 抄送已读不算「被处理过」（PRD §3.5.4 括号说明）
                Task.node_type != TaskType.CC,
            )
            .limit(1)
        )
        if handled is not None:
            raise UnprocessableError(
                "已经有任务被处理过，不能撤回；如需终止请联系管理员",
                code="WITHDRAW_NOT_ALLOWED",
            )

    def _assert_opinion_and_attachment(
        self, node: Any, action: str, opinion: str | None, attachment_ids: Sequence[int]
    ) -> None:
        if getattr(node.raw, "opinion_required", False) and not (opinion or "").strip():
            raise UnprocessableError("本节点要求填写审批意见", code="OPINION_REQUIRED")
        # 驳回必须说明理由 —— 否则发起人不知道要改什么（PRD §3.5.4）
        if action == AssignmentResult.REJECT and not (opinion or "").strip():
            raise UnprocessableError("驳回必须填写意见", code="REJECT_OPINION_REQUIRED")
        if getattr(node.raw, "attachment_required", False) and not attachment_ids:
            raise UnprocessableError("本节点要求上传附件", code="ATTACHMENT_REQUIRED")

    def _assert_action_allowed(
        self,
        node: Any,
        action: str,
        return_target: str | None,
        compiled: CompiledFlow,
        cursor: Cursor,
    ) -> None:
        if node.type == "fill":
            if action not in {AssignmentResult.SUBMIT, AssignmentResult.RETURN}:
                raise UnprocessableError(
                    "填写节点只有「提交」与「退回」两个动作", code="ACTION_NOT_ALLOWED"
                )
        elif node.type == "approval":
            if action not in {
                AssignmentResult.AGREE, AssignmentResult.REJECT, AssignmentResult.RETURN
            }:
                raise UnprocessableError("审批节点只能用同意 / 驳回 / 退回", code="ACTION_NOT_ALLOWED")
            if action == AssignmentResult.REJECT and getattr(node.raw, "reject_policy", "") == "reject_forbidden":
                raise UnprocessableError("本节点不允许驳回", code="REJECT_FORBIDDEN")
        else:
            raise UnprocessableError(f"节点类型 {node.type} 不接受处理动作", code="ACTION_NOT_ALLOWED")

        if action == AssignmentResult.RETURN and not return_target:
            raise UnprocessableError("退回必须选择目标节点", code="RETURN_TARGET_REQUIRED")

    def _assert_required(
        self,
        permissions: Mapping[str, FieldPermission],
        values: Mapping[str, Any],
        form_schema: Any,
        *,
        partial: bool = False,
    ) -> None:
        """必填校验。

        `partial=True`（动作处理时）只校验**本节点可编辑的**字段 ——
        审批人不该因为申请人漏填了别的字段而无法提交。
        """
        missing: list[str] = []
        for section in form_schema.sections:
            for field in section.fields:
                permission = permissions.get(field.key)
                if permission is None or not permission.required:
                    continue
                if partial and not permission.editable:
                    continue
                value = values.get(field.key)
                if value in (None, "", []) :
                    missing.append(field.label)
                elif field.type.value == "subtable" and isinstance(value, list):
                    for index, row in enumerate(value):
                        for col in field.columns or []:
                            if not col.required:
                                continue
                            cell = row.get(col.key) if isinstance(row, dict) else None
                            if cell in (None, "", []):
                                missing.append(f"{field.label} 第 {index + 1} 行的「{col.label}」")
        if missing:
            raise UnprocessableError(
                "以下必填项未填写：" + "、".join(missing[:5]) + ("…" if len(missing) > 5 else ""),
                code="REQUIRED_FIELDS_MISSING",
                extra={"fields": missing},
            )

    def _assert_values_valid(
        self,
        form_schema: Any,
        values: Mapping[str, Any],
        permissions: Mapping[str, FieldPermission],
        *,
        editable_only: bool = False,
    ) -> None:
        """字段级规则校验（长度/范围/正则/选项/级联/子表行数）。

        `editable_only=True` 时只查本节点可编辑的字段 —— 别人填过的旧值
        不归这次操作负责（与 `_assert_required(partial=...)` 同一套道理）。
        """
        only_keys = editable_keys(permissions) if editable_only else None
        issues = validate_values(form_schema, values, only_keys=only_keys)
        if not issues:
            return
        raise UnprocessableError(
            "、".join(issue.message for issue in issues[:5])
            + ("…" if len(issues) > 5 else ""),
            code="FIELD_VALIDATION_FAILED",
            extra={"issues": [i.to_dict() for i in issues]},
        )

    # ==================================================================== 杂项

    @staticmethod
    def _task_type(node_type: str) -> str:
        return {
            "approval": TaskType.APPROVAL,
            "fill": TaskType.FILL,
            "cc": TaskType.CC,
        }.get(node_type, TaskType.APPROVAL)

    @staticmethod
    def _flatten_picks(picks: Mapping[str, Sequence[int]]) -> list[int]:
        """发起人指定审批人的选择结果拍平成一个列表（按审批人来源取用）。"""
        out: list[int] = []
        for ids in picks.values():
            for uid in ids:
                if uid not in out:
                    out.append(uid)
        return out

    @staticmethod
    def _reason_label(reason: str) -> str:
        return {
            CancelReason.ANY_SIGN_DONE: "其他人已处理",
            CancelReason.REJECTED: "流程被驳回",
            CancelReason.RETURNED: "流程被退回",
            CancelReason.WITHDRAWN: "发起人撤回",
            CancelReason.TERMINATED: "管理员终止",
            CancelReason.RESUBMITTED: "发起人重新提交",
            CancelReason.GROUP_FAILED: "并行组已有成员未通过",
        }.get(reason, reason)

    @staticmethod
    def _update_field_meta(
        meta: dict[str, Any] | None,
        diffs: Sequence[Any],
        *,
        node_key: str,
        actor_id: int,
        action_id: int,
        round_no: int,
    ) -> dict[str, Any]:
        out = dict(meta or {})
        stamp = utcnow().isoformat()
        for item in diffs:
            key = item.key if hasattr(item, "key") else item.get("key")
            if not key:
                continue
            out[key] = {
                "node": node_key,
                "actor_id": actor_id,
                "action_id": action_id,
                "round": round_no,
                "at": stamp,
            }
        return out

    @staticmethod
    def _event(
        event_type: str, instance: FlowInstance, node_key: str | None, payload: Mapping[str, Any]
    ):
        from app.engine.types import EngineEvent

        return EngineEvent(
            type=event_type,
            payload={"instance_id": instance.id, "node_key": node_key, **payload},
            at=utcnow(),
        )


def _status_label(status: str) -> str:
    """实例状态的中文名，用于给用户看的错误信息。"""
    return INSTANCE_STATUS_LABELS.get(status, status)
