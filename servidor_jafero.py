from http.server import BaseHTTPRequestHandler, HTTPServer
import json, urllib.request, urllib.error, os, re, time

API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
PORT      = int(os.getenv("PORT", 10000))
MODEL     = "claude-haiku-4-5-20251001"
WEB_SEARCH_AGENTS = {"atlas", "nexo"}

# Almacenamiento de landing pages en memoria + disco
PAGES     = {}          # slug -> html
PAGES_DIR = "pages"
os.makedirs(PAGES_DIR, exist_ok=True)

# Cargar páginas guardadas al arrancar
for fn in os.listdir(PAGES_DIR):
    if fn.endswith(".html"):
        slug = fn[:-5]
        with open(os.path.join(PAGES_DIR, fn), encoding="utf-8") as f:
            PAGES[slug] = f.read()
print(f"  Páginas cargadas: {len(PAGES)}")

def make_slug(html):
    m = re.search(r"<!--\s*slug:\s*/?([\w-]+)\s*-->", html, re.IGNORECASE)
    if m: return m.group(1)
    t = re.search(r"<title>([^<]+)</title>", html, re.IGNORECASE)
    if t:
        s = t.group(1).lower()
        s = re.sub(r"[^a-z0-9\s-]", "", s)
        s = re.sub(r"\s+", "-", s.strip())[:50]
        if s: return s
    return "landing-" + str(int(time.time()))

class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"  {args[0]} {args[1]}")

    def do_OPTIONS(self):
        self.send_response(200); self._cors(); self.end_headers()

    def do_GET(self):
        # Servir landing page publicada
        if self.path.startswith("/p/"):
            slug = self.path[3:].split("?")[0].rstrip("/")
            if slug not in PAGES:
                fp = os.path.join(PAGES_DIR, f"{slug}.html")
                if os.path.exists(fp):
                    PAGES[slug] = open(fp, encoding="utf-8").read()
            if slug in PAGES:
                b = PAGES[slug].encode("utf-8")
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                self._cors(); self.end_headers(); self.wfile.write(b)
                return
            self.send_error(404, "Página no encontrada"); return

        # Servir el frontend
        if self.path in ["/", "/index.html"]:
            for name in ["centro_mando_jafero.html", "mis_agentes_jafero.html", "index.html"]:
                if os.path.exists(name):
                    html = open(name, encoding="utf-8").read()
                    b = html.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(b)))
                    self._cors(); self.end_headers(); self.wfile.write(b)
                    return
            self.send_error(404); return
        self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)

        # ── Guardar landing page ─────────────────────────────
        if self.path == "/save-page":
            try:
                data  = json.loads(body)
                pg_html = data.get("html", "")
                slug  = data.get("slug", "") or make_slug(pg_html)
                slug  = re.sub(r"[^a-z0-9-]", "", slug.lower().replace(" ", "-"))[:60] or f"landing-{int(time.time())}"
                # Guardar en memoria y en disco
                PAGES[slug] = pg_html
                with open(os.path.join(PAGES_DIR, f"{slug}.html"), "w", encoding="utf-8") as f:
                    f.write(pg_html)
                print(f"  Página guardada: /p/{slug}")
                self._json({"ok": True, "slug": slug, "path": f"/p/{slug}"})
            except Exception as e:
                self._json({"ok": False, "error": str(e)})
            return

        # ── Llamada a la IA ──────────────────────────────────
        if self.path != "/api":
            self.send_error(404); return

        try:
            data = json.loads(body)
        except Exception:
            self._json({"response": "Error: JSON invalido"}); return

        if not API_KEY:
            self._json({"response": "Error: ANTHROPIC_API_KEY no configurada en Render"}); return

        agent_id   = data.get("agentId", "")
        use_search = agent_id in WEB_SEARCH_AGENTS

        payload = {
            "model"     : MODEL,
            "max_tokens": min(int(data.get("max_tokens", 4000)), 8000),
            "messages"  : data.get("messages", [])
        }
        if data.get("system"):
            payload["system"] = data["system"]
        if use_search:
            payload["tools"] = [{"type": "web_search_20250305", "name": "web_search"}]
            print(f"  Web search: {agent_id}")

        print(f"  -> modelo={MODEL} | agente={agent_id} | tokens={payload['max_tokens']}")

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

            respuesta = ""
            for block in result.get("content", []):
                if block.get("type") == "text":
                    respuesta += block.get("text", "")

            if not respuesta:
                respuesta = "Sin respuesta."

            # Limpiar markdown
            import re as _re
            respuesta = respuesta.strip()
            respuesta = _re.sub(r"^```html\s*", "", respuesta, flags=_re.IGNORECASE)
            respuesta = _re.sub(r"^```\s*", "", respuesta)
            respuesta = _re.sub(r"```\s*$", "", respuesta)
            if "<!DOCTYPE" in respuesta:
                respuesta = respuesta[respuesta.index("<!DOCTYPE"):]
            elif "<html" in respuesta.lower():
                respuesta = respuesta[respuesta.lower().index("<html"):]
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
        self.send_header("Content-type",   "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self._cors(); self.end_headers(); self.wfile.write(b)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

if __name__ == "__main__":
    print(f"\nJafero Backend | Puerto={PORT} | Modelo={MODEL} | Key={'OK' if API_KEY else 'NO CONFIGURADA'}")
    print(f"Landing pages en: /{PAGES_DIR}/")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
