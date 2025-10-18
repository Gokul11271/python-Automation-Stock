from flask import Flask, request, jsonify
from functools import wraps
from datetime import datetime
import csv, os, threading
from dotenv import load_dotenv
load_dotenv()  # loads .env if present

# API_TOKEN = os.getenv("VA_API_TOKEN", "change-me-to-a-strong-token")  # your secure token
API_TOKEN = "0yA790zy/Oeu30pNfQqvtYMauPJApRRBN2vB7ql6Wok="
APP_PORT = int(os.getenv("VA_PORT", 5000))

DATA_FILE = "virtual_account.json"
AUDIT_CSV = "audit_log.csv"

app = Flask(__name__)
lock = threading.Lock()

# initial account state
DEFAULT_STATE = {
    "login": "virtual-1001",
    "currency": "USD",
    "balance": 10000.0,
    "equity": 10000.0,
    "margin": 0.0,
    "timestamp": datetime.utcnow().isoformat()
}

def save_state(state):
    import json
    with open(DATA_FILE, "w") as f:
        json.dump(state, f, indent=2)

def load_state():
    import json
    if not os.path.exists(DATA_FILE):
        save_state(DEFAULT_STATE)
        return DEFAULT_STATE.copy()
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def append_audit(action, details, actor="local"):
    existed = os.path.exists(AUDIT_CSV)
    with open(AUDIT_CSV, "a", newline="") as f:
        writer = csv.writer(f)
        if not existed:
            writer.writerow(["timestamp","actor","action","details"])
        writer.writerow([datetime.utcnow().isoformat(), actor, action, details])

def require_token(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        token = request.headers.get("Authorization", "")
        if not token.startswith("Bearer "):
            return jsonify({"error":"missing bearer token"}), 401
        token = token.split(" ",1)[1]
        if token != API_TOKEN:
            return jsonify({"error":"invalid token"}), 403
        return func(*args, **kwargs)
    return wrapper

@app.route("/account", methods=["GET"])
@require_token
def get_account():
    state = load_state()
    return jsonify(state)

@app.route("/modify", methods=["POST"])
@require_token
def modify_account():
    """
    JSON payload examples:
    {"op":"add_balance","amount":500.0,"reason":"analysis add"}
    {"op":"set_balance","amount":12345.67,"reason":"reset for scenario"}
    {"op":"add_profit_per_trade","amount":50.0,"trades":3,"reason":"simulate profits"}
    """
    payload = request.get_json(force=True)
    if not payload or "op" not in payload:
        return jsonify({"error":"invalid payload"}), 400

    op = payload["op"]
    actor = request.headers.get("X-Actor", "analyst")
    reason = payload.get("reason", "")
    with lock:
        state = load_state()
        old_balance = float(state.get("balance", 0.0))
        old_equity = float(state.get("equity", 0.0))

        if op == "add_balance":
            amt = float(payload.get("amount", 0.0))
            state["balance"] = old_balance + amt
            state["equity"] = old_equity + amt
            action = f"add_balance {amt}"
        elif op == "set_balance":
            amt = float(payload.get("amount", 0.0))
            state["balance"] = amt
            # keep equity consistent unless provided
            state["equity"] = float(payload.get("equity", amt))
            action = f"set_balance {amt}"
        elif op == "add_profit_per_trade":
            amt = float(payload.get("amount", 0.0))
            trades = int(payload.get("trades", 1))
            total = amt * trades
            state["balance"] = old_balance + total
            state["equity"] = old_equity + total
            action = f"add_profit_per_trade {amt} x {trades} => {total}"
        else:
            return jsonify({"error":"unknown op"}), 400

        state["timestamp"] = datetime.utcnow().isoformat()
        save_state(state)
        append_audit(action, reason, actor)

    return jsonify({
        "status":"ok",
        "action": action,
        "old_balance": old_balance,
        "new_balance": state["balance"],
        "old_equity": old_equity,
        "new_equity": state["equity"],
        "timestamp": state["timestamp"]
    })

@app.route("/audit", methods=["GET"])
@require_token
def get_audit():
    # Return last N lines
    n = int(request.args.get("n", 200))
    if not os.path.exists(AUDIT_CSV):
        return jsonify([])
    with open(AUDIT_CSV, "r") as f:
        rows = list(csv.DictReader(f))
    return jsonify(rows[-n:])

if __name__ == "__main__":
    # ensure files exist
    if not os.path.exists(DATA_FILE):
        save_state(DEFAULT_STATE)
    if not os.path.exists(AUDIT_CSV):
        open(AUDIT_CSV, "w").close()
    print(f"Starting virtual account API on port {APP_PORT}. Use header Authorization: Bearer {API_TOKEN}")
    app.run(host="0.0.0.0", port=APP_PORT, debug=False)
