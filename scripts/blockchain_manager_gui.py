"""
blockchain_manager_gui.py — Professional PoE Blockchain Manager GUI
===================================================================

Visual GUI with animations, loading states, and integrated frontend control.

Features:
  • Start/stop Hardhat node
  • Deploy AuditLedger contract
  • Auto-update .env files (root + frontend)
  • Start/stop frontend dev server (npm run dev)
  • Animated button states & progress feedback
  • Real-time logs & status dashboard

Run:
    python blockchain_manager_gui.py

Build EXE:
    pyinstaller --onefile --windowed blockchain_manager_gui.py
"""

from __future__ import annotations

import atexit
import json
import os
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, font as tkfont
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
BLOCKCHAIN_DIR = BASE_DIR / "blockchain"
FRONTEND_DIR = BASE_DIR / "frontend"
FRONTEND_ENV = FRONTEND_DIR / ".env"
ROOT_ENV = BASE_DIR / ".env"

# ---------------------------------------------------------------------------
# Process tracking
# ---------------------------------------------------------------------------

_running_processes: list[subprocess.Popen] = []


def _cleanup() -> None:
    for proc in _running_processes:
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


atexit.register(_cleanup)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_windows() -> bool:
    return os.name == "nt"


def _cmd_prefix(cmd: str) -> list[str]:
    """On Windows, npx/npm must be invoked via cmd /c because they're .cmd files."""
    if _is_windows():
        return ["cmd", "/c", cmd]
    return [cmd]


def run_cmd(cmd: list[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        shell=False,
    )


def start_background(cmd: list[str], cwd: Optional[Path] = None) -> subprocess.Popen:
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if _is_windows() else 0,
    )
    _running_processes.append(proc)
    return proc


