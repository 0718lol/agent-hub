/**
 * OpenCode Agent Proxy — OpenAI 兼容 API 代理
 *
 * 将 OpenCode 的 Agent 能力（工具调用、多轮推理、文件操作）
 * 包装为标准 OpenAI /v1/chat/completions 端点。
 *
 * 前置条件：opencode serve 已启动
 * 启动方式：node opencode_proxy.mjs --port 4097
 */

import { createOpencodeClient } from "@opencode-ai/sdk";
import http from "node:http";

// ---- 参数解析 ----
const args = process.argv.slice(2);
function getArg(name, def) {
  const idx = args.indexOf(`--${name}`);
  return idx !== -1 && args[idx + 1] ? args[idx + 1] : def;
}
const PORT = parseInt(getArg("port", "4097"));
const OPENCODE_URL = getArg("opencode-url", "http://127.0.0.1:4098");

// ---- OpenCode 客户端 ----
const client = createOpencodeClient({ baseUrl: OPENCODE_URL });

// ---- 工具函数 ----
function sseHeaders(res) {
  res.writeHead(200, {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    Connection: "keep-alive",
    "Access-Control-Allow-Origin": "*",
  });
}

function sendSSE(res, data) {
  res.write(`data: ${JSON.stringify(data)}\n\n`);
}

function sendDone(res) {
  res.write("data: [DONE]\n\n");
  res.end();
}

function sendError(res, status, message) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ error: { message, type: "proxy_error" } }));
}

function readBody(req) {
  return new Promise((resolve) => {
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => resolve(body));
  });
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// ---- 核心：调用 OpenCode 获取响应 ----
async function askOpenCode(userMessage, historyMessages) {
  // 1. 创建会话
  const session = await client.session.create();
  const sessionId = session.data?.id;
  if (!sessionId) throw new Error("Failed to create OpenCode session");

  // 2. 构建完整 prompt（含历史）
  let prompt = userMessage;
  if (historyMessages && historyMessages.length > 0) {
    const historyText = historyMessages
      .map((m) => `[${m.role}]: ${m.content}`)
      .join("\n");
    prompt = `[对话历史]\n${historyText}\n\n[当前问题]\n${userMessage}`;
  }

  // 3. 发送 prompt（同步等待完成）
  await client.session.prompt({
    path: { id: sessionId },
    body: { parts: [{ type: "text", text: prompt }] },
  });

  // 4. 轮询获取响应
  let responseText = "";
  let reasoningText = "";
  for (let attempt = 0; attempt < 30; attempt++) {
    await sleep(1000);
    const msgs = await client.session.messages({ path: { id: sessionId } });
    const msgCount = msgs.data?.length || 0;
    responseText = "";
    reasoningText = "";
    for (const m of msgs.data || []) {
      // SDK 返回的 role 可能是 undefined，第二条消息就是 assistant 回复
      for (const p of m.parts || []) {
        if (p.type === "text" && p.text) responseText = p.text;
        if (p.type === "reasoning" && p.text) reasoningText = p.text;
      }
    }
    if (responseText) break;
  }

  return responseText || reasoningText || "(无响应)";
}

// ---- 路由处理 ----
async function handleChatCompletions(req, res) {
  const body = JSON.parse(await readBody(req));
  const messages = body.messages || [];
  const stream = body.stream !== false;
  const userMessage = messages[messages.length - 1]?.content || "";
  const historyMessages = messages.slice(0, -1);

  try {
    const responseText = await askOpenCode(userMessage, historyMessages);

    if (stream) {
      sseHeaders(res);
      // 模拟流式：每 5 个字符一个 chunk
      const chunkSize = 5;
      for (let i = 0; i < responseText.length; i += chunkSize) {
        sendSSE(res, {
          id: `chatcmpl-${Date.now()}`,
          object: "chat.completion.chunk",
          created: Math.floor(Date.now() / 1000),
          model: body.model || "opencode-agent",
          choices: [{
            index: 0,
            delta: { content: responseText.slice(i, i + chunkSize) },
            finish_reason: null,
          }],
        });
      }
      sendSSE(res, {
        id: `chatcmpl-${Date.now()}`,
        object: "chat.completion.chunk",
        created: Math.floor(Date.now() / 1000),
        model: body.model || "opencode-agent",
        choices: [{ index: 0, delta: {}, finish_reason: "stop" }],
      });
      sendDone(res);
    } else {
      res.writeHead(200, {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
      });
      res.end(JSON.stringify({
        id: `chatcmpl-${Date.now()}`,
        object: "chat.completion",
        created: Math.floor(Date.now() / 1000),
        model: body.model || "opencode-agent",
        choices: [{
          index: 0,
          message: { role: "assistant", content: responseText },
          finish_reason: "stop",
        }],
        usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
      }));
    }
  } catch (e) {
    console.error("Proxy error:", e.message);
    if (!res.headersSent) {
      sendError(res, 500, `OpenCode proxy error: ${e.message}`);
    } else {
      res.end();
    }
  }
}

// ---- HTTP 服务 ----
const server = http.createServer(async (req, res) => {
  if (req.method === "OPTIONS") {
    res.writeHead(204, {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization",
    });
    res.end();
    return;
  }

  const url = new URL(req.url, `http://localhost:${PORT}`);

  if (url.pathname === "/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "ok", opencode_url: OPENCODE_URL }));
    return;
  }

  if (url.pathname === "/v1/chat/completions" && req.method === "POST") {
    await handleChatCompletions(req, res);
    return;
  }

  sendError(res, 404, `Unknown endpoint: ${url.pathname}`);
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`OpenCode Agent Proxy listening on http://127.0.0.1:${PORT}`);
  console.log(`  OpenCode server: ${OPENCODE_URL}`);
  console.log(`  Endpoint: POST /v1/chat/completions`);
  console.log(`  Health: GET /health`);
});
