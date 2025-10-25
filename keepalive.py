from flask import Flask
from threading import Thread
import os

app = Flask(__name__)

@app.route('/')
def home():
    return "🚀 DavidAPI Keep-Alive Server is Running!"

@app.route('/health')
def health():
    return "✅ Healthy", 200

def run():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True  # This makes the thread exit when main thread exits
    t.start()
    print("✅ Keep-alive server started!")
