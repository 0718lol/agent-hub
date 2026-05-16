# AgentHub - 多 Agent 协作平台

> 用 IM 聊天的方式，与多个 AI Agent 协作完成软件开发全流程。

## 项目简介

AgentHub 是一个 IM 风格的多 Agent 协作平台。用户像在钉钉/飞书里聊天一样，与 6 个预置 AI Agent 对话，驱动需求分析、任务拆解、代码生成、UI 设计、测试验证、部署上线的完整开发流程。

## 核心功能

**单聊 & 群聊**
- 与 6 个 Agent 1v1 对话，或创建项目群多 Agent 协作
- 流式输出，Agent 回复逐字显示（模拟 ChatGPT 体验）
- 消息支持 Markdown 渲染和代码语法高亮

**6 个预置 Agent**
- PM 小助手 📋 — 需求分析、任务拆解
- 前端工程师 🎨 — React 组件、样式开发
- 后端工程师 ⚙️ — API 接口、数据模型
- 测试工程师 🧪 — 测试用例、Bug 分析
- 运维工程师 🚀 — Docker、CI/CD、部署
- 设计顾问 🎯 — UI/UX 设计、原型图生成

**可视化协作画布**
- DAG 图实时展示 Agent 间任务流转
- 任务看板（待办/进行中/已完成，支持拖拽）
- 代码 Diff 视图（Monaco Editor）
- 网页预览（iframe sandbox 实时渲染）

**消息卡片系统**
- 代码卡片 — 语法高亮 + 一键复制
- 原型卡片 — SVG 线框图（Todo/登录/仪表盘/电商）
- 任务卡片 — 状态标签 + 指派 Agent

## 技术栈

**后端**
- FastAPI + WebSocket（实时双向通信）
- Pydantic 数据校验
- Agent 策略模式（可扩展）

**前端**
- React 18 + Vite
- Zustand 状态管理
- Monaco Editor 代码编辑/Diff
- SVG 原型图渲染

**通信**
- WebSocket 实时消息
- 流式输出模拟（可无缝接入 LLM API）

## 快速启动

```bash
# 后端
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000

# 前端
cd frontend
npm install
npm run dev
```

打开 http://localhost:3000

## 项目结构

```
agent-hub/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI + WebSocket 入口
│   │   ├── agents/              # 6 个 Agent 实现
│   │   ├── core/                # 配置、WebSocket 管理
│   │   ├── routers/             # API 路由
│   │   └── services/            # 业务逻辑
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Layout/          # 三栏布局
│   │   │   ├── Chat/            # 聊天组件
│   │   │   └── Canvas/          # 画布组件
│   │   ├── stores/              # Zustand 状态
│   │   └── utils/               # WebSocket、流式模拟
│   └── package.json
└── README.md
```

## 后续规划

- 接入真实 LLM API（GPT-4o / 通义千问）
- Agent 记忆系统（上下文关联）
- 代码沙箱执行（浏览器内运行）
- 更多 Agent 角色和工作流模板
