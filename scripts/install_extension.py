"""Install this bridge's menu extension, preserving a previous version."""
import argparse
from datetime import datetime
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server import Bridge, read_json

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--destination", type=Path, required=True, help="Absolute Aseprite extensions directory")
args = parser.parse_args()
if not args.destination.is_absolute():
    parser.error("destination must be absolute")
target = args.destination / "codex-aseprite-bridge"
if target.exists():
    manifest = target / "package.json"
    if not manifest.is_file() or read_json(manifest).get("name") != "codex-aseprite-bridge":
        raise SystemExit("Destination belongs to another extension; refusing to replace it")
    backup = ROOT / ".state" / ("extension-backup-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    shutil.copytree(target, backup)
Bridge().prepare_live(target)
print(f"Installed Aseprite extension: {target}. Restart Aseprite, then File > Scripts > Connect to Codex.")
