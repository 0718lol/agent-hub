# 多 Agent 辩论 Harness 开发指南

> **开发原则**：增量开发 (OCP)，按组件建文件，禁止改大文件；Prompt 分离到 prompts/ 目录；Mock 先行；特性分支 `feat/名字-功能名`。

## 一、当前进度评估

| 模块 | 已完成 | 未完成 | 技术栈 |
|------|--------|--------|--------|
| **前端 UI** | 基础聊天框、流式输出、代码卡片、选项按钮 | 辩论卡片、投票UI、观点对比面板 | React 18 + Zustand |
| **后端 AI 调度** | 8个Agent、LLM流式调用、PM分发、Quality Gate | 辩论编排、Agent对抗、多轮控制 | FastAPI + WebSocket |
| **主控路由** | PM → [assign] → 并行子Agent | 辩论路由、正反方分配、裁决流程 | WebSocket |
| **规范文档** | Prompt Engine 6层、Quality Standards | 辩论协议、评估标准、Skill文档 | Spec/Rules |

## 二、新增文件清单（严格遵守 OCP，不改已有大文件）

```
backend/app/
├── core/
│   └── debate_engine.py          ← 新建：辩论编排引擎（核心逻辑）
├── routers/
│   └── debate.py                 ← 新建：辩论 REST + WS 路由（不改 main.py）
├── prompts/
│   ├── debate_round1_stance.txt  ← 已建：立论 prompt 模板
│   ├── debate_round2_rebuttal.txt← 已建：反驳 prompt 模板
│   └── debate_round3_summary.txt ← 已建：总结 prompt 模板
├── mock_data/
│   └── debate_result.json        ← 已建：Mock 数据（前后端联调契约）

frontend/src/
├── components/Chat/
│   └── DebateCard.jsx            ← 新建：辩论卡片组件（不改 MessageBubble）
├── components/Canvas/
│   └── DebatePanel.jsx           ← 新建：辩论看板面板
└── stores/
    └── debateStore.js            ← 新建：辩论状态管理（不改 canvasStore）
```

## 三、接口契约（Mock 先行）

前后端联调前，前端直接读 `mock_data/debate_result.json` 画 UI，后端照此格式输出。

### WebSocket 消息类型扩展

```json
// 1. 辩论开始
{
  "type": "debate_start",
  "conversation_id": "conv_xxx",
  "topic": "商城技术选型：React vs Vue",
  "rounds": 3,
  "participants": [
    { "agent_id": "agent_frontend", "stance": "pro", "position": "支持 React", "avatar": "🎨" },
    { "agent_id": "agent_backend", "stance": "con", "position": "支持 Vue", "avatar": "⚙️" }
  ]
}

// 2. 回合开始
{
  "type": "debate_round",
  "conversation_id": "conv_xxx",
  "round": 1,
  "total_rounds": 3,
  "status": "in_progress"
}

// 3. Agent 发言（流式，复用 message 类型）
{
  "type": "message",
  "conversation_id": "conv_xxx",
  "sender": "agent_frontend",
  "content": { "text": "我支持 React 的理由是..." },
  "stream": true
}

// 4. Agent 本轮完成
{
  "type": "debate_round",
  "conversation_id": "conv_xxx",
  "round": 1,
  "agent_id": "agent_frontend",
  "stance": "pro",
  "status": "agent_done"
}

// 5. 辩论结束，请求裁决
{
  "type": "debate_vote",
  "conversation_id": "conv_xxx",
  "topic": "商城技术选型：React vs Vue",
  "options": [
    { "agent_id": "agent_frontend", "stance": "pro", "position": "支持 React", "summary": "..." },
    { "agent_id": "agent_backend", "stance": "con", "position": "支持 Vue", "summary": "..." }
  ]
}

// 6. 用户裁决
{
  "type": "debate_result",
  "conversation_id": "conv_xxx",
  "winner": "agent_frontend"
}
```

## 四、开发步骤

### Step 1：后端 — 辩论引擎（新建文件，不改 main.py）

**新建**: `backend/app/core/debate_engine.py`

