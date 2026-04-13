#!/usr/bin/python3
# -*- coding: utf-8 -*-

from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import urllib.parse
import threading
import time
import json  # <--- 必须在最顶层导入，避免作用域错误
import subprocess

# 导入配置和模块
from controller.config import HTML_DIR, IMAGE_DIR, LOG_FILE, MEDIA_DIR, SHUTDOWN_PASSWORD, NAS_IP, NAS_USER, ALLOWED_IPS
from controller import auth, guest, system, pve_api, nas_api

# ==========================================
# [核心优化] 内存缓存机制，彻底解决并发堵塞
# ==========================================
GLOBAL_NAS_DATA = {"online": False, "disks": []}

def nas_polling_loop():
    """独立后台线程：每 5 秒轮询一次 NAS，主程序直接读缓存，耗时 0 毫秒"""
    global GLOBAL_NAS_DATA
    nas = nas_api.QNAPManager(NAS_IP)
    while True:
        try:
            # 注意：如果你的 nas_api.py 中的方法名是 get_stats，请在这里保持一致
            GLOBAL_NAS_DATA = nas.get_stats() 
        except Exception as e:
            GLOBAL_NAS_DATA = {"online": False, "error": str(e)}
        time.sleep(5)

class PVERouter(BaseHTTPRequestHandler):
    
    # ==========================================
    # 1. 基础工具函数
    # ==========================================
    def get_ip(self):
        return self.headers.get('X-Forwarded-For', self.client_address[0]).split(',')[0].strip()

    def get_sid(self):
        cookie_str = self.headers.get('Cookie', '')
        cookies = urllib.parse.parse_qs(cookie_str.replace('; ', '&'))
        return cookies.get('session_id', [None])[0]

    def read_html(self, filename):
        file_path = os.path.join(HTML_DIR, filename)
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        return f"<h3 style='color:red;'>模板丢失: {filename}</h3>"

    def load_template(self, content_html, client_ip):
        layout = self.read_html("layout.html")
        return layout.replace("{{content}}", content_html).replace("{{client_ip}}", client_ip)

    def load_admin_template(self, content_html, active_tab):
        layout = self.read_html("admin_layout.html")
        for tab in ["pve", "vms", "nas", "sys"]:
            layout = layout.replace(f"{{{{active_{tab}}}}}" , "active" if tab == active_tab else "")
        return layout.replace("{{admin_content}}", content_html)

    #def send_page(self, html_content, status=200, sid=None, c_type='text/html; charset=utf-8'):
    #    self.send_response(status)
    #    self.send_header('Content-type', c_type)
    #    if sid:
    #        # 【修复点】：增加 Max-Age=31536000 (365天)。
    #        # 这样即使关闭浏览器，Cookie 也会存活。真正的过期时间由后端的 auth.py 严格把控。
    #        self.send_header('Set-Cookie', f'session_id={sid}; Path=/; HttpOnly; Max-Age=31536000')
    #    self.end_headers()
    #    self.wfile.write(html_content.encode('utf-8'))

    def send_page(self, html_content, status=200, sid=None, c_type='text/html; charset=utf-8'):
        self.send_response(status)
        self.send_header('Content-type', c_type)
        if sid:
            # 强制 Cookie 存活 365 天，真正的过期验证交由 auth.py 处理
            self.send_header('Set-Cookie', f'session_id={sid}; Path=/; HttpOnly; Max-Age=31536000')
        self.end_headers()
        self.wfile.write(html_content.encode('utf-8'))
  
    def serve_resource(self, path):
        filename = os.path.basename(path)
        ext = os.path.splitext(filename)[1].lower()
        
        if ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg']:
            file_path = os.path.join(IMAGE_DIR, filename)
        elif ext in ['.mp4', '.webm', '.ogg']:
            file_path = os.path.join(MEDIA_DIR, filename)
        else:
            file_path = os.path.join(HTML_DIR, filename)

        try:
            if os.path.exists(file_path):
                with open(file_path, 'rb') as f: content = f.read()
                self.send_response(200)
                if ext == '.css': self.send_header('Content-type', 'text/css')
                elif ext in ['.png', '.jpg', '.jpeg']: self.send_header('Content-type', 'image/png')
                elif ext == '.mp4': self.send_header('Content-type', 'video/mp4')
                elif ext == '.ico': self.send_header('Content-type', 'image/x-icon')
                elif ext == '.js': self.send_header('Content-type', 'application/javascript')
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404)
        except:
            self.send_error(500)

    # ==========================================
    # 2. 页面渲染函数
    # ==========================================
    def render_msg(self, msg, ip):
        html = f"<h2>提示</h2><p>{msg}</p><button class='btn btn-primary' onclick=\"location.href='/'\">返回主页</button>"
        self.send_page(self.load_template(html, ip))

    def render_redirect(self, msg, ip, sid=None, target="/"):
        html = f"<div class='status-box running'>{msg}</div><script>setTimeout(()=>{{location.href='{target}'}},1200)</script>"
        self.send_page(self.load_template(html, ip), sid=sid)

    def render_admin_pve(self):
        status = pve_api.get_pve_status()
        snippet = self.read_html("snippet_node.html")
        nodes_html = snippet.replace("{{name}}", "Localhost")\
                            .replace("{{status}}", "online")\
                            .replace("{{uptime}}", status.get('uptime', '未知'))\
                            .replace("{{cpu}}", status.get('cpu', '0%').replace('%',''))\
                            .replace("{{mem_gb}}", status.get('mem', '0/0').split(' / ')[0].replace('G',''))\
                            .replace("{{maxmem_gb}}", status.get('mem', '0/0').split(' / ')[1].replace('G',''))
        page = self.read_html("admin_pve.html").replace("{{nodes_html}}", nodes_html)
        self.send_page(self.load_admin_template(page, "pve"))

    def render_admin_vms(self):
        vms = pve_api.get_vm_list()
        snippet = self.read_html("snippet_vm.html")
        vms_content = ""
        for v in vms:
            v_id = str(v.get('id', v.get('vmid', 'N/A')))
            v_status = str(v.get('status', 'unknown'))
            color = "#10b981" if v_status == 'running' else "#ef4444"
            vms_content += snippet.replace("{{vmid}}", v_id)\
                                  .replace("{{name}}", str(v.get('name', 'Unknown')))\
                                  .replace("{{status}}", v_status)\
                                  .replace("{{status_color}}", color)\
                                  .replace("{{cpu}}", str(v.get('cpu', v.get('cpu_pct', '0'))))\
                                  .replace("{{mem_mb}}", str(v.get('mem', v.get('used_mem_gb', '0'))))
        if not vms_content: vms_content = '<div style="color:#64748b; padding:20px;">无数据</div>'
        page = self.read_html("admin_vms.html").replace("{{vms_content}}", vms_content)
        self.send_page(self.load_admin_template(page, "vms"))

    def render_admin_nas(self):
        page = self.read_html("admin_nas.html")
        self.send_page(self.load_admin_template(page, "nas"))

    def render_admin_sys(self):
        page = self.read_html("admin_sys.html")
        self.send_page(self.load_admin_template(page, "sys"))

    # ==========================================
    # 3. GET 路由 (无阻塞响应)
    # ==========================================
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        ip = self.get_ip()
        sid = self.get_sid()
        ua = self.headers.get('User-Agent', 'Unknown')

        resource_exts = ('.css', '.png', '.jpg', '.jpeg', '.gif', '.ico', '.mp4', '.webm', '.js')
        if path.endswith(resource_exts) or '/static/' in path:
            self.serve_resource(path)
            return

        # [秒回数据]：不执行耗时的 SNMP 查询，直接返回后台线程准备好的 JSON 内存数据
        if path == '/api/nas_stats':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(GLOBAL_NAS_DATA).encode('utf-8'))
            return

        if path.startswith('/admin/'):
            if not auth.is_trusted(ip, sid, ua):
                self.send_page(self.load_template(self.read_html("admin_choice.html"), ip))
                return

        if path == '/':
            is_stopped, rem = guest.get_guest_status()
            content = self.read_html("index.html")
            status_cls = "running" if is_stopped else "auto"
            status_txt = f"临时停止响应模式 (剩余 {rem} 小时)" if is_stopped else "系统正在自动检测中..."
            btn_txt = "解除锁定并返回自动模式" if is_stopped else "临时停止响应 (8小时)"
            btn_url = "/start" if is_stopped else "/stop"
            
            content = content.replace("{{status_class}}", status_cls)\
                             .replace("{{status_text}}", status_txt)\
                             .replace("{{guest_btn_text}}", btn_txt)\
                             .replace("{{guest_btn_url}}", btn_url)
            self.send_page(self.load_template(content, ip))

        elif path == '/start':
            guest.toggle_guest("start")
            self.render_redirect("✅ 自动检测模式已恢复...", ip, target="/")
        elif path == '/stop':
            guest.toggle_guest("stop")
            self.render_redirect("⚠️ 系统已进入临时停止模式...", ip, target="/")

        # “关闭pve主机”按钮跳转页面功能
        elif path == '/shutdown_confirm':
            # 获取当前会话类型
            current_auth_type = auth.get_session_type(ip, sid)
            
            # 判定是否享受免密待遇：
            # 1. IP 必须在白名单内
            # 2. 且当前会话不能是 TEMP（如果是 TEMP 哪怕 IP 对了也要输密码）
            is_whitelist_user = (ALLOWED_IPS and ip in ALLOWED_IPS) and (current_auth_type != "TEMP")

            if is_whitelist_user:
                form_html = """
                <form action="/shutdown_execute" method="POST">
                    <p style="color: #10b981; font-weight: bold;">✅ 已识别为受信任的白名单设备</p>
                    <button type="submit" class="btn btn-danger" style="margin-top: 15px; width: 100%; padding: 12px;">🔌 确认物理关机</button>
                </form>
                """
            else:
                form_html = """
                <form action="/shutdown_execute" method="POST">
                    <p>请输入维护密码执行物理关机：</p>
                    <div style="margin: 15px 0;">
                        <input type="password" name="admin_pwd" placeholder="系统维护密码" required 
                               style="width:100%; padding:12px; font-size:1.1rem; text-align:center; border-radius:6px; border:1px solid #555; background:#222; color:#fff; outline:none;">
                    </div>
                    <button type="submit" class="btn btn-danger" style="margin-top: 10px; width: 100%; padding: 12px;">⚠️ 确认物理关机</button>
                </form>
                """
            
            content = self.read_html("shutdown.html")\
                        .replace("{{auth_content}}", form_html)\
                        .replace("{{auth_note}}", "警告：访客或临时授权设备需验证维护密码。<br>系统关机后所有服务将停止。")
            self.send_page(self.load_template(content, ip)) 

        #下两行替换成后面5行
        #elif path == '/admin':
        #    self.send_page(self.load_template(self.read_html("admin_choice.html"), ip))
        elif path == '/admin':
            # 如果已经登录，直接重定向到 PVE 看板，跳过选择页
            if auth.is_trusted(ip, sid, ua):
                self.send_page(self.load_template("<script>location.href='/admin/pve'</script>", ip))
            else:
                self.send_page(self.load_template(self.read_html("admin_choice.html"), ip))
        elif path == '/admin_login_temp':
            content = self.read_html("admin_login.html").replace("{{login_title}}", "临时终端授权").replace("{{login_desc}}", "1小时临时访问权限").replace("{{auth_mode}}", "temp").replace("{{password_field}}", "")
            self.send_page(self.load_template(content, ip))
        elif path == '/admin_login_perm':
            pwd_field = '<div style="margin: 20px 0;"><label style="display:block; text-align:left; font-size:0.8rem; color:#888;">管理员密钥</label><input type="password" name="admin_pwd" required style="width:100%; padding:12px; font-size:1.2rem; text-align:center;"></div>'
            content = self.read_html("admin_login.html").replace("{{login_title}}", "深度信任授权").replace("{{login_desc}}", "365天免验权限").replace("{{auth_mode}}", "perm").replace("{{password_field}}", pwd_field)
            self.send_page(self.load_template(content, ip))
        elif path == '/shutdown_confirm':
            content = self.read_html("shutdown.html").replace("{{auth_content}}", "请输入维护密码执行物理关机。").replace("{{auth_note}}", "警告：此操作不可逆。")
            self.send_page(self.load_template(content, ip))
        
        elif path == '/admin/pve': self.render_admin_pve()
        elif path == '/admin/vms': self.render_admin_vms()
        elif path == '/admin/nas': self.render_admin_nas()
        elif path == '/admin/sys': self.render_admin_sys()
        else: self.send_error(404)

    # ==========================================
    # 4. POST 路由 (包含 SSH 关机)
    # ==========================================
    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        ip = self.get_ip()
        sid = self.get_sid()
        ua = self.headers.get('User-Agent', 'Unknown')

        # [NAS SSH 物理关机接口]
        if path == '/api/nas_shutdown':
            if not auth.is_trusted(ip, sid, ua):
                self.send_error(403)
                return
            try:
                cmd = f"ssh -o StrictHostKeyChecking=no {NAS_USER}@{NAS_IP} 'poweroff'"
                subprocess.run(cmd, shell=True)
                system.write_log(f"[NAS指令] IP {ip} 触发了 {NAS_IP} 的物理关机。")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")
            except Exception as e:
                system.write_log(f"[NAS关机失败] {str(e)}")
                self.send_error(500)
            return

        content_length = int(self.headers.get('Content-Length', 0)) if self.headers.get('Content-Length') else 0
        post_data = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else ""
        params = urllib.parse.parse_qs(post_data)

        if path == '/admin_login_submit':
            auth_mode = params.get('auth_mode', ['temp'])[0]
            otp_token = params.get('otp_token', [''])[0]
            admin_pwd = params.get('admin_pwd', [''])[0]

            if not auth.verify_totp(otp_token):
                self.render_msg("❌ 验证码错误或已失效。", ip)
                return

            if auth_mode == 'perm' and admin_pwd != SHUTDOWN_PASSWORD:
                self.render_msg("❌ 密钥错误，深度信任请求被拒绝。", ip)
                return

            ## 【修复点】：传入 ip 变量，以便 auth.py 能将 IP 写入文件名
            #session_id = auth.create_session(ip, ua, is_temp=(auth_mode == 'temp'))
            #self.render_redirect("✅ 授权成功，欢迎回来。", ip, sid=session_id, target="/admin/pve")
            # 之前是 session_id = auth.create_session(ua, is_temp=...)
            # 现在改成传入 ip 变量：
            session_id = auth.create_session(ip, ua, is_temp=(auth_mode == 'temp'))
            self.render_redirect("✅ 授权成功，欢迎回来。", ip, sid=session_id, target="/admin/pve")

      
        elif path == '/shutdown_execute':
            admin_pwd = params.get('admin_pwd', [''])[0]
            current_auth_type = auth.get_session_type(ip, sid)
            
            # 免密条件：在白名单 IP 内，且不是临时会话
            can_skip_auth = (ALLOWED_IPS and ip in ALLOWED_IPS) and (current_auth_type != "TEMP")

            if can_skip_auth or (admin_pwd == SHUTDOWN_PASSWORD):
                system.graceful_shutdown(ip, ua)
                self.send_page(self.load_template(self.read_html("final_shutdown.html"), ip))
            else:
                self.render_msg("❌ 关机失败：访客临时授权设备必须提供有效的维护密码。", ip)

# ==========================================
# 5. 服务启动 (双线程架构)
# ==========================================
def run(server_class=ThreadingHTTPServer, handler_class=PVERouter, port=8081):
    # 线程1：清理过期的认证和会话文件
    threading.Thread(target=guest.auto_clean_loop, daemon=True).start()
    
    # 线程2：后台静默轮询 NAS 硬件状态
    threading.Thread(target=nas_polling_loop, daemon=True).start()
    
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    print(f"PVE Management Panel Service Started on port {port}")
    httpd.serve_forever()

if __name__ == '__main__':
    run()