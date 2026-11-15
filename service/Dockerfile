# Build context is the repository root (see docker-compose.yml) so the multi-module build resolves.
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY pom.xml .
COPY service/pom.xml service/pom.xml
COPY replayer/pom.xml replayer/pom.xml
RUN mvn -B -q -pl service -am dependency:go-offline || true
COPY service service
COPY replayer replayer
COPY dashboard dashboard
RUN mvn -B -q -pl service -am -DskipTests package

FROM eclipse-temurin:21-jre
WORKDIR /app
# curl for the HEALTHCHECK below; installed explicitly rather than trusting the base image to carry it
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 monitor
COPY --from=build /src/service/target/service-*.jar app.jar
USER monitor
EXPOSE 8080
ENV JAVA_OPTS="-XX:MaxRAMPercentage=75"
HEALTHCHECK --interval=10s --timeout=3s --start-period=40s --retries=6 \
  CMD curl -fsS http://localhost:8080/actuator/health || exit 1
ENTRYPOINT ["sh", "-c", "exec java $JAVA_OPTS -jar app.jar"]
