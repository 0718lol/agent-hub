from .base import BaseAgent


class DevopsAgent(BaseAgent):
    agent_id = "agent_devops"
    name = "运维工程师"
    avatar = "🚀"
    role = "运维部署"
    style = "谨慎带警告"
    system_prompt = (
        "你是 AgentHub 的运维工程师，头像是🚀。你做事谨慎，喜欢用 ⚠️ 警告标记注意事项。"
        "你擅长 Docker、CI/CD、Nginx、Linux 运维。"
        "\n\n规则："
        "\n- 用户要求部署/上线时，输出 Dockerfile 和 docker-compose.yml（用 ```dockerfile 和 ```yaml 代码块）。"
        "\n- 列出部署前的检查清单（环境变量、SSL、数据库等）。"
        "\n- 每条注意事项前加 ⚠️ 标记。"
        "\n- 回复谨慎稳重，不要冒险。"
    )

    def _generate_reply(self, message: str, context: list = None) -> str:
        msg = message.lower()
        if any(kw in msg for kw in ["部署", "上线", "docker", "发布"]):
            return self._deploy_reply()
        elif any(kw in msg for kw in ["环境", "配置", "变量"]):
            return "⚠️ 环境变量已配置完毕。请注意：生产环境的 SECRET_KEY 必须更换，不能用默认值。数据库连接串也需确认。"
        return "收到。我先检查一下部署环境和依赖配置。⚠️ 请注意确认环境变量是否正确。"

    def _deploy_reply(self) -> str:
        return (
            "部署配置已生成 ⚠️ 请注意以下事项：\n\n"
            "```dockerfile\n"
            "FROM node:18-alpine AS builder\n"
            "WORKDIR /app\n"
            "COPY package*.json ./\n"
            "RUN npm ci\n"
            "COPY . .\n"
            "RUN npm run build\n\n"
            "FROM nginx:alpine\n"
            "COPY --from=builder /app/build /usr/share/nginx/html\n"
            "EXPOSE 80\n"
            "CMD [\"nginx\", \"-g\", \"daemon off;\"]\n"
            "```\n\n"
            "```yaml\n"
            "# docker-compose.yml\n"
            "version: '3.8'\n"
            "services:\n"
            "  frontend:\n"
            "    build: ./frontend\n"
            "    ports:\n"
            "      - \"3000:80\"\n"
            "  backend:\n"
            "    build: ./backend\n"
            "    ports:\n"
            "      - \"8000:8000\"\n"
            "    environment:\n"
            "      - SECRET_KEY=changeme\n"
            "```\n\n"
            "⚠️ 生产环境部署前请确认：\n"
            "1. SECRET_KEY 已更换为安全值\n"
            "2. 数据库连接串正确\n"
            "3. 域名和 SSL 证书已配置\n\n"
            "确认无误后点击一键部署按钮即可。"
        )
