# The Python Container Image with Bash

## About

This container provides Bash, Python3, Pip, and Setuptools.  It's my recomendation to not deploy containers with a shell, but this is being provided for use in multi-stage container builds.  When "/bin/sh" is not part of the container image,
 `docker build` will fail on `RUN` statements in the Dockerfile.  The image size with python3 and bash is around 64 MB.

## Container contents
* The C library is glibc 2.35.134
* Python 3.10.5
* Pip 21.2.4
* Setuptools 62.1.0
* Bash 5.1.16
* An application user named appuser is included with the container image.

## Examples

This is an example of packaging the flask application as part of a multi-stage build. Next flask will be copied into
a Python3 container that does not have Bash.  This demonstration shows how one can deploy a flask app with minimum dependencies.

We will package the flask application server using [shiv](https://pypi.org/project/shiv/).  Flask will then be copied into a bash-less python3 container for deployment.

First our flask application code.  Let's pretend it's stored in a file named hello.py.
```
from flask import Flask

app = Flask(__name__)

@app.route("/")
def hello_world():
    return "<p>Just Enough containers provide just enough to get you going!</p>"
```

This is our Dockerfile
```
FROM just_enough_python3_bash
USER appuser
RUN /usr/bin/python3 -m venv /tmp/flask
RUN source /tmp/flask/bin/activate && \
pip install shiv && \
mkdir /tmp/artifacts && \
shiv -c flask -o /tmp/artifacts/flask -p /usr/bin/python3 flask 

FROM ghcr.io/amf3/just_enough_python3:latest
USER appuser
COPY --from=0 /tmp/artifacts/flask /tmp/flask
COPY hello.py /tmp/hello.py
EXPOSE 5000/tcp
CMD ["/tmp/flask", "--app", "/tmp/hello.py", "run", "--host=0.0.0.0"]
```

Build the container
```
$ docker build -t python-flask .
```

Run the container and export TCP port 5000.  
```
$ docker run -p 5000:5000 python-flask
```

Open a web browser to view the app on port 5000.   This demonstrates how we can build a container with minimal dependencies which can be used to run flask apps.

