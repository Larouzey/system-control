# /root/controller/auth.py
import os, uuid, time, pyotp
from controller.config import FA2_DIR, ALLOWED_IPS, TOTP_SECRET

def verify_totp(token):
    totp = pyotp.TOTP(TOTP_SECRET)
    return totp.verify(token)

def create_session(client_ip, ua, is_temp=False):
    new_id = str(uuid.uuid4())
    if not os.path.exists(FA2_DIR): os.makedirs(FA2_DIR)
    file_path = os.path.join(FA2_DIR, f"{client_ip}_auth_{new_id}.txt")
    with open(file_path, 'w') as f:
        auth_type = "TEMP" if is_temp else "PERM"
        f.write(f"{auth_type}|{int(time.time())}|{ua}")
    return new_id

def get_session_type(client_ip, session_id):
    """获取会话类型：返回 'TEMP'、'PERM' 或 None"""
    if not session_id: return None
    auth_file = os.path.join(FA2_DIR, f"{client_ip}_auth_{session_id}.txt")
    if not os.path.exists(auth_file): return None
    try:
        with open(auth_file, 'r') as f:
            data = f.read().strip().split('|')
            return data[0] # 返回 TEMP 或 PERM
    except:
        return None

def is_trusted(client_ip, session_id, current_ua):
    if ALLOWED_IPS and client_ip not in ALLOWED_IPS:
        return False
    if not session_id:
        return False
    auth_file = os.path.join(FA2_DIR, f"{client_ip}_auth_{session_id}.txt")
    if not os.path.exists(auth_file):
        return False
    try:
        with open(auth_file, 'r') as f:
            data = f.read().strip().split('|')
            if len(data) < 3: return False
            auth_type, timestamp, saved_ua = data[0], int(data[1]), data[2]
            if saved_ua != current_ua: return False
            elapsed = int(time.time()) - timestamp
            if auth_type == "TEMP" and elapsed > 3600: return False
            if auth_type == "PERM" and elapsed > 31536000: return False
            return True
    except:
        return False