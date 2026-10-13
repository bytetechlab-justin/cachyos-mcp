#!/bin/sh
# Install/update only our applet and add it beside the tray on each bottom panel.
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ -f /.flatpak-info ]; then
    exec /usr/bin/flatpak-spawn --host "$PROJECT_DIR/scripts/install-usage-widget.sh" "$@"
fi
if kpackagetool6 --type Plasma/Applet --show org.cachyos.agentusage >/dev/null 2>&1; then
    kpackagetool6 --type Plasma/Applet --upgrade "$PROJECT_DIR/plasma/org.cachyos.agentusage"
else
    kpackagetool6 --type Plasma/Applet --install "$PROJECT_DIR/plasma/org.cachyos.agentusage"
fi
qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript '
const plugin = "org.cachyos.agentusage";
const targets = panels().filter(p => p.location === "bottom");
if (!targets.length) throw new Error("No bottom panel found; add CachyOS Agent Usage using Add Widgets.");
for (const panel of targets) {
    const widgets = panel.widgets();
    if (widgets.some(w => w.type === plugin)) continue;
    const tray = widgets.find(w => w.type === "org.kde.plasma.systemtray");
    const widget = panel.addWidget(plugin);
    if (tray) widget.index = tray.index;
}
print("Agent usage widget installed on " + targets.length + " bottom panel(s).");
'
