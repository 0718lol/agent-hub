"""Official project skeletons for deterministic project initialization."""

from dataclasses import dataclass

from app.services.project_workspace import (
    GeneratedProjectFile,
    materialize_project_files,
)


class ProjectTemplateNotFound(ValueError):
    pass


@dataclass(frozen=True)
class ProjectTemplate:
    id: str
    name: str
    project_type: str
    description: str
    files: tuple[GeneratedProjectFile, ...]

    def public_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "project_type": self.project_type,
            "description": self.description,
            "files": [item.path for item in self.files],
        }


WEB_TEMPLATE = ProjectTemplate(
    id="web-static",
    name="Web 工具",
    project_type="web",
    description="零依赖静态 Web 工具，可立即预览并打包发布。",
    files=(
        GeneratedProjectFile(
            "index.html",
            "html",
            """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentHub Web Tool</title>
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; font-family: system-ui, sans-serif; background: #f4f7fa; color: #17202a; }
    main { width: min(720px, calc(100% - 32px)); margin: 48px auto; }
    section { border: 1px solid #d8e0e8; background: white; padding: 24px; border-radius: 8px; }
    input, button { font: inherit; padding: 10px 12px; }
    input { width: 100%; border: 1px solid #aeb9c4; border-radius: 6px; }
    button { margin-top: 12px; border: 0; border-radius: 6px; color: white; background: #087f5b; cursor: pointer; }
    #result { min-height: 24px; margin-top: 16px; }
  </style>
</head>
<body>
  <main>
    <h1>Web 工具</h1>
    <section>
      <label for="value">输入内容</label>
      <input id="value" placeholder="在这里输入">
      <button id="run" type="button">执行</button>
      <div id="result" aria-live="polite"></div>
    </section>
  </main>
  <script>
    document.getElementById("run").addEventListener("click", () => {
      const value = document.getElementById("value").value.trim();
      document.getElementById("result").textContent = value || "请输入内容";
    });
  </script>
</body>
</html>
""",
        ),
        GeneratedProjectFile(
            "README.md",
            "markdown",
            "# Web 工具\n\n直接打开 `index.html`，或使用 AgentHub 预览与发布流水线。\n",
        ),
    ),
)

API_TEMPLATE = ProjectTemplate(
    id="api-fastapi",
    name="FastAPI 服务",
    project_type="api",
    description="带健康检查和容器配置的 FastAPI 服务。",
    files=(
        GeneratedProjectFile(
            "main.py",
            "python",
            """from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="AgentHub Generated API")


class EchoRequest(BaseModel):
    text: str


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/echo")
async def echo(payload: EchoRequest):
    return {"text": payload.text}
""",
        ),
        GeneratedProjectFile("requirements.txt", "text", "fastapi==0.116.1\nuvicorn==0.35.0\n"),
        GeneratedProjectFile(
            "Dockerfile",
            "dockerfile",
            """FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
""",
        ),
        GeneratedProjectFile(
            "README.md",
            "markdown",
            "# FastAPI 服务\n\n本地运行：`uvicorn main:app --reload`。\n",
        ),
    ),
)

MINIPROGRAM_TEMPLATE = ProjectTemplate(
    id="miniprogram-basic",
    name="微信小程序",
    project_type="miniprogram",
    description="可在微信开发者工具导入并接入真实上传流水线的小程序。",
    files=(
        GeneratedProjectFile(
            "project.config.json",
            "json",
            """{
  "description": "AgentHub generated mini program",
  "compileType": "miniprogram",
  "miniprogramRoot": "miniprogram/",
  "appid": "touristappid",
  "setting": {"es6": true, "minified": true}
}
""",
        ),
        GeneratedProjectFile("miniprogram/app.js", "javascript", "App({})\n"),
        GeneratedProjectFile(
            "miniprogram/app.json",
            "json",
            """{
  "pages": ["pages/index/index"],
  "window": {
    "navigationBarTitleText": "AgentHub 工具",
    "navigationBarBackgroundColor": "#087f5b",
    "navigationBarTextStyle": "white"
  }
}
""",
        ),
        GeneratedProjectFile(
            "miniprogram/app.wxss",
            "css",
            "page { background: #f4f7fa; color: #17202a; font-family: sans-serif; }\n",
        ),
        GeneratedProjectFile(
            "miniprogram/pages/index/index.wxml",
            "html",
            """<view class="page">
  <view class="title">小程序工具</view>
  <input class="input" placeholder="请输入内容" bindinput="onInput" />
  <button type="primary" bindtap="run">执行</button>
  <view class="result">{{result}}</view>
</view>
""",
        ),
        GeneratedProjectFile(
            "miniprogram/pages/index/index.js",
            "javascript",
            """Page({
  data: {value: "", result: ""},
  onInput(event) {
    this.setData({value: event.detail.value});
  },
  run() {
    this.setData({result: this.data.value || "请输入内容"});
  }
});
""",
        ),
        GeneratedProjectFile(
            "miniprogram/pages/index/index.wxss",
            "css",
            """.page { padding: 40rpx; }
.title { margin-bottom: 32rpx; font-size: 44rpx; font-weight: 700; }
.input { margin-bottom: 24rpx; padding: 20rpx; border: 1px solid #aeb9c4; background: white; }
.result { margin-top: 24rpx; }
""",
        ),
        GeneratedProjectFile("miniprogram/pages/index/index.json", "json", "{}\n"),
    ),
)

