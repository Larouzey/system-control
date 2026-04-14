#!/usr/bin/python3
# -*- coding: utf-8 -*-

from http.server import ThreadingHTTPServer
import threading

from controller import guest
from server.router import PVERouter
from server.tasks import nas_polling_loop

HOST = "0.0.0.0"
PORT = 8081

def run():
    # 1. 启动后台任务线程
    threading.Thread(target=guest.auto_clean_loop, daemon=True).start()
    threading.Thread(target=nas_polling_loop, daemon=True).start()

    # 2. 启动 Web 服务器
    server = ThreadingHTTPServer((HOST, PORT), PVERouter)
    print(f"Server started on http://{HOST}:{PORT}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("Server stopped.")

if __name__ == "__main__":
    run()
