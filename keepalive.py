import subprocess
import time
import threading
import requests
import os
from datetime import datetime, timedelta

def health_check():
    """Check if the API is responding"""
    try:
        port = os.environ.get('PORT', '10000')  # ← USE SAME PORT
        response = requests.get(f'http://localhost:{port}/health', timeout=10)
        return response.status_code == 200
    except:
        return False

# Add periodic self-pinging in keepalive.py
def self_ping():
    try:
        # This keeps the Render instance awake
        requests.get('https://davidaccentapi.onrender.com/health', timeout=5)
    except:
        pass

def run_flask_app():
    """Run the Flask application"""
    try:
        # Pass the PORT environment variable to the subprocess
        env = os.environ.copy()
        process = subprocess.Popen([
            'python', 'davidapi.py'
        ], env=env)
        return process
    except Exception as e:
        print(f"Error starting Flask app: {e}")
        return None

def keep_alive():
    """Main keepalive loop that ensures 12+ hours of uptime"""
    start_time = datetime.now()
    target_duration = timedelta(hours=12)
    
    flask_process = None
    restart_count = 0
    max_restarts = 10
    
    print(f"🚀 Starting keepalive system at {start_time}")
    print(f"🎯 Target duration: 12 hours (until {start_time + target_duration})")
    
    while datetime.now() - start_time < target_duration and restart_count < max_restarts:
        try:
            # Start Flask app if not running
            if flask_process is None or flask_process.poll() is not None:
                print(f"🔄 Starting Flask app (Restart #{restart_count + 1})...")
                flask_process = run_flask_app()
                if flask_process:
                    restart_count += 1
                    print("✅ Flask app started successfully")
                    # Wait for app to fully start
                    time.sleep(10)
                else:
                    print("❌ Failed to start Flask app")
                    time.sleep(5)
                    continue
            
            # Perform health check
            if health_check():
                current_uptime = datetime.now() - start_time
                hours = current_uptime.total_seconds() / 3600
                print(f"✅ Health check passed - Uptime: {hours:.2f} hours")
            else:
                print("❌ Health check failed - Restarting Flask app...")
                if flask_process:
                    flask_process.terminate()
                    flask_process.wait(timeout=5)
                flask_process = None
                time.sleep(2)
                continue
            
            # Sleep before next health check
            time.sleep(60)  # Check every minute
            
        except Exception as e:
            print(f"⚠️ Keepalive error: {e}")
            if flask_process:
                try:
                    flask_process.terminate()
                except:
                    pass
            flask_process = None
            time.sleep(5)
    
    # Cleanup
    if flask_process:
        flask_process.terminate()
        flask_process.wait(timeout=5)
    
    final_uptime = datetime.now() - start_time
    hours = final_uptime.total_seconds() / 3600
    print(f"🏁 Keepalive session completed - Total uptime: {hours:.2f} hours")
    
    # If we haven't reached 12 hours, restart the entire process
    if hours < 12:
        print("🔄 Restarting keepalive system to reach 12 hours...")
        time.sleep(5)
        keep_alive()

if __name__ == "__main__":
    keep_alive()
