import sys
import os
import threading
import time
from flask import Flask, request, jsonify, Response

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from scraper import Scraper
from storage import StationsStorage
from errors import StationNotFound
from validators import validate_date

app = Flask(__name__)

monitor_state = {
    "running": False,
    "status": "idle",
    "message": "",
    "found_trains": [],
    "last_check": None,
}
monitor_thread = None
stop_event = threading.Event()


def parse_time(t):
    h, m = map(int, t.strip().split(":"))
    return h * 60 + m


def resolve_station(name):
    for candidate in [f"{name} (Todas)", name, name.upper()]:
        try:
            return StationsStorage.get_station(candidate.upper())
        except StationNotFound:
            continue
    suggestions = StationsStorage.find_station(name)
    return None, suggestions


def monitor_loop(origin, dest, date, from_min, to_min):
    global monitor_state
    interval = 15
    while not stop_event.is_set():
        try:
            scraper = Scraper(origin, dest, date.date)
            trains = scraper.get_trainrides()
            found = [
                t.departure_time.strftime("%H:%M")
                for t in trains
                if t.available and from_min <= parse_time(t.departure_time.strftime("%H:%M")) <= to_min
            ]
            monitor_state["last_check"] = time.strftime("%H:%M:%S")
            if found:
                monitor_state["status"] = "found"
                monitor_state["found_trains"] = found
                monitor_state["running"] = False
                return
            else:
                monitor_state["status"] = "monitoring"
                monitor_state["message"] = "Sin plazas. Ultimo check: " + monitor_state["last_check"]
        except Exception as e:
            monitor_state["status"] = "error"
            monitor_state["message"] = str(e)
        stop_event.wait(interval)
    monitor_state["status"] = "stopped"
    monitor_state["running"] = False


HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Renfe Monitor</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Syne+Mono&family=Syne:wght@400;600;800&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #0a0a0a;
    --surface: #111111;
    --border: #222222;
    --amber: #f5a623;
    --amber-dim: #7a5212;
    --green: #22c55e;
    --red: #ef4444;
    --text: #e8e8e8;
    --muted: #555;
  }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Syne', sans-serif;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 2rem;
  }
  body::before {
    content: '';
    position: fixed;
    inset: 0;
    background: repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.08) 2px, rgba(0,0,0,0.08) 4px);
    pointer-events: none;
    z-index: 100;
  }
  .container { width: 100%; max-width: 520px; }
  header { margin-bottom: 2.5rem; }
  .logo { font-size: 0.7rem; letter-spacing: 0.3em; color: var(--amber); font-family: 'Syne Mono', monospace; margin-bottom: 0.5rem; }
  h1 { font-size: 2.4rem; font-weight: 800; line-height: 1; color: var(--text); }
  h1 span { color: var(--amber); }
  .card { background: var(--surface); border: 1px solid var(--border); padding: 2rem; margin-bottom: 1rem; }
  .field { margin-bottom: 1.4rem; }
  .field:last-child { margin-bottom: 0; }
  label { display: block; font-size: 0.65rem; letter-spacing: 0.2em; color: var(--muted); margin-bottom: 0.5rem; text-transform: uppercase; }
  input { width: 100%; background: var(--bg); border: 1px solid var(--border); color: var(--text); font-family: 'Syne Mono', monospace; font-size: 1rem; padding: 0.75rem 1rem; outline: none; transition: border-color 0.2s; }
  input:focus { border-color: var(--amber); }
  input::placeholder { color: var(--muted); }
  .row { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
  button { width: 100%; padding: 1rem; font-family: 'Syne', sans-serif; font-weight: 600; font-size: 0.85rem; letter-spacing: 0.15em; text-transform: uppercase; cursor: pointer; border: none; transition: all 0.2s; }
  #btn-start { background: var(--amber); color: #000; }
  #btn-start:hover { background: #ffbb44; }
  #btn-start:disabled { background: var(--amber-dim); color: #333; cursor: not-allowed; }
  #btn-stop { background: transparent; border: 1px solid var(--border); color: var(--muted); margin-top: 0.5rem; display: none; }
  #btn-stop:hover { border-color: var(--red); color: var(--red); }
  .status-box { border: 1px solid var(--border); padding: 1.5rem; display: none; margin-bottom: 1rem; }
  .status-box.visible { display: block; }
  .status-label { font-size: 0.65rem; letter-spacing: 0.2em; color: var(--muted); text-transform: uppercase; margin-bottom: 0.75rem; }
  .status-text { font-family: 'Syne Mono', monospace; font-size: 0.9rem; color: var(--text); display: flex; align-items: center; gap: 0.75rem; }
  .dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
  .dot.amber { background: var(--amber); animation: pulse 1.5s infinite; }
  .dot.green { background: var(--green); }
  .dot.red { background: var(--red); }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.2; } }
  .found-box { background: rgba(34,197,94,0.08); border: 1px solid var(--green); padding: 1.5rem; display: none; margin-bottom: 1rem; }
  .found-box.visible { display: block; }
  .found-title { font-size: 0.65rem; letter-spacing: 0.2em; color: var(--green); text-transform: uppercase; margin-bottom: 0.75rem; }
  .found-trains { font-family: 'Syne Mono', monospace; font-size: 1.4rem; font-weight: 600; color: var(--green); margin-bottom: 1rem; letter-spacing: 0.05em; }
  .renfe-link { display: block; text-align: center; padding: 0.85rem; background: var(--green); color: #000; font-weight: 700; font-size: 0.85rem; letter-spacing: 0.15em; text-transform: uppercase; text-decoration: none; transition: background 0.2s; }
  .renfe-link:hover { background: #4ade80; }
  .error-msg { font-family: 'Syne Mono', monospace; font-size: 0.8rem; color: var(--red); padding: 0.75rem 1rem; border: 1px solid var(--red); display: none; margin-bottom: 1rem; }
  .error-msg.visible { display: block; }
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="logo">// Sistema de monitorizacion</div>
    <h1>Renfe<span>.</span>Monitor</h1>
  </header>

  <div class="error-msg" id="error-msg"></div>

  <div class="found-box" id="found-box">
    <div class="found-title">Plaza disponible</div>
    <div class="found-trains" id="found-trains"></div>
    <a href="https://venta.renfe.com" target="_blank" class="renfe-link">Comprar ahora</a>
  </div>

  <div class="status-box" id="status-box">
    <div class="status-label">Estado</div>
    <div class="status-text">
      <div class="dot amber" id="status-dot"></div>
      <span id="status-text">Iniciando...</span>
    </div>
  </div>

  <div class="card">
    <div class="field">
      <label>Origen</label>
      <input type="text" id="origin" placeholder="A Coruna" />
    </div>
    <div class="field">
      <label>Destino</label>
      <input type="text" id="dest" placeholder="Madrid" />
    </div>
    <div class="field">
      <label>Fecha</label>
      <input type="text" id="date" placeholder="DD/MM/YYYY" />
    </div>
    <div class="field row">
      <div>
        <label>Hora minima</label>
        <input type="text" id="from_hour" placeholder="06:00" />
      </div>
      <div>
        <label>Hora maxima</label>
        <input type="text" id="to_hour" placeholder="22:00" />
      </div>
    </div>
  </div>

  <button id="btn-start">Iniciar monitorizacion</button>
  <button id="btn-stop">Detener</button>
</div>

<script>
var pollInterval = null;

function showError(msg) {
  var el = document.getElementById('error-msg');
  el.textContent = msg;
  el.classList.add('visible');
}

function hideError() {
  document.getElementById('error-msg').classList.remove('visible');
}

function setStatus(text, dotClass) {
  document.getElementById('status-text').textContent = text;
  var dot = document.getElementById('status-dot');
  dot.className = 'dot ' + dotClass;
  document.getElementById('status-box').classList.add('visible');
}

function pollStatus() {
  fetch('/status')
    .then(function(res) { return res.json(); })
    .then(function(data) {
      if (data.status === 'found') {
        clearInterval(pollInterval);
        document.getElementById('btn-start').disabled = false;
        document.getElementById('btn-stop').style.display = 'none';
        document.getElementById('status-box').classList.remove('visible');
        document.getElementById('found-trains').textContent = data.found_trains.join(' / ');
        document.getElementById('found-box').classList.add('visible');
      } else if (data.status === 'monitoring') {
        setStatus(data.message, 'amber');
      } else if (data.status === 'error') {
        setStatus('Error: ' + data.message, 'red');
      } else if (data.status === 'stopped') {
        clearInterval(pollInterval);
        setStatus('Detenido.', 'red');
      }
    });
}

document.getElementById('btn-start').addEventListener('click', function() {
  hideError();
  document.getElementById('found-box').classList.remove('visible');

  var origin    = document.getElementById('origin').value.trim();
  var dest      = document.getElementById('dest').value.trim();
  var date      = document.getElementById('date').value.trim();
  var from_hour = document.getElementById('from_hour').value.trim();
  var to_hour   = document.getElementById('to_hour').value.trim();

  if (!origin || !dest || !date || !from_hour || !to_hour) {
    showError('Rellena todos los campos.');
    return;
  }

  fetch('/start', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({origin: origin, dest: dest, date: date, from_hour: from_hour, to_hour: to_hour})
  })
  .then(function(res) { return res.json(); })
  .then(function(data) {
    if (!data.ok) {
      showError(data.error + (data.suggestions ? ' Prueba con: ' + data.suggestions.join(', ') : ''));
      return;
    }
    document.getElementById('btn-start').disabled = true;
    document.getElementById('btn-stop').style.display = 'block';
    setStatus('Monitorizando...', 'amber');
    pollInterval = setInterval(pollStatus, 3000);
  });
});

document.getElementById('btn-stop').addEventListener('click', function() {
  fetch('/stop', {method: 'POST'});
  clearInterval(pollInterval);
  document.getElementById('btn-start').disabled = false;
  document.getElementById('btn-stop').style.display = 'none';
  setStatus('Monitorizacion detenida.', 'red');
});
</script>
</body>
</html>"""


@app.route("/")
def index():
    return Response(HTML, mimetype='text/html')


@app.route("/start", methods=["POST"])
def start():
    global monitor_thread, stop_event, monitor_state

    if monitor_state["running"]:
        return jsonify({"ok": False, "error": "Ya hay una monitorizacion en curso."})

    data = request.json
    origin_input = data.get("origin", "")
    dest_input   = data.get("dest", "")
    date_input   = data.get("date", "")
    from_hour    = data.get("from_hour", "")
    to_hour      = data.get("to_hour", "")

    origin_result = resolve_station(origin_input)
    if isinstance(origin_result, tuple):
        _, suggestions = origin_result
        return jsonify({
            "ok": False,
            "error": "Estacion de origen no encontrada: '{}'.".format(origin_input),
            "suggestions": [s.title() for s in (suggestions or [])][:5]
        })

    dest_result = resolve_station(dest_input)
    if isinstance(dest_result, tuple):
        _, suggestions = dest_result
        return jsonify({
            "ok": False,
            "error": "Estacion de destino no encontrada: '{}'.".format(dest_input),
            "suggestions": [s.title() for s in (suggestions or [])][:5]
        })

    from datetime import datetime
    try:
        parsed_date = datetime.strptime(date_input, "%d/%m/%Y")
        date_result = type('obj', (object,), {'date': parsed_date})()
    except ValueError:
        return jsonify({"ok": False, "error": "Fecha no valida. Usa DD/MM/YYYY."})

    try:
        from_min = parse_time(from_hour)
        to_min   = parse_time(to_hour)
    except Exception:
        return jsonify({"ok": False, "error": "Formato de hora invalido. Usa HH:MM."})

    stop_event.clear()
    monitor_state.update({
        "running": True,
        "status": "monitoring",
        "message": "Iniciando...",
        "found_trains": [],
        "last_check": None,
    })

    monitor_thread = threading.Thread(
        target=monitor_loop,
        args=(origin_result, dest_result, date_result, from_min, to_min),
        daemon=True
    )
    monitor_thread.start()
    return jsonify({"ok": True})


@app.route("/stop", methods=["POST"])
def stop():
    stop_event.set()
    return jsonify({"ok": True})


@app.route("/status")
def status():
    return jsonify(monitor_state)


if __name__ == "__main__":
    print("Abre tu navegador en http://127.0.0.1:5000")
    app.run(debug=False, host='127.0.0.1', port=8080)