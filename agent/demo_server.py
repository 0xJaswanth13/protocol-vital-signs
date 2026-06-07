#!/usr/bin/env python3
"""
demo_server.py — Local demo server for Protocol Vital Signs Agent
Serves a browser UI with Start Agent / Run Attack buttons.

Usage:
  python3 demo_server.py
  Then open: http://localhost:3333
"""

import http.server
import json
import os
import re
import subprocess
import sys
import threading
import time as _time
from pathlib import Path

PORT = 3333

BASE_DIR      = Path(__file__).parent.parent
AGENT_SCRIPT  = Path(__file__).parent / "agent.py"
ATTACK_SCRIPT = Path(__file__).parent / "attack.py"

agent_proc    = None
agent_lock    = threading.Lock()
agent_output  = []
report_history = []     # list of dicts, newest last
MAX_LOG_LINES  = 60
MAX_HISTORY    = 5

# Pending report being assembled from live log lines
_pending = {}

def _parse_log_line(line):
    """Update _pending report from each log line; commit when a check cycle ends."""
    global _pending, report_history

    if "VITAL SIGNS CHECK #" in line:
        _pending = {"timestamp": int(_time.time()), "overallRisk": "—",
                    "tvlStatus": "—", "adminStatus": "—", "liquidityStatus": "—",
                    "txStatus": "—", "upgradeStatus": "—", "aiDiagnosis": "—"}
        return

    if not _pending:
        return

    if "OVERALL RISK:" in line:
        m = re.search(r"OVERALL RISK:\s*(\w+)", line)
        if m: _pending["overallRisk"] = m.group(1)

    if "TVL:" in line and "|" in line and "VLT" in line and "Liquidity" not in line:
        m = re.search(r"\|\s*(\w+)\s*$", line.strip())
        if m: _pending["tvlStatus"] = m.group(1)

    if "Admin:" in line and "Liquidity:" in line:
        m1 = re.search(r"Admin:\s*(\w+)", line)
        m2 = re.search(r"Liquidity:.*\|\s*(\w+)", line)
        if m1: _pending["adminStatus"] = m1.group(1)
        if m2: _pending["liquidityStatus"] = m2.group(1)

    if "TX:" in line and "Upgrades:" in line:
        m1 = re.search(r"TX:\s*(\w+)", line)
        m2 = re.search(r"Upgrades:\s*(\w+)", line)
        if m1: _pending["txStatus"] = m1.group(1)
        if m2: _pending["upgradeStatus"] = m2.group(1)

    if ("Recommended:" in line or "FALLBACK:" in line) and _pending.get("aiDiagnosis") == "—":
        _pending["aiDiagnosis"] = re.sub(r"^\s*", "", line).strip()

    # Commit report when the "Next check in" line appears
    if "Next check in" in line and _pending.get("overallRisk") != "—":
        report_history.append(dict(_pending))
        if len(report_history) > MAX_HISTORY:
            report_history.pop(0)
        _pending = {}


def log_agent_output(proc):
    for line in iter(proc.stdout.readline, ''):
        line = line.rstrip()
        if line:
            with agent_lock:
                agent_output.append(line)
                if len(agent_output) > MAX_LOG_LINES:
                    agent_output.pop(0)
                _parse_log_line(line)
    with agent_lock:
        agent_output.append("[Agent process ended]")


def agent_is_running():
    global agent_proc
    return agent_proc is not None and agent_proc.poll() is None


# ── HTTP Handler ───────────────────────────────────────────────────────────────

class DemoHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass

    def send_json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send_html(DASHBOARD_HTML)
        elif self.path == "/api/status":
            with agent_lock:
                lines   = list(agent_output)
                history = list(report_history)
            self.send_json(200, {"agent_running": agent_is_running(), "log": lines, "history": history})
        elif self.path == "/api/token-status":
            try:
                data = get_token_status()
                self.send_json(200, data)
            except Exception as e:
                self.send_json(500, {"error": str(e)})
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        global agent_proc, agent_output, report_history, _pending

        if self.path == "/api/agent/start":
            if agent_is_running():
                self.send_json(200, {"ok": True, "message": "Agent already running"})
                return
            try:
                agent_output = ["[Starting Protocol Vital Signs Agent...]"]
                proc = subprocess.Popen(
                    [sys.executable, "-u", str(AGENT_SCRIPT)],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1,
                    env={**os.environ, "PYTHONUNBUFFERED": "1"},
                    cwd=str(BASE_DIR)
                )
                with agent_lock:
                    agent_proc = proc
                threading.Thread(target=log_agent_output, args=(proc,), daemon=True).start()
                self.send_json(200, {"ok": True, "message": "Agent started"})
            except Exception as e:
                self.send_json(500, {"ok": False, "error": str(e)})

        elif self.path == "/api/agent/stop":
            with agent_lock:
                proc = agent_proc
            if proc and proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=5)
            with agent_lock:
                agent_output.append("[Agent stopped by user]")
            self.send_json(200, {"ok": True, "message": "Agent stopped"})

        elif self.path == "/api/attack/run":
            if not os.path.exists(ATTACK_SCRIPT):
                self.send_json(404, {"ok": False, "error": "attack.py not found"})
                return
            try:
                proc = subprocess.Popen(
                    [sys.executable, "-u", str(ATTACK_SCRIPT)],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1,
                    env={**os.environ, "PYTHONUNBUFFERED": "1"},
                    cwd=str(BASE_DIR)
                )
                def read_attack(p):
                    for line in iter(p.stdout.readline, ''):
                        line = line.rstrip()
                        if line:
                            with agent_lock:
                                agent_output.append("[ATTACK] " + line)
                                if len(agent_output) > MAX_LOG_LINES:
                                    agent_output.pop(0)
                threading.Thread(target=read_attack, args=(proc,), daemon=True).start()
                self.send_json(200, {"ok": True, "message": "Attack started"})
            except Exception as e:
                self.send_json(500, {"ok": False, "error": str(e)})

        elif self.path == "/api/refill":
            try:
                # Stop agent first so its stale liquidity/TVL history is cleared
                with agent_lock:
                    proc = agent_proc
                if proc and proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=5)
                with agent_lock:
                    agent_output.append("[Agent stopped for refill — restart it after]")
                    report_history = []
                    _pending = {}
                msg = run_refill()
                self.send_json(200, {"ok": True, "message": msg})
            except Exception as e:
                self.send_json(500, {"ok": False, "error": str(e)})

        elif self.path == "/api/set-tvl":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body   = json.loads(self.rfile.read(length))
                amount = int(body.get("amount", 0))
                if amount <= 0 or amount > 100000:
                    self.send_json(400, {"ok": False, "error": "Amount must be 1–100000"})
                    return
                msg = deposit_tvl(amount)
                self.send_json(200, {"ok": True, "message": msg})
            except Exception as e:
                self.send_json(500, {"ok": False, "error": str(e)})

        elif self.path == "/api/full-reset":
            try:
                msg = full_reset()
                self.send_json(200, {"ok": True, "message": msg})
            except Exception as e:
                self.send_json(500, {"ok": False, "error": str(e)})

        else:
            self.send_json(404, {"error": "not found"})


