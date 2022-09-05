from flask import Flask

app = Flask(__name__)

@app.route("/")
def hello_world():
        return "<p>Just Enough containers provide just enough to get you going!</p>"
