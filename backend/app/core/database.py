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
    ''')

    default_convs = [
        ('conv_pm', 'single', 'PM 小助手', '📋', 'agent_pm', None, '需求分析与任务拆解'),
        ('conv_frontend', 'single', '前端工程师', '🎨', 'agent_frontend', None, 'React 组件与样式开发'),
        ('conv_backend', 'single', '后端工程师', '⚙️', 'agent_backend', None, 'API 接口与数据模型'),
        ('conv_tester', 'single', '测试工程师', '🧪', 'agent_tester', None, '测试用例与 Bug 分析'),
        ('conv_devops', 'single', '运维工程师', '🚀', 'agent_devops', None, 'Docker 部署与 CI/CD'),
        ('conv_designer', 'single', '设计顾问', '🎯', 'agent_designer', None, 'UI/UX 设计建议'),
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