# ── Blockchain helpers ─────────────────────────────────────────────────────────

def _load_web3():
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
    from web3 import Web3
    import json as _json
    w3 = Web3(Web3.HTTPProvider(os.getenv("MONAD_RPC_URL")))
    def abi(n):
        with open(BASE_DIR / "out" / f"{n}.sol" / f"{n}.json") as f:
            return _json.load(f)["abi"]
    token    = w3.eth.contract(address=Web3.to_checksum_address(os.getenv("MOCK_TOKEN_ADDRESS")),    abi=abi("MockToken"))
    protocol = w3.eth.contract(address=Web3.to_checksum_address(os.getenv("MOCK_PROTOCOL_ADDRESS")), abi=abi("MockProtocol"))
    return w3, token, protocol


def get_token_status():
    from web3 import Web3
    w3, token, protocol = _load_web3()
    backup = Web3.to_checksum_address(os.getenv("BACKUP_WALLET"))
    D = 10**18
    return {
        "protocol_tvl":       protocol.functions.getTVL().call() // D,
        "protocol_liquidity": protocol.functions.getLiquidity().call() // D,
        "backup_balance":     token.functions.balanceOf(backup).call() // D,
        "backup_wallet":      backup,
    }


def deposit_tvl(amount_vlt):
    from web3 import Web3
    w3, token, protocol = _load_web3()
    deployer = w3.eth.account.from_key(os.getenv("PRIVATE_KEY"))
    protocol_addr = Web3.to_checksum_address(os.getenv("MOCK_PROTOCOL_ADDRESS"))
    amt = amount_vlt * 10**18

    def send(fn, label):
        nonce = w3.eth.get_transaction_count(deployer.address)
        tx = fn.build_transaction({"from": deployer.address, "nonce": nonce,
                                   "gas": 300000, "gasPrice": w3.eth.gas_price, "chainId": 10143})
        signed = w3.eth.account.sign_transaction(tx, os.getenv("PRIVATE_KEY"))
        txh = w3.eth.send_raw_transaction(signed.rawTransaction)
        w3.eth.wait_for_transaction_receipt(txh, timeout=60)

    send(token.functions.mint(deployer.address, amt), "mint")
    send(token.functions.approve(protocol_addr, amt), "approve")
    send(protocol.functions.deposit(amt), "deposit")
    new_tvl = protocol.functions.getTVL().call() // 10**18
    return f"Deposited {amount_vlt} VLT. New TVL: {new_tvl} VLT"


def run_refill():
    from web3 import Web3
    w3, token, protocol = _load_web3()
    deployer      = w3.eth.account.from_key(os.getenv("PRIVATE_KEY"))
    agent_acct    = w3.eth.account.from_key(os.getenv("AGENT_PRIVATE_KEY"))
    protocol_addr = Web3.to_checksum_address(os.getenv("MOCK_PROTOCOL_ADDRESS"))
    REFILL = 1000 * 10**18
    steps  = []

    def send(acct, pk, fn, label, gas=300000):
        nonce  = w3.eth.get_transaction_count(acct.address)
        tx     = fn.build_transaction({
            "from": acct.address, "nonce": nonce,
            "gas": gas, "gasPrice": w3.eth.gas_price, "chainId": 10143
        })
        signed = w3.eth.account.sign_transaction(tx, pk)
        txh    = w3.eth.send_raw_transaction(signed.rawTransaction)
        r      = w3.eth.wait_for_transaction_receipt(txh, timeout=60)
        ok     = "OK" if r["status"] == 1 else "FAIL"
        steps.append(f"[{ok}] {label}")
        return r["status"] == 1

    # Mint and deposit 1000 VLT per user into MockProtocol
    send(deployer, os.getenv("PRIVATE_KEY"),
         token.functions.mint(deployer.address, REFILL), "Mint 1000 VLT to deployer")
    send(deployer, os.getenv("PRIVATE_KEY"),
         token.functions.approve(protocol_addr, REFILL), "Approve MockProtocol (deployer)")
    send(deployer, os.getenv("PRIVATE_KEY"),
         protocol.functions.deposit(REFILL), "Deposit 1000 VLT (User 1)")

    send(deployer, os.getenv("PRIVATE_KEY"),
         token.functions.mint(agent_acct.address, REFILL), "Mint 1000 VLT to User 2")
    send(agent_acct, os.getenv("AGENT_PRIVATE_KEY"),
         token.functions.approve(protocol_addr, REFILL), "Approve MockProtocol (User 2)")
    send(agent_acct, os.getenv("AGENT_PRIVATE_KEY"),
         protocol.functions.deposit(REFILL), "Deposit 1000 VLT (User 2)")

    # Add liquidity back
    send(deployer, os.getenv("PRIVATE_KEY"),
         token.functions.mint(deployer.address, 5000 * 10**18), "Mint 5000 VLT for liquidity")
    send(deployer, os.getenv("PRIVATE_KEY"),
         token.functions.approve(protocol_addr, 5000 * 10**18), "Approve MockProtocol (liquidity)")
    send(deployer, os.getenv("PRIVATE_KEY"),
         protocol.functions.addLiquidity(5000 * 10**18), "Add 5000 VLT liquidity")

    return " | ".join(steps)


