# xmz 负责模块：评测 Harness 框架 + 判断机制工具化

> 2026-05-24 与 AI 协作对齐版本。本文档是给团队成员看的方案说明，对应 AgentHub 比赛"AI 协作能力 30%"权重。

## 方向调整说明

最初规划是"多 Agent 辩论 UI"，对齐后升级为**完整的 AI 评测 Harness 框架**：
- 辩论 UI 是其中一个被测对象（子模块），不是终点
- 增加判断机制工具化 + 自动跑用例 + 自动打分 + 报告体系
- 这是命中比赛 30% 权重最直接的方式（单项权重最高）

## 方案架构（两层）

### 第一层：判断机制工具化

**新建** `backend/app/tools/judge_tools.py`：

统一抽象 `JudgeTool` 协议：

```python
class JudgeTool:
    tool_id: str
    name: str
    async def run(self, input: dict) -> JudgeResult: ...

@dataclass
class JudgeResult:
    decision: Any           # True/False/score/label
    score: float            # 0~1 置信度
    reason: str             # 可解释的人类语言
    signals: list[str]      # ["keyword:还是", "llm_conf:0.82"]
    raw: dict               # 原始证据
```

四个具体实现：

| Tool | 职责 | 来源 |
|---|---|---|
| `InteractionJudgeTool` | 判断要不要触发辩论 | 升级现有 evaluate_interaction_need |
| `ComplexityJudgeTool` | 判断任务复杂度（PM 拆解前用） | 新增 |
| `QualityJudgeTool` | 判断输出质量 | 包装 quality_gate |
| `AlignmentJudgeTool` | actual vs expected 语义对齐 | 新增（LLM Judge） |

**好处**：判断逻辑可独立单测，可挂载到任意 Agent 的 tools 字段，便于评测时直接调用。

### 第二层：Harness 评测框架

**新建目录** `backend/app/harness/`：

```
harness/
├── runner.py         # HarnessRunner: 跑 suite / case
├── evaluator.py      # 4 维打分
├── reporter.py       # JSON + HTML 报告
├── samples/          # JSON 用例集
│   ├── interaction_judge.json
│   ├── debate_arena.json
│   ├── pm_decomposition.json
│   └── code_quality.json
├── reports/          # 自动产出（gitignore）
└── cli.py            # python -m app.harness.cli run --suite all
```

**样例 JSON 格式**（一份契约管全部）：

```json
{
  "suite": "interaction_judge",
  "target_tool": "interaction_judge",
  "cases": [
    {
      "id": "ij_001",
      "input": "你好",
      "expected": {"decision": false},
      "tags": ["simple", "greeting"],
      "weight": 1.0
    },
    {
      "id": "ij_002",
      "input": "用 React 还是 Vue 做商城",
      "expected": {"decision": true, "signals_contains": "keyword"},
      "tags": ["debate", "selection"],
      "weight": 2.0
    }
  ]
}
```

**Evaluator 多维打分**：

| 维度 | 规则 | 权重 |
|---|---|---|
| `correctness` | decision 字段完全匹配 | 40% |
| `confidence` | score 在期望区间 | 20% |
| `signals` | signals 包含期望关键证据 | 20% |
| `semantic` | LLM Judge actual vs expected（可选） | 20% |

**双入口**：
- CLI：`python -m app.harness.cli run --suite all`
- REST API：`POST /api/harness/run`、`GET /api/harness/runs/:id`

前端可加 `HarnessPanel` 到 Canvas（运行按钮 + 矩阵热力图 + 详情抽屉）。

## 辩论子模块 UI 决策

| 项 | 决定 | 理由 |
|---|---|---|
| 位置 | 聊天流内嵌卡片 | 沉浸感优于 Canvas 切 Tab |
| 裁决粒度 | 3 按钮 + 理由 textarea | 理由可沉淀为 AI 协作规范文档素材 |
| 流式渲染 | 每段边生成边展示 | 视觉冲击 |
| 触发原因卡片 | 显示关键词命中 + LLM 置信度 | 评判过程可见，可解释性 |

裁决按钮三选：`accept_a` / `accept_b` / `reject_all`，后端已有 `handle_verdict` 支持。

## 与现有代码的关系（OCP 原则）

| 现有 | 调整 |
|---|---|
| `harness_engine.py` | 不动，作为 Runner 的被测对象 |
| `harness_handler.py` | 升级流式广播 + 接受 verdict reason 字段 |
| `auto_evaluator.py` | 包装为 QualityJudgeTool 复用 |
| `quality_gate.py` | 包装一层 Tool 接口，不改实现 |

所有改动是"新增 + 包装"，不破坏已有功能。

## 排期与优先级（基于 6/10 截止）

| 优先级 | 任务 | 耗时 |
|---|---|---|
| P0 | tools/judge_tools.py 骨架 + InteractionJudgeTool | 半天 |
| P0 | harness/runner + evaluator + 第一个 suite | 1 天 |
| P0 | 补齐 4 个 suite 各 ~8-10 case | 1 天 |
| P0 | 前端辩论 UI（debateStore + DebateCard + VerdictPanel） | 1.5 天 |
| P1 | REST API + 前端 HarnessPanel 矩阵图 | 1 天 |
| P1 | LLM Judge 维度 + HTML 报告美化 | 1 天 |

## 答辩话术锚点

- **工具化** → AI 工程模块化思想
- **benchmark suite** → 像传统软件一样可测试
- **多维评分 + 报告** → AI 协作过程可审计、可复盘
- **用户裁决理由** → 人类在环的真实价值落地

## 评分维度命中分析

| 评分维度 | 命中点 |
|---|---|
| AI 协作 30% | 完整 benchmark 体系 → "AI 协作规范"最强证据 |
| 功能完整度 25% | 工具化 + 自动跑分 + 报告 → 闭环 |
| 生成效果 20% | 矩阵可视化 + 多维评分 → 视觉冲击 |
| 代码理解度 15% | 分层清晰（Tools / Runner / Eval / Reporter） |
| 创新 10% | 比赛项目里植入完整 AI Eval 框架，少见 |
