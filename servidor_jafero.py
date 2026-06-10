from http.server import BaseHTTPRequestHandler, HTTPServer
import json, urllib.request, urllib.error, os

API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
PORT    = int(os.getenv("PORT", 10000))
MODEL   = "claude-haiku-4-5-20251001"

# Agentes que usan búsqueda web en tiempo real
WEB_SEARCH_AGENTS = {"atlas", "nexo", "nova"}

class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"  {args[0]} {args[1]}")

    def do_OPTIONS(self):
        self.send_response(200); self._cors(); self.end_headers()

    def do_GET(self):
        if self.path in ["/", "/index.html"]:
            for name in ["centro_mando_jafero.html", "mis_agentes_jafero.html", "index.html"]:
                if os.path.exists(name):
                    html = open(name, encoding="utf-8").read()
                    self.send_response(200)
                    self.send_header("Content-type", "text/html; charset=utf-8")
                    self._cors(); self.end_headers()
                    self.wfile.write(html.encode()); return
            self.send_error(404)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/api":
            self.send_error(404); return

        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)

        try:
            data = json.loads(body)
        except Exception:
            self._json({"response": "Error: JSON invalido"}); return

        if not API_KEY:
            self._json({"response": "Error: ANTHROPIC_API_KEY no configurada en Render"}); return

        agent_id  = data.get("agentId", "")
        use_search = agent_id in WEB_SEARCH_AGENTS

        payload = {
            "model"     : MODEL,
            "max_tokens": min(int(data.get("max_tokens", 4000)), 8000),
            "messages"  : data.get("messages", [])
        }
        if data.get("system"):
            payload["system"] = data["system"]

        # Activar web search para ATLAS y NEXO
        if use_search:
            payload["tools"] = [{"type": "web_search_20250305", "name": "web_search"}]
            print(f"  🔍 Web search activado para agente: {agent_id}")

        print(f"  -> modelo={MODEL} | agente={agent_id} | tokens={payload['max_tokens']} | search={use_search}")

        try:
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data    = json.dumps(payload).encode("utf-8"),
                headers = {
                    "x-api-key"         : API_KEY,
                    "anthropic-version" : "2023-06-01",
                    "content-type"      : "application/json"
                }
            )
            with urllib.request.urlopen(req, timeout=120) as res:
                result = json.loads(res.read())

            # Extraer texto de todos los bloques (puede haber tool_use + text)
            respuesta = ""
            for block in result.get("content", []):
                if block.get("type") == "text":
                    respuesta += block.get("text", "")

            if not respuesta:
                respuesta = "Sin respuesta de la IA."

            # Limpiar markdown code blocks que la IA puede añadir
            import re
            respuesta = respuesta.strip()
            respuesta = re.sub(r'^```html\s*', '', respuesta, flags=re.IGNORECASE)
            respuesta = re.sub(r'^```\s*', '', respuesta)
            respuesta = re.sub(r'```\s*$', '', respuesta)
            # Extraer solo desde DOCTYPE si hay texto previo
            if '<!DOCTYPE' in respuesta:
                respuesta = respuesta[respuesta.index('<!DOCTYPE'):]
            elif '<html' in respuesta.lower():
                respuesta = respuesta[respuesta.lower().index('<html'):]
            respuesta = respuesta.strip()

            print(f"  OK {len(respuesta)} chars")

        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="ignore")
            print(f"  ERROR {e.code}: {err[:200]}")
            respuesta = f"Error {e.code}: {err[:400]}"
        except Exception as e:
            print(f"  ERROR: {e}")
            respuesta = f"Error: {str(e)}"

        self._json({"response": respuesta})

    def _json(self, obj):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self._cors(); self.end_headers(); self.wfile.write(b)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

if __name__ == "__main__":
    print(f"\nJafero Backend | Puerto={PORT} | Modelo={MODEL} | Key={'OK' if API_KEY else 'NO CONFIGURADA'}")
    print(f"Web Search activado para: {WEB_SEARCH_AGENTS}\n")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
