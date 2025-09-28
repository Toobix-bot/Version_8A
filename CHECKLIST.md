Kurz-Checklist: MCP / ChatGPT Connector (aktivierbar machen)

1) Server mit sichtbarer Tool-Registrierung starten

Im Verzeichnis `echo-bridge`:

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Start mit sichtbaren Logs
python run_mcp_http.py --host 0.0.0.0 --port 3337 --log-level debug
```

Erwartung im Log: eine Zeile wie `Registered tool: bridge01` oder eine Liste der registrierten Tools.


2) Tunnel exakt auf denselben Port

```bash
ngrok http 3337
```

Öffentliche URL (Beispiel): `https://tools-ready-surface-sur.trycloudflare.com/mcp`


3) SSE-Handshake schnell prüfen

```bash
curl -i -H "Accept: text/event-stream" \
  https://tools-ready-surface-sur.trycloudflare.com/mcp
```

Gut: `200 OK` + `Content-Type: text/event-stream` (stiller Stream ist okay). 
Nicht gut: `406` oder `text/html`/ngrok-Landing → Probe schlägt fehl.


4) Sicherstellen, dass `bridge01` wirklich registriert wird

Stell sicher, dass die Registrierung beim Import passiert (nicht nur in `if __name__ == "__main__":`). Beispiel-Pattern:

```python
import logging

try:
    from echo_bridge.mcp_setup import register_bridge01
    register_bridge01()
    logging.info("Registered tool: bridge01")
except Exception as e:
    logging.exception("Tool registration failed: %s", e)
```


5) Kleiner Health-Check (temporär)

```python
@app.get("/health")
def health():
    return {"ok": True, "tools": ["bridge01"]}
```

Prüfung:

```bash
curl -s https://tools-ready-surface-sur.trycloudflare.com/health
```

Siehst du `bridge01`? Wenn nein → Registrierung fehlt.


6) Aktivierung in ChatGPT

In ChatGPT Developer Tools → Custom Connector → URL: `https://<your-ngrok>.ngrok-free.dev/mcp`

Wenn weiterhin „nicht aktivierbar“: zurück zu Schritt 4 (Logs/Registrierung prüfen).


Mini-Troubleshooting (Symptom → Ursache)
- "Verbunden, nicht aktivierbar" → Tools fehlen in Handshake (Registrierung fehlt).
- `502 Bad Gateway` → Server läuft nicht auf getunneltem Port.
- `406 Not Acceptable` → fehlender SSE-Accept oder falsche Route.
- `text/html` (ngrok landing) → ngrok leitet nicht an deinen Prozess (falscher local addr oder Proxy nicht gebunden).


Was du mir schicken solltest:
1) 5–10 Zeilen Server-Log ab Start (die Stelle mit Tool-Registrierung)
2) Ausgabe von:

```bash
curl -i -H "Accept: text/event-stream" \
  https://tools-ready-surface-sur.trycloudflare.com/mcp
```

Dann sage ich dir genau, was fehlt und gebe die minimale Code-Fix-Anweisung.