# ===== 第一阶段：Maven 编译 =====
FROM maven:3.9.6-eclipse-temurin-17 AS builder

WORKDIR /build

RUN mkdir -p /root/.m2 \
    && printf '%s\n' \
    '<settings xmlns="http://maven.apache.org/SETTINGS/1.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.0.0 https://maven.apache.org/xsd/settings-1.0.0.xsd">' \
    '  <mirrors>' \
    '    <mirror>' \
    '      <id>aliyunmaven</id>' \
    '      <mirrorOf>*</mirrorOf>' \
    '      <name>阿里云公共仓库</name>' \
    '      <url>https://maven.aliyun.com/repository/public</url>' \
    '    </mirror>' \
    '  </mirrors>' \
    '</settings>' > /root/.m2/settings.xml

# 先复制 pom.xml，利用 Docker 缓存加速依赖下载
COPY pom.xml .
RUN mvn -s /root/.m2/settings.xml dependency:go-offline -B

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
