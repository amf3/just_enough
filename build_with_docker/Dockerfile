FROM ubuntu:latest

ARG UID=1000
ARG GID=1000

RUN groupadd -g ${GID} devgroup || true && \
    useradd -u ${UID} -g ${GID} -m devuser

RUN apt update && apt install -y build-essential && \
    libncurses-dev file wget cpio unzip rsync bc

USER devuser
WORKDIR /home/devuser/app
