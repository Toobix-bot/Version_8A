#!/usr/bin/env python3
"""Interactive control panel for ECHO bridge, MCP backend, and Cloudflare tunnel.

This lightweight Tkinter UI lets you:
- Start/stop the MCP HTTP server
- Start/stop the FastAPI bridge
- Start/stop a Cloudflared quick tunnel pointing at the bridge
- Detect and display the public tunnel URL
- Run a built-in smoke test against local and public endpoints
- Inspect combined logs in real time

The script only depends on the Python standard library. It is designed to be
run from the repository root (`python tools/control_panel.py`).
"""

from __future__ import annotations

import json
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PYTHON = sys.executable or "python"
DEFAULT_CLOUDFLARED = "cloudflared.exe" if os.name == "nt" else "cloudflared"
TUNNEL_URL_PATTERN = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")


class ProcessEntry:
    """Track a managed subprocess and its reader thread."""

    def __init__(self) -> None:
        self.proc: Optional[subprocess.Popen[str]] = None
        self.thread: Optional[threading.Thread] = None


class ControlPanel(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("ECHO Bridge Control Panel")
        self.geometry("960x640")

        self.log_queue: "queue.Queue[tuple[str, str]]" = queue.Queue()
        self.processes: Dict[str, ProcessEntry] = {
            "mcp": ProcessEntry(),
            "bridge": ProcessEntry(),
            "tunnel": ProcessEntry(),
        }

        self.python_var = tk.StringVar(value=str(DEFAULT_PYTHON))
        self.bridge_host_var = tk.StringVar(value="127.0.0.1")
        self.bridge_port_var = tk.StringVar(value="3333")
        self.mcp_host_var = tk.StringVar(value="127.0.0.1")
        self.mcp_port_var = tk.StringVar(value="3339")
        self.cloudflared_var = tk.StringVar(value=self._discover_cloudflared())
        self.public_base_var = tk.StringVar(value="")
        self.auto_public_var = tk.BooleanVar(value=True)
        self.tunnel_url_var = tk.StringVar(value="")
        self.connector_url_var = tk.StringVar(value="")
        self.alt_connector_url_var = tk.StringVar(value="")
        self._last_synced_public = ""

        self.tunnel_url_var.trace_add("write", lambda *_: self._refresh_connector_urls())
        self.public_base_var.trace_add("write", lambda *_: self._refresh_connector_urls())
        self._refresh_connector_urls()

        self.status_vars = {
            "mcp": tk.StringVar(value="stopped"),
            "bridge": tk.StringVar(value="stopped"),
            "tunnel": tk.StringVar(value="stopped"),
        }

        self._build_ui()
        self.after(200, self._drain_log_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        main = ttk.Frame(self)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        config_frame = ttk.LabelFrame(main, text="Configuration")
        config_frame.pack(fill=tk.X, pady=(0, 10))

        self._add_labeled_entry(config_frame, "Python executable", self.python_var, 0, span=3, browse=True)
        self._add_labeled_entry(config_frame, "Cloudflared path", self.cloudflared_var, 1, span=3, browse=True)

        self._add_labeled_entry(config_frame, "Bridge host", self.bridge_host_var, 2)
        self._add_labeled_entry(config_frame, "Bridge port", self.bridge_port_var, 2, column=2)
        self._add_labeled_entry(config_frame, "MCP host", self.mcp_host_var, 3)
        self._add_labeled_entry(config_frame, "MCP port", self.mcp_port_var, 3, column=2)

        ttk.Label(config_frame, text="PUBLIC_BASE_URL override").grid(row=4, column=0, sticky=tk.W, pady=4)
        ttk.Entry(config_frame, textvariable=self.public_base_var, width=55).grid(row=4, column=1, sticky=tk.EW, pady=4)
        ttk.Checkbutton(config_frame, text="Auto-apply tunnel URL", variable=self.auto_public_var).grid(row=4, column=2, sticky=tk.W)

        config_frame.columnconfigure(1, weight=1)

        status_frame = ttk.Frame(main)
        status_frame.pack(fill=tk.X, pady=(0, 10))
        self._add_status_label(status_frame, "MCP", "mcp", 0)
        self._add_status_label(status_frame, "Bridge", "bridge", 1)
        self._add_status_label(status_frame, "Tunnel", "tunnel", 2)

        control_frame = ttk.Frame(main)
        control_frame.pack(fill=tk.X)
        self._add_control_buttons(control_frame)

        tunnel_frame = ttk.LabelFrame(main, text="Tunnel")
        tunnel_frame.pack(fill=tk.X, pady=(10, 10))
        ttk.Label(tunnel_frame, text="Detected public URL:").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(tunnel_frame, textvariable=self.tunnel_url_var, state="readonly", width=80).grid(row=0, column=1, sticky=tk.EW, padx=5)
        ttk.Button(tunnel_frame, text="Copy", command=self._copy_tunnel_url).grid(row=0, column=2)
        ttk.Button(tunnel_frame, text="Set as PUBLIC_BASE_URL", command=self._apply_tunnel_to_public).grid(row=0, column=3, padx=5)

        ttk.Label(tunnel_frame, text="ChatGPT connector URL (/mcp):").grid(row=1, column=0, sticky=tk.W, pady=(6, 0))
        ttk.Entry(tunnel_frame, textvariable=self.connector_url_var, state="readonly", width=80).grid(row=1, column=1, sticky=tk.EW, padx=5, pady=(6, 0))
        ttk.Button(tunnel_frame, text="Copy", command=lambda: self._copy_to_clipboard(self.connector_url_var.get(), "Connector URL")).grid(row=1, column=2, pady=(6, 0))

        ttk.Label(tunnel_frame, text="Alternate path (/mcp_app):").grid(row=2, column=0, sticky=tk.W)
        ttk.Entry(tunnel_frame, textvariable=self.alt_connector_url_var, state="readonly", width=80).grid(row=2, column=1, sticky=tk.EW, padx=5)
        ttk.Button(tunnel_frame, text="Copy", command=lambda: self._copy_to_clipboard(self.alt_connector_url_var.get(), "Alternate URL")).grid(row=2, column=2)
        tunnel_frame.columnconfigure(1, weight=1)

        smoke_frame = ttk.LabelFrame(main, text="Smoke test")
        smoke_frame.pack(fill=tk.X)
        ttk.Button(smoke_frame, text="Run smoke test", command=self._run_smoke_test_async).grid(row=0, column=0, padx=5, pady=5)
        self.smoke_status = ttk.Label(smoke_frame, text="Idle")
        self.smoke_status.grid(row=0, column=1, sticky=tk.W)

        log_frame = ttk.LabelFrame(main, text="Logs")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        self.log_text = tk.Text(log_frame, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=scroll.set)

    def _add_labeled_entry(
        self,
        master: ttk.Frame,
        label: str,
        variable: tk.StringVar,
        row: int,
        column: int = 0,
        span: int = 1,
        browse: bool = False,
    ) -> None:
        ttk.Label(master, text=label).grid(row=row, column=column, sticky=tk.W, pady=4, padx=(0, 4))
        entry = ttk.Entry(master, textvariable=variable)
        entry.grid(row=row, column=column + 1, sticky=tk.EW, pady=4)
        if span > 1:
            master.grid_columnconfigure(column + 1, weight=1)
        if browse:
            button = ttk.Button(master, text="Browse", command=lambda v=variable: self._pick_file(v))
            button.grid(row=row, column=column + span, padx=4, pady=4)

    def _add_status_label(self, master: ttk.Frame, label: str, key: str, column: int) -> None:
        frame = ttk.Frame(master)
        frame.grid(row=0, column=column, padx=5)
        ttk.Label(frame, text=f"{label}:").pack(side=tk.LEFT)
        status_lbl = ttk.Label(frame, textvariable=self.status_vars[key], foreground="red")
        status_lbl.pack(side=tk.LEFT)

    def _add_control_buttons(self, master: ttk.Frame) -> None:
        ttk.Button(master, text="Start MCP", command=self.start_mcp).grid(row=0, column=0, padx=5, pady=5)
        ttk.Button(master, text="Stop MCP", command=lambda: self.stop_process("mcp")).grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(master, text="Start Bridge", command=self.start_bridge).grid(row=0, column=2, padx=5, pady=5)
        ttk.Button(master, text="Stop Bridge", command=lambda: self.stop_process("bridge")).grid(row=0, column=3, padx=5, pady=5)
        ttk.Button(master, text="Start Tunnel", command=self.start_tunnel).grid(row=0, column=4, padx=5, pady=5)
        ttk.Button(master, text="Stop Tunnel", command=lambda: self.stop_process("tunnel")).grid(row=0, column=5, padx=5, pady=5)

    # ------------------------------------------------------------------ Helpers
    def _discover_cloudflared(self) -> str:
        candidates = [
            BASE_DIR / DEFAULT_CLOUDFLARED,
            Path.cwd() / DEFAULT_CLOUDFLARED,
            Path(DEFAULT_CLOUDFLARED),
        ]
        for path in candidates:
            if path.exists():
                return str(path)
        return DEFAULT_CLOUDFLARED

    def log(self, message: str, key: str = "app") -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_queue.put((key, f"[{timestamp}] {message}\n"))

    def _pick_file(self, var: tk.StringVar) -> None:
        path = filedialog.askopenfilename()
        if path:
            var.set(path)

    def _copy_to_clipboard(self, value: str, label: str) -> None:
        if not value:
            messagebox.showinfo(label, "Nothing to copy yet.")
            return
        self.clipboard_clear()
        self.clipboard_append(value)
        messagebox.showinfo(label, f"Copied to clipboard:\n{value}")

    def _copy_tunnel_url(self) -> None:
        self._copy_to_clipboard(self.tunnel_url_var.get(), "Tunnel URL")

    def _apply_tunnel_to_public(self) -> None:
        url = self.tunnel_url_var.get()
        if not url:
            messagebox.showwarning("Tunnel", "No tunnel URL to apply.")
            return
        self.public_base_var.set(url)
        messagebox.showinfo("Tunnel", f"Set PUBLIC_BASE_URL to {url}")
        self._refresh_connector_urls()

    # ------------------------------------------------------------------ Process control
    def start_mcp(self) -> None:
        command = [
            self.python_var.get() or DEFAULT_PYTHON,
            "run_mcp_http.py",
            "--host",
            self.mcp_host_var.get(),
            "--port",
            self.mcp_port_var.get(),
        ]
        self._start_process("mcp", command, cwd=str(BASE_DIR))

    def start_bridge(self) -> None:
        command = [
            self.python_var.get() or DEFAULT_PYTHON,
            "-m",
            "uvicorn",
            "echo_bridge.main:app",
            "--host",
            self.bridge_host_var.get(),
            "--port",
            self.bridge_port_var.get(),
        ]
        env = os.environ.copy()
        if self.public_base_var.get().strip():
            env["PUBLIC_BASE_URL"] = self.public_base_var.get().strip()
        self._start_process("bridge", command, cwd=str(BASE_DIR), env=env)

    def start_tunnel(self) -> None:
        cloudflared = Path(self.cloudflared_var.get())
        if not cloudflared.exists():
            messagebox.showerror("Cloudflared", f"cloudflared not found: {cloudflared}")
            return
        url = f"http://{self.bridge_host_var.get()}:{self.bridge_port_var.get()}"
        command = [
            str(cloudflared),
            "tunnel",
            "--no-autoupdate",
            "--url",
            url,
        ]
        self._start_process("tunnel", command, cwd=str(BASE_DIR))

    def _start_process(self, key: str, command: List[str], cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None) -> None:
        entry = self.processes[key]
        if entry.proc and entry.proc.poll() is None:
            messagebox.showinfo("Process", f"{key} already running.")
            return
        try:
            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            proc = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=creationflags,
            )
        except FileNotFoundError as exc:
            messagebox.showerror("Process", f"Failed to start {key}: {exc}")
            return
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Process", f"Failed to start {key}: {exc}")
            return

        entry.proc = proc
        entry.thread = threading.Thread(target=self._watch_process_output, args=(key,), daemon=True)
        entry.thread.start()
        self._set_status(key, "running")
        self.log(f"Started {' '.join(command)}", key)

    def stop_process(self, key: str) -> None:
        entry = self.processes[key]
        proc = entry.proc
        if not proc or proc.poll() is not None:
            self.log(f"{key} is not running", key)
            self._set_status(key, "stopped")
            return
        self.log(f"Stopping {key}...", key)
        try:
            if os.name == "nt":
                proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
                time.sleep(0.5)
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        except Exception as exc:  # noqa: BLE001
            self.log(f"Error stopping {key}: {exc}", key)
        finally:
            entry.proc = None
            self._set_status(key, "stopped")

    # ------------------------------------------------------------------ Process output reader
    def _watch_process_output(self, key: str) -> None:
        entry = self.processes[key]
        proc = entry.proc
        if not proc or not proc.stdout:
            return
        for raw_line in proc.stdout:
            line = raw_line.rstrip("\n")
            self.log(line, key)
            if key == "tunnel":
                match = TUNNEL_URL_PATTERN.search(line)
                if match:
                    url = match.group(0)
                    self.tunnel_url_var.set(url)
                    self.log(f"Detected tunnel URL: {url}", key="app")
                    if self.auto_public_var.get():
                        self.public_base_var.set(url)
                    self._refresh_connector_urls()
        code = proc.wait()
        self.log(f"{key} exited with code {code}", key)
        self._set_status(key, "stopped")
        entry.proc = None

    def _refresh_connector_urls(self) -> None:
        base = self.tunnel_url_var.get().strip() or self.public_base_var.get().strip()
        if not base:
            self.connector_url_var.set("")
            self.alt_connector_url_var.set("")
            return
        base = base.rstrip("/")
        self.connector_url_var.set(f"{base}/mcp")
        self.alt_connector_url_var.set(f"{base}/mcp_app")
        if base != self._last_synced_public:
            self._rewrite_public_specs(base)
            self._last_synced_public = base

    def _rewrite_public_specs(self, base: str) -> None:
        public_dir = BASE_DIR / "public"
        manifests = [
            public_dir / "chatgpt_tool_manifest.json",
            public_dir / "chatgpt_tool_manifest.generated.json",
        ]
        openapis = [
            public_dir / "openapi.json",
            public_dir / "openapi.generated.json",
        ]

        target_openapi_url = f"{base}/openapi.json"
        for path in manifests:
            if not path.exists():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                api = data.setdefault("api", {})
                api.setdefault("type", "openapi")
                api["url"] = target_openapi_url
                path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                self.log(f"Updated manifest URL in {path.name} -> {target_openapi_url}", key="app")
            except Exception as exc:  # noqa: BLE001
                self.log(f"Failed to update {path.name}: {exc}", key="app")

        for path in openapis:
            if not path.exists():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                data["servers"] = [{"url": base}]
                path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                self.log(f"Updated OpenAPI servers in {path.name} -> {base}", key="app")
            except Exception as exc:  # noqa: BLE001
                self.log(f"Failed to update {path.name}: {exc}", key="app")

    def _drain_log_queue(self) -> None:
        try:
            while True:
                key, message = self.log_queue.get_nowait()
                self.log_text.configure(state=tk.NORMAL)
                self.log_text.insert(tk.END, f"[{key}] {message}")
                self.log_text.configure(state=tk.DISABLED)
                self.log_text.see(tk.END)
        except queue.Empty:
            pass
        self.after(200, self._drain_log_queue)

    def _set_status(self, key: str, status: str) -> None:
        var = self.status_vars[key]
        var.set(status)

    # ------------------------------------------------------------------ Smoke test
    def _run_smoke_test_async(self) -> None:
        threading.Thread(target=self._run_smoke_test, daemon=True).start()

    def _run_smoke_test(self) -> None:
        self.smoke_status.configure(text="Running...")
        try:
            results = self._collect_smoke_results()
        except Exception as exc:  # noqa: BLE001
            self.smoke_status.configure(text=f"Error: {exc}")
            return
        summary = [f"{name}: {status}" for name, status in results]
        self.smoke_status.configure(text=" | ".join(summary) or "No checks")
        self.log("Smoke test results:\n" + "\n".join(f" - {name}: {status}" for name, status in results), key="smoke")

    def _collect_smoke_results(self) -> List[tuple[str, str]]:
        bridge_base = f"http://{self.bridge_host_var.get()}:{self.bridge_port_var.get()}"
        public_base = self.tunnel_url_var.get().strip() or self.public_base_var.get().strip()
        targets: List[tuple[str, str]] = [
            ("Local openapi", f"{bridge_base}/openapi.json"),
            ("Local manifest", f"{bridge_base}/chatgpt_tool_manifest.json"),
            ("Local MCP openapi", f"{bridge_base}/mcp/openapi.json"),
        ]
        if public_base:
            targets.extend(
                [
                    ("Public openapi", f"{public_base}/openapi.json"),
                    ("Public manifest", f"{public_base}/chatgpt_tool_manifest.json"),
                    ("Public MCP openapi", f"{public_base}/mcp/openapi.json"),
                    ("Public MCP SSE", f"{public_base}/mcp"),
                ]
            )
        else:
            targets.append(("Public", "No public URL set"))
        results: List[tuple[str, str]] = []
        for name, url in targets:
            if url.startswith("No public"):
                results.append((name, url))
                continue
            results.append((name, self._probe_url(name, url)))
        return results

    def _probe_url(self, name: str, url: str) -> str:
        headers = {"User-Agent": "ECHO-Control-Panel/1.0"}
        if "manifest" in url or "openapi" in url:
            headers["Origin"] = "https://chat.openai.com"
        if name.endswith("SSE"):
            headers["Accept"] = "text/event-stream"
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=8) as resp:
                status = resp.status
                content_type = resp.headers.get("Content-Type", "?")
                origin = resp.headers.get("Access-Control-Allow-Origin", "")
                if name.endswith("SSE"):
                    # Try to read a small chunk to ensure stream
                    try:
                        _ = resp.read(32)
                        return f"{status} stream"
                    except Exception as exc:  # noqa: BLE001
                        return f"{status} stream error: {exc}"
                extra = f"CT={content_type}"
                if origin:
                    extra += f" ACAO={origin}"
                return f"{status} {extra}"
        except urllib.error.HTTPError as exc:
            return f"HTTP {exc.code}: {exc.reason}"
        except urllib.error.URLError as exc:
            return f"Error: {exc.reason}"

    # ------------------------------------------------------------------ Shutdown
    def _on_close(self) -> None:
        if messagebox.askokcancel("Quit", "Stop all processes and exit?"):
            for key in list(self.processes.keys()):
                self.stop_process(key)
            self.destroy()


def main() -> None:
    app = ControlPanel()
    app.mainloop()


if __name__ == "__main__":
    main()
