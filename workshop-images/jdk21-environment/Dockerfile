#syntax=docker/dockerfile:1.3-labs

ARG IMAGE_REPOSITORY=localhost:5001
ARG BASE_IMAGE_NAME=educates-base-environment
ARG PACKAGE_VERSION=latest

FROM ${IMAGE_REPOSITORY}/${BASE_IMAGE_NAME}:${PACKAGE_VERSION} AS scratch-image

ARG TARGETARCH

RUN mkdir -p /opt/{java,gradle,maven}

RUN <<EOF
    set -eo pipefail
    ARCHNAME_amd64=x64
    ARCHNAME_arm64=aarch64
    ARCHNAME=ARCHNAME_${TARGETARCH}
    CHECKSUM_amd64="a2650fba422283fbed20d936ce5d2a52906a5414ec17b2f7676dddb87201dbae"
    CHECKSUM_arm64="04fe1273f624187d927f1b466e8cdb630d70786db07bee7599bfa5153060afd3"
    CHECKSUM=CHECKSUM_${TARGETARCH}
    curl --fail -sL -o /tmp/jdk21.tar.gz https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.6%2B7/OpenJDK21U-jdk_${!ARCHNAME}_linux_hotspot_21.0.6_7.tar.gz
    echo "${!CHECKSUM} /tmp/jdk21.tar.gz" | sha256sum --check --status
    tar -C /opt/java --strip-components 1 -zxf /tmp/jdk21.tar.gz
    rm /tmp/jdk21.tar.gz
EOF

RUN curl --fail -sL -o /tmp/maven.tar.gz https://archive.apache.org/dist/maven/maven-3/3.9.9/binaries/apache-maven-3.9.9-bin.tar.gz && \
    echo "a555254d6b53d267965a3404ecb14e53c3827c09c3b94b5678835887ab404556bfaf78dcfe03ba76fa2508649dca8531c74bca4d5846513522404d48e8c4ac8b /tmp/maven.tar.gz" | sha512sum --check --status && \
    tar -C /opt/maven --strip-components 1 -zxf /tmp/maven.tar.gz && \
    rm /tmp/maven.tar.gz

    RUN curl --fail -sL -o /tmp/gradle.zip https://services.gradle.org/distributions/gradle-8.8-bin.zip && \
    echo "a4b4158601f8636cdeeab09bd76afb640030bb5b144aafe261a5e8af027dc612 /tmp/gradle.zip" | sha256sum --check --status && \
    unzip -d /opt/gradle /tmp/gradle.zip && \
    mv /opt/gradle/gradle-8.8/* /opt/gradle/ && \
    rm -rf /opt/gradle/gradle-8.8 && \
    rm /tmp/gradle.zip

ENV PATH=/opt/java/bin:/opt/gradle/bin:/opt/maven/bin:$PATH \
    JAVA_HOME=/opt/java \
    M2_HOME=/opt/maven \
    GRADLE_HOME=/opt/gradle

COPY gradle.properties-arm64 .

RUN if [ "${TARGETARCH}" = "arm64" ]; then \
        export MAVEN_OPTS="-XX:UseSVE=0"; \
        export JAVA_OPTS="-XX:UseSVE=0"; \
    fi && \
    mvn archetype:generate -DgroupId=com.mycompany.app -DartifactId=my-app \
        -DarchetypeArtifactId=maven-archetype-quickstart \
        -DarchetypeVersion=1.4 -DinteractiveMode=false && \
    cd my-app && \
    mvn wrapper:wrapper

RUN if [ "${TARGETARCH}" = "arm64" ]; then \
        export MAVEN_OPTS="-XX:UseSVE=0"; \
        export JAVA_OPTS="-XX:UseSVE=0"; \
        mv gradle.properties-arm64 gradle.properties; \
    fi && \
    gradle init && \
    gradle wrapper --gradle-version=8.8 --distribution-type=bin && \
    ./gradlew build

FROM ${IMAGE_REPOSITORY}/${BASE_IMAGE_NAME}:${PACKAGE_VERSION}

COPY --from=scratch-image --chown=1001:0 /opt/java /opt/java
COPY --from=scratch-image --chown=1001:0 /opt/gradle /opt/gradle
COPY --from=scratch-image --chown=1001:0 /opt/maven /opt/maven

COPY --from=scratch-image --chown=1001:0 /home/eduk8s/.m2 /home/eduk8s/.m2
COPY --from=scratch-image --chown=1001:0 /home/eduk8s/.gradle /home/eduk8s/.gradle

COPY --chown=1001:0 opt/. /opt/

ENV PATH=/opt/java/bin:/opt/gradle/bin:/opt/maven/bin:$PATH \
    JAVA_HOME=/opt/java \
    M2_HOME=/opt/maven
