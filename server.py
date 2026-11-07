"""Aseprite 1.3+ MCP bridge. Python 3.10+, standard library, JSON lines stdio."""
from __future__ import annotations

import argparse
import base64
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path(os.environ.get("ASEPRITE_MCP_HOME", Path(__file__).resolve().parent)).resolve()
VERSION = "1.0.0"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def integer(value, label, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{label} must be an integer in [{low}, {high}]")
    return value


def lua_string(value):
    # Lua uses decimal byte escapes, while JSON uses incompatible Unicode escapes.
    return '"' + "".join(f"\\{b:03d}" for b in str(value).encode("utf-8")) + '"'


class Bridge:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        config_path = self.root / "config.json"
        self.config = read_json(config_path) if config_path.is_file() else read_json(self.root / "config.example.json")
        configured_exe = self.config.get("aseprite_path", "")
        self.exe = Path(os.environ.get("ASEPRITE_PATH", configured_exe)) if (os.environ.get("ASEPRITE_PATH") or configured_exe) else Path("aseprite.exe")
        self.timeout = integer(self.config.get("timeout_sec", 45), "timeout_sec", 2, 300)
        self.state = self.root / ".state"
        self.queue = self.state / "live"
        self.outputs = self.root / "outputs"

    def path(self, value, *, exists=False):
        if not isinstance(value, str) or not value.strip() or "\x00" in value:
            raise ValueError("A nonempty filesystem path is required")
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = self.outputs / path
        path = path.resolve()
        if exists and not path.is_file():
            raise ValueError(f"Input file not found: {path}")
        return path

    def output(self, value, overwrite=False, extensions=None):
        path = self.path(value)
        if extensions and path.suffix.lower() not in extensions:
            raise ValueError(f"Output extension must be one of {sorted(extensions)}")
        if path.exists() and not overwrite:
            raise ValueError(f"Output exists; choose a new path or set overwrite=true: {path}")
        if path == self.exe.resolve() or path.is_relative_to(self.root / "lua"):
            raise ValueError("Output cannot replace the application or bridge runtime")
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)

    def process(self, args, timeout=None):
        if not self.exe.is_file():
            raise ValueError(f"Aseprite not found: {self.exe}; set ASEPRITE_PATH or config.json")
        return subprocess.run([str(self.exe), *args], capture_output=True, timeout=timeout or self.timeout,
                              stdin=subprocess.DEVNULL,
                              encoding="utf-8", errors="replace",
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

    def live_status(self):
        try:
            h = read_json(self.queue / "heartbeat.json")
            age = time.time() - h["updated"]
            return {"connected": 0 <= age < 4, "age_sec": round(age, 2), **h}
        except (OSError, ValueError, KeyError):
            return {"connected": False}

    def run(self, q, mode="batch"):
        if mode not in ("batch", "live"):
            raise ValueError("mode must be batch or live")
        if mode == "live" and not self.live_status()["connected"]:
            raise ValueError("Aseprite live bridge is offline. Call aseprite_connect or File > Scripts > Connect to Codex.")
        folder = self.queue if mode == "live" else self.state / "jobs" / uuid.uuid4().hex
        folder.mkdir(parents=True, exist_ok=True)
        job = f"{time.time_ns()}-{uuid.uuid4().hex}"
        request, response = folder / f"{job}.request.json", folder / f"{job}.response.json"
        ready = Path(str(response) + ".ready")
        q = {**q, "deadline": math.floor(time.time() + self.timeout)}
        write_json(request, q)
        if mode == "batch":
            proc = self.process(["-b", "--script-param", f"engine={self.root / 'lua/engine.lua'}",
                                 "--script-param", f"request={request}", "--script-param", f"response={response}",
                                 "--script", str(self.root / "lua/batch.lua")])
            if proc.returncode or not response.is_file():
                raise RuntimeError(f"Aseprite batch failed ({proc.returncode}): {proc.stderr[-4000:]} {proc.stdout[-4000:]}")
        else:
            deadline = time.monotonic() + self.timeout
            while not ready.is_file() and time.monotonic() < deadline:
                time.sleep(0.05)
            if not ready.is_file():
                request.unlink(missing_ok=True)
                raise TimeoutError(f"Live request timed out: {job}. It may have executed; inspect active document before retrying.")
        reply = read_json(response)
        if mode == "live":
            request.unlink(missing_ok=True)
            response.unlink(missing_ok=True)
            ready.unlink(missing_ok=True)
        if not reply.get("ok"):
            raise RuntimeError(reply.get("error", "Unknown Lua error"))
        if q.get("output") and not Path(q["output"]).is_file():
            raise RuntimeError(f"Aseprite returned without creating output: {q['output']}")
        return {"result": reply.get("result"), "mode": mode, "request_id": job,
                **({"output": q["output"]} if q.get("output") else {})}

    def prepare_live(self, destination):
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        self.queue.mkdir(parents=True, exist_ok=True)
        for name in ("bridge.lua", "main.lua", "package.json"):
            shutil.copy2(self.root / "extension" / name, destination / name)
        shutil.copy2(self.root / "lua/engine.lua", destination / "engine.lua")
        (destination / "settings.lua").write_text(
            f"return {{queue={lua_string(self.queue)},engine={lua_string(destination / 'engine.lua')}}}\n", encoding="utf-8")
        return destination

    def call(self, name, args):
        mode = args.get("mode", "batch")
        if name == "aseprite_viewer":
            from viewer_control import Viewer
            return Viewer(self).call(args)
        if name == "aseprite_status":
            p = self.process(["--version"])
            return {"version": p.stdout.strip() or p.stderr.strip(), "executable": str(self.exe),
                    "live": self.live_status(), "home": str(self.root), "output_dir": str(self.outputs),
                    "api_docs": "https://aseprite.org/api/"}
        if name == "aseprite_connect":
            if self.live_status()["connected"]:
                return {"connected": True, "started": False}
            prepared = self.prepare_live(self.state / "bootstrap")
            if args.get("launch", True):
                # Aseprite is the requested interactive tool; hide only its console window.
                log = self.state / "aseprite-ui.log"
                with log.open("ab") as out:
                    proc = subprocess.Popen([str(self.exe), "--script", str(prepared / "bridge.lua")],
                                            stdin=subprocess.DEVNULL, stdout=out, stderr=out,
                                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                for _ in range(60):
                    if self.live_status()["connected"]:
                        return {"connected": True, "started": True, "pid": proc.pid, "log": str(log)}
                    if proc.poll() is not None:
                        break
                    time.sleep(0.1)
                return {"connected": False, "pid": proc.pid, "log": str(log),
                        "next_step": "Check Aseprite for its Lua file-access prompt; allow the bridge and call aseprite_status."}
            return {"connected": False, "script": str(prepared / "bridge.lua"),
                    "next_step": "Run this script inside Aseprite, or use the installed Connect to Codex menu command."}
        if name == "aseprite_inspect":
            q = {"op": "info"}
            if args.get("input"):
                q["input"] = str(self.path(args["input"], exists=True))
            elif mode == "batch":
                raise ValueError("batch inspect requires input; live inspects the active document")
            return self.run(q, mode)
        if name == "aseprite_create":
            spec = args["spec"]
            self.validate_spec(spec)
            output = self.output(args["output"], args.get("overwrite", False), {".aseprite", ".ase"})
            return self.run({"op": "create", "spec": spec, "output": output}, mode)
        if name == "aseprite_eval":
            code = args["code"]
            if not isinstance(code, str) or not code.strip() or len(code.encode("utf-8")) > 1_048_576:
                raise ValueError("code must contain Lua source up to 1 MiB")
            q = {"op": "eval", "code": code, "transaction": args.get("transaction", True)}
            if args.get("input"):
                q["input"] = str(self.path(args["input"], exists=True))
            if args.get("output"):
                q["output"] = self.output(args["output"], args.get("overwrite", False), {".aseprite", ".ase"})
            if mode == "batch" and not q.get("output") and not args.get("read_only", False):
                raise ValueError("batch edits require output; for a read-only Lua query set read_only=true")
            return self.run(q, mode)
        if name in ("aseprite_export", "aseprite_preview"):
            q = {"op": "preview" if name.endswith("preview") else "export"}
            if args.get("input"):
                q["input"] = str(self.path(args["input"], exists=True))
            elif mode == "batch":
                raise ValueError("batch export/preview requires input")
            if q["op"] == "preview":
                q.update(frame=integer(args.get("frame", 1), "frame", 1, 100000),
                         scale=integer(args.get("scale", 1), "scale", 1, 16))
                output = args.get("output", f"preview-{uuid.uuid4().hex[:8]}.png")
                exts = {".png"}
            else:
                kind = args.get("kind", "image")
                if kind not in ("image", "sheet"):
                    raise ValueError("kind must be image or sheet")
                q.update(kind=kind, sheet_type=args.get("sheet_type", "horizontal"),
                         columns=integer(args.get("columns", 0), "columns", 0, 4096))
                if q["sheet_type"] not in ("horizontal", "vertical", "packed", "rows", "columns"):
                    raise ValueError("Unsupported sheet_type")
                output, exts = args["output"], {".png"} if kind == "sheet" else {".png", ".gif", ".webp"}
            q["output"] = self.output(output, args.get("overwrite", False), exts)
            if q.get("kind") == "sheet":
                q["data"] = self.output(args.get("data", str(Path(q["output"]).with_suffix(".json"))), args.get("overwrite", False), {".json"})
                if q["data"] == q["output"] or q.get("input") in (q["data"], q["output"]):
                    raise ValueError("Input, texture and metadata must have distinct paths")
            if mode == "live" and q["op"] == "export":
                # UI saveAs prompts for lossy formats (e.g. GIF discards tags).
                # Snapshot a native copy, then render in an isolated batch process.
                snapshot = self.state / "snapshots" / (uuid.uuid4().hex + ".aseprite")
                snapshot.parent.mkdir(parents=True, exist_ok=True)
                snapshot_request = {"op": "snapshot", "output": str(snapshot)}
                if q.get("input"):
                    snapshot_request["input"] = q["input"]
                self.run(snapshot_request, "live")
                try:
                    result = self.run({**q, "input": str(snapshot)}, "batch")
                    result["mode"] = "live-snapshot"
                finally:
                    snapshot.unlink(missing_ok=True)
            else:
                result = self.run(q, mode)
            result["files"] = [{"path": q[k], "bytes": Path(q[k]).stat().st_size} for k in ("output", "data") if q.get(k)]
            if q["op"] == "preview":
                image = Path(q["output"]).read_bytes()
                if len(image) > 8 * 1024 * 1024:
                    raise ValueError("Preview exceeds 8 MiB; reduce scale")
                result["_image"] = base64.b64encode(image).decode("ascii")
            return result
        raise ValueError(f"Unknown tool: {name}")

    @staticmethod
    def validate_spec(s):
        w, h = integer(s["width"], "width", 1, 4096), integer(s["height"], "height", 1, 4096)
        durations = s.get("durations_ms")
        if not isinstance(durations, list) or not 1 <= len(durations) <= 256 or w * h * len(durations) > 16_777_216:
            raise ValueError("Use 1–256 frames and at most 16 million canvas pixels total")
        for ms in durations:
            integer(ms, "duration_ms", 1, 65535)
        palette = s.get("palette", {})
        if not isinstance(palette, dict) or not palette:
            raise ValueError("palette must map single ASCII symbols to #RRGGBB or #RRGGBBAA")
        for symbol, c in palette.items():
            if len(symbol) != 1 or not 32 <= ord(symbol) <= 126 or not isinstance(c, str) or not re.fullmatch(r"#[\da-fA-F]{6}([\da-fA-F]{2})?", c):
                raise ValueError("Invalid palette symbol/color")
        layers = s.get("layers")
        if not isinstance(layers, list) or not 1 <= len(layers) <= 64 or w * h * len(durations) * len(layers) > 33_554_432:
            raise ValueError("Use 1–64 layers and at most 32 million layer pixels total")
        for layer in layers:
            if not isinstance(layer.get("name"), str) or not layer["name"] or len(layer["frames"]) > len(durations):
                raise ValueError("Each layer needs a name and no more frames than durations_ms")
            for cel in layer["frames"]:
                x = integer(cel.get("x", 0), "x", 0, w - 1)
                y = integer(cel.get("y", 0), "y", 0, h - 1)
                rows = cel["rows"]
                if not isinstance(rows, list) or len(rows) + y > h:
                    raise ValueError("Cel rows exceed height")
                for row in rows:
                    if not isinstance(row, str) or len(row) + x > w or any(c not in palette for c in row):
                        raise ValueError("Cel row exceeds width or uses undefined palette symbols")
        for tag in s.get("tags", []):
            integer(tag["from"], "tag.from", 1, len(durations))
            integer(tag["to"], "tag.to", tag["from"], len(durations))
            if not isinstance(tag.get("name"), str) or not tag["name"]:
                raise ValueError("Tag name is required")


def prop(t, description, **extra):
    return {"type": t, "description": description, **extra}


MODE = prop("string", "batch: separate file process; live: current Aseprite UI document", enum=["batch", "live"])
INPUT = prop("string", "Input file; required in batch, optional in live (opens a document)")
OUTPUT = prop("string", "Destination. Relative paths use the plugin's outputs directory")
OVERWRITE = prop("boolean", "Allow replacing this destination; defaults to false")


def tool(name, description, properties=None, required=(), read_only=False):
    return {"name": name, "description": description,
            "inputSchema": {"type": "object", "properties": properties or {}, "required": list(required), "additionalProperties": False},
            "annotations": {"readOnlyHint": read_only, "destructiveHint": not read_only,
                            "idempotentHint": read_only, "openWorldHint": False}}


TOOLS = [
    tool("aseprite_viewer", "Manage separately installed N7z/aseprite-live: watch saved sprite files, preview animations and replay save history in a local browser. Return URL for open_in_codex. Unsaved UI edits require saving before they appear.",
         {"action": prop("string", "start, status or stop", enum=["start", "status", "stop"]),
          "watch": prop("string", "Directory to watch; defaults to plugin outputs. Stop before changing directories."),
          "port": prop("integer", "Preferred local port, 0 chooses an ephemeral port", minimum=0, maximum=65535),
          "max_steps": prop("integer", "History versions per file (1–1000), used on startup", minimum=1, maximum=1000)}),
    tool("aseprite_status", "Check installed Aseprite version, paths and live bridge heartbeat", read_only=True),
    tool("aseprite_connect", "Connect to Aseprite's live canvas. Launches Aseprite with the bridge when offline; may show a Lua permission prompt.",
         {"launch": prop("boolean", "Launch Aseprite when offline; false prepares a script to run manually")}),
    tool("aseprite_inspect", "Read dimensions, layers, frames, tags and open UI documents", {"mode": MODE, "input": INPUT}, read_only=True),
    tool("aseprite_create", "Create an editable layered pixel sprite/animation using ASCII rows and a color palette. Frames and tags are 1-based.",
         {"mode": MODE, "output": OUTPUT, "overwrite": OVERWRITE,
          "spec": prop("object", "width,height,durations_ms:[100,...],palette:{'.':'#00000000','X':'#FF0000'},layers:[{name:'Body',frames:[{rows:['.XX.','XXXX'],x:0,y:0}]}],tags:[{name:'idle',from:1,to:2}]. All row symbols must be in palette.")}, ("output", "spec")),
    tool("aseprite_eval", "Execute Lua using the official Aseprite API (full Lua privileges). Use for drawing, layers, frames, palettes, tags, selections, transforms and commands. Return a JSON-serializable value. This is not a Lua sandbox; paths inside Lua are the caller's responsibility.",
         {"mode": MODE, "input": INPUT, "output": OUTPUT, "overwrite": OVERWRITE,
          "code": prop("string", "Lua source; app.sprite is available after input opens"),
          "transaction": prop("boolean", "Wrap in a named undo transaction, default true; false for commands requiring their own transaction"),
          "read_only": prop("boolean", "Declare a query without saving in batch; does not restrict Lua privileges")}, ("code",)),
    tool("aseprite_export", "Export PNG/GIF/WebP or PNG sprite sheet with JSON frame/layer/tag metadata",
         {"mode": MODE, "input": INPUT, "output": OUTPUT, "overwrite": OVERWRITE,
          "kind": prop("string", "image or sheet", enum=["image", "sheet"]),
          "data": prop("string", "Sprite sheet JSON path; default output with .json extension"),
          "sheet_type": prop("string", "Sheet layout", enum=["horizontal", "vertical", "packed", "rows", "columns"]),
          "columns": prop("integer", "Column count for rows layout", minimum=0, maximum=4096)}, ("output",)),
    tool("aseprite_preview", "Render one frame to PNG and return an inline MCP image, with integer scaling for pixel art",
         {"mode": MODE, "input": INPUT, "output": OUTPUT, "overwrite": OVERWRITE,
          "frame": prop("integer", "1-based frame number", minimum=1),
          "scale": prop("integer", "Integer magnification, 1–16", minimum=1, maximum=16)}),
]


def rpc(message, bridge):
    ident, method = message.get("id"), message.get("method")
    if "id" not in message:
        return None
    result = None
    if method == "initialize":
        requested = message.get("params", {}).get("protocolVersion")
        result = {"protocolVersion": requested if requested in ("2024-11-05", "2025-03-26", "2025-06-18") else "2024-11-05",
                  "capabilities": {"tools": {}}, "serverInfo": {"name": "aseprite-local", "version": VERSION}}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        try:
            params = message["params"]
            name = params["name"]
            spec = next((t for t in TOOLS if t["name"] == name), None)
            if spec is None:
                raise ValueError(f"Unknown tool: {name}")
            args = params.get("arguments", {})
            if not isinstance(args, dict):
                raise ValueError("arguments must be an object")
            schema = spec["inputSchema"]
            if set(args) - set(schema["properties"]) or set(schema["required"]) - set(args):
                raise ValueError("Unknown or missing tool arguments")
            from viewer_control import Viewer
            viewer = Viewer(bridge)
            observed = json.loads(json.dumps(message))
            for key in ("input", "output"):
                value_path = observed.get("params", {}).get("arguments", {}).get(key)
                if value_path:
                    observed["params"]["arguments"][key] = str(bridge.path(value_path))
            if name != "aseprite_viewer":
                viewer.event(observed, "begin")
            try:
                value = bridge.call(name, args)
            except Exception:
                if name != "aseprite_viewer":
                    viewer.event({"jsonrpc":"2.0","id":ident,"result":{"isError":True}}, "end")
                raise
            if name != "aseprite_viewer":
                viewer.event({"jsonrpc":"2.0","id":ident,"result":{"isError":False}}, "end")
            image = value.pop("_image", None)
            content = [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]
            if image:
                content.append({"type": "image", "mimeType": "image/png", "data": image})
            result = {"content": content, "isError": False}
        except Exception as exc:
            result = {"content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}], "isError": True}
    else:
        return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": "Method not found"}}
    return {"jsonrpc": "2.0", "id": ident, "result": result}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=ROOT)
    parser.add_argument("--call", help="Direct CLI tool name for diagnostics")
    parser.add_argument("--args", default="{}", help="Direct CLI arguments JSON")
    args = parser.parse_args()
    bridge = Bridge(args.home)
    if args.call:
        value = bridge.call(args.call, json.loads(args.args))
        value.pop("_image", None)
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return
    for line in sys.stdin:
        try:
            message = json.loads(line)
            if not isinstance(message, dict):
                raise ValueError("JSON-RPC message must be an object")
            reply = rpc(message, bridge)
        except Exception as exc:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}
        if reply is not None:
            print(json.dumps(reply, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