```python
"""
Debate Harness — Multi-Agent adversarial debate engine.
独立模块，通过路由文件接入，不修改 main.py。
"""

import os
from dataclasses import dataclass, field

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")


@dataclass
class DebateParticipant:
    agent_id: str
    stance: str      # "pro" | "con"
    position: str    # e.g. "支持 React"
    avatar: str = "🤖"
    arguments: list[str] = field(default_factory=list)


@dataclass
class DebateSession:
    conversation_id: str
    topic: str
    participants: list[DebateParticipant]
    rounds: int = 3
    current_round: int = 0
    status: str = "pending"  # pending | debating | voting | finished
    history: list[dict] = field(default_factory=list)


class DebateEngine:
    DEBATE_TRIGGERS = [
        "还是", "哪个好", "选什么", "对比", "比较", "vs", "VS",
        "应该用", "推荐用", "优缺点", "利弊", "trade-off",
    ]

    STANCE_MAP = {
        "react": [("agent_frontend", "pro"), ("agent_backend", "con")],
        "vue": [("agent_backend", "pro"), ("agent_frontend", "con")],
        "数据库": [("agent_backend", "pro"), ("agent_tester", "con")],
        "部署": [("agent_devops", "pro"), ("agent_backend", "con")],
    }

    def __init__(self):
        self.active_sessions: dict[str, DebateSession] = {}

    def should_trigger(self, message: str) -> bool:
        msg = message.lower()
        return any(kw in msg for kw in self.DEBATE_TRIGGERS)

    def create_session(self, conversation_id: str, topic: str,
                       participants: list[DebateParticipant],
                       rounds: int = 3) -> DebateSession:
        session = DebateSession(
            conversation_id=conversation_id, topic=topic,
            participants=participants, rounds=rounds, status="debating",
        )
        self.active_sessions[conversation_id] = session
        return session

    def auto_assign_stance(self, topic: str) -> list[DebateParticipant]:
        msg = topic.lower()
        for keyword, assignments in self.STANCE_MAP.items():
            if keyword in msg:
                return [
                    DebateParticipant(
                        agent_id=aid, stance=s,
                        position=f"{'支持' if s == 'pro' else '反对'} {keyword}",
                    )
                    for aid, s in assignments
                ]
        return [
            DebateParticipant(agent_id="agent_frontend", stance="pro", position="方案A"),
            DebateParticipant(agent_id="agent_backend", stance="con", position="方案B"),
        ]

    def _load_prompt(self, filename: str) -> str:
        """从 prompts/ 目录加载模板文件，与后端逻辑分离。"""
        path = os.path.join(PROMPTS_DIR, filename)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    def get_round_prompt(self, session: DebateSession,
                         participant: DebateParticipant,
                         opponent_args: list[str]) -> str:
        round_num = session.current_round
        total = session.rounds
        opponent_text = "\n".join(f"- {a}" for a in opponent_args)

        if round_num == 1:
            template = self._load_prompt("debate_round1_stance.txt")
        elif round_num < total:
            template = self._load_prompt("debate_round2_rebuttal.txt")
        else:
            template = self._load_prompt("debate_round3_summary.txt")

        return template.format(
            topic=session.topic,
            position=participant.position,
            total_rounds=total,
            opponent_args=opponent_text,
        )

    def advance_round(self, session: DebateSession) -> bool:
        session.current_round += 1
        if session.current_round > session.rounds:
            session.status = "voting"
            return False
        return True

    def finish(self, session: DebateSession, winner: str):
        session.status = "finished"
        return {"winner": winner, "topic": session.topic}

    def get_session(self, conversation_id: str) -> DebateSession | None:
        return self.active_sessions.get(conversation_id)


debate_engine = DebateEngine()
```

### Step 2：后端 — 辩论路由（新建路由文件，不改 main.py）

**新建**: `backend/app/routers/debate.py`

