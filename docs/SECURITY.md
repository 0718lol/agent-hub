# AgentHub 安全文档

## 1. 安全审计概述
- 4 轮安全审计
- 69 个问题修复
- 3 个 RCE 级漏洞封堵

## 2. SSRF 三层防御
- URL 校验（协议、主机名）
- DNS 解析校验（私有 IP 拦截）
- 重定向校验（手动跟随重定向）

## 3. MCP 命令注入防护
- 命令白名单（npx、node、python、uvx）
- Shell 元字符拦截（;、|、&、`、$()）
- 危险参数检测（python -c、node -e）

## 4. AST 沙盒隔离
- builtins 隔离（_make_safe_builtin）
- 属性访问拦截（__builtins__、__globals__、__class__）
- sys.stdout 替代（_safe_print）

## 5. 路径穿越防护
- 文件上传路径校验
- 符号链接穿越检测
- 会话目录隔离

## 6. 浏览器安全
- URL 白名单（内网地址拦截）
- 反自动化检测（playwright-stealth）
- 元素操作频率限制

## 7. 输出校验
- Pydantic 模型校验
- 反模式检测（问句拦截）
- 自动重试机制

## 8. 测试覆盖
- 304 个后端测试
- 安全专项测试：SSRF（31）、路径穿越（18）、MCP（6）、加密（5）
- 输出校验测试（21）

## 9. CI/CD 安全
- GitHub Actions 自动化
- Ruff lint + pytest + ESLint + Bandit
- 每次 PR 自动运行
