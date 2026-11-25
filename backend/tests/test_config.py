"""应用配置：系统名称是前端显示的唯一来源（PRD 决策 12）。"""

from __future__ import annotations

from app.core.config import Settings


def test_app_name_is_trimmed_and_never_blank() -> None:
    assert Settings(app_name="  内部审批平台  ").app_name == "内部审批平台"
    # 空名称会让登录页、侧边栏和浏览器标题变成空白，退回默认名
    assert Settings(app_name="   ").app_name == "FlowForm"
