FROM ghcr.io/amf3/just_enough/busybox:latest AS my-busybox   
FROM ghcr.io/amf3/just_enough/python3.14:latest             

RUN --mount=type=bind,from=my-busybox,source=/bin/busybox,target=/bin/busybox \
    ["/bin/busybox", "mkdir", "/applications"]

COPY ./hello.py /applications/hello.py

RUN ["/usr/bin/python3.14", "-m", "pip", "install", "flask"]
WORKDIR /applications
ENV FLASK_APP=hello.py

EXPOSE 5000/tcp
ENTRYPOINT ["flask", "run", "--host=0.0.0.0"]




