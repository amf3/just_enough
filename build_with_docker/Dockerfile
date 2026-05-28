FROM ubuntu:latest

ARG APP_DIR=/app
ARG UID=1000
ARG GID=1000

RUN groupadd -g ${GID} devgroup || true 
RUN useradd -u ${UID} -g ${GID} -m devuser || true
RUN mkdir -p ${APP_DIR} && chown ${UID}:${GID} ${APP_DIR}

RUN apt update && \
 apt install -y build-essential bc binutils bzip2 \
   cpio curl ca-certificates coreutils-from-uutils \
   diffutils \
   file findutils \
   g++ gcc git golang-go gnupg-agent gzip \
   libncurses-dev libssl-dev less libcrypt-dev \
   jq \
   make patch python3 python3-pip python3-yaml\
   pax-utils \
   rsync  \
   software-properties-common \
   tree \
   unzip \
   wget \
   vim && \
 rm -rf /var/lib/apt/lists/*

USER ${UID}
WORKDIR ${APP_DIR}
