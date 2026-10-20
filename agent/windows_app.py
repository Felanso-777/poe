"""Consent-first Windows desktop interface for the PoE agent.

Light, flat tkinter UI matching the Proof of Effort web dashboard: chalk
background, navy ink, sky-blue accent, rounded controls and hash "fingerprint"
strips. Consent, folder selection, start/stop, analysis and shutdown logic are
unchanged; only the look and layout were reworked.
"""

from __future__ import annotations

import colorsys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

from agent.config import grant_consent, save_config
from agent.runner import ProductionSessionRunner


# Palette (shared with the web dashboard)
CHALK = "#f3f6f9"
CARD = "#ffffff"
FIELD = "#fbfcfd"
BORDER = "#d8e0e8"
INK = "#0b1b2b"
MUTED = "#5b6b7b"
IDLE = "#94a3b8"
ACCENT = "#0284c7"
ACCENT_HOVER = "#0369a1"
ACCENT_OFF = "#b9d9ea"
SUCCESS = "#047857"
WARN = "#b45309"
DANGER = "#be123c"
DANGER_BG = "#fff1f2"
HOVER_BG = "#f1f5f9"

UI = "Segoe UI"
HEAD = "Segoe UI Semibold"
MONO = "Consolas"


# ---------------------------------------------------------------------- #
# Drawing helpers
# ---------------------------------------------------------------------- #
def round_rect(canvas: tk.Canvas, x1, y1, x2, y2, r, **kw):
    pts = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
        x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(pts, smooth=True, **kw)


def fingerprint_colors(value: str, cells: int) -> list[str]:
    """Deterministic colour cells derived from a string (same idea as the web UI)."""
    s = value or "x"
    colors = []
    for i in range(cells):
        n = (ord(s[(i * 7) % len(s)]) * 31 + ord(s[(i * 7 + 3) % len(s)]) * 17 + i * 53) % 256
        hue = ((190 + round(n / 255 * 170)) % 360) / 360
        light = (40 + (n % 5) * 6) / 100
        r, g, b = colorsys.hls_to_rgb(hue, light, 0.60)
        colors.append(f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}")
    return colors


def draw_fingerprint(canvas: tk.Canvas, value: str | None, cells: int, cell_w: int, height: int) -> None:
    canvas.delete("all")
    colors = fingerprint_colors(value, cells) if value else ["#e6ecf2"] * cells
    for i, color in enumerate(colors):
        canvas.create_rectangle(i * cell_w, 0, (i + 1) * cell_w - 2, height, fill=color, outline=color)


class RoundedButton(tk.Canvas):
    """Canvas-drawn rounded button that supports configure(state=...)."""

    KINDS = {  # background, hover, text, border
        "primary": (ACCENT, ACCENT_HOVER, "#ffffff", ACCENT),
        "outline": (CARD, HOVER_BG, INK, BORDER),
        "danger": (CARD, DANGER_BG, DANGER, BORDER),
        "ghost": (CARD, DANGER_BG, DANGER, CARD),
    }

    def __init__(self, parent, text, command, kind="primary", width=140, height=38, bg=CARD):
        super().__init__(parent, width=width, height=height, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self._text, self._command, self._kind = text, command, kind
        self._state, self._hover = tk.NORMAL, False
        self.bind("<Configure>", lambda _e: self._render())
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._release)
        self._render()

    def configure(self, cnf=None, **kw):
        if "state" in kw:
            self._state = kw.pop("state")
            tk.Canvas.configure(self, cursor="hand2" if self._state == tk.NORMAL else "arrow")
            self._render()
        if "text" in kw:
            self._text = kw.pop("text")
            self._render()
        if cnf or kw:
            return super().configure(cnf, **kw)

    config = configure

    def _set_hover(self, value: bool) -> None:
        self._hover = value
        self._render()

    def _release(self, event) -> None:
        inside = 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height()
        if inside and self._state == tk.NORMAL and self._command:
            self._command()

    def _render(self) -> None:
        w = self.winfo_width()
        w = w if w > 1 else self.winfo_reqwidth()
        h = self.winfo_height()
        h = h if h > 1 else self.winfo_reqheight()
        bg, hover, fg, border = self.KINDS[self._kind]
        if self._state != tk.NORMAL:
            bg, fg, border = (ACCENT_OFF, "#ffffff", ACCENT_OFF) if self._kind == "primary" else (CARD, IDLE, BORDER)
        elif self._hover:
            bg = hover
        self.delete("all")
        round_rect(self, 1, 1, w - 1, h - 1, 10, fill=bg, outline=border)
        self.create_text(w / 2, h / 2, text=self._text, fill=fg, font=(HEAD, 10))