def wait_for_hardhat(timeout: int = 60) -> bool:
    import urllib.request
    import urllib.error

    payload = json.dumps({"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1}).encode()
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:8545",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                if "result" in data:
                    return True
        except Exception:
            time.sleep(1)
    return False


def read_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def write_env_file(path: Path, env: dict[str, str]) -> None:
    lines: list[str] = []
    existing_keys = set(env.keys())

    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                lines.append(line)
                continue
            if "=" in stripped:
                key, _, _ = stripped.partition("=")
                key = key.strip()
                if key in env:
                    lines.append(f"{key}={env[key]}")
                    existing_keys.discard(key)
                else:
                    lines.append(line)
            else:
                lines.append(line)

    for key in existing_keys:
        lines.append(f"{key}={env[key]}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Animated Button
# ---------------------------------------------------------------------------

class AnimatedButton(ttk.Button):
    """A button that shows a spinning animation while busy."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._spinning = False
        self._spin_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠶", "⠷"]
        self._spin_index = 0
        self._original_text = kwargs.get("text", "")
        self._spin_job: Optional[str] = None

    def set_busy(self, busy: bool, text: Optional[str] = None) -> None:
        self._spinning = busy
        if busy:
            display_text = text or f"{self._original_text}..."
            self._spin_index = 0
            self._spin()
            self.config(state="disabled")
        else:
            if self._spin_job:
                self.after_cancel(self._spin_job)
                self._spin_job = None
            self.config(text=self._original_text, state="normal")

    def _spin(self) -> None:
        if not self._spinning:
            return
        char = self._spin_chars[self._spin_index % len(self._spin_chars)]
        self.config(text=f"{char} {self._original_text}...")
        self._spin_index += 1
        self._spin_job = self.after(120, self._spin)


# ---------------------------------------------------------------------------
# Status Indicator
# ---------------------------------------------------------------------------

class StatusIndicator(tk.Frame):
    """A colored dot + text status indicator."""

    COLORS = {
        "running": "#10b981",   # green
        "stopped": "#ef4444",   # red
        "warning": "#f59e0b",   # amber
        "info": "#3b82f6",      # blue
    }

    def __init__(self, parent, label: str = "", **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(bg="#ffffff")

        self.dot = tk.Canvas(self, width=14, height=14, bg="#ffffff", highlightthickness=0)
        self.dot.pack(side=tk.LEFT, padx=(0, 8))
        self._dot_circle = self.dot.create_oval(2, 2, 12, 12, fill=self.COLORS["stopped"], outline="")

        self.label_var = tk.StringVar(value=label)
        self.label = ttk.Label(self, textvariable=self.label_var, font=("Segoe UI", 10))
        self.label.pack(side=tk.LEFT)

    def set(self, status: str, text: str) -> None:
        color = self.COLORS.get(status, self.COLORS["info"])
        self.dot.itemconfig(self._dot_circle, fill=color)
        self.label_var.set(text)


# ---------------------------------------------------------------------------
# Main Application
# ---------------------------------------------------------------------------

class PoEBlockchainManager(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("PoE Blockchain Manager")
        self.geometry("900x700")
        self.minsize(800, 600)

        # Process references
        self.node_proc: Optional[subprocess.Popen] = None
        self.frontend_proc: Optional[subprocess.Popen] = None
        self.contract_address: Optional[str] = None

        # UI state
        self._node_busy = False
        self._deploy_busy = False
        self._frontend_busy = False

        self._setup_styles()
        self._build_ui()
        self._refresh_all()

    # ------------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------------

    def _setup_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")

        # Colors
        style.configure("TFrame", background="#f8fafc")
        style.configure("Card.TFrame", background="#ffffff", relief="flat")
        style.configure("Title.TLabel", background="#f8fafc", foreground="#0f172a",
                        font=("Segoe UI", 20, "bold"))
        style.configure("Subtitle.TLabel", background="#f8fafc", foreground="#64748b",
                        font=("Segoe UI", 11))
        style.configure("CardTitle.TLabel", background="#ffffff", foreground="#1e293b",
                        font=("Segoe UI", 12, "bold"))
        style.configure("CardText.TLabel", background="#ffffff", foreground="#64748b",
                        font=("Segoe UI", 10))
        style.configure("Action.TButton", font=("Segoe UI", 10, "bold"))
        style.configure("Success.TLabel", background="#ffffff", foreground="#10b981",
                        font=("Segoe UI", 10, "bold"))
        style.configure("Warning.TLabel", background="#ffffff", foreground="#ef4444",
                        font=("Segoe UI", 10, "bold"))

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Main container with slight background
        self.main = tk.Frame(self, bg="#f8fafc")
        self.main.pack(fill=tk.BOTH, expand=True)

        # Header
        self._build_header()

        # Notebook for sections
        self.notebook = ttk.Notebook(self.main)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))

        # Tab 1: Dashboard
        self.dash_frame = ttk.Frame(self.notebook, style="Card.TFrame")
        self.notebook.add(self.dash_frame, text="📊 Dashboard")
        self._build_dashboard_tab()

        # Tab 2: Blockchain
        self.bc_frame = ttk.Frame(self.notebook, style="Card.TFrame")
        self.notebook.add(self.bc_frame, text="⛓️ Blockchain")
        self._build_blockchain_tab()

        # Tab 3: Frontend
        self.fe_frame = ttk.Frame(self.notebook, style="Card.TFrame")
        self.notebook.add(self.fe_frame, text="🌐 Frontend")
        self._build_frontend_tab()

        # Tab 4: Logs
        self.log_frame = ttk.Frame(self.notebook, style="Card.TFrame")
        self.notebook.add(self.log_frame, text="📜 Logs")
        self._build_logs_tab()

        # Footer
        self._build_footer()

    def _build_header(self) -> None:
        header = tk.Frame(self.main, bg="#f8fafc")
        header.pack(fill=tk.X, padx=20, pady=(20, 10))

        ttk.Label(
            header,
            text="Proof of Effort — Blockchain Manager",
            style="Title.TLabel",
        ).pack(anchor=tk.W)

        ttk.Label(
            header,
            text="Start Hardhat, deploy AuditLedger, configure .env, and run the dashboard — all from one place.",
            style="Subtitle.TLabel",
        ).pack(anchor=tk.W, pady=(4, 0))

    def _build_dashboard_tab(self) -> None:
        # Scrollable content
        canvas = tk.Canvas(self.dash_frame, bg="#ffffff", highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.dash_frame, orient="vertical", command=canvas.yview)
        scrollable = tk.Frame(canvas, bg="#ffffff")

        scrollable.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Status cards row
        cards = tk.Frame(scrollable, bg="#ffffff")
        cards.pack(fill=tk.X, padx=20, pady=20)

        self.dash_node = self._make_dash_card(cards, "Hardhat Node", "● Not Running", "#ef4444", 0)
        self.dash_contract = self._make_dash_card(cards, "Contract", "● Not Deployed", "#ef4444", 1)
        self.dash_env = self._make_dash_card(cards, ".env Files", "● Not Updated", "#ef4444", 2)
        self.dash_frontend = self._make_dash_card(cards, "Frontend", "● Not Running", "#ef4444", 3)

        # Quick actions
        actions = tk.LabelFrame(scrollable, text="Quick Actions", bg="#ffffff",
                                font=("Segoe UI", 12, "bold"), fg="#1e293b")
        actions.pack(fill=tk.X, padx=20, pady=(0, 20))

        btn_row = tk.Frame(actions, bg="#ffffff")
        btn_row.pack(fill=tk.X, padx=15, pady=15)

        self.dash_btn_all = AnimatedButton(
            btn_row,
            text="🚀 All-in-One Setup",
            command=self._all_in_one,
            style="Action.TButton",
        )
        self.dash_btn_all.pack(fill=tk.X, pady=6)

        self.dash_btn_stop = AnimatedButton(
            btn_row,
            text="🛑 Stop Everything",
            command=self._stop_all,
            style="Action.TButton",
        )
        self.dash_btn_stop.pack(fill=tk.X, pady=6)

        # Info
        info = tk.LabelFrame(scrollable, text="Next Steps", bg="#ffffff",
                             font=("Segoe UI", 12, "bold"), fg="#1e293b")
        info.pack(fill=tk.X, padx=20, pady=(0, 20))

        info_text = (
            "1. Click 'All-in-One Setup' to start the node and deploy the contract\n"
            "2. Click 'Start Frontend' in the Frontend tab\n"
            "3. Open http://localhost:5173 in your browser\n"
            "4. Run: python log_effort.py --duration 10  (to create a session)"
        )
        tk.Label(info, text=info_text, bg="#ffffff", fg="#64748b",
                 font=("Segoe UI", 10), justify=tk.LEFT).pack(
            anchor=tk.W, padx=15, pady=15
        )

    def _make_dash_card(self, parent, title, value, color, column) -> tk.Frame:
        card = tk.Frame(parent, bg="#ffffff", relief="solid", bd=1)
        card.grid(row=0, column=column, padx=8, pady=5, sticky="nsew")
        cards_parent = parent.winfo_toplevel()
        parent.grid_columnconfigure(column, weight=1)

        tk.Label(card, text=title, bg="#ffffff", fg="#64748b",
                 font=("Segoe UI", 9, "bold")).pack(pady=(12, 2))

        var = tk.StringVar(value=value)
        lbl = tk.Label(card, textvariable=var, bg="#ffffff", fg=color,
                       font=("Segoe UI", 13, "bold"))
        lbl.pack(pady=(0, 12))

        # Store reference for updates
        card._var = var
        card._lbl = lbl
        card._color = color
        return card

    def _update_dash_card(self, card, status: str, text: str, color: str) -> None:
        card._var.set(text)
        card._lbl.config(fg=color)

    def _build_blockchain_tab(self) -> None:
        # Scrollable
        canvas = tk.Canvas(self.bc_frame, bg="#ffffff", highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.bc_frame, orient="vertical", command=canvas.yview)
        scrollable = tk.Frame(canvas, bg="#ffffff")

        scrollable.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Status indicators
        status_frame = tk.Frame(scrollable, bg="#ffffff")
        status_frame.pack(fill=tk.X, padx=20, pady=20)

        self.bc_node_ind = StatusIndicator(status_frame, "Hardhat Node: Checking...")
        self.bc_node_ind.pack(anchor=tk.W, pady=4)

        self.bc_contract_ind = StatusIndicator(status_frame, "Contract: Checking...")
        self.bc_contract_ind.pack(anchor=tk.W, pady=4)

        self.bc_env_ind = StatusIndicator(status_frame, ".env Files: Checking...")
        self.bc_env_ind.pack(anchor=tk.W, pady=4)

        # Buttons
        btn_frame = tk.LabelFrame(scrollable, text="Actions", bg="#ffffff",
                                  font=("Segoe UI", 12, "bold"), fg="#1e293b")
        btn_frame.pack(fill=tk.X, padx=20, pady=20)

        btn_row = tk.Frame(btn_frame, bg="#ffffff")
        btn_row.pack(fill=tk.X, padx=15, pady=15)

        self.bc_btn_node = AnimatedButton(
            btn_row,
            text="Start Hardhat Node",
            command=self._start_node,
        )
        self.bc_btn_node.pack(fill=tk.X, pady=6)

        self.bc_btn_deploy = AnimatedButton(
            btn_row,
            text="Deploy AuditLedger Contract",
            command=self._deploy,
        )
        self.bc_btn_deploy.pack(fill=tk.X, pady=6)

        self.bc_btn_update = AnimatedButton(
            btn_row,
            text="Update .env Files Only",
            command=self._update_env_only,
        )
        self.bc_btn_update.pack(fill=tk.X, pady=6)

        # Current address display
        addr_frame = tk.LabelFrame(scrollable, text="Contract Address", bg="#ffffff",
                                   font=("Segoe UI", 12, "bold"), fg="#1e293b")
        addr_frame.pack(fill=tk.X, padx=20, pady=(0, 20))

        self.bc_addr_var = tk.StringVar(value="Not deployed yet")
        tk.Label(addr_frame, textvariable=self.bc_addr_var, bg="#ffffff",
                 fg="#1e293b", font=("Consolas", 11)).pack(padx=15, pady=15)

    def _build_frontend_tab(self) -> None:
        canvas = tk.Canvas(self.fe_frame, bg="#ffffff", highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.fe_frame, orient="vertical", command=canvas.yview)
        scrollable = tk.Frame(canvas, bg="#ffffff")

        scrollable.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Status
        self.fe_ind = StatusIndicator(scrollable, "Frontend: Not Running")
        self.fe_ind.pack(anchor=tk.W, padx=20, pady=20)

        # Buttons
        btn_frame = tk.LabelFrame(scrollable, text="Actions", bg="#ffffff",
                                  font=("Segoe UI", 12, "bold"), fg="#1e293b")
        btn_frame.pack(fill=tk.X, padx=20, pady=20)

        btn_row = tk.Frame(btn_frame, bg="#ffffff")
        btn_row.pack(fill=tk.X, padx=15, pady=15)

        self.fe_btn_start = AnimatedButton(
            btn_row,
            text="Start Frontend (npm run dev)",
            command=self._start_frontend,
        )
        self.fe_btn_start.pack(fill=tk.X, pady=6)

        self.fe_btn_stop = AnimatedButton(
            btn_row,
            text="Stop Frontend",
            command=self._stop_frontend,
        )
        self.fe_btn_stop.pack(fill=tk.X, pady=6)

        # Info
        info = tk.LabelFrame(scrollable, text="Info", bg="#ffffff",
                             font=("Segoe UI", 12, "bold"), fg="#1e293b")
        info.pack(fill=tk.X, padx=20, pady=(0, 20))

        info_text = (
            "The frontend runs on http://localhost:5173\n"
            "Make sure .env is updated before starting.\n"
            "You must keep this GUI window open while the frontend runs."
        )
        tk.Label(info, text=info_text, bg="#ffffff", fg="#64748b",
                 font=("Segoe UI", 10), justify=tk.LEFT).pack(
            anchor=tk.W, padx=15, pady=15
        )

    def _build_logs_tab(self) -> None:
        self.log_text = scrolledtext.ScrolledText(
            self.log_frame,
            wrap=tk.WORD,
            font=("Consolas", 10),
            bg="#0f172a",
            fg="#22d3ee",
            insertbackground="#ffffff",
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        btn_frame = tk.Frame(self.log_frame, bg="#ffffff")
        btn_frame.pack(fill=tk.X, padx=20, pady=(0, 20))

        ttk.Button(btn_frame, text="🗑️ Clear Logs",
                   command=self._clear_logs).pack(side=tk.LEFT)

    def _build_footer(self) -> None:
        footer = tk.Frame(self.main, bg="#f8fafc")
        footer.pack(fill=tk.X, padx=20, pady=(0, 20))

        ttk.Label(
            footer,
            text="Proof of Effort — Keep this window open while using the dashboard.",
            style="Subtitle.TLabel",
        ).pack(anchor=tk.W)

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log(self, message: str, level: str = "info") -> None:
        timestamp = time.strftime("%H:%M:%S")
        prefix = {
            "info": "[INFO]",
            "ok": "[✓]",
            "error": "[✗]",
            "warn": "[!]",
        }.get(level, "[INFO]")
        self.log_text.insert(tk.END, f"{timestamp} {prefix} {message}\n")
        self.log_text.see(tk.END)
        self.update_idletasks()

    def _clear_logs(self) -> None:
        self.log_text.delete("1.0", tk.END)

    # ------------------------------------------------------------------
    # Status refresh
    # ------------------------------------------------------------------

    def _refresh_all(self) -> None:
        self._refresh_dashboard()
        self._refresh_blockchain()
        self._refresh_frontend()

    def _refresh_dashboard(self) -> None:
        import urllib.request
        import urllib.error

        # Node
        try:
            payload = json.dumps({"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1}).encode()
            req = urllib.request.Request(
                "http://127.0.0.1:8545",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
                block = data.get("result", "?")
                self._update_dash_card(self.dash_node, "running",
                                       f"● Running (block {block})", "#10b981")
        except Exception:
            self._update_dash_card(self.dash_node, "stopped", "● Not Running", "#ef4444")

        # Contract
        root_env = read_env_file(ROOT_ENV)
        addr = root_env.get("POE_CONTRACT_ADDRESS", "")
        if addr and addr != "0xREPLACE_WITH_DEPLOYED_CONTRACT_ADDRESS":
            self._update_dash_card(self.dash_contract, "running",
                                   f"● Deployed: {addr[:10]}...", "#10b981")
            self.contract_address = addr
        else:
            self._update_dash_card(self.dash_contract, "stopped", "● Not Deployed", "#ef4444")

        # Env
        frontend_env = read_env_file(FRONTEND_ENV)
        root_ok = bool(addr and addr != "0xREPLACE_WITH_DEPLOYED_CONTRACT_ADDRESS")
        fe_ok = bool(frontend_env.get("VITE_POE_CONTRACT_ADDRESS", "") not in
                     ("", "0xREPLACE_WITH_DEPLOYED_CONTRACT_ADDRESS"))
        if root_ok and fe_ok:
            self._update_dash_card(self.dash_env, "running", "● Updated", "#10b981")
        else:
            self._update_dash_card(self.dash_env, "stopped", "● Not Updated", "#ef4444")

        # Frontend
        if self.frontend_proc and self.frontend_proc.poll() is None:
            self._update_dash_card(self.dash_frontend, "running", "● Running", "#10b981")
        else:
            self._update_dash_card(self.dash_frontend, "stopped", "● Not Running", "#ef4444")

    def _refresh_blockchain(self) -> None:
        import urllib.request
        import urllib.error

        # Node
        try:
            payload = json.dumps({"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1}).encode()
            req = urllib.request.Request(
                "http://127.0.0.1:8545",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
                block = data.get("result", "?")
                self.bc_node_ind.set("running", f"Hardhat Node: Running (block {block})")
        except Exception:
            self.bc_node_ind.set("stopped", "Hardhat Node: Not Running")

        # Contract
        root_env = read_env_file(ROOT_ENV)
        addr = root_env.get("POE_CONTRACT_ADDRESS", "")
        if addr and addr != "0xREPLACE_WITH_DEPLOYED_CONTRACT_ADDRESS":
            self.contract_address = addr
            self.bc_contract_ind.set("running", f"Contract: Deployed ({addr[:10]}...)")
            self.bc_addr_var.set(addr)
        else:
            self.bc_contract_ind.set("stopped", "Contract: Not Deployed")
            self.bc_addr_var.set("Not deployed yet")

        # Env
        frontend_env = read_env_file(FRONTEND_ENV)
        root_ok = bool(addr and addr != "0xREPLACE_WITH_DEPLOYED_CONTRACT_ADDRESS")
        fe_ok = bool(frontend_env.get("VITE_POE_CONTRACT_ADDRESS", "") not in
                     ("", "0xREPLACE_WITH_DEPLOYED_CONTRACT_ADDRESS"))
        if root_ok and fe_ok:
            self.bc_env_ind.set("running", ".env Files: Updated")
        else:
            self.bc_env_ind.set("stopped", ".env Files: Not Updated")

        # Refresh dashboard too
        self._refresh_dashboard()

    def _refresh_frontend(self) -> None:
        if self.frontend_proc and self.frontend_proc.poll() is None:
            self.fe_ind.set("running", "Frontend: Running")
        else:
            self.fe_ind.set("stopped", "Frontend: Not Running")

    # ------------------------------------------------------------------
    # Blockchain actions
    # ------------------------------------------------------------------

    def _start_node(self) -> None:
        if self._node_busy:
            return
        self._node_busy = True
        self.bc_btn_node.set_busy(True, "Starting Hardhat Node")
        self.log("🚀 Starting Hardhat node...")

        def _run():
            import urllib.request
            import urllib.error

            # Check if already running
            try:
                payload = json.dumps({"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1}).encode()
                req = urllib.request.Request(
                    "http://127.0.0.1:8545",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=3) as resp:
                    data = json.loads(resp.read().decode())
                    if "result" in data:
                        self.log("✓ Hardhat node is already running.")
                        self.after(0, lambda: self._finish_node_start(True))
                        return
            except Exception:
                pass

            self.after(0, lambda: self.log("  Starting npx hardhat node in blockchain folder..."))

            try:
                proc = start_background(
                    _cmd_prefix("npx hardhat node"),
                    cwd=BLOCKCHAIN_DIR,
                )
                self.node_proc = proc

                def _read_output():
                    for line in proc.stdout:
                        self.after(0, lambda l=line: self.log(f"[hardhat] {l.rstrip()}"))

                threading.Thread(target=_read_output, daemon=True).start()

                if wait_for_hardhat():
                    self.after(0, lambda: self.log("✓ Hardhat node is ready."))
                    self.after(0, lambda: self._finish_node_start(True))
                else:
                    self.after(0, lambda: self.log("✗ Hardhat node not ready in time."))
                    self.after(0, lambda: self._finish_node_start(False))
            except Exception as e:
                self.after(0, lambda: self.log(f"✗ Failed to start node: {e}"))
                self.after(0, lambda: self._finish_node_start(False))

        threading.Thread(target=_run, daemon=True).start()

    def _finish_node_start(self, success: bool) -> None:
        self._node_busy = False
        self.bc_btn_node.set_busy(False)
        self._refresh_blockchain()

    def _deploy(self) -> None:
        if self._deploy_busy:
            return
        self._deploy_busy = True
        self.bc_btn_deploy.set_busy(True, "Deploying Contract")
        self.log("📦 Deploying AuditLedger contract...")

        def _run():
            import urllib.request
            import urllib.error

            # Check node
            try:
                payload = json.dumps({"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1}).encode()
                req = urllib.request.Request(
                    "http://127.0.0.1:8545",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=3) as _:
                    pass
            except Exception:
                self.after(0, lambda: self.log("✗ Hardhat node is not running. Start it first."))
                self.after(0, lambda: messagebox.showwarning(
                    "Not Running", "Please start the Hardhat node first."))
                self.after(0, lambda: self._finish_deploy(False))
                return

            try:
                result = run_cmd(
                    _cmd_prefix("npx hardhat run scripts/deploy.js --network localhost"),
                    cwd=BLOCKCHAIN_DIR,
                )
                self.after(0, lambda: self.log(f"[deploy] {result.stdout}"))
                if result.stderr:
                    self.after(0, lambda: self.log(f"[deploy stderr] {result.stderr}"))

                if result.returncode != 0:
                    self.after(0, lambda: self.log("✗ Deployment failed."))
                    self.after(0, lambda: self._finish_deploy(False))
                    return

                match = re.search(r"deployed at:\s*(0x[a-fA-F0-9]{40})", result.stdout)
                if not match:
                    self.after(0, lambda: self.log("✗ Could not find contract address."))
                    self.after(0, lambda: self._finish_deploy(False))
                    return

                address = match.group(1)
                self.contract_address = address
                self.after(0, lambda: self.log(f"✓ Contract deployed at: {address}"))

                # Update .env files
                self.after(0, lambda: self.log("📝 Updating .env files..."))

                root_env = read_env_file(ROOT_ENV)
                root_env["POE_CONTRACT_ADDRESS"] = address
                root_env.setdefault("POE_RPC_URL", "http://127.0.0.1:8545")
                root_env.setdefault("POE_CHAIN_ID", "31337")
                root_env.setdefault("POE_PRIVATE_KEY",
                                    "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80")
                write_env_file(ROOT_ENV, root_env)
                self.after(0, lambda: self.log(f"✓ Updated {ROOT_ENV.name}"))

                frontend_env = read_env_file(FRONTEND_ENV)
                frontend_env["VITE_POE_CONTRACT_ADDRESS"] = address
                frontend_env.setdefault("VITE_POE_RPC_URL", "http://127.0.0.1:8545")
                frontend_env.setdefault("VITE_POE_CHAIN_ID", "31337")
                frontend_env.setdefault("VITE_DEMO_MODE", "false")
                write_env_file(FRONTEND_ENV, frontend_env)
                self.after(0, lambda: self.log(f"✓ Updated {FRONTEND_ENV.name}"))

                self.after(0, lambda: messagebox.showinfo(
                    "Deployed",
                    f"Contract deployed at:\n{address}\n\n.env files updated.\n"
                    "You can now start the frontend from the Frontend tab.",
                ))

                self.after(0, lambda: self._finish_deploy(True))
            except Exception as e:
                self.after(0, lambda: self.log(f"✗ Deploy error: {e}"))
                self.after(0, lambda: self._finish_deploy(False))

        threading.Thread(target=_run, daemon=True).start()

    def _finish_deploy(self, success: bool) -> None:
        self._deploy_busy = False
        self.bc_btn_deploy.set_busy(False)
        self._refresh_blockchain()
        self._refresh_dashboard()

    def _all_in_one(self) -> None:
        self.log("🚀 Running All-in-One Setup...")
        self._start_node()
        self.after(4000, self._deploy)

    def _update_env_only(self) -> None:
        if not self.contract_address:
            root_env = read_env_file(ROOT_ENV)
            self.contract_address = root_env.get("POE_CONTRACT_ADDRESS", "")
        if not self.contract_address or self.contract_address == "0xREPLACE_WITH_DEPLOYED_CONTRACT_ADDRESS":
            messagebox.showwarning("No Address", "No contract address found. Deploy first.")
            return
        self.log("📝 Updating .env files...")
        root_env = read_env_file(ROOT_ENV)
        root_env["POE_CONTRACT_ADDRESS"] = self.contract_address
        root_env.setdefault("POE_RPC_URL", "http://127.0.0.1:8545")
        root_env.setdefault("POE_CHAIN_ID", "31337")
        root_env.setdefault("POE_PRIVATE_KEY",
                            "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80")
        write_env_file(ROOT_ENV, root_env)
        self.log(f"✓ Updated {ROOT_ENV.name}")

        frontend_env = read_env_file(FRONTEND_ENV)
        frontend_env["VITE_POE_CONTRACT_ADDRESS"] = self.contract_address
        frontend_env.setdefault("VITE_POE_RPC_URL", "http://127.0.0.1:8545")
        frontend_env.setdefault("VITE_POE_CHAIN_ID", "31337")
        frontend_env.setdefault("VITE_DEMO_MODE", "false")
        write_env_file(FRONTEND_ENV, frontend_env)
        self.log(f"✓ Updated {FRONTEND_ENV.name}")
        self._refresh_blockchain()
        self._refresh_dashboard()
        messagebox.showinfo("Updated", ".env files updated with contract address.")

    def _stop_all(self) -> None:
        self.log("🛑 Stopping all processes...")
        killed = 0
        for proc in list(_running_processes):
            if proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                    killed += 1
                except Exception:
                    try:
                        proc.kill()
                        killed += 1
                    except Exception:
                        pass
        _running_processes.clear()
        self.node_proc = None
        self.frontend_proc = None

        try:
            subprocess.run(["taskkill", "/F", "/IM", "node.exe"], capture_output=True, text=True)
        except Exception:
            pass

        self.log(f"✓ Stopped {killed} process(es).")
        self._refresh_all()

    # ------------------------------------------------------------------
    # Frontend actions
    # ------------------------------------------------------------------

    def _start_frontend(self) -> None:
        if self._frontend_busy:
            return
        self._frontend_busy = True
        self.fe_btn_start.set_busy(True, "Starting Frontend")
        self.log("🌐 Starting frontend (npm run dev)...")

        # Check .env has contract address
        frontend_env = read_env_file(FRONTEND_ENV)
        if not frontend_env.get("VITE_POE_CONTRACT_ADDRESS") or \
           frontend_env.get("VITE_POE_CONTRACT_ADDRESS") == "0xREPLACE_WITH_DEPLOYED_CONTRACT_ADDRESS":
            self.after(0, lambda: self.log("✗ .env missing contract address. Deploy first."))
            self.after(0, lambda: self._finish_frontend(False))
            return

        def _run():
            try:
                proc = start_background(
                    _cmd_prefix("npm run dev"),
                    cwd=FRONTEND_DIR,
                )
                self.frontend_proc = proc

                def _read_output():
                    for line in proc.stdout:
                        self.after(0, lambda l=line: self.log(f"[vite] {l.rstrip()}"))

                threading.Thread(target=_read_output, daemon=True).start()
                self.after(0, lambda: self.log("✓ Frontend started on http://localhost:5173"))
                self.after(0, lambda: self._finish_frontend(True))
            except Exception as e:
                self.after(0, lambda: self.log(f"✗ Failed to start frontend: {e}"))
                self.after(0, lambda: self._finish_frontend(False))

        threading.Thread(target=_run, daemon=True).start()

    def _stop_frontend(self) -> None:
        self.log("🛑 Stopping frontend...")
        if self.frontend_proc and self.frontend_proc.poll() is None:
            try:
                self.frontend_proc.terminate()
                self.frontend_proc.wait(timeout=5)
            except Exception:
                try:
                    self.frontend_proc.kill()
                except Exception:
                    pass
        self.frontend_proc = None
        # Also kill vite processes
        try:
            subprocess.run(["taskkill", "/F", "/IM", "node.exe"], capture_output=True, text=True)
        except Exception:
            pass
        self.log("✓ Frontend stopped.")
        self._refresh_frontend()
        self._refresh_dashboard()

    def _finish_frontend(self, success: bool) -> None:
        self._frontend_busy = False
        self.fe_btn_start.set_busy(False)
        self._refresh_frontend()
        self._refresh_dashboard()


def main():
    app = PoEBlockchainManager()
    app.mainloop()


if __name__ == "__main__":
    main()
