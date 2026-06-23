FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置时区与编码环境变量
ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# 先复制依赖文件，利用 Docker 缓存层
COPY requirements.txt /app/requirements.txt

# 安装依赖
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# 复制项目代码
COPY . /app

# 暴露服务端口
EXPOSE 8081

# 启动 FastAPI 服务
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8081"]
