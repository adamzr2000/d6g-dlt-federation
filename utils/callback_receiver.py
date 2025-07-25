# callback_receiver.py
from flask import Flask, request

app = Flask(__name__)

@app.route("/callback", methods=["POST"])
def cb():
    print("📬 Notification received:", request.json)
    return "", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9000)