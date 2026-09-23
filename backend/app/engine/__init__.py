"""流程引擎与表达式求值。

分层约束（TECH-DESIGN §2）：`engine` 的纯函数核心**不得** import `db`，
以便脱离数据库做单测 —— 事实上全包只有 `service.py` 会 import `models`。
模块地图与一次事件的完整调用链见 `docs/ENGINE.md`。
"""
