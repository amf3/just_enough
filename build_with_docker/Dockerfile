FROM ubuntu:latest

ARG APP_DIR=/app
ARG UID=1000
ARG GID=1000

RUN groupadd -g ${GID} devgroup || true 
RUN useradd -u ${UID} -g ${GID} -m devuser || true
RUN mkdir -p ${APP_DIR} && chown ${UID}:${GID} ${APP_DIR}

RUN apt update && \
 apt install -y build-essential bash bc binutils bzip2 cpio diffutils file findutils g++ gcc git gzip libncurses-dev make patch perl python3 rsync unzip wget vim libcrypt-dev libssl-dev

USER ${UID}
WORKDIR ${APP_DIR}
