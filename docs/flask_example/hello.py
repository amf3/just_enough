from flask import Flask, request
from datetime import datetime

app = Flask(__name__)

@app.route("/")
def hello_world():
    # 1. Get the current time on the server
    # Format it cleanly (e.g., "2026-06-16 08:52:15")
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 2. Get the caller's IP address
    # Flask looks at the incoming request network headers
    caller_ip = request.remote_addr
    
    # 3. Return a styled, dynamic HTML payload
    return f"""
    <div style="font-family: sans-serif; max-width: 500px; margin: 50px auto; padding: 20px; border: 1px solid #eee; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
        <h2 style="color: #2c3e50;">Just Enough Python Container</h2>
        <p>Just enough to get you going!</p>
        <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
        <p style="font-size: 0.9em; color: #555;">
            <strong>Your IP Address:</strong> <code style="background: #f4f6f7; padding: 2px 6px; border-radius: 4px;">{caller_ip}</code>
        </p>
        <p style="font-size: 0.9em; color: #555;">
            <strong>Server Time:</strong> <span style="color: #e74c3c;">{current_time}</span>
        </p>
    </div>
    """

