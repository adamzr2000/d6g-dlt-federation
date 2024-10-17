from flask import Flask, jsonify
import time
import os

app = Flask(__name__)
request_count = 0

# Read server_id from environment variable
server_id = os.getenv('SERVER_ID', 'Unknown')

@app.route('/')
def index():
    global request_count
    request_count += 1
    return jsonify({
        'timestamp': time.time(),
        'server_id': server_id,
        'request_count': request_count,
        'message': 'Hello from the dummy federation app!',
        'status': 'success'
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
