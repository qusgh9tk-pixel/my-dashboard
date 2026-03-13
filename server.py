#!/usr/bin/env python3
"""
투자 대시보드 서버
- 정적 파일 서빙 (index.html 등)
- /api/kis/* → https://openapi.koreainvestment.com:9443/* 프록시
  (브라우저 CORS / 포트 제한 우회)
"""
import http.server, http.client, json, ssl, os, sys

PORT      = 8787
SERVE_DIR = os.path.dirname(os.path.abspath(__file__))
KIS_HOST  = "openapi.koreainvestment.com"
KIS_PORT  = 9443
PREFIX    = "/api/kis"

# KIS 요청 시 넘길 헤더 목록
FORWARD_HEADERS = [
    "content-type", "authorization",
    "appkey", "appsecret", "tr_id", "custtype"
]

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=SERVE_DIR, **kwargs)

    # ── OPTIONS (CORS preflight) ─────────────────────────
    def do_OPTIONS(self):
        self._cors(200)
        self.end_headers()

    # ── POST ─────────────────────────────────────────────
    def do_POST(self):
        if self.path.startswith(PREFIX):
            self._proxy("POST")
        else:
            self.send_error(404)

    # ── GET ──────────────────────────────────────────────
    def do_GET(self):
        if self.path.startswith(PREFIX):
            self._proxy("GET")
        else:
            super().do_GET()

    # ── 프록시 핵심 로직 ──────────────────────────────────
    def _proxy(self, method):
        kis_path = self.path[len(PREFIX):]  # /api/kis/... → /...

        # ① 요청 바디 읽기
        body = b""
        cl_str = self.headers.get("Content-Length")
        if cl_str:
            body = self.rfile.read(int(cl_str))
        elif method == "POST":
            # chunked transfer-encoding 처리
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
                    self.rfile.readline()  # CRLF
                body = b"".join(chunks)

        # ② 포워딩 헤더 구성
        fwd = {}
        for h in FORWARD_HEADERS:
            v = self.headers.get(h)
            if v:
                fwd[h] = v
        # Content-Length 는 실제 body 크기로 세팅
        if body:
            fwd["Content-Length"] = str(len(body))
        elif method == "POST":
            fwd["Content-Length"] = "0"

        sys.stderr.write(
            f"[KIS] {method} https://{KIS_HOST}:{KIS_PORT}{kis_path}\n"
            f"      headers={list(fwd.keys())}  body_len={len(body)}\n"
        )

        # ③ KIS 서버로 전송 (http.client — urllib 보다 직접적)
        try:
            ctx = ssl.create_default_context()
            conn = http.client.HTTPSConnection(
                KIS_HOST, KIS_PORT, context=ctx, timeout=15
            )
            conn.request(method, kis_path,
                         body=body if body else None,
                         headers=fwd)
            resp = conn.getresponse()
            data = resp.read()
            conn.close()

            ct = resp.getheader("Content-Type",
                                "application/json; charset=utf-8")
            sys.stderr.write(
                f"      → KIS {resp.status}  body={data[:200]}\n"
            )

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

    # ── CORS 헤더 ─────────────────────────────────────────
    def _cors(self, status):
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers",
                         "Content-Type, Authorization, "
                         "appkey, appsecret, tr_id, custtype")

    def log_message(self, fmt, *args):
        pass   # 액세스 로그 억제

if __name__ == "__main__":
    os.chdir(SERVE_DIR)
    with http.server.HTTPServer(("", PORT), Handler) as srv:
        print(f"✅  대시보드 서버 → http://localhost:{PORT}")
        print(f"   KIS 프록시: /api/kis/* → https://{KIS_HOST}:{KIS_PORT}/*")
        print("   종료: Ctrl+C\n")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\n서버 종료")