```python
"""
辩论功能路由 — 独立文件，通过 include_router 接入 main.py。
main.py 只需加一行：app.include_router(debate_router.router, prefix="/api")
"""

from fastapi import APIRouter

router = APIRouter(prefix="/debate", tags=["debate"])


@router.get("/triggers")
async def list_debate_triggers():
    """返回辩论触发关键词列表，供前端展示提示。"""
    from app.core.debate_engine import debate_engine
    return {"triggers": debate_engine.DEBATE_TRIGGERS}


@router.get("/sessions/{conversation_id}")
async def get_debate_session(conversation_id: str):
    """获取辩论会话状态。"""
    from app.core.debate_engine import debate_engine
    session = debate_engine.get_session(conversation_id)
    if not session:
        return {"error": "no active debate"}
    return {
        "topic": session.topic,
        "rounds": session.rounds,
        "current_round": session.current_round,
        "status": session.status,
        "participants": [
            {"agent_id": p.agent_id, "stance": p.stance, "position": p.position,
             "arguments_count": len(p.arguments)}
            for p in session.participants
        ],
        "history": session.history,
    }
```

**main.py 只加一行**（不改其他代码）：

```python
from app.routers import debate as debate_router
app.include_router(debate_router.router, prefix="/api")
```

### Step 3：后端 — 辩论 WebSocket 处理（新建处理函数，main.py 只加调用）

在 `main.py` 的 websocket_endpoint 中，消息处理分支只加一个判断：

```python
from app.routers.debate import handle_debate_message

# 在用户消息处理处加一行：
if sender == "user" and handle_debate_message:
    handled = await handle_debate_message(conversation_id, text, stop_event, manager, AGENTS)
    if handled:
        continue
```

辩论实际逻辑全部在 `debate.py` 的 `handle_debate_message` 函数中。

### Step 4：前端 — 辩论状态管理（新建文件，不改 canvasStore）

**新建**: `frontend/src/stores/debateStore.js`

```javascript
import { create } from 'zustand'

export const useDebateStore = create((set) => ({
  session: null,      // { topic, rounds, participants, status }
  history: [],        // [{ round, agentId, stance, content }]
  currentRound: 0,

  setSession: (session) => set({ session, history: [], currentRound: 0 }),
  addRoundEntry: (entry) => set((s) => ({
    history: [...s.history, entry],
    currentRound: entry.round,
  })),
  setStatus: (status) => set((s) => ({
    session: s.session ? { ...s.session, status } : null,
  })),
  clear: () => set({ session: null, history: [], currentRound: 0 }),
}))
```

### Step 5：前端 — 辩论卡片组件（新建文件，不改 MessageBubble）

**新建**: `frontend/src/components/Chat/DebateCard.jsx`

```jsx
import React from 'react'
import { useDebateStore } from '../../stores/debateStore'
import { wsClient } from '../../utils/websocket'
import { useChatStore } from '../../stores/chatStore'

const STANCE_COLORS = {
  pro: { bg: 'rgba(16,185,129,0.08)', border: 'rgba(16,185,129,0.3)', text: '#10b981', label: '正方' },
  con: { bg: 'rgba(239,68,68,0.08)', border: 'rgba(239,68,68,0.3)', text: '#ef4444', label: '反方' },
}

export function DebateStartCard() {
  const session = useDebateStore((s) => s.session)
  if (!session || session.status === 'finished') return null

  return (
    <div style={{
      margin: '12px 0', padding: '16px', borderRadius: 12,
      background: 'linear-gradient(135deg, rgba(99,102,241,0.06), rgba(236,72,153,0.06))',
      border: '1px solid rgba(99,102,241,0.2)',
    }}>
      <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>辩论模式</div>
      <div style={{ fontSize: 14, color: '#94a3b8', marginBottom: 12 }}>
        主题：{session.topic}
      </div>
      <div style={{ display: 'flex', gap: 12 }}>
        {session.participants.map((p) => {
          const style = STANCE_COLORS[p.stance] || STANCE_COLORS.pro
          return (
            <div key={p.agent_id} style={{
              flex: 1, padding: '10px 14px', borderRadius: 8,
              background: style.bg, border: `1px solid ${style.border}`,
            }}>
              <div style={{ fontSize: 12, color: style.text, fontWeight: 600 }}>{style.label}</div>
              <div style={{ fontSize: 13, marginTop: 4 }}>{p.position}</div>
            </div>
          )
        })}
      </div>
      <div style={{ fontSize: 12, color: '#64748b', marginTop: 8 }}>
        第 {session.currentRound}/{session.rounds} 轮 · {session.status}
      </div>
    </div>
  )
}

export function DebateVoteCard() {
  const session = useDebateStore((s) => s.session)
  const clear = useDebateStore((s) => s.clear)
  const activeId = useChatStore((s) => s.activeConversationId)

  if (!session || session.status !== 'voting') return null

  const handleVote = (agentId) => {
    wsClient.send({
      type: 'debate_result',
      conversation_id: activeId,
      winner: agentId,
    })
    clear()
  }

  return (
    <div style={{
      margin: '12px 0', padding: '16px', borderRadius: 12,
      background: 'linear-gradient(135deg, rgba(245,158,11,0.06), rgba(239,68,68,0.06))',
      border: '1px solid rgba(245,158,11,0.3)',
    }}>
      <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 12 }}>辩论结束，请裁决</div>
      {session.participants.map((p) => {
        const style = STANCE_COLORS[p.stance] || STANCE_COLORS.pro
        return (
          <div key={p.agent_id} onClick={() => handleVote(p.agent_id)} style={{
            marginBottom: 10, padding: '12px 16px', borderRadius: 10,
            background: style.bg, border: `1px solid ${style.border}`,
            cursor: 'pointer', transition: 'all 0.2s',
          }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: style.text }}>
              {style.label}：{p.position}
            </div>
          </div>
        )
      })}
    </div>
  )
}
```

