"""Iris: windowed launcher for the proxy (8888) and the API (8000).

No console window. Splash shows the name and a brief fading rainbow
arc, then the main window offers Start / Stop / Open Dashboard, status
lines in words (Running / Stopped), and the last log lines of each
process. Closing while running asks first.
"""
import os
import queue
import subprocess
import sys
import threading
import webbrowser

PROXY_HOST = "127.0.0.1"
PROXY_PORT = 8888
API_PORT = 8000
DASHBOARD_URL = f"http://{PROXY_HOST}:{API_PORT}/"

def project_dir() -> str:
    """Folder holding proxy.py/api.py: beside the source, or above dist/ when frozen."""
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        if os.path.basename(exe_dir).lower() == "dist":
            return os.path.dirname(exe_dir)
        return exe_dir
    return os.path.dirname(os.path.abspath(__file__))


PROXY_ARGS = [
    "proxy.py",
    "--port", "8888",
    "--db", os.path.join(project_dir(), "attempts.db"),
    "--allowlist", "127.0.0.1,localhost,::1",
    "--rate-limit", "100",
    "--rate-window", "10",
    "--relay-timeout", "30",
]
API_ARGS = ["-m", "uvicorn", "api:app", "--host", "127.0.0.1", "--port", "8000"]

RAINBOW = [
    "#e53935", "#fb8c00", "#fdd835",
    "#43a047", "#1e88e5", "#8e24aa",
]
BACKGROUND = "#ffffff"

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def python_exe(proj: str) -> str:
    """Venv python when present, else whatever python is on PATH."""
    candidate = os.path.join(proj, ".venv", "Scripts", "python.exe")
    return candidate if os.path.exists(candidate) else "python"


def proxy_cmd(py: str) -> list:
    return [py] + PROXY_ARGS


def api_cmd(py: str) -> list:
    return [py] + API_ARGS


def mix(hex_a: str, hex_b: str, t: float) -> str:
    """Blend two #rrggbb colours; t=0 gives a, t=1 gives b."""
    a = int(hex_a[1:], 16)
    b = int(hex_b[1:], 16)
    c = tuple(
        round(((a >> s) & 0xFF) * (1 - t) + ((b >> s) & 0xFF) * t)
        for s in (16, 8, 0)
    )
    return f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}"


