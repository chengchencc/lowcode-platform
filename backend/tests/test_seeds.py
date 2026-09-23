"""初始化种子（F6.5 / M6 ①）。

示例数据最容易出的一种问题是「写进去就没人验过」：模板能建、但发布校验
过不去，或者流程引用了不存在的角色 id。这里把种子库真的跑一遍。

`conftest.py` 的 session 夹具已经在建库时跑过一次 `run_seed`（含示例流程库），
所以下面的断言顺带证明了「每次启动的种子是幂等的」。
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.constants import (
    FlowStatus,
    FlowVersionStatus,
    FormStatus,
    FormVersionStatus,
    RoleCode,
    UserStatus,
)
from app.models import (
    Department,
    FlowInstance,
    FlowTemplate,
    FlowVersion,
    FormTemplate,
    FormVersion,
    Role,
    User,
    UserRole,
)
from app.seeds import demo_accounts, sample_flows
from app.services import flow_service


def _published(db, name: str) -> tuple[FormTemplate, FormVersion]:
    template = db.scalar(select(FormTemplate).where(FormTemplate.name == name))
    assert template is not None, f"缺少示例表单模板：{name}"
    version = db.get(FormVersion, template.current_version_id)
    assert version is not None
    return template, version


class TestSampleFlows:
    def test_both_samples_are_published(self, db):
        for form_name, flow_name in (
            ("请假申请单", "请假申请"),
            ("费用报销单", "费用报销"),
        ):
            form, form_version = _published(db, form_name)
            assert form.status == FormStatus.PUBLISHED
            assert form.group_name == sample_flows.SAMPLE_GROUP
            assert form_version.status == FormVersionStatus.PUBLISHED

            flow = db.scalar(select(FlowTemplate).where(FlowTemplate.name == flow_name))
            assert flow is not None, f"缺少示例流程模板：{flow_name}"
            assert flow.status == FlowStatus.PUBLISHED
            assert flow.form_template_id == form.id
            assert flow.initiator_scope == {"type": "all"}
            version = db.get(FlowVersion, flow.current_version_id)
            assert version is not None and version.status == FlowVersionStatus.PUBLISHED

    def test_role_sources_are_filled_with_real_role_ids(self, db):
        """定义里的角色占位要换成真实 id —— 否则审批人永远解析不出来。"""
        role_ids = {
            r.id for r in db.scalars(select(Role).where(Role.code.in_(
                [RoleCode.FINANCE, RoleCode.PLATFORM_ADMIN, RoleCode.DEPT_MANAGER]
            ))).all()
        }
        flow = db.scalar(select(FlowTemplate).where(FlowTemplate.name == "费用报销"))
        assert flow is not None
        version = db.get(FlowVersion, flow.current_version_id)
        assert version is not None

        found: list[int] = []

        def walk(steps: list[dict]) -> None:
            for step in steps:
                for holder in (step.get("assignee"), step.get("cc_to")):
                    for source in (holder or {}).get("sources", []) or []:
                        found.extend(source.get("role_ids", []) or [])
                walk(step.get("members", []) or [])
                for branch in step.get("branches", []) or []:
                    walk(branch.get("steps", []) or [])

        walk(version.definition["steps"])
        assert found, "示例流程里应当有角色来源"
        assert set(found) <= role_ids

    def test_leave_flow_is_usable_by_anyone(self, db):
        """示例流程对全员开放，且锁定的是自己的表单发布版本。"""
        flow = db.scalar(select(FlowTemplate).where(FlowTemplate.name == "请假申请"))
        assert flow is not None
        form, form_version = _published(db, "请假申请单")
        version = db.get(FlowVersion, flow.current_version_id)
        assert version is not None
        assert version.locked_form_version_id == form_version.id
        assert form.current_version_id == form_version.id
        # 示例表单要有实质内容（不是空的默认 schema）
        keys = [f["key"] for s in form_version.schema["sections"] for f in s["fields"]]
        assert {"leaveType", "startDate", "endDate", "days"} <= set(keys)

    def test_seed_is_idempotent(self, db):
        """再跑一次不新增、不报错 —— 每次启动都会调用它。"""
        admin = db.scalar(select(User).where(User.is_superuser.is_(True)))
        assert admin is not None

        before = db.scalar(select(__import__("sqlalchemy").func.count()).select_from(
            FlowTemplate
        ))
        sample_flows.run_seed(db, admin)
        after = db.scalar(select(__import__("sqlalchemy").func.count()).select_from(
            FlowTemplate
        ))
        assert after == before


class TestDemoAccounts:
    def test_disabled_by_default(self):
        """示例账号默认不建 —— 密码公开，只有试用环境才该开。"""
        from app.core.config import Settings

        assert Settings().seed_demo_accounts is False

    def test_accounts_carry_roles_and_managers(self, db, test_settings):
        """显式打开时才建号；建出来的人要能当审批人。"""
        if not test_settings.seed_demo_accounts:
            demo_accounts.run_seed(db)
            db.commit()

        roles = {r.code: r.id for r in db.scalars(select(Role)).all()}
        for username, real_name, dept_code, role_code, _is_manager in demo_accounts.DEMO_USERS:
            user = db.scalar(select(User).where(User.username == username))
            assert user is not None, f"缺少示例账号：{username}"
            assert user.real_name == real_name
            assert user.status == UserStatus.ACTIVE
            dept = db.scalar(select(Department).where(Department.code == dept_code))
            assert dept is not None and user.dept_id == dept.id
            if role_code is not None:
                hit = db.scalar(
                    select(UserRole.id).where(
                        UserRole.user_id == user.id, UserRole.role_id == roles[role_code]
                    )
                )
                assert hit is not None, f"{username} 缺少角色 {role_code}"

        # 部门主管挂上了：dept_manager 这条审批人来源才解析得出人来
        tech = db.scalar(select(Department).where(Department.code == "TECH"))
        assert tech is not None and tech.manager_user_id is not None

    def test_can_be_used_as_approvers(self, db, test_settings):
        """示例账号真的能当审批人：部门主管挂在部门上，引擎从那里解析。"""
        if not test_settings.seed_demo_accounts:
            demo_accounts.run_seed(db)
            db.commit()

        lisi = db.scalar(select(User).where(User.username == "lisi"))
        tech = db.scalar(select(Department).where(Department.code == "TECH"))
        assert lisi is not None and tech is not None
        assert tech.manager_user_id == lisi.id

    def test_not_recreated_when_present(self, db):
        demo_accounts.run_seed(db)
        db.commit()
        users = list(db.scalars(select(User).where(User.username == "zhangsan")).all())
        assert len(users) == 1


@pytest.fixture(autouse=True)
def _no_instances_left_behind(db):
    """示例流程库只建模板，不该顺手建出实例来。"""
    yield
    assert db.scalar(select(__import__("sqlalchemy").func.count()).select_from(
        FlowInstance
    )) == 0


def test_flow_service_can_read_back_samples(db):
    """示例流程能被正常的列表查询读到（发起中心就是走这条路）。"""
    templates = flow_service.list_templates(db)   # 返回的是 dict（列表页 DTO）
    names = {t["name"] for t in templates}
    assert {"请假申请", "费用报销"} <= names