class StatusPill(tk.Canvas):
    """Rounded status chip: coloured dot + text on a tinted background."""

    def __init__(self, parent, bg=CHALK):
        super().__init__(parent, width=220, height=30, bg=bg, highlightthickness=0, bd=0)

    def set(self, text: str, color: str, tint: str) -> None:
        width = tkfont.Font(family=HEAD, size=9).measure(text) + 46
        self.configure(width=width)
        self.delete("all")
        round_rect(self, 0, 0, width, 30, 15, fill=tint, outline=tint)
        self.create_oval(14, 10, 24, 20, fill=color, outline=color)
        self.create_text(33, 15, text=text, anchor="w", fill=color, font=(HEAD, 9))


class MonitoringApp:
    """Simple operator UI around the production collector and analysis runner."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Proof of Effort — Activity Monitor")
        self.root.geometry("1020x720")
        self.root.minsize(900, 640)
        self.root.configure(bg=CHALK)
        self._style()

        self.folders: list[str] = []
        self.runner: ProductionSessionRunner | None = None
        self.started_at: datetime | None = None

        # Status variables
        self.status_var = tk.StringVar(value="Ready — no session is running")
        self.session_var = tk.StringVar(value="No active session")
        self.elapsed_var = tk.StringVar(value="00:00:00")
        self.events_var = tk.StringVar(value="—")
        self.analysis_var = tk.StringVar(value="Not available")
        self.integrity_var = tk.StringVar(value="Not submitted")

        self._build()
        self.status_var.trace_add("write", self._on_status)
        self.session_var.trace_add("write", self._on_session)
        self._on_status()
        self._on_session()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self._tick()

    # ------------------------------------------------------------------ #
    # Styling / helpers
    # ------------------------------------------------------------------ #
    def _style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Card.TCheckbutton", background=CARD, foreground=INK, font=(UI, 9), focuscolor=CARD)
        style.map(
            "Card.TCheckbutton",
            background=[("active", CARD)],
            indicatorcolor=[("selected", ACCENT), ("!selected", "#ffffff")],
        )
        style.configure(
            "Vertical.TScrollbar",
            troughcolor=FIELD, background=BORDER, bordercolor=FIELD,
            lightcolor=BORDER, darkcolor=BORDER, arrowcolor=MUTED, relief="flat",
        )

    def _card(self, parent, title: str, hint: str | None = None):
        outer = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        tk.Label(outer, text=title, bg=CARD, fg=INK, font=(HEAD, 12), anchor="w").pack(
            fill="x", padx=20, pady=(16, 0)
        )
        if hint:
            tk.Label(outer, text=hint, bg=CARD, fg=MUTED, font=(UI, 9), anchor="w", justify="left").pack(
                fill="x", padx=20, pady=(2, 0)
            )
        body = tk.Frame(outer, bg=CARD)
        body.pack(fill="both", expand=True, padx=20, pady=(14, 18))
        return outer, body

    # ------------------------------------------------------------------ #
    # Layout
    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=3)
        self.root.rowconfigure(3, weight=2)

        header = tk.Frame(self.root, bg=CHALK)
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(18, 16))
        logo = tk.Canvas(header, width=50, height=34, bg=CHALK, highlightthickness=0)
        logo.pack(side="left")
        draw_fingerprint(logo, "proof-of-effort", 5, 10, 34)
        titles = tk.Frame(header, bg=CHALK)
        titles.pack(side="left", padx=(14, 0))
        tk.Label(titles, text="Proof of Effort", font=(HEAD, 18), bg=CHALK, fg=INK).pack(anchor="w")
        tk.Label(titles, text="Activity monitor", font=(UI, 9), bg=CHALK, fg=MUTED).pack(anchor="w")
        self.pill = StatusPill(header)
        self.pill.pack(side="right")

        tk.Frame(self.root, bg=BORDER, height=1).grid(row=1, column=0, sticky="ew")

        main = tk.Frame(self.root, bg=CHALK)
        main.grid(row=2, column=0, sticky="nsew", padx=28, pady=(20, 14))
        main.columnconfigure(0, weight=5, uniform="cols")
        main.columnconfigure(1, weight=6, uniform="cols")
        main.rowconfigure(0, weight=1)
        self._build_authorization_panel(main)
        self._build_status_panel(main)

        log_card, log_body = self._card(self.root, "Activity log")
        log_card.grid(row=3, column=0, sticky="nsew", padx=28, pady=(0, 24))
        log_body.columnconfigure(0, weight=1)
        log_body.rowconfigure(0, weight=1)
        self.activity = tk.Text(
            log_body, height=5, bg=FIELD, fg=INK, font=(MONO, 9), bd=0, padx=12, pady=10, wrap="word",
            highlightthickness=1, highlightbackground=BORDER, highlightcolor=BORDER,
        )
        self.activity.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_body, orient="vertical", command=self.activity.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.activity.configure(yscrollcommand=scroll.set)
        self.activity.tag_configure("ts", foreground=MUTED)
        self.activity.configure(state=tk.DISABLED)

    def _build_authorization_panel(self, parent) -> None:
        card, body = self._card(
            parent, "Authorized folders", "Only the folders listed here are monitored. Nothing else is read."
        )
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self.folder_list = tk.Listbox(
            body, bg=FIELD, fg=INK, selectbackground=ACCENT, selectforeground="#ffffff", font=(UI, 9), bd=0,
            highlightthickness=1, highlightbackground=BORDER, highlightcolor=BORDER, activestyle="none",
        )
        self.folder_list.grid(row=0, column=0, sticky="nsew", pady=(0, 12))
        self.folder_empty = tk.Label(
            self.folder_list, text="No folders yet\nAdd the folders you consent to monitor.",
            bg=FIELD, fg=MUTED, font=(UI, 9), justify="center",
        )
        self.folder_empty.place(relx=0.5, rely=0.5, anchor="center")

        btn_row = tk.Frame(body, bg=CARD)
        btn_row.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        btn_row.columnconfigure(0, weight=1)
        RoundedButton(btn_row, "Add folder…", self._add_folder, "outline", width=124, height=36).grid(row=0, column=0, sticky="w")
        RoundedButton(btn_row, "Clear all", self._clear_folders, "ghost", width=96, height=36).grid(row=0, column=1, sticky="e")

        self.processes_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            body, text="Include process monitoring", variable=self.processes_var, style="Card.TCheckbutton"
        ).grid(row=2, column=0, sticky="w")

    def _build_status_panel(self, parent) -> None:
        card, body = self._card(parent, "Session")
        card.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        body.columnconfigure(0, weight=1)

        tk.Label(body, text="Elapsed time", bg=CARD, fg=MUTED, font=(UI, 9)).grid(row=0, column=0, sticky="w")
        tk.Label(body, textvariable=self.elapsed_var, bg=CARD, fg=INK, font=(HEAD, 40)).grid(row=1, column=0, sticky="w")

        self.session_print = tk.Canvas(body, width=288, height=22, bg=CARD, highlightthickness=0)
        self.session_print.grid(row=2, column=0, sticky="w", pady=(8, 4))
        tk.Label(body, textvariable=self.session_var, bg=CARD, fg=MUTED, font=(MONO, 9)).grid(row=3, column=0, sticky="w")

        action_row = tk.Frame(body, bg=CARD)
        action_row.grid(row=4, column=0, sticky="w", pady=(18, 18))
        self.start_button = RoundedButton(action_row, "Start monitoring", self._start, "primary", width=170, height=42)
        self.start_button.pack(side="left")
        self.stop_button = RoundedButton(action_row, "Stop", self._stop, "danger", width=100, height=42)
        self.stop_button.configure(state=tk.DISABLED)
        self.stop_button.pack(side="left", padx=(10, 0))

        rows = [("Events", self.events_var), ("Analysis", self.analysis_var), ("Blockchain", self.integrity_var)]
        for i, (label, var) in enumerate(rows):
            tk.Frame(body, bg=BORDER, height=1).grid(row=5 + i * 2, column=0, sticky="ew")
            line = tk.Frame(body, bg=CARD)
            line.grid(row=6 + i * 2, column=0, sticky="ew", pady=8)
            line.columnconfigure(1, weight=1)
            tk.Label(line, text=label, bg=CARD, fg=MUTED, font=(UI, 9), width=11, anchor="w").grid(row=0, column=0, sticky="nw")
            tk.Label(
                line, textvariable=var, bg=CARD, fg=INK, font=(HEAD, 10), anchor="w", justify="left", wraplength=380
            ).grid(row=0, column=1, sticky="w")

    # ------------------------------------------------------------------ #
    # Visual reactions to state (no logic)
    # ------------------------------------------------------------------ #
    def _on_status(self, *_args) -> None:
        text = self.status_var.get()
        low = text.lower()
        if "active" in low:
            color, tint = SUCCESS, "#ecfdf5"
        elif "analy" in low:
            color, tint = WARN, "#fffbeb"
        elif "error" in low:
            color, tint = DANGER, DANGER_BG
        elif "completed" in low:
            color, tint = ACCENT, "#e0f2fe"
        else:
            color, tint = MUTED, "#e8eef4"
        self.pill.set(text, color, tint)

    def _on_session(self, *_args) -> None:
        value = self.session_var.get()
        draw_fingerprint(self.session_print, None if value == "No active session" else value, 24, 12, 22)

    def _refresh_empty(self) -> None:
        if self.folders:
            self.folder_empty.place_forget()
        else:
            self.folder_empty.place(relx=0.5, rely=0.5, anchor="center")

    # ------------------------------------------------------------------ #
    # Behaviour (unchanged)
    # ------------------------------------------------------------------ #
    def _add_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select an authorized folder")
        if folder and folder not in self.folders:
            self.folders.append(folder)
            self.folder_list.insert(tk.END, folder)
            self._write(f"Authorized folder added: {folder}")
            self._refresh_empty()

    def _clear_folders(self) -> None:
        self.folders.clear()
        self.folder_list.delete(0, tk.END)
        self._write("Authorized folder list cleared.")
        self._refresh_empty()

    def _write(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.activity.configure(state=tk.NORMAL)
        self.activity.insert(tk.END, f"[{timestamp}] ", "ts")
        self.activity.insert(tk.END, f"{message}\n")
        self.activity.see(tk.END)
        self.activity.configure(state=tk.DISABLED)

    def _start(self) -> None:
        if not self.folders:
            messagebox.showwarning(
                "Folder required", "Select at least one authorized folder first."
            )
            return
        try:
            config = grant_consent(
                self.folders, include_processes=self.processes_var.get()
            )
            save_config(config)
            self.runner = ProductionSessionRunner(config, on_status=self._write)
            session_id = self.runner.start()
        except (OSError, ValueError, RuntimeError) as exc:
            messagebox.showerror("Cannot start monitoring", str(exc))
            self.runner = None
            return
        self.started_at = datetime.now()
        self.session_var.set(session_id[:12] + "…")
        self.status_var.set("Monitoring active")
        self.analysis_var.set("Analysis will appear after stopping")
        self.integrity_var.set("Blockchain: pending")
        self.start_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        self._write(
            "Consent recorded. Only the selected folders are being monitored."
        )

    def _stop(self) -> None:
        if self.runner is None:
            return
        self.stop_button.configure(state=tk.DISABLED)
        self.status_var.set("Analyzing session…")
        self.root.update_idletasks()
        try:
            result = self.runner.stop()
        except (RuntimeError, OSError) as exc:
            messagebox.showerror("Cannot stop monitoring", str(exc))
            self.status_var.set("Error")
            self.stop_button.configure(state=tk.NORMAL)
            return
        self.runner = None
        self.started_at = None
        self.status_var.set("Session completed")
        self.events_var.set(str(result.get("event_count", "—")))
        status = result.get("blockchain_status", "UNKNOWN")
        self.integrity_var.set(f"Blockchain: {status}")
        self.analysis_var.set(
            f"Report saved | Merkle: {str(result.get('merkle_root', ''))[:16]}…"
        )
        self.start_button.configure(state=tk.NORMAL)
        self._write(
            f"Session complete. Report: {result.get('report_path', 'not available')}"
        )
        self._write(f"Integrity status: {status}")

    def _tick(self) -> None:
        if self.started_at is not None:
            elapsed = int((datetime.now() - self.started_at).total_seconds())
            hours, remainder = divmod(elapsed, 3600)
            minutes, seconds = divmod(remainder, 60)
            self.elapsed_var.set(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        self.root.after(1000, self._tick)

    def _close(self) -> None:
        if self.runner is not None:
            if not messagebox.askyesno(
                "Monitoring active",
                "Stop and analyze the current session before closing?",
            ):
                return
            self._stop()
        self.root.destroy()


def main() -> None:
    try:  # crisp text on high-DPI Windows displays
        from ctypes import windll

        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    MonitoringApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
