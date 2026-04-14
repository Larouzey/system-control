
from http.server import BaseHTTPRequestHandler
from server.handlers_get import handle_get
from server.handlers_post import handle_post

class PVERouter(BaseHTTPRequestHandler):
    # 接收到 GET 请求，把自己 (self) 传给外部的 GET 处理器
    def do_GET(self):
        handle_get(self)

    # 接收到 POST 请求，把自己 (self) 传给外部的 POST 处理器
    def do_POST(self):
        handle_post(self)
