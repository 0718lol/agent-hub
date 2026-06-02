"""
Cron Task CRUD operations.

Handles scheduling, querying, updating, and deleting periodic tasks
associated with conversations.
"""
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
def delete_cron_task(task_id: str):
    with Session(_engine_mod.engine) as session:
        task = session.get(CronTask, task_id)
        if task:
            session.delete(task)
            session.commit()
