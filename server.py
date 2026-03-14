#!/usr/bin/env python3
"""
투자 대시보드 서버
- 정적 파일 서빙 (index.html 등)
- /api/kis/*    → https://openapi.koreainvestment.com:9443/*    (실전투자)
- /api/kisvts/* → https://openapivts.koreainvestment.com:9443/* (모의투자)
  (브라우저 CORS / 포트 9443 우회)
"""
import http.server, http.client, json, ssl, os, sys

PORT      = 8787
SERVE_DIR = os.path.dirname(os.path.abspath(__file__))
KIS_PORT  = 9443

ROUTES = {
    "/api/kis":    "openapi.koreainvestment.com",
    "/api/kisvts": "openapivts.koreainvestment.com",
}

FORWARD_HEADERS = [
    "content-type", "authorization",
    "appkey", "appsecret", "tr_id", "custtype"
]

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=SERVE_DIR, **kwargs)

    def do_OPTIONS(self):
        self._cors(200); self.end_headers()

    def do_POST(self):
        info = self._match_route()
        if info:
            self._proxy("POST", *info)
        else:
            self.send_error(404)

    def do_GET(self):
        info = self._match_route()
        if info:
            self._proxy("GET", *info)
        else:
            super().do_GET()

    def _match_route(self):
        """경로 prefix 매칭 → (kis_host, kis_path) 반환"""
        for prefix, host in ROUTES.items():
            if self.path.startswith(prefix):
                return host, self.path[len(prefix):]
        return None

    def _proxy(self, method, kis_host, kis_path):
        # ① 바디 읽기
        body = b""
        cl_str = self.headers.get("Content-Length")
        if cl_str:
            body = self.rfile.read(int(cl_str))
        elif method == "POST":
            te = self.headers.get("Transfer-Encoding", "")
            if "chunked" in te.lower():
                chunks = []
                while True:
                    line = self.rfile.readline().strip()
                    if not line:
                        break
                    size = int(line, 16)
                    if size == 0:
                        break
                    chunks.append(self.rfile.read(size))
                    self.rfile.readline()
                body = b"".join(chunks)

        # ② 헤더 구성
        fwd = {}
        for h in FORWARD_HEADERS:
            v = self.headers.get(h)
            if v:
                fwd[h] = v
        fwd["Content-Length"] = str(len(body)) if body else "0"

        sys.stderr.write(
            f"[KIS] {method} https://{kis_host}:{KIS_PORT}{kis_path}\n"
            f"      headers={list(fwd.keys())}  body={body[:120]}\n"
        )

        # ③ KIS 서버로 전송
        try:
            ctx = ssl.create_default_context()
            conn = http.client.HTTPSConnection(
                kis_host, KIS_PORT, context=ctx, timeout=15
            )
            conn.request(method, kis_path,
                         body=body if body else None, headers=fwd)
            resp = conn.getresponse()
            data = resp.read()
            conn.close()

            sys.stderr.write(f"      → {resp.status}  {data[:300]}\n")

            ct = resp.getheader("Content-Type",
                                "application/json; charset=utf-8")
            self._cors(resp.status)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        except Exception as e:
            sys.stderr.write(f"[KIS PROXY ERROR] {e}\n")
            err = json.dumps({"error": str(e)}).encode("utf-8")
            self._cors(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)

    def _cors(self, status):
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers",
                         "Content-Type, Authorization, "
                         "appkey, appsecret, tr_id, custtype")

    def log_message(self, fmt, *args):
        pass

if __name__ == "__main__":
    os.chdir(SERVE_DIR)
    with http.server.HTTPServer(("", PORT), Handler) as srv:
        print(f"[OK] Dashboard server -> http://localhost:{PORT}")
        print(f"     /api/kis/*    -> openapi.koreainvestment.com:{KIS_PORT}")
        print(f"     /api/kisvts/* -> openapivts.koreainvestment.com:{KIS_PORT}")
        print("     Ctrl+C to stop\n")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\n서버 종료")