def run_gui() -> None:
    import tkinter as tk
    from tkinter import messagebox

    procs = {"proxy": None, "api": None}
    queues = {"proxy": queue.Queue(), "api": queue.Queue()}

    root = tk.Tk()
    root.title("Iris — proxy + API launcher")
    root.withdraw()

    statuses = {}
    log_boxes = {}
    buttons = {}

    def set_status(which: str, text: str) -> None:
        statuses[which].config(text=text)

    def append_log(which: str, line: str) -> None:
        box = log_boxes[which]
        box.config(state="normal")
        box.insert("end", line + "\n")
        lines = int(box.index("end-1c").split(".")[0])
        if lines > 300:
            box.delete("1.0", f"{lines - 300}.0")
        box.see("end")
        box.config(state="disabled")

    def reader(which: str, proc: subprocess.Popen) -> None:
        try:
            for line in proc.stdout:
                queues[which].put(line.rstrip("\n"))
        except Exception as exc:  # never kill the thread loudly
            queues[which].put(f"(log reader ended: {exc})")

    def poll() -> None:
        for which in ("proxy", "api"):
            try:
                while True:
                    append_log(which, queues[which].get_nowait())
            except queue.Empty:
                pass
            proc = procs[which]
            if proc is not None and proc.poll() is not None:
                set_status(which, f"{label(which)}: Stopped (exit {proc.poll()})")
                procs[which] = None
                buttons["start"].config(state="normal")
                buttons["stop"].config(state="disabled")
        root.after(250, poll)

    def label(which: str) -> str:
        port = PROXY_PORT if which == "proxy" else API_PORT
        return f"{which.capitalize()} {PROXY_HOST}:{port}"

    def start_both() -> None:
        if procs["proxy"] is not None or procs["api"] is not None:
            return
        proj = project_dir()
        py = python_exe(proj)
        for which, cmd in (("proxy", proxy_cmd(py)), ("api", api_cmd(py))):
            proc = subprocess.Popen(
                cmd, cwd=proj,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, creationflags=CREATE_NO_WINDOW,
            )
            procs[which] = proc
            threading.Thread(target=reader, args=(which, proc), daemon=True).start()
            set_status(which, f"{label(which)}: Running")
        buttons["start"].config(state="disabled")
        buttons["stop"].config(state="normal")

    def stop_both() -> None:
        for which in ("proxy", "api"):
            proc = procs[which]
            if proc is None:
                continue
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
            set_status(which, f"{label(which)}: Stopped")
            procs[which] = None
        buttons["start"].config(state="normal")
        buttons["stop"].config(state="disabled")

    def on_close() -> None:
        running = [w for w, p in procs.items() if p is not None]
        if running and not messagebox.askyesno(
            "Iris", "Proxy and API are still running. Stop them and close?"
        ):
            return
        stop_both()
        root.destroy()

    # --- main window (built first, shown after the splash) ---
    tk.Label(root, text="Iris", font=("Segoe UI", 22, "bold")).pack(pady=(12, 0))
    tk.Label(root, text="Local proxy only. Metadata only. No bodies, no keys.").pack()
    for which in ("proxy", "api"):
        statuses[which] = tk.Label(root, text=f"{label(which)}: Stopped",
                                   font=("Segoe UI", 11, "bold"))
        statuses[which].pack(pady=(8, 0))
        tk.Label(root, text=f"Last log lines ({which}):").pack()
        box = tk.Text(root, height=8, width=90, state="disabled")
        box.pack(padx=12)
        log_boxes[which] = box
    row = tk.Frame(root)
    row.pack(pady=12)
    buttons["start"] = tk.Button(row, text="Start", width=12, command=start_both)
    buttons["start"].pack(side="left", padx=6)
    buttons["stop"] = tk.Button(row, text="Stop", width=12, command=stop_both,
                               state="disabled")
    buttons["stop"].pack(side="left", padx=6)
    tk.Button(row, text="Open Dashboard", width=16,
              command=lambda: webbrowser.open(DASHBOARD_URL)).pack(side="left", padx=6)
    root.protocol("WM_DELETE_WINDOW", on_close)

    # --- splash: name, tagline, one rainbow arc fading in and out ---
    splash = tk.Toplevel(root)
    splash.title("Iris")
    splash.overrideredirect(True)
    W, H = 420, 300
    splash.geometry(f"{W}x{H}+{(splash.winfo_screenwidth() - W) // 2}"
                   f"+{(splash.winfo_screenheight() - H) // 2}")
    tk.Label(splash, text="Iris", font=("Segoe UI", 30, "bold")).pack(pady=(24, 0))
    tk.Label(splash, text="Local proxy only. Metadata only. No bodies, no keys.").pack()
    canvas = tk.Canvas(splash, width=360, height=190, highlightthickness=0)
    canvas.pack()
    DIAMOND = "#212121"
    gate = canvas.create_polygon(180, 8, 302, 95, 180, 182, 58, 95,
                                 outline=BACKGROUND, fill="", width=7)
    arcs = []
    for i, colour in enumerate(RAINBOW):
        r = 124 - i * 9
        arcs.append(canvas.create_arc(180 - r, 152 - r, 180 + r, 152 + r,
                                     start=0, extent=180, style="arc",
                                     outline=BACKGROUND, width=8))
    pieces = [(gate, DIAMOND)] + list(zip(arcs, RAINBOW))
    STEPS, HOLD_MS, TICK_MS = 7, 350, 110

    def paint(frame: int) -> None:
        total = STEPS * 2 + 1
        if frame > total:
            splash.destroy()
            root.deiconify()
            return
        if frame <= STEPS:
            t = frame / STEPS
        else:
            t = (total - frame) / STEPS
        for item, colour in pieces:
            canvas.itemconfig(item, outline=mix(BACKGROUND, colour, t))
        splash.after(TICK_MS if frame != STEPS else HOLD_MS, paint, frame + 1)

    paint(0)
    root.after(250, poll)
    root.mainloop()


if __name__ == "__main__":
    run_gui()
