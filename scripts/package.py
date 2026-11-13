"""Bundle the build into one board package that descent (the board viewer) opens: build/<board>-rev<rev>.zip

    python3 scripts/package.py <board> <out dir>

The zip holds the files below, flat, plus board.json, the manifest descent reads first:

  {"format": 1,                  package format version, raised when descent must read it differently
   "title", "rev", "date",       from the PCB's title block
   "commit",                     git describe of the source, "-dirty" if the repository had uncommitted changes
   "files": {role: file name}}   the roles are the keys of FILES below
"""
import json
import re
import subprocess
import sys
import zipfile

board, out = sys.argv[1:]
FILES = {  # role -> path
    "schematic": f"hw/{board}.kicad_sch",
    "pcb": f"hw/{board}.kicad_pcb",
    "model": f"{out}/{board}.glb",
    "schematicPdf": f"{out}/{board}-schematic.pdf",
    "gerbers": f"{out}/{board}-gerbers.zip",
    "bom": f"{out}/{board}-bom.csv",
    "cpl": f"{out}/{board}-cpl.csv",
}


def title_block(pcb):
    """title, rev and date from the PCB's (title_block ...)."""
    with open(pcb) as f:
        text = f.read()
    return {k: re.search(rf'\({k} "([^"]*)"\)', text).group(1) for k in ("title", "rev", "date")}


def main():
    info = title_block(FILES["pcb"])
    commit = subprocess.run(["git", "describe", "--always", "--dirty"], capture_output=True, text=True,
                            check=True).stdout.strip()
    manifest = {"format": 1, **info, "commit": commit,
                "files": {role: path.rsplit("/", 1)[-1] for role, path in FILES.items()}}

    package = f"{out}/{board}-rev{info['rev']}.zip"
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("board.json", json.dumps(manifest, indent=2) + "\n")
        for path in FILES.values():
            z.write(path, path.rsplit("/", 1)[-1])
    print(f"Board package: {package} ({commit})")


main()
