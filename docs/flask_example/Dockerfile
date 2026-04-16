#FROM just_enough_python3_bash
#RUN pip install flask
#RUN mkdir /applications
#COPY ./hello.py /applications/hello.py
#ENV FLASK_APP=/applications
#CMD ["flask", "--app", "hello", "run"]

FROM just_enough_python3_bash
USER appuser
RUN /usr/bin/python3 -m venv /tmp/flask
RUN source /tmp/flask/bin/activate && \
pip install shiv && \
mkdir /tmp/artifacts && \
shiv -c flask -o /tmp/artifacts/flask -p /usr/bin/python3 flask 

FROM just_enough_python3
COPY --from=0 /tmp/artifacts/flask /tmp/flask
COPY hello.py /tmp/hello.py
EXPOSE 5000/tcp
CMD ["/tmp/flask", "-A", "/tmp/hello.py", "run", "--host=0.0.0.0"]