def full_reset():
    """Drain all TVL and liquidity from MockProtocol to zero and stop the agent."""
    from web3 import Web3
    w3, token, protocol = _load_web3()
    deployer = w3.eth.account.from_key(os.getenv("PRIVATE_KEY"))
    D        = 10**18
    steps    = []

    def send(acct, pk, fn, label, gas=300000):
        nonce  = w3.eth.get_transaction_count(acct.address)
        tx     = fn.build_transaction({
            "from": acct.address, "nonce": nonce,
            "gas": gas, "gasPrice": w3.eth.gas_price, "chainId": 10143
        })
        signed = w3.eth.account.sign_transaction(tx, pk)
        txh    = w3.eth.send_raw_transaction(signed.rawTransaction)
        r      = w3.eth.wait_for_transaction_receipt(txh, timeout=60)
        ok     = "OK" if r["status"] == 1 else "FAIL"
        steps.append(f"[{ok}] {label}")
        return r["status"] == 1

    # Stop agent
    global agent_proc
    with agent_lock:
        proc = agent_proc
    if proc and proc.poll() is None:
        proc.terminate()
        proc.wait(timeout=5)
        with agent_lock:
            agent_output.append("[Agent stopped for full reset]")

    # Drain TVL back to deployer
    tvl = protocol.functions.getTVL().call()
    if tvl > 0:
        drain_addr = Web3.to_checksum_address(deployer.address)
        send(deployer, os.getenv("PRIVATE_KEY"),
             protocol.functions.adminTransferFunds(drain_addr, tvl),
             f"Drain TVL ({tvl//D} VLT)")

    # Drain liquidity
    liq = protocol.functions.getLiquidity().call()
    if liq > 0:
        send(deployer, os.getenv("PRIVATE_KEY"),
             protocol.functions.removeLiquidity(liq),
             f"Drain liquidity ({liq//D} VLT)")

    return "Full reset done. MockProtocol=0. " + " | ".join(steps)


# ── Dashboard HTML — Light Theme ───────────────────────────────────────────────

