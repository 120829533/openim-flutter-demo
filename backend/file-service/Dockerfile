FROM python:3.11-slim

# 安装 Pillow 所需的系统依赖（zlib、libjpeg 等）
RUN apt-get update && apt-get install -y --no-install-recommends \
    zlib1g-dev \
    libjpeg62-turbo-dev \
    libjpeg-dev \
    zlib1g \
    libjpeg62-turbo \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先复制依赖文件，利用 Docker 缓存层
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

EXPOSE 8083

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8083"]
