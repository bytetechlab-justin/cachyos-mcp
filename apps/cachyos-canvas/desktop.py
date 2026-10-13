"""Install the user menu shortcut; no root privileges needed."""

import os
from pathlib import Path

app = Path(__file__).resolve().parent
target = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
target = target / "applications/cachy-canvas.desktop"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(
    "[Desktop Entry]\nType=Application\nName=Cachy Canvas\n"
    "Comment=Local AI image generation\n"
    f'Exec=bash "{app / "launch.sh"}"\n'
    f"Icon={app / 'icon.svg'}\nTerminal=false\nCategories=Graphics;\n",
    encoding="utf-8",
)
print(f"Menu shortcut: {target}")