DASHBOARD_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>Protocol Vital Signs Agent — Monad</title>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/ethers/6.7.0/ethers.umd.min.js"></script>
  <style>
    *{margin:0;padding:0;box-sizing:border-box}
    body{background:#f0f2f5;color:#1a1a2e;font-family:'Segoe UI',system-ui,sans-serif;min-height:100vh}

    /* ── Header ── */
    header{
      background:#fff;border-bottom:1px solid #e8e8e8;
      padding:14px 28px;display:flex;justify-content:space-between;align-items:center;
      box-shadow:0 2px 8px rgba(0,0,0,.06)
    }
    .logo{display:flex;align-items:center;gap:12px}
    .logo-icon{
      width:40px;height:40px;background:linear-gradient(135deg,#836EF9,#6c3ff5);
      border-radius:10px;display:flex;align-items:center;justify-content:center;
      font-size:20px;font-weight:900;color:#fff;box-shadow:0 4px 12px rgba(131,110,249,.3)
    }
    .logo-text h1{font-size:17px;font-weight:700;color:#1a1a2e}
    .logo-text p{font-size:12px;color:#836EF9;margin-top:2px;font-weight:500}
    .header-right{font-size:12px;color:#888;text-align:right}
    .header-right span{color:#555;display:block;margin-top:3px}

    /* ── Controls Bar ── */
    .controls{
      background:#fff;border-bottom:3px solid #836EF9;
      padding:12px 28px;display:flex;align-items:center;gap:12px;flex-wrap:wrap;
      box-shadow:0 2px 6px rgba(0,0,0,.04)
    }
    .controls-label{
      font-size:10px;letter-spacing:2px;text-transform:uppercase;
      color:#836EF9;font-weight:700;margin-right:6px
    }
    .btn{
      padding:9px 22px;border-radius:8px;border:none;font-size:13px;
      font-weight:700;cursor:pointer;letter-spacing:.3px;transition:all .18s;
      box-shadow:0 2px 6px rgba(0,0,0,.1)
    }
    .btn-start{background:#16a34a;color:#fff}
    .btn-start:hover:not(:disabled){background:#15803d;box-shadow:0 4px 12px rgba(22,163,74,.3)}
    .btn-stop{background:#fff;color:#888;border:1.5px solid #ddd}
    .btn-stop:hover:not(:disabled){background:#f5f5f5;color:#555}
    .btn-attack{background:#dc2626;color:#fff}
    .btn-attack:hover:not(:disabled){background:#b91c1c;box-shadow:0 4px 12px rgba(220,38,38,.3)}
    .btn:disabled{opacity:.35;cursor:not-allowed;box-shadow:none}
    .agent-status{display:flex;align-items:center;gap:8px;font-size:13px;margin-left:auto;font-weight:600}
    .status-dot{width:9px;height:9px;border-radius:50%;background:#ccc}
    .status-dot.running{background:#16a34a;animation:pulse-dot 2s infinite}
    @keyframes pulse-dot{0%,100%{box-shadow:0 0 0 0 rgba(22,163,74,.4)}50%{box-shadow:0 0 0 5px rgba(22,163,74,0)}}

    /* ── Risk Banner ── */
    #risk-banner{
      padding:28px 32px;text-align:center;
      transition:all .5s ease;border-bottom:4px solid #e0e0e0
    }
    #risk-banner.loading  {background:#f8f9fa;border-bottom-color:#ddd}
    #risk-banner.HEALTHY  {background:linear-gradient(135deg,#dcfce7,#bbf7d0);border-bottom-color:#16a34a}
    #risk-banner.WARNING  {background:linear-gradient(135deg,#fef9c3,#fde68a);border-bottom-color:#ca8a04}
    #risk-banner.CRITICAL {background:linear-gradient(135deg,#ffedd5,#fed7aa);border-bottom-color:#ea580c}
    #risk-banner.EMERGENCY{background:linear-gradient(135deg,#fee2e2,#fecaca);border-bottom-color:#dc2626;animation:pulse-banner 1.4s infinite}
    @keyframes pulse-banner{0%,100%{opacity:1}50%{opacity:.85}}

    .risk-label{font-size:11px;letter-spacing:3px;text-transform:uppercase;color:rgba(0,0,0,.4);margin-bottom:8px}
    #risk-level-text{font-size:48px;font-weight:900;letter-spacing:6px;text-transform:uppercase;transition:color .4s}
    #risk-subtitle{font-size:14px;color:rgba(0,0,0,.5);margin-top:8px;font-weight:500}

    /* ── Main layout ── */
    main{max-width:1200px;margin:0 auto;padding:24px;display:grid;grid-template-columns:1fr 320px;gap:20px}
    .left-col{min-width:0}
    @media(max-width:960px){main{grid-template-columns:1fr}}

    .section-title{font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#888;margin-bottom:12px;font-weight:700}

    /* ── Vital Signs ── */
    .vitals-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:20px}
    @media(max-width:860px){.vitals-grid{grid-template-columns:repeat(2,1fr)}}

    .vital-card{
      background:#fff;border:2px solid #e8e8e8;border-radius:12px;
      padding:20px 12px;text-align:center;
      transition:all .25s;box-shadow:0 2px 6px rgba(0,0,0,.05)
    }
    .vital-card.NORMAL  {border-color:#16a34a;box-shadow:0 4px 14px rgba(22,163,74,.12)}
    .vital-card.WARNING {border-color:#ca8a04;box-shadow:0 4px 14px rgba(202,138,4,.12)}
    .vital-card.CRITICAL{border-color:#ea580c;box-shadow:0 4px 14px rgba(234,88,12,.15)}
    .vital-card.ALERT   {border-color:#d97706;box-shadow:0 4px 14px rgba(217,119,6,.12)}

    .vital-icon{font-size:28px;margin-bottom:8px}
    .vital-name{font-size:10px;color:#999;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;font-weight:600}
    .vital-badge{display:inline-block;padding:4px 12px;border-radius:20px;font-size:11px;font-weight:800;letter-spacing:.5px}
    .badge-NORMAL  {background:#dcfce7;color:#15803d}
    .badge-WARNING {background:#fef9c3;color:#a16207}
    .badge-CRITICAL{background:#ffedd5;color:#c2410c}
    .badge-ALERT   {background:#fef3c7;color:#b45309}
    .badge-UNKNOWN {background:#f3f4f6;color:#9ca3af}

    /* ── AI Diagnosis ── */
    .diagnosis-box{
      background:#fff;border:2px solid #836EF9;border-radius:12px;
      padding:20px;margin-bottom:20px;box-shadow:0 4px 14px rgba(131,110,249,.1)
    }
    .diagnosis-label{
      font-size:11px;letter-spacing:2px;text-transform:uppercase;
      color:#836EF9;margin-bottom:12px;display:flex;align-items:center;gap:8px;font-weight:700
    }
    .ai-dot{width:7px;height:7px;border-radius:50%;background:#836EF9;animation:blink 2s infinite}
    #diagnosis-text{font-size:14px;color:#374151;line-height:1.75;font-family:'Courier New',monospace}

    /* ── History Table ── */
    .history-box{
      background:#fff;border:1px solid #e8e8e8;border-radius:12px;
      overflow:hidden;margin-bottom:20px;box-shadow:0 2px 6px rgba(0,0,0,.05)
    }
    .history-header{
      padding:13px 18px;background:#f9fafb;border-bottom:1px solid #e8e8e8;
      font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#888;font-weight:700
    }
    table{width:100%;border-collapse:collapse}
    th{text-align:left;padding:10px 16px;font-size:11px;color:#9ca3af;text-transform:uppercase;letter-spacing:1px;background:#f9fafb;border-bottom:1px solid #f0f0f0}
    td{padding:12px 16px;font-size:13px;border-bottom:1px solid #f5f5f5;color:#374151;vertical-align:middle}
    tr:last-child td{border-bottom:none}
    tr:hover td{background:#fafafa}
    tr.row-HEALTHY   td:first-child{border-left:4px solid #16a34a;padding-left:12px}
    tr.row-WARNING   td:first-child{border-left:4px solid #ca8a04;padding-left:12px}
    tr.row-CRITICAL  td:first-child{border-left:4px solid #ea580c;padding-left:12px}
    tr.row-EMERGENCY td:first-child{border-left:4px solid #dc2626;padding-left:12px}

    .tbadge{display:inline-block;padding:3px 9px;border-radius:5px;font-size:11px;font-weight:800}
    .tb-HEALTHY  {background:#dcfce7;color:#15803d}
    .tb-WARNING  {background:#fef9c3;color:#a16207}
    .tb-CRITICAL {background:#ffedd5;color:#c2410c}
    .tb-EMERGENCY{background:#fee2e2;color:#b91c1c}
    .no-data{text-align:center;padding:32px;color:#bbb;font-size:14px}

    /* ── Log Panel ── */
    .log-panel{
      background:#fff;border:1px solid #e8e8e8;border-radius:12px;
      overflow:hidden;box-shadow:0 2px 6px rgba(0,0,0,.05)
    }
    .log-header{
      padding:12px 16px;background:#f9fafb;border-bottom:1px solid #e8e8e8;
      font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#888;
      display:flex;justify-content:space-between;align-items:center;font-weight:700
    }
    #log-lines{
      height:380px;overflow-y:auto;padding:12px;
      font-family:'Courier New',monospace;font-size:11.5px;line-height:1.65;
      background:#1e1e2e;color:#9ca3af
    }
    #log-lines .log-ok    {color:#4ade80}
    #log-lines .log-warn  {color:#facc15}
    #log-lines .log-err   {color:#f87171}
    #log-lines .log-attack{color:#f472b6;font-weight:700}
    #log-lines .log-chain {color:#a78bfa}
    #log-lines .log-dim   {color:#6b7280}

    /* ── Footer ── */
    footer{
      border-top:1px solid #e8e8e8;padding:16px 28px;text-align:center;
      font-size:12px;color:#aaa;background:#fff
    }
    footer a{color:#836EF9;text-decoration:none;font-weight:600}

    /* ── Token Flow Panel ── */
    .flow-panel{
      background:#fff;border:1px solid #e8e8e8;border-radius:12px;
      padding:20px;margin-bottom:20px;box-shadow:0 2px 6px rgba(0,0,0,.05)
    }
    .flow-grid{display:grid;grid-template-columns:1fr 32px 1fr 32px 1fr;gap:0;align-items:center;margin-top:12px}
    .flow-box{
      background:#f9fafb;border:2px solid #e8e8e8;border-radius:10px;
      padding:14px 10px;text-align:center;transition:all .3s
    }
    .flow-box.highlight{border-color:#836EF9;box-shadow:0 0 12px rgba(131,110,249,.15)}
    .flow-box.safe     {border-color:#16a34a;box-shadow:0 0 12px rgba(22,163,74,.12)}
    .flow-box.danger   {border-color:#ea580c;box-shadow:0 0 12px rgba(234,88,12,.12)}
    .flow-box-icon{font-size:22px;margin-bottom:6px}
    .flow-box-label{font-size:10px;color:#999;text-transform:uppercase;letter-spacing:1px;font-weight:700;margin-bottom:6px}
    .flow-box-value{font-size:20px;font-weight:900;color:#1a1a2e}
    .flow-box-sub{font-size:11px;color:#aaa;margin-top:4px}
    .flow-arrow{text-align:center;font-size:20px;color:#ccc}
    .flow-arrow.active{color:#836EF9}
    .flow-status{
      display:flex;align-items:center;gap:8px;margin-top:14px;
      padding:10px 14px;background:#f9fafb;border-radius:8px;font-size:13px
    }
    .flow-dot{width:8px;height:8px;border-radius:50%;background:#ccc;flex-shrink:0}
    .flow-dot.ok  {background:#16a34a}
    .flow-dot.warn{background:#ca8a04}
    .flow-dot.bad {background:#dc2626;animation:blink 1s infinite}

    .btn-refill{background:#836EF9;color:#fff}
    .btn-refill:hover:not(:disabled){background:#6c3ff5;box-shadow:0 4px 12px rgba(131,110,249,.35)}
    .btn-full-reset{background:#fff;color:#dc2626;border:1.5px solid #dc2626}
    .btn-full-reset:hover:not(:disabled){background:#fef2f2}

    /* TVL input */
    .tvl-input-row{display:flex;gap:6px;margin-top:10px;align-items:center}
    .tvl-input{
      flex:1;padding:6px 10px;border:1.5px solid #e0e0e0;border-radius:7px;
      font-size:13px;font-weight:600;color:#1a1a2e;background:#fff;
      text-align:center;outline:none;
    }
    .tvl-input:focus{border-color:#836EF9}
    .btn-tvl{
      padding:6px 12px;background:#836EF9;color:#fff;border:none;
      border-radius:7px;font-size:12px;font-weight:700;cursor:pointer;
      white-space:nowrap;transition:background .2s
    }
    .btn-tvl:hover:not(:disabled){background:#6c3ff5}
    .btn-tvl:disabled{opacity:.4;cursor:not-allowed}

    .live-dot{
      display:inline-block;width:7px;height:7px;border-radius:50%;
      background:#836EF9;animation:blink 2s infinite;margin-right:5px;vertical-align:middle
    }
    @keyframes blink{0%,100%{opacity:1}50%{opacity:.2}}

    .toast{
      position:fixed;bottom:24px;right:24px;background:#1a1a2e;color:#fff;
      padding:12px 20px;border-radius:10px;font-size:13px;font-weight:600;
      z-index:999;opacity:0;transform:translateY(8px);transition:all .3s;
      box-shadow:0 8px 24px rgba(0,0,0,.2)
    }
    .toast.show{opacity:1;transform:translateY(0)}
  </style>
</head>
<body>

<!-- Header -->
<header>
  <div class="logo">
    <div class="logo-icon">+</div>
    <div class="logo-text">
      <h1>Protocol Vital Signs Agent</h1>
      <p>Powered by Monad + OpenAI gpt-4o-mini</p>
    </div>
  </div>
  <div class="header-right">
    <span class="live-dot"></span>Live on Monad Testnet
    <span id="last-updated-time">Connecting...</span>
  </div>
</header>

<!-- Controls -->
<div class="controls">
  <span class="controls-label">Demo Controls</span>
  <button class="btn btn-start"  id="btn-start"  onclick="startAgent()">&#9654; Start Agent</button>
  <button class="btn btn-stop"   id="btn-stop"   onclick="stopAgent()"   disabled>&#9632; Stop Agent</button>
  <button class="btn btn-attack" id="btn-attack" onclick="runAttack()"   disabled>&#9889; Run Attack</button>
  <button class="btn btn-refill" id="btn-refill" onclick="runRefill()">&#8635; Refill Demo</button>
  <button class="btn btn-full-reset" id="btn-full-reset" onclick="fullReset()">&#9866; Full Reset</button>
  <div class="agent-status">
    <div class="status-dot" id="status-dot"></div>
    <span id="status-text" style="color:#aaa">Agent Stopped</span>
  </div>
</div>

<!-- Risk Banner -->
<div id="risk-banner" class="loading">
  <div class="risk-label">Overall Protocol Risk</div>
  <div id="risk-level-text" style="color:#aaa">CONNECTING</div>
  <div id="risk-subtitle">Waiting for agent to start...</div>
</div>

<main>
<div class="left-col">

  <!-- Token Flow Status -->
  <div class="section-title">Token Flow Status</div>
  <div class="flow-panel">
    <div class="flow-grid">
      <div class="flow-box danger" id="flow-protocol">
        <div class="flow-box-icon">🏦</div>
        <div class="flow-box-label">MockProtocol (Attack Target)</div>
        <div class="flow-box-value" id="flow-tvl">—</div>
        <div class="flow-box-sub" id="flow-liq">Liquidity: — VLT</div>
        <div class="tvl-input-row">
          <input class="tvl-input" id="tvl-input" type="number" min="100" max="100000" placeholder="e.g. 5000" title="Enter VLT amount to deposit as TVL"/>
          <button class="btn-tvl" id="btn-tvl" onclick="setTVL()">+ Add TVL</button>
        </div>
      </div>
      <div class="flow-arrow" id="arrow1">→</div>
      <div class="flow-box safe" id="flow-backup">
        <div class="flow-box-icon">✅</div>
        <div class="flow-box-label">Backup Wallet</div>
        <div class="flow-box-value" id="flow-backup-bal">—</div>
        <div class="flow-box-sub">SAFE</div>
      </div>
    </div>
    <div class="flow-status" id="flow-status-row">
      <div class="flow-dot" id="flow-dot"></div>
      <span id="flow-status-text">Loading token status...</span>
    </div>
  </div>

  <div class="section-title">5 Vital Signs</div>
  <div class="vitals-grid">
    <div class="vital-card" id="card-tvl">
      <div class="vital-icon">📊</div>
      <div class="vital-name">TVL</div>
      <span class="vital-badge badge-UNKNOWN" id="badge-tvl">—</span>
    </div>
    <div class="vital-card" id="card-admin">
      <div class="vital-icon">👤</div>
      <div class="vital-name">Admin Wallet</div>
      <span class="vital-badge badge-UNKNOWN" id="badge-admin">—</span>
    </div>
    <div class="vital-card" id="card-liquidity">
      <div class="vital-icon">💧</div>
      <div class="vital-name">Liquidity Pool</div>
      <span class="vital-badge badge-UNKNOWN" id="badge-liquidity">—</span>
    </div>
    <div class="vital-card" id="card-tx">
      <div class="vital-icon">&#9889;</div>
      <div class="vital-name">TX Pattern</div>
      <span class="vital-badge badge-UNKNOWN" id="badge-tx">—</span>
    </div>
    <div class="vital-card" id="card-upgrades">
      <div class="vital-icon">&#128295;</div>
      <div class="vital-name">Contract Upgrades</div>
      <span class="vital-badge badge-UNKNOWN" id="badge-upgrades">—</span>
    </div>
  </div>

  <div class="section-title">AI Diagnosis</div>
  <div class="diagnosis-box">
    <div class="diagnosis-label">
      <span class="ai-dot"></span>
      OpenAI gpt-4o-mini — Written permanently on Monad blockchain
    </div>
    <div id="diagnosis-text">Start the agent to begin monitoring...</div>
  </div>

  <div class="section-title">Report History</div>
  <div class="history-box">
    <div class="history-header">Last 5 health reports — most recent first</div>
    <div id="history-container"><div class="no-data">No reports yet.</div></div>
  </div>

</div><!-- /left-col -->

<!-- Live Log Panel -->
<div class="right-col">
  <div class="section-title">Agent Live Log</div>
  <div class="log-panel">
    <div class="log-header">
      <span>Terminal Output</span>
      <span id="log-count" style="color:#ccc">0 lines</span>
    </div>
    <div id="log-lines"><span style="color:#555">Waiting for agent to start...</span></div>
  </div>
</div>

</main>

<footer>
  Built on
  <a href="https://testnet.monadexplorer.com/address/0xF530be2A3Cd4189cc1fD670F2FEe555dBa834A3c" target="_blank">Monad Testnet</a>
  &nbsp;|&nbsp;
  VitalSigns: <a href="https://testnet.monadexplorer.com/address/0xF530be2A3Cd4189cc1fD670F2FEe555dBa834A3c" target="_blank">0xF530...834A3c</a>
  &nbsp;|&nbsp;
  Monad Blitz Bangalore V4
</footer>

<div class="toast" id="toast"></div>

<script>
  const API_BASE = window.location.origin;

  function sc(s){
    const v=(s||'').toUpperCase();
    if(v==='NORMAL'||v==='HEALTHY')return'NORMAL';
    if(v==='WARNING')return'WARNING';
    if(v==='CRITICAL')return'CRITICAL';
    if(v==='ALERT')return'ALERT';
    return'UNKNOWN';
  }
  function riskColor(r){
    const v=(r||'').toUpperCase();
    if(v==='HEALTHY')  return'#15803d';
    if(v==='WARNING')  return'#92400e';
    if(v==='CRITICAL') return'#c2410c';
    if(v==='EMERGENCY')return'#b91c1c';
    return'#9ca3af';
  }
  function subtext(r){
    const v=(r||'').toUpperCase();
    if(v==='HEALTHY')  return'All vital signs within normal parameters. Protocol is safe.';
    if(v==='WARNING')  return'Anomalies detected. Monitor closely and prepare to withdraw.';
    if(v==='CRITICAL') return'Multiple vital signs critical. Consider withdrawing funds now.';
    if(v==='EMERGENCY')return'RUG PULL DETECTED — Emergency evacuation triggered automatically!';
    return'Waiting for agent to start...';
  }
  function tsToTime(ts){
    const n=Number(ts);
    if(!n)return'—';
    return new Date(n*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',second:'2-digit'});
  }
  function trunc(s,n){return s&&s.length>n?s.slice(0,n)+'...':(s||'—')}
  function esc(s){return(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}

  function showToast(msg){
    const t=document.getElementById('toast');
    t.textContent=msg;t.classList.add('show');
    setTimeout(()=>t.classList.remove('show'),3500);
  }

  function updateBanner(risk){
    const v=(risk||'loading').toUpperCase();
    document.getElementById('risk-banner').className=v;
    document.getElementById('risk-level-text').textContent=v==='LOADING'?'CONNECTING':v;
    document.getElementById('risk-level-text').style.color=riskColor(v);
    document.getElementById('risk-subtitle').textContent=subtext(v);
  }

  function updateCard(cId,bId,raw){
    const cls=sc(raw);
    document.getElementById(cId).className='vital-card '+cls;
    const b=document.getElementById(bId);
    b.className='vital-badge badge-'+cls;
    b.textContent=(raw||'—').toUpperCase();
  }

  function updateHistory(reports){
    const el=document.getElementById('history-container');
    if(!reports||!reports.length){el.innerHTML='<div class="no-data">No reports yet — agent is still collecting readings.</div>';return;}
    // newest first
    const rows=[...reports].reverse().slice(0,5).map(r=>{
      const risk=(r.overallRisk||'').toUpperCase();
      const t=Number(r.timestamp);
      const timeStr=t?new Date(t*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',second:'2-digit'}):'—';
      return`<tr class="row-${risk}">
        <td>${timeStr}</td>
        <td><span class="tbadge tb-${risk}">${risk}</span></td>
        <td><span class="tbadge badge-${sc(r.tvlStatus)}" style="font-size:10px">${(r.tvlStatus||'—').toUpperCase()}</span></td>
        <td><span class="tbadge badge-${sc(r.adminStatus)}" style="font-size:10px">${(r.adminStatus||'—').toUpperCase()}</span></td>
        <td><span class="tbadge badge-${sc(r.liquidityStatus)}" style="font-size:10px">${(r.liquidityStatus||'—').toUpperCase()}</span></td>
        <td style="color:#6b7280;font-size:12px">${esc(trunc(r.aiDiagnosis,70))}</td>
      </tr>`;
    }).join('');
    el.innerHTML=`<table>
      <thead><tr><th>Time</th><th>Risk</th><th>TVL</th><th>Admin</th><th>Liquidity</th><th>Diagnosis</th></tr></thead>
      <tbody>${rows}</tbody></table>`;
  }

  // Parse latest vital signs from agent log lines
  function parseVitalsFromLog(lines){
    const result={tvl:'—',admin:'—',liquidity:'—',tx:'—',upgrades:'—',risk:'—',diagnosis:'—'};
    for(let i=lines.length-1;i>=0;i--){
      const l=lines[i];
      if(l.includes('OVERALL RISK:') && result.risk==='—'){
        const m=l.match(/OVERALL RISK:\\s*(\\w+)/);
        if(m) result.risk=m[1];
      }
      if(l.includes('TVL:') && l.includes('|') && result.tvl==='—'){
        const m=l.match(/TVL:.*?\\|\\s*(\\w+)/);
        if(m) result.tvl=m[1];
      }
      if(l.includes('Admin:') && result.admin==='—'){
        const m=l.match(/Admin:\\s*(\\w+)/);
        if(m) result.admin=m[1];
      }
      if(l.includes('Liquidity:') && l.includes('|') && result.liquidity==='—'){
        const m=l.match(/Liquidity:.*?\\|\\s*(\\w+)/);
        if(m) result.liquidity=m[1];
      }
      if(l.includes('TX:') && result.tx==='—'){
        const m=l.match(/TX:\\s*(\\w+)/);
        if(m) result.tx=m[1];
      }
      if(l.includes('Upgrades:') && result.upgrades==='—'){
        const m=l.match(/Upgrades:\\s*(\\w+)/);
        if(m) result.upgrades=m[1];
      }
      if((l.includes('FALLBACK:') || l.includes('Recommended:')) && result.diagnosis==='—'){
        result.diagnosis=l.replace(/^\\s*\\[.*?\\]\\s*/,'').trim();
      }
    }
    return result;
  }

  async function loadChainData(){
    try{
      const r=await fetch(API_BASE+'/api/status');
      const d=await r.json();
      const lines=d.log||[];
      const v=parseVitalsFromLog(lines);

      if(v.risk==='—'){
        document.getElementById('diagnosis-text').textContent='No agent reports yet. Click Start Agent above.';
        document.getElementById('last-updated-time').textContent='Updated '+new Date().toLocaleTimeString();
        updateHistory(d.history||[]);
        return;
      }
      updateBanner(v.risk);
      updateCard('card-tvl','badge-tvl',v.tvl);
      updateCard('card-admin','badge-admin',v.admin);
      updateCard('card-liquidity','badge-liquidity',v.liquidity);
      updateCard('card-tx','badge-tx',v.tx);
      updateCard('card-upgrades','badge-upgrades',v.upgrades);
      if(v.diagnosis!=='—') document.getElementById('diagnosis-text').textContent=v.diagnosis;
      updateHistory(d.history||[]);
      document.getElementById('last-updated-time').textContent='Updated '+new Date().toLocaleTimeString();
    }catch(e){
      document.getElementById('last-updated-time').textContent='Retrying...';
    }
  }

  async function pollStatus(){
    try{
      const r=await fetch(API_BASE+'/api/status');
      const d=await r.json();
      const running=d.agent_running;
      document.getElementById('status-dot').className='status-dot'+(running?' running':'');
      document.getElementById('status-text').textContent=running?'Agent Running':'Agent Stopped';
      document.getElementById('status-text').style.color=running?'#16a34a':'#aaa';
      document.getElementById('btn-start').disabled=running;
      document.getElementById('btn-stop').disabled=!running;
      document.getElementById('btn-attack').disabled=!running;

      const lines=d.log||[];
      if(lines.length){
        const logEl=document.getElementById('log-lines');
        logEl.innerHTML=lines.map(l=>{
          if(l.includes('[ATTACK]'))          return`<div class="log-attack">${esc(l)}</div>`;
          if(l.includes('EMERGENCY')||l.includes('[SOS]')) return`<div class="log-err">${esc(l)}</div>`;
          if(l.includes('SUCCESS')||l.includes('[OK]')||l.includes('evacuation complete'))
                                              return`<div class="log-ok">${esc(l)}</div>`;
          if(l.includes('CRITICAL')||l.includes('WARNING')||l.includes('[!!!]')||l.includes('[!!]'))
                                              return`<div class="log-warn">${esc(l)}</div>`;
          if(l.includes('TX:')||l.includes('Block:')||l.includes('CHAIN')||l.includes('testnet.monad'))
                                              return`<div class="log-chain">${esc(l)}</div>`;
          if(l.startsWith('===')||l.startsWith('---')||l.startsWith('!!!'))
                                              return`<div class="log-dim">${esc(l)}</div>`;
          return`<div>${esc(l)}</div>`;
        }).join('');
        logEl.scrollTop=logEl.scrollHeight;
        document.getElementById('log-count').textContent=lines.length+' lines';
      }
    }catch(e){}
  }

  async function startAgent(){
    document.getElementById('btn-start').disabled=true;
    document.getElementById('btn-start').textContent='Starting...';
    try{
      const r=await fetch(API_BASE+'/api/agent/start',{method:'POST'});
      const d=await r.json();
      showToast(d.ok?'Agent started! First check in ~10 seconds.':'Error: '+d.error);
    }catch(e){showToast('Cannot reach server.');}
    document.getElementById('btn-start').textContent='&#9654; Start Agent';
  }

  async function stopAgent(){
    try{
      await fetch(API_BASE+'/api/agent/stop',{method:'POST'});
      showToast('Agent stopped.');
    }catch(e){}
  }

  async function runAttack(){
    if(!confirm('Run the rug pull attack now?\\n\\nThis will drain TVL and remove liquidity to trigger EMERGENCY.'))return;
    document.getElementById('btn-attack').disabled=true;
    document.getElementById('btn-attack').textContent='Attacking...';
    try{
      const r=await fetch(API_BASE+'/api/attack/run',{method:'POST'});
      const d=await r.json();
      showToast(d.ok?'Attack launched! Watch the dashboard change...':'Error: '+d.error);
    }catch(e){showToast('Cannot reach server.');}
    setTimeout(()=>{
      document.getElementById('btn-attack').textContent='&#9889; Run Attack';
    },8000);
  }

  async function loadTokenStatus(){
    try{
      const r=await fetch(API_BASE+'/api/token-status');
      const d=await r.json();
      document.getElementById('flow-tvl').textContent=d.protocol_tvl+' VLT';
      document.getElementById('flow-liq').textContent='Liquidity: '+d.protocol_liquidity+' VLT';
      document.getElementById('flow-backup-bal').textContent=d.backup_balance+' VLT';

      const dot=document.getElementById('flow-dot');
      const txt=document.getElementById('flow-status-text');
      const arr1=document.getElementById('arrow1');

      if(d.backup_balance>0 && d.protocol_tvl===0){
        dot.className='flow-dot bad';
        txt.textContent='EVACUATED: '+d.backup_balance+' VLT saved in backup wallet. MockProtocol is now empty.';
        arr1.className='flow-arrow active';
      } else if(d.protocol_tvl>0){
        dot.className='flow-dot ok';
        txt.textContent='MONITORING: '+d.protocol_tvl+' VLT in MockProtocol. Agent watching for attacks.';
        arr1.className='flow-arrow';
      } else {
        dot.className='flow-dot warn';
        txt.textContent='MockProtocol TVL is 0. Click Refill Demo to deposit user funds for next demo run.';
        arr1.className='flow-arrow';
      }
    }catch(e){}
  }

  async function runRefill(){
    if(!confirm('Refill demo?\\n\\nThis will:\\n• Reset emergency flag\\n• Deposit 1000 VLT per user into MockProtocol\\n• Add 5000 VLT liquidity back\\n\\nTakes ~30 seconds.')) return;
    const btn=document.getElementById('btn-refill');
    btn.disabled=true; btn.textContent='Refilling...';
    showToast('Refilling demo state... please wait ~30 seconds.');
    try{
      const r=await fetch(API_BASE+'/api/refill',{method:'POST'});
      const d=await r.json();
      if(d.ok){
        showToast('Refill complete! Ready for next demo run.');
        loadTokenStatus();
        loadChainData();
      } else {
        showToast('Refill error: '+d.error);
      }
    }catch(e){showToast('Cannot reach server.');}
    btn.disabled=false; btn.textContent='&#8635; Refill Demo';
  }

  async function fullReset(){
    if(!confirm('FULL RESET\\n\\nThis will:\\n• Stop the agent\\n• Withdraw all user deposits to zero\\n• Drain all TVL from MockProtocol\\n• Drain all liquidity\\n• Clear emergency flag\\n\\nEverything goes to 0. Takes ~45 seconds.')) return;
    const btn=document.getElementById('btn-full-reset');
    btn.disabled=true; btn.textContent='Resetting...';
    showToast('Full reset in progress... ~45 seconds.');
    try{
      const r=await fetch(API_BASE+'/api/full-reset',{method:'POST'});
      const d=await r.json();
      if(d.ok){
        showToast('Reset complete! TVL=0, Deposits=0. Ready to start fresh.');
        loadTokenStatus();
        loadChainData();
      }else{
        showToast('Reset error: '+(d.error||'Unknown'));
      }
    }catch(e){showToast('Cannot reach server.');}
    btn.disabled=false; btn.textContent='&#9866; Full Reset';
  }

  async function setTVL(){
    const amount=parseInt(document.getElementById('tvl-input').value);
    if(!amount||amount<=0){showToast('Enter a valid VLT amount');return;}
    const btn=document.getElementById('btn-tvl');
    btn.disabled=true; btn.textContent='Depositing...';
    showToast('Depositing '+amount+' VLT into MockProtocol... please wait.');
    try{
      const r=await fetch(API_BASE+'/api/set-tvl',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({amount})
      });
      const d=await r.json();
      if(d.ok){
        showToast(d.message);
        loadTokenStatus();
        loadChainData();
      }else{
        showToast('Error: '+(d.error||'Unknown'));
      }
    }catch(e){showToast('Cannot reach server.');}
    btn.disabled=false; btn.textContent='+ Add TVL';
  }

  setInterval(loadChainData, 15000);
  setInterval(pollStatus, 3000);
  setInterval(loadTokenStatus, 10000);
  loadChainData();
  pollStatus();
  loadTokenStatus();
</script>
</body>
</html>'''


# ── Server startup ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    os.chdir(BASE_DIR)
    server = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), DemoHandler)

    print("=" * 55)
    print("  Protocol Vital Signs — Demo Server")
    print("=" * 55)
    print(f"  Local:   http://localhost:{PORT}")
    print(f"  Network: http://0.0.0.0:{PORT}")
    print()
    print("  To share publicly, run in another terminal:")
    print(f"  npx localtunnel --port {PORT}")
    print()
    print("  Press Ctrl+C to stop.")
    print("=" * 55)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Shutting down...")
        if agent_proc and agent_proc.poll() is None:
            agent_proc.terminate()
        server.shutdown()
