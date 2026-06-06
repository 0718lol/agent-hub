@echo off
REM 启动 OpenCode Agent Proxy
REM 需要先安装 OpenCode: npm install -g opencode

echo Starting OpenCode server...
start "OpenCode Serve" cmd /c "set NODE_TLS_REJECT_UNAUTHORIZED=0 && opencode serve --port 4098"

echo Waiting for OpenCode server...
timeout /t 5 /nobreak >nul

echo Starting Agent Proxy...
cd /d "%~dp0\..\.."
node app\proxy\opencode_proxy.mjs --port 4097 --opencode-url http://127.0.0.1:4098