### Step 6：前端 — WebSocket 消息处理（新建 handler，不改 websocket.js 主体）

**新建**: `frontend/src/utils/debateHandler.js`

```javascript
import { useDebateStore } from '../stores/debateStore'

export function handleDebateMessage(data) {
  const store = useDebateStore.getState()

  switch (data.type) {
    case 'debate_start':
      store.setSession({
        topic: data.topic,
        rounds: data.rounds,
        participants: data.participants,
        currentRound: 0,
        status: 'debating',
      })
      return true

    case 'debate_round':
      if (data.status === 'agent_done') {
        store.addRoundEntry({
          round: data.round,
          agentId: data.agent_id,
          stance: data.stance,
        })
      }
      return true

    case 'debate_vote':
      store.setStatus('voting')
      return true

    default:
      return false
  }
}
```

然后在 `websocket.js` 的 onmessage 中只加一行：

```javascript
import { handleDebateMessage } from './debateHandler'

// onmessage 中：
if (handleDebateMessage(data)) return  // 辩论消息由 debateStore 处理
```

### Step 7：前端 — ChatPanel 集成（只加 import + 组件标签）

在 `ChatPanel.jsx` 中只加两行：

```jsx
import { DebateStartCard, DebateVoteCard } from '../Chat/DebateCard'

// JSX 中：
<DebateStartCard />
<DebateVoteCard />
```

## 五、Git 工作流

```bash
# 1. 从 main 切特性分支
git checkout main && git pull origin main
git checkout -b feat/xmz-debate-engine

# 2. 开发完成后提 PR
git add backend/app/core/debate_engine.py backend/app/routers/debate.py ...
git commit -m "feat: add debate harness engine and router"
git push origin feat/xmz-debate-engine
# 在 GitHub 创建 PR，让队友 Review
```

## 六、开发排期

| 优先级 | 任务 | 文件（全部新建） | 预计耗时 |
|--------|------|-----------------|----------|
| P0 | 辩论引擎 | `core/debate_engine.py` | 2h |
| P0 | 辩论路由 | `routers/debate.py` | 1h |
| P0 | Mock 数据 | `mock_data/debate_result.json` | 已完成 |
| P0 | Prompt 模板 | `prompts/debate_round*.txt` | 已完成 |
| P0 | 辩论卡片 | `Chat/DebateCard.jsx` | 2h |
| P0 | 辩论状态 | `stores/debateStore.js` | 0.5h |
| P0 | WS handler | `utils/debateHandler.js` | 0.5h |
| P1 | 辩论看板 | `Canvas/DebatePanel.jsx` | 1.5h |
| P1 | main.py 接入 | 加 2 行 import | 5min |

## 七、答辩话术

> "辩论 Harness 是创新功能：用户面临技术选型时，系统自动分配正反方 Agent 多轮辩论。每个 Agent 基于专业领域提出不同视角论点，经立论→反驳→总结三阶段后，用户裁决最优方案并自动执行。这体现了 AI 不只是工具，而是可以像团队成员一样建设性对抗，帮助用户做出更全面的决策。"
