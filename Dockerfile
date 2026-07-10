# pydoctrans Docker 镜像
# =========================
#
# 构建:
#   docker build -t pydoctrans .
#
# 运行:
#   docker run -p 8000:8000 pydoctrans
#
# 配置（环境变量）:
#   docker run -p 8000:8000 \
#     -e MAX_CONCURRENT=4 \
#     -e LO_TIMEOUT=120 \
#     pydoctrans

FROM ubuntu:22.04

# 系统包 + 字体
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    # LibreOffice headless 运行时依赖
    libx11-6 libxext6 libxrender1 libxinerama1 \
    libx11-xcb1 libxcb1 libxcb-shm0 libxcb-render0 \
    libcairo2 libcups2 libdbus-glib-1-2 libglib2.0-0 libsm6 \
    libssl3 libnss3 libnspr4 \
    libfontconfig1 libfreetype6 \
    # PDF 后处理
    ghostscript \
    # 中文字体 + 常用字体（对齐 parser 项目）
    fonts-noto-cjk \
    fonts-dejavu fonts-liberation fonts-noto fonts-freefont-ttf \
    fonts-ubuntu fonts-cantarell fonts-lmodern fonts-inconsolata \
    # 工具
    wget ca-certificates \
    python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

# 安装 LibreOffice 26.2.4（parser 项目已验证的稳定版本）
ARG LO_VERSION=26.2.4
ARG LO_BASE=https://downloadarchive.documentfoundation.org/libreoffice/old
ENV LO_VERSION=${LO_VERSION}

RUN wget -q ${LO_BASE}/${LO_VERSION}.2/deb/x86_64/LibreOffice_${LO_VERSION}.2_Linux_x86-64_deb.tar.gz \
    -O /tmp/lo.tar.gz && \
    mkdir -p /tmp/lo && \
    tar -xzf /tmp/lo.tar.gz -C /tmp/lo && \
    dpkg -i /tmp/lo/LibreOffice_${LO_VERSION}*_Linux_x86-64_deb/DEBS/*.deb || \
    apt-get install -f -y && \
    dpkg -i /tmp/lo/LibreOffice_${LO_VERSION}*_Linux_x86-64_deb/DEBS/*.deb && \
    rm -rf /tmp/lo /tmp/lo.tar.gz && \
    apt-get clean

# 安装 pydoctrans
WORKDIR /app
COPY . .
RUN pip3 install --no-cache-dir -e . && \
    pip3 install --no-cache-dir uvicorn[standard]

# 验证 LO 可用
RUN python3 -c "from pydoctrans.env import detect; \
    env = detect(); \
    assert env.found, 'LO not found'; \
    print(f'LO version: {env.version[:80]}')"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python3 -c "import urllib.request; \
        urllib.request.urlopen('http://localhost:8000/health')" || exit 1

ENV HOST=0.0.0.0
ENV PORT=8000
ENV MAX_CONCURRENT=10
ENV LO_TIMEOUT=300
ENV MAX_FILE_SIZE=52428800
ENV TMP_DIR=/tmp

ENTRYPOINT ["python3", "-m", "pydoctrans"]
