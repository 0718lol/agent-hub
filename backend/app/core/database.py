import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'agenthub.db')


def _ensure_dir():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def get_db():
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            name TEXT NOT NULL,
            avatar TEXT,
            agent_id TEXT,
            agents TEXT,
            preview TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            sender TEXT NOT NULL,
            content TEXT NOT NULL,
            streaming INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        );

        CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);

        CREATE TABLE IF NOT EXISTS custom_agents (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            avatar TEXT DEFAULT '🤖',
            role TEXT DEFAULT '',
            style TEXT DEFAULT '',
            system_prompt TEXT NOT NULL,
            tools TEXT DEFAULT '[]',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS project_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            source TEXT DEFAULT 'system',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_mem_conv_key ON project_memory(conversation_id, key);

        CREATE TABLE IF NOT EXISTS cron_tasks (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            task_prompt TEXT NOT NULL,
            interval_seconds INTEGER NOT NULL,
            last_run TEXT,
            next_run TEXT,
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        );

        CREATE INDEX IF NOT EXISTS idx_cron_next_run ON cron_tasks(next_run) WHERE status = 'active';
    ''')

    default_convs = [
        ('conv_pm', 'single', 'PM 小助手', '📋', 'agent_pm', None, '需求分析与任务拆解'),
        ('conv_frontend', 'single', '前端工程师', '🎨', 'agent_frontend', None, 'React 组件与样式开发'),
        ('conv_backend', 'single', '后端工程师', '⚙️', 'agent_backend', None, 'API 接口与数据模型'),
        ('conv_tester', 'single', '测试工程师', '🧪', 'agent_tester', None, '测试用例与 Bug 分析'),
        ('conv_devops', 'single', '运维工程师', '🚀', 'agent_devops', None, 'Docker 部署与 CI/CD'),
        ('conv_designer', 'single', '设计顾问', '🎯', 'agent_designer', None, 'UI/UX 设计建议'),
        ('conv_builder', 'single', 'Agent 工坊', '🔧', 'agent_builder', None, '对话式创建自定义 Agent'),
        ('conv_group_demo', 'group', 'Demo 项目群', '💬', None,
         json.dumps(['agent_pm', 'agent_frontend', 'agent_backend', 'agent_tester', 'agent_devops', 'agent_designer']),
         '多 Agent 协作演示'),
    ]

    for conv in default_convs:
        conn.execute(
            'INSERT OR IGNORE INTO conversations (id, type, name, avatar, agent_id, agents, preview) VALUES (?, ?, ?, ?, ?, ?, ?)',
            conv
        )

    conn.commit()
    conn.close()


def save_message(conversation_id: str, sender: str, content: dict, streaming: bool = False):
    conn = get_db()
    conn.execute(
        'INSERT INTO messages (conversation_id, sender, content, streaming) VALUES (?, ?, ?, ?)',
        (conversation_id, sender, json.dumps(content, ensure_ascii=False), int(streaming))
    )
    conn.commit()
    conn.close()


def get_messages(conversation_id: str, limit: int = 100):
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC LIMIT ?',
        (conversation_id, limit)
    ).fetchall()
    conn.close()
    return [
        {
            'id': row['id'],
            'conversation_id': row['conversation_id'],
            'sender': row['sender'],
            'content': json.loads(row['content']),
            'streaming': bool(row['streaming']),
            'timestamp': row['created_at'],
        }
        for row in rows
    ]


def get_conversations():
    conn = get_db()
    rows = conn.execute('SELECT * FROM conversations ORDER BY created_at ASC').fetchall()
    conn.close()
    result = []
    for row in rows:
        conv = dict(row)
        if conv['agents']:
            conv['agents'] = json.loads(conv['agents'])
        result.append(conv)
    return result


def clear_messages(conversation_id: str):
    conn = get_db()
    conn.execute('DELETE FROM messages WHERE conversation_id = ?', (conversation_id,))
    conn.commit()
    conn.close()


# ---- Custom Agents CRUD ----

def save_custom_agent(agent_id: str, name: str, avatar: str, role: str,
                      style: str, system_prompt: str, tools: list[str]):
    conn = get_db()
    conn.execute(
        'INSERT OR REPLACE INTO custom_agents (id, name, avatar, role, style, system_prompt, tools) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (agent_id, name, avatar, role, style, system_prompt, json.dumps(tools, ensure_ascii=False))
    )
    conn.commit()
    conn.close()


def get_custom_agents() -> list[dict]:
    conn = get_db()
    rows = conn.execute('SELECT * FROM custom_agents ORDER BY created_at ASC').fetchall()
    conn.close()
    return [
        {
            'agent_id': row['id'],
            'name': row['name'],
            'avatar': row['avatar'],
            'role': row['role'],
            'style': row['style'],
            'system_prompt': row['system_prompt'],
            'tools': json.loads(row['tools']),
            'created_at': row['created_at'],
            'custom': True,
        }
        for row in rows
    ]


def delete_custom_agent(agent_id: str):
    conn = get_db()
    conn.execute('DELETE FROM custom_agents WHERE id = ?', (agent_id,))
    conn.execute('DELETE FROM conversations WHERE agent_id = ?', (agent_id,))
    conn.execute('DELETE FROM messages WHERE conversation_id = ?', (f'conv_{agent_id}',))
    conn.commit()
    conn.close()


def create_conversation(conv_id: str, conv_type: str, name: str, avatar: str,
                        agent_id: str = None, agents: list[str] = None, preview: str = ''):
    conn = get_db()
    conn.execute(
        'INSERT OR IGNORE INTO conversations (id, type, name, avatar, agent_id, agents, preview) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (conv_id, conv_type, name, avatar, agent_id,
         json.dumps(agents, ensure_ascii=False) if agents else None, preview)
    )
    conn.commit()
    conn.close()


def update_conversation_details(conv_id: str, name: str, avatar: str, preview: str):
    conn = get_db()
    conn.execute(
        'UPDATE conversations SET name = ?, avatar = ?, preview = ? WHERE id = ?',
        (name, avatar, preview, conv_id)
    )
    conn.commit()
    conn.close()


# ---- Project Long-term Memory CRUD ----

def save_memory_item(conversation_id: str, key: str, value: str, source: str = "system"):
    conn = get_db()
    conn.execute(
        '''
        INSERT OR REPLACE INTO project_memory (conversation_id, key, value, source, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''',
        (conversation_id, key, value, source)
    )
    conn.commit()
    conn.close()


def get_project_memory(conversation_id: str) -> dict:
    conn = get_db()
    rows = conn.execute(
        'SELECT key, value, source, updated_at FROM project_memory WHERE conversation_id = ?',
        (conversation_id,)
    ).fetchall()
    conn.close()
    return {
        row['key']: {
            'value': row['value'],
            'source': row['source'],
            'updated_at': row['updated_at']
        }
        for row in rows
    }


def delete_memory_item(conversation_id: str, key: str):
    conn = get_db()
    conn.execute(
        'DELETE FROM project_memory WHERE conversation_id = ? AND key = ?',
        (conversation_id, key)
    )
    conn.commit()
    conn.close()


# ---- Offline Cron Tasks CRUD ----

def save_cron_task(task_id: str, conversation_id: str, agent_id: str, task_prompt: str,
                   interval_seconds: int, status: str = 'active', last_run: str = None, next_run: str = None):
    conn = get_db()
    conn.execute(
        '''
        INSERT OR REPLACE INTO cron_tasks (id, conversation_id, agent_id, task_prompt, interval_seconds, status, last_run, next_run)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (task_id, conversation_id, agent_id, task_prompt, interval_seconds, status, last_run, next_run)
    )
    conn.commit()
    conn.close()


def get_cron_tasks(conversation_id: str = None) -> list[dict]:
    conn = get_db()
    if conversation_id:
        rows = conn.execute(
            'SELECT * FROM cron_tasks WHERE conversation_id = ? ORDER BY created_at DESC',
            (conversation_id,)
        ).fetchall()
    else:
        rows = conn.execute('SELECT * FROM cron_tasks ORDER BY created_at DESC').fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_due_cron_tasks(now_str: str) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM cron_tasks WHERE status = 'active' AND next_run <= ?",
        (now_str,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_cron_task_run_time(task_id: str, last_run: str, next_run: str, status: str = 'active'):
    conn = get_db()
    conn.execute(
        'UPDATE cron_tasks SET last_run = ?, next_run = ?, status = ? WHERE id = ?',
        (last_run, next_run, status, task_id)
    )
    conn.commit()
    conn.close()


def update_cron_task_status(task_id: str, status: str):
    conn = get_db()
    conn.execute('UPDATE cron_tasks SET status = ? WHERE id = ?', (status, task_id))
    conn.commit()
    conn.close()


def delete_cron_task(task_id: str):
    conn = get_db()
    conn.execute('DELETE FROM cron_tasks WHERE id = ?', (task_id,))
    conn.commit()
    conn.close()

