#!/usr/bin/env python3
"""
투자 대시보드 서버
- 정적 파일 서빙 (index.html 등)
- /api/kis/* → https://openapi.koreainvestment.com:9443/* 프록시
  (브라우저 CORS / 포트 제한 우회)
"""
import http.server, urllib.request, urllib.parse, json, ssl, os, sys

PORT      = 8787
SERVE_DIR = os.path.dirname(os.path.abspath(__file__))
KIS_BASE  = "https://openapi.koreainvestment.com:9443"
PREFIX    = "/api/kis"

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
        kis_path = self.path[len(PREFIX):]          # /api/kis/oauth2/... → /oauth2/...
        kis_url  = KIS_BASE + kis_path

        # 클라이언트 헤더 그대로 전달
        fwd = {}
        for h in ["content-type", "authorization", "appkey",
                  "appsecret", "tr_id", "custtype"]:
            v = self.headers.get(h)
            if v:
                fwd[h] = v

        # POST body
        body = None
        if method == "POST":
            n = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(n) if n else None

        try:
            ctx = ssl.create_default_context()
            req = urllib.request.Request(kis_url, data=body,
                                         headers=fwd, method=method)
            with urllib.request.urlopen(req, context=ctx, timeout=10) as res:
                data = res.read()
                self._cors(res.status)
                self.send_header("Content-Type",
                                 res.headers.get("Content-Type", "application/json"))
                self.end_headers()
                self.wfile.write(data)
        except Exception as e:
            err = json.dumps({"error": str(e)}).encode()
            self._cors(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(err)

    # ── CORS 헤더 ─────────────────────────────────────────
    def _cors(self, status):
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers",
                         "Content-Type, Authorization, appkey, appsecret, tr_id, custtype")

    def log_message(self, fmt, *args):
        pass   # 로그 억제 (필요 시 주석 해제)

if __name__ == "__main__":
    os.chdir(SERVE_DIR)
    with http.server.HTTPServer(("", PORT), Handler) as srv:
        print(f"✅  대시보드 서버 실행 중 → http://localhost:{PORT}")
        print(f"   KIS 프록시: /api/kis/* → {KIS_BASE}/*")
        print("   종료: Ctrl+C\n")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\n서버 종료")