APK_TEMPLATE = ProjectTemplate(
    id="apk-kotlin",
    name="Android APK",
    project_type="apk",
    description="原生 Kotlin Android 工程，可进入 APK 构建与双签名流水线。",
    files=(
        GeneratedProjectFile(
            "settings.gradle.kts",
            "kotlin",
            """pluginManagement {
    repositories { google(); mavenCentral(); gradlePluginPortal() }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories { google(); mavenCentral() }
}
rootProject.name = "AgentHubGenerated"
include(":app")
""",
        ),
        GeneratedProjectFile(
            "build.gradle.kts",
            "kotlin",
            """plugins {
    id("com.android.application") version "8.7.3" apply false
    id("org.jetbrains.kotlin.android") version "2.0.21" apply false
}
""",
        ),
        GeneratedProjectFile(
            "gradle.properties",
            "properties",
            "org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8\nandroid.useAndroidX=true\n",
        ),
        GeneratedProjectFile(
            "gradlew",
            "shell",
            """#!/bin/sh
set -eu
VERSION=8.9
ROOT="${GRADLE_USER_HOME:-$HOME/.gradle}/agenthub/gradle-$VERSION"
ZIP="$ROOT/gradle.zip"
if [ ! -x "$ROOT/gradle-$VERSION/bin/gradle" ]; then
  mkdir -p "$ROOT"
  wget -q "https://services.gradle.org/distributions/gradle-$VERSION-bin.zip" -O "$ZIP"
  wget -q "https://services.gradle.org/distributions/gradle-$VERSION-bin.zip.sha256" -O "$ZIP.sha256"
  printf "%s  %s\\n" "$(cat "$ZIP.sha256")" "$ZIP" | sha256sum -c -
  unzip -q -o "$ZIP" -d "$ROOT"
fi
exec "$ROOT/gradle-$VERSION/bin/gradle" "$@"
""",
        ),
        GeneratedProjectFile(
            "app/build.gradle.kts",
            "kotlin",
            """plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.agenthub.generated"
    compileSdk = 35
    defaultConfig {
        applicationId = "com.agenthub.generated"
        minSdk = 24
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"
    }
}
""",
        ),
        GeneratedProjectFile(
            "app/src/main/AndroidManifest.xml",
            "xml",
            """<manifest xmlns:android="http://schemas.android.com/apk/res/android">
  <application android:theme="@style/AppTheme" android:label="AgentHub Tool">
    <activity android:name=".MainActivity" android:exported="true">
      <intent-filter>
        <action android:name="android.intent.action.MAIN" />
        <category android:name="android.intent.category.LAUNCHER" />
      </intent-filter>
    </activity>
  </application>
</manifest>
""",
        ),
        GeneratedProjectFile(
            "app/src/main/java/com/agenthub/generated/MainActivity.kt",
            "kotlin",
            """package com.agenthub.generated

import android.app.Activity
import android.os.Bundle
import android.view.Gravity
import android.widget.TextView

class MainActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(TextView(this).apply {
            text = "AgentHub APK Tool"
            textSize = 24f
            gravity = Gravity.CENTER
        })
    }
}
""",
        ),
        GeneratedProjectFile(
            "app/src/main/res/values/styles.xml",
            "xml",
            """<resources>
  <style name="AppTheme" parent="android:style/Theme.Material.Light.NoActionBar">
    <item name="android:fontFamily">sans</item>
    <item name="android:colorAccent">#087F5B</item>
  </style>
</resources>
""",
        ),
    ),
)

PROJECT_TEMPLATES = {
    item.id: item
    for item in (WEB_TEMPLATE, API_TEMPLATE, MINIPROGRAM_TEMPLATE, APK_TEMPLATE)
}


def list_project_templates() -> list[dict]:
    return [template.public_dict() for template in PROJECT_TEMPLATES.values()]


async def initialize_project_template(
    conversation_id: str,
    template_id: str,
) -> dict:
    template = PROJECT_TEMPLATES.get(template_id)
    if template is None:
        raise ProjectTemplateNotFound(template_id)
    result = await materialize_project_files(
        conversation_id,
        "system_template",
        list(template.files),
        require_empty=True,
    )
    return {"template": template.public_dict(), **result}
