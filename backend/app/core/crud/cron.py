"""
Cron Task CRUD operations.

Handles scheduling, querying, updating, and deleting periodic tasks
associated with conversations.
"""
from sqlalchemy import update
from sqlmodel import Session, select

import app.core._engine as _engine_mod
from app.core.crud.utils import db_write_transaction
from app.core.models import CronTask


@db_write_transaction
def save_cron_task(task_id: str, conversation_id: str, agent_id: str,
                   task_prompt: str, interval_seconds: int,
                   status: str = "active", last_run: str | None = None,
                   next_run: str | None = None):
    with Session(_engine_mod.engine) as session:
        task = CronTask(
            id=task_id,
            conversation_id=conversation_id,
            agent_id=agent_id,
            task_prompt=task_prompt,
            interval_seconds=interval_seconds,
            status=status,
            last_run=last_run,
            next_run=next_run
        )
        session.merge(task)
        session.commit()


def get_cron_tasks(conversation_id: str | None = None) -> list[dict]:
    with Session(_engine_mod.engine) as session:
        if conversation_id:
            statement = select(CronTask).where(
                CronTask.conversation_id == conversation_id
            ).order_by(CronTask.created_at.desc())
        else:
            statement = select(CronTask).order_by(CronTask.created_at.desc())
        results = session.exec(statement).all()
        return [row.model_dump() for row in results]


def get_due_cron_tasks(now_str: str) -> list[dict]:
    with Session(_engine_mod.engine) as session:
        statement = select(CronTask).where(
            CronTask.status == "active"
        ).where(CronTask.next_run <= now_str)
        results = session.exec(statement).all()
        return [row.model_dump() for row in results]


@db_write_transaction
def claim_cron_task(task_id: str, include_paused: bool = False) -> bool:
    """Atomically claim a task so scheduled and manual triggers cannot overlap."""
    claimable = ["active"]
    if include_paused:
        claimable.append("paused")
    with Session(_engine_mod.engine) as session:
        result = session.exec(
            update(CronTask)
            .where(CronTask.id == task_id)
            .where(CronTask.status.in_(claimable))
            .values(status="running")
        )
        session.commit()
        return bool(result.rowcount)


@db_write_transaction
def update_cron_task_run_time(task_id: str, last_run: str, next_run: str, status: str = "active"):
    with Session(_engine_mod.engine) as session:
        task = session.get(CronTask, task_id)
        if task:
            task.last_run = last_run
            task.next_run = next_run
            task.status = status
            session.add(task)
            session.commit()


@db_write_transaction
def update_cron_task_status(task_id: str, status: str):
    with Session(_engine_mod.engine) as session:
        task = session.get(CronTask, task_id)
        if task:
            task.status = status
            session.add(task)
            session.commit()


@db_write_transaction
def recover_running_cron_tasks(now_str: str, protected_task_ids: set[str] | None = None) -> int:
    """Return tasks stranded by a prior process crash to the active queue."""
    protected_task_ids = protected_task_ids or set()
    with Session(_engine_mod.engine) as session:
        tasks = session.exec(select(CronTask).where(CronTask.status == "running")).all()
        recovered = 0
        for task in tasks:
            if task.id in protected_task_ids:
                continue
            task.status = "active"
            task.next_run = now_str
            session.add(task)
            recovered += 1
        session.commit()
        return recovered


@db_write_transaction
def delete_cron_task(task_id: str):
    with Session(_engine_mod.engine) as session:
        task = session.get(CronTask, task_id)
        if task:
            session.delete(task)
            session.commit()
