#!/bin/sh
# Install/update only our applet and place it once, top right on the primary desktop.
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ -f /.flatpak-info ]; then
    exec /usr/bin/flatpak-spawn --host "$PROJECT_DIR/scripts/install-ram-widget.sh" "$@"
fi
if kpackagetool6 --type Plasma/Applet --show org.cachyos.ramgauge >/dev/null 2>&1; then
    kpackagetool6 --type Plasma/Applet --upgrade "$PROJECT_DIR/plasma/org.cachyos.ramgauge"
else
    kpackagetool6 --type Plasma/Applet --install "$PROJECT_DIR/plasma/org.cachyos.ramgauge"
fi
qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript '
const plugin = "org.cachyos.ramgauge";
const shown = desktops().filter(d => d.screen >= 0);
if (!shown.length) throw new Error("No desktop found; add RAM Gauge using Add Widgets.");
if (shown.some(d => d.widgets().some(w => w.type === plugin))) {
    print("RAM Gauge is already on the desktop.");
} else {
    const desktop = shown.find(d => d.screen === 0) || shown[0];
    const size = 220;
    desktop.addWidget(plugin, screenGeometry(desktop.screen).width - size - 48, 48, size, size);
    print("RAM Gauge added to the desktop on screen " + desktop.screen + ".");
}
'
