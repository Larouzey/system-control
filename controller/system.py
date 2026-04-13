# /root/controller/system.py
import os, time, threading, subprocess
from datetime import datetime
from controller.config import LOG_FILE

def write_log(message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")

def graceful_shutdown(client_ip, ua):
    write_log(f"[指令接收] IP: {client_ip} | UA: {ua} | 动作: 关机")
    
    def safe_poweroff():
        cmd = "pvesh create /nodes/localhost/stopall"
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            write_log(f"[任务反馈] stopall 结果: {result.stdout.strip()} {result.stderr.strip()}")
        except Exception as e:
            write_log(f"[严重错误] {str(e)}")
        
        time.sleep(10)
        write_log("[系统动作] 执行 poweroff")
        os.system("poweroff")

    threading.Timer(2, safe_poweroff).start()
