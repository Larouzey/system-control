# /root/controller/guest.py
import os, time
from controller.config import LOCK_FILE, LIMIT_SECONDS, FA2_DIR

def toggle_guest(action):
    if action == "stop":
        with open(LOCK_FILE, "w") as f: f.write(str(time.time()))
    elif action == "start" and os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)

def get_guest_status():
    if os.path.exists(LOCK_FILE):
        mtime = os.path.getmtime(LOCK_FILE)
        rem = LIMIT_SECONDS - (time.time() - mtime)
        if rem > 0:
            return True, round(rem/3600, 1)
    return False, 0

def auto_clean_loop():
    while True:
        status, _ = get_guest_status()
        if os.path.exists(LOCK_FILE) and not status:
            try: os.remove(LOCK_FILE)
            except: pass
            
        # 兼容带 IP 前缀的新版 2FA 授权文件清理
        if os.path.exists(FA2_DIR):
            for filename in os.listdir(FA2_DIR):
                if "_auth_" in filename and filename.endswith(".txt"):
                    file_path = os.path.join(FA2_DIR, filename)
                    try:
                        with open(file_path, 'r') as f:
                            data = f.read().split('|')
                            if len(data) >= 2:
                                auth_type = data[0]
                                timestamp = int(data[1])
                                elapsed = time.time() - timestamp
                                # 超过 1 小时清理 TEMP，超过 365 天清理 PERM
                                if (auth_type == "TEMP" and elapsed > 3600) or (auth_type == "PERM" and elapsed > 31536000):
                                    os.remove(file_path)
                    except:
                        pass
        time.sleep(60)