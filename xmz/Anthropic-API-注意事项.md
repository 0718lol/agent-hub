# Anthropic API 调用注意事项

> 2026-05-24 踩坑记录。本文档记录调用 Anthropic Messages API 时必须遵守的硬性约束，避免重复踩坑。

## 核心规则

调用 Anthropic Messages API 前**必须 sanitize messages 数组**：
1. 必须以 `user` role 开头
2. `user` / `assistant` 必须严格交替
3. 相邻同 role 的消息要合并

## 与 OpenAI 的关键差异

| | OpenAI | Anthropic |
|---|---|---|
| 连续同 role 消息 | 容忍，照常工作 | **400 报错** |
| 第一条非 user | 容忍 | 报错 |
| system 消息 | 放在 messages 数组里 | 放在顶层 `system` 字段 |

## 实际踩坑记录

**症状**：OpenAI 格式 Agent 调用正常，切到 Anthropic 立即失败。

**根因**：
1. `main.py` 收到用户消息后先 `save_message` 存数据库
2. 紧接着 `get_messages(limit=20)` 取 history（**已包含刚保存的 user message**）
3. 然后 `base.py` 的 `_build_messages` 又 `append({"role": "user", ...})` 一次
4. 结果：messages 末尾出现**连续两条 user role**
5. OpenAI 容忍 → 正常返回
6. Anthropic 严格校验 → 400 错误

## 修复实现

`backend/app/core/llm_client.py` 中已加 `_sanitize_for_anthropic()`：

```python
def _sanitize_for_anthropic(messages: list[dict]) -> list[dict]:
    """合并相邻同 role 消息，丢弃开头的 assistant，保证以 user 开头。"""
    cleaned = []
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        if not content or role not in ("user", "assistant"):
            continue
        if cleaned and cleaned[-1]["role"] == role:
            cleaned[-1]["content"] = f"{cleaned[-1]['content']}\n\n{content}"
        else:
            cleaned.append({"role": role, "content": content})
    while cleaned and cleaned[0]["role"] != "user":
        cleaned.pop(0)
    return cleaned
```

`_anthropic_stream` 调用前先跑一遍 sanitize。

## 后续接入新 Anthropic 调用要做什么

1. 调用前必走 `_sanitize_for_anthropic()`
2. 涉及 history + 新 user message 拼接的逻辑要警惕"先存后取再 append"的重复 bug 模式
3. base.py 的 `_build_messages` 已加防御：append 前判断 history 末尾是否已是同内容 user message
4. 新增 LLM 调用接入点要复用 `llm_client`，不要自己重复实现 Anthropic 请求逻辑
