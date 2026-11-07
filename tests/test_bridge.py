"""Integration checks run against the installed Aseprite executable."""
import json
from pathlib import Path
import struct
import subprocess
import sys
import unittest
import uuid
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import Bridge, ROOT, TOOLS


def sample():
    return {"width": 8, "height": 8, "durations_ms": [120, 160],
            "palette": {".": "#00000000", "X": "#E87BB8", "O": "#322449"},
            "layers": [{"name": "像素角色", "frames": [
                {"rows": ["..XXXX..", ".XXXXXX.", "XXOXXOXX", "XXXXXXXX", ".XOOOX..", "..XXX...", "..X.X...", "........"]},
                {"rows": ["..XXXX..", ".XXXXXX.", "XXOXXOXX", "XXXXXXXX", ".XOOOX..", "..XXX...", ".X...X..", "........"]}]}],
            "tags": [{"name": "idle", "from": 1, "to": 2}]}


class Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = Bridge()
        cls.dir = ROOT / "outputs" / ("验收-" + uuid.uuid4().hex[:8])
        cls.dir.mkdir(parents=True)
        cls.sprite = str(cls.dir / "角色.aseprite")
        cls.b.call("aseprite_create", {"spec": sample(), "output": cls.sprite})

    def test_01_native_file_and_pixels(self):
        data = Path(self.sprite).read_bytes()
        self.assertEqual(struct.unpack_from("<H", data, 4)[0], 0xA5E0)
        info = self.b.call("aseprite_inspect", {"input": self.sprite})["result"]
        self.assertEqual((info["width"], info["height"]), (8, 8))
        self.assertEqual(info["layers"][0]["name"], "像素角色")
        self.assertEqual([f["duration_ms"] for f in info["frames"]], [120, 160])
        self.assertEqual(info["tags"][0]["name"], "idle")
        result = self.b.call("aseprite_eval", {"input": self.sprite, "read_only": True,
            "code": "local p=app.sprite.cels[1].image:getPixel(2,0); return {r=app.pixelColor.rgbaR(p),a=app.pixelColor.rgbaA(p)}"})["result"]
        self.assertEqual(result, {"r": 232, "a": 255})

    def test_02_lua_edit_and_persistence(self):
        output = str(self.dir / "编辑后.aseprite")
        self.b.call("aseprite_eval", {"input": self.sprite, "output": output,
            "code": "app.sprite.layers[1].name='修改图层'; local l=app.sprite:newLayer(); l.name='光效'; return {layers=#app.sprite.layers}"})
        info = self.b.call("aseprite_inspect", {"input": output})["result"]
        self.assertEqual([l["name"] for l in info["layers"]], ["修改图层", "光效"])
        self.assertEqual(len(self.b.call("aseprite_inspect", {"input": self.sprite})["result"]["layers"]), 1)

    def test_03_exports(self):
        out = str(self.dir / "sheet.png")
        self.b.call("aseprite_export", {"input": self.sprite, "output": out, "kind": "sheet"})
        meta = json.loads(Path(out).with_suffix(".json").read_text(encoding="utf-8"))
        self.assertEqual(len(meta["frames"]), 2)
        self.assertEqual(meta["meta"]["frameTags"][0]["name"], "idle")
        gif = str(self.dir / "animation.gif")
        self.b.call("aseprite_export", {"input": self.sprite, "output": gif})
        self.assertIn(Path(gif).read_bytes()[:6], (b"GIF87a", b"GIF89a"))
        info = self.b.call("aseprite_inspect", {"input": gif})["result"]
        self.assertEqual(len(info["frames"]), 2)
        png=str(self.dir / "single.png")
        self.b.call("aseprite_export", {"input":self.sprite,"output":png})
        self.assertEqual(struct.unpack_from(">II",Path(png).read_bytes(),16),(8,8))

    def test_04_preview(self):
        out = str(self.dir / "preview.png")
        r = self.b.call("aseprite_preview", {"input": self.sprite, "output": out, "scale": 16})
        self.assertIn("_image", r)
        self.assertEqual(struct.unpack_from(">II", Path(out).read_bytes(), 16), (128, 128))

    def test_05_failures(self):
        with self.assertRaisesRegex(ValueError, "Output exists"):
            self.b.call("aseprite_create", {"spec": sample(), "output": self.sprite})
        with self.assertRaisesRegex(RuntimeError, "intentional"):
            self.b.call("aseprite_eval", {"read_only": True, "code": "error('intentional')"})
        with self.assertRaisesRegex(ValueError, "batch edits require output"):
            self.b.call("aseprite_eval", {"code": "Sprite(8,8)"})
        broken = sample(); broken["layers"][0]["frames"][0]["rows"] = ["?" * 9]
        with self.assertRaises(ValueError):
            self.b.validate_spec(broken)

    def test_06_stdio_protocol(self):
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "aseprite_inspect", "arguments": {"input": self.sprite}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "aseprite_eval", "arguments": {"code": "error('rpc error')", "read_only": True}}},
        ]
        p = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "server.py")],
                           input="\n".join(json.dumps(m) for m in messages) + "\n",
                           capture_output=True, encoding="utf-8", timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        replies = [json.loads(line) for line in p.stdout.splitlines()]
        self.assertEqual([r["id"] for r in replies], [1, 2, 3, 4])
        self.assertEqual(replies[0]["result"]["protocolVersion"], "2025-03-26")
        self.assertEqual(len(replies[1]["result"]["tools"]), len(TOOLS))
        self.assertFalse(replies[2]["result"]["isError"])
        self.assertTrue(replies[3]["result"]["isError"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
