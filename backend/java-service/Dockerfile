# ===== 第一阶段：Maven 编译 =====
FROM maven:3.9.6-eclipse-temurin-17 AS builder

WORKDIR /build

# 先复制 pom.xml，利用 Docker 缓存加速依赖下载
COPY pom.xml .
RUN mvn dependency:go-offline -B

# 复制源码并打包
COPY src ./src
RUN mvn clean package -DskipTests -B

# ===== 第二阶段：运行环境 =====
FROM eclipse-temurin:17-jre

LABEL maintainer="openim"

WORKDIR /app

# 复制构建产物
COPY --from=builder /build/target/openim-java-service-1.0.0.jar /app/app.jar

# 暴露 8082 端口（Spring Boot 服务端口）
EXPOSE 8082

# 设置时区为 Asia/Shanghai
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# JVM 参数
ENV JAVA_OPTS="-Xms256m -Xmx512m"

ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar /app/app.jar"]
