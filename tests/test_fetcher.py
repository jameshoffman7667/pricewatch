import os
import sys
import threading
import http.server
import socketserver

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.fetcher import fetch_static  # noqa: E402

PAGE = b"""<html><body><div class="price">$123.45</div></body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, format, *args):
        pass


def _start_server():
    httpd = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, port


def test_fetch_static_gets_page():
    httpd, port = _start_server()
    try:
        result = fetch_static(f"http://127.0.0.1:{port}/product")
        assert result.status_code == 200
        assert b"$123.45" in result.html.encode() or "$123.45" in result.html
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    test_fetch_static_gets_page()
    print("PASS test_fetch_static_gets_page")
