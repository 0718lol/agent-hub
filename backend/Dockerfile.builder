# Dedicated deployment worker with Android SDK and Docker CLI.
FROM python:3.12-slim-bookworm

ARG ANDROID_CMDLINE_VERSION=14742923
ARG ANDROID_CMDLINE_SHA1=48833c34b761c10cb20bcd16582129395d121b27
ENV ANDROID_HOME=/opt/android-sdk \
    ANDROID_SDK_ROOT=/opt/android-sdk \
    PATH=/opt/android-sdk/cmdline-tools/latest/bin:/opt/android-sdk/platform-tools:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
        docker.io gcc nodejs npm openjdk-17-jdk-headless unzip wget \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p ${ANDROID_HOME}/cmdline-tools /tmp/android-tools \
    && wget -q https://dl.google.com/android/repository/commandlinetools-linux-${ANDROID_CMDLINE_VERSION}_latest.zip -O /tmp/android-tools/tools.zip \
    && echo "${ANDROID_CMDLINE_SHA1}  /tmp/android-tools/tools.zip" | sha1sum -c - \
    && unzip -q /tmp/android-tools/tools.zip -d /tmp/android-tools \
    && mv /tmp/android-tools/cmdline-tools ${ANDROID_HOME}/cmdline-tools/latest \
    && yes | sdkmanager --licenses >/dev/null \
    && sdkmanager "platform-tools" "platforms;android-35" "platforms;android-36" "build-tools;35.0.0" "build-tools;36.0.0" \
    && rm -rf /tmp/android-tools

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN npm install -g miniprogram-ci@2.1.31 && npm cache clean --force
ENV NODE_PATH=/usr/local/lib/node_modules
COPY . .
RUN mkdir -p /app/data /agenthub_export /root/.gradle

CMD ["python", "-m", "app.workers.deployment_worker"]
