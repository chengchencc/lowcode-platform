"""重建实例业务字段索引（M13）。

用法：
    python -m app.scripts.rebuild_search_index --all
    python -m app.scripts.rebuild_search_index --flow-template-id 3
    python -m app.scripts.rebuild_search_index --form-template-id 1 --dry-run

幂等：先删后建，可重复执行。分批提交，避免长事务。
"""

from __future__ import annotations

import argparse

from sqlalchemy import select

from app.core.constants import InstanceStatus
from app.db.session import SessionLocal
from app.models import FlowInstance, FlowTemplate
from app.services import search_service


def main() -> None:
    parser = argparse.ArgumentParser(description="重建实例业务字段索引")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="重建全部非草稿实例")
    group.add_argument("--flow-template-id", type=int, help="只重建某个流程模板的实例")
    group.add_argument("--form-template-id", type=int, help="只重建某个表单模板的实例")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写库")
    args = parser.parse_args()

    stmt = select(FlowInstance).where(FlowInstance.status != InstanceStatus.DRAFT)
    if args.flow_template_id is not None:
        stmt = stmt.where(FlowInstance.flow_template_id == args.flow_template_id)
    if args.form_template_id is not None:
        stmt = stmt.where(
            FlowInstance.flow_template_id.in_(
                select(FlowTemplate.id).where(
                    FlowTemplate.form_template_id == args.form_template_id
                )
            )
        )
    stmt = stmt.order_by(FlowInstance.id)

    db = SessionLocal()
    total = 0
    try:
        offset = 0
        while True:
            batch = list(db.scalars(stmt.limit(args.batch_size).offset(offset)).all())
            if not batch:
                break
            total += len(batch)
            if not args.dry_run:
                for instance in batch:
                    search_service.sync_instance_index(db, instance=instance)
                db.commit()
                print(f"已重建 {total} 条")
            offset += len(batch)

        if args.dry_run:
            print(f"将重建 {total} 条实例")
            return

        if args.form_template_id is not None:
            search_service.mark_backfilled(db, args.form_template_id)
        elif args.flow_template_id is not None:
            template = db.get(FlowTemplate, args.flow_template_id)
            if template is not None:
                search_service.mark_backfilled(db, template.form_template_id)
        else:
            template_ids = {row[0] for row in db.execute(select(FlowTemplate.id)).all()}
            for template_id in template_ids:
                search_service.mark_backfilled(db, template_id)
        print(f"完成，共 {total} 条实例")
    finally:
        db.close()


if __name__ == "__main__":
    main()
