from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import urllib.request
import urllib.error
import os

API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
PORT    = int(os.getenv("PORT", 10000))

MODEL = "claude-3-haiku-20240307"
class Handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path in ["/", "/index.html"]:
            for name in ["centro_mando_jafero.html", "index.html"]:
                if os.path.exists(name):
                    with open(name, "r", encoding="utf-8") as f:
                        html = f.read()
                    self.send_response(200)
                    self.send_header("Content-type", "text/html; charset=utf-8")
                    self._cors()
                    self.end_headers()
                    self.wfile.write(html.encode("utf-8"))
                    return
            self.send_error(404)
            return
        self.send_error(404)

    def do_POST(self):
        if self.path != "/api":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length)

        try:
            data = json.loads(raw_body)
        except:
            self._json({"response": "JSON inválido"})
            return

        if not API_KEY:
            self._json({"response": "Falta API KEY"})
            return

        payload = {
            "model": MODEL,
            "max_tokens": 1500,
            "messages": data.get("messages", [])
        }

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-api-key": API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as res:
                result = json.loads(res.read().decode("utf-8"))
                respuesta = result["content"][0]["text"]

        except urllib.error.HTTPError as e:
            error = e.read().decode()
            respuesta = f"Error HTTP {e.code}: {error}"

        except Exception as e:
            respuesta = f"Error general: {str(e)}"

        self._json({"response": respuesta})

    def _json(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

if __name__ == "__main__":
    print("Servidor iniciado correctamente")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
