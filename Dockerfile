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
#     -e MAX_FILE_SIZE=104857600 \
#     pydoctrans

FROM ubuntu:22.04

# 系统包
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    # LibreOffice 依赖
    libx11-6 \
    libxext6 \
    libxrender1 \
    libxinerama1 \
    libcairo2 \
    libcups2 \
    libdbus-glib-1-2 \
    libglib2.0-0 \
    libsm6 \
    # 工具
    wget \
    ca-certificates \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# 安装 LibreOffice（从官方 deb 包）
ARG LO_VERSION=26.2.3
ARG LO_BASE=https://download.documentfoundation.org/libreoffice/stable
ENV LO_VERSION=${LO_VERSION}

RUN wget -q ${LO_BASE}/${LO_VERSION}/deb/x86_64/LibreOffice_${LO_VERSION}_Linux_x86-64_deb.tar.gz \
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
    print(f'LO detected: {env.version}')"

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
