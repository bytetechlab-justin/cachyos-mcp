import QtQuick
import QtQuick.Layouts
import QtQuick.Shapes
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.plasma5support as P5Support
import org.kde.ksysguard.sensors as Sensors

PlasmoidItem {
    id: root
    preferredRepresentation: fullRepresentation
    Plasmoid.backgroundHints: PlasmaCore.Types.NoBackground
    property bool busy: false
    property string notice: ""
    readonly property bool ready: percent.value !== undefined && total.value !== undefined
    readonly property real level: ready ? Math.max(0, Math.min(100, Number(percent.value))) : 0
    readonly property color levelColor: level >= 85 ? Kirigami.Theme.negativeTextColor
        : level >= 65 ? Kirigami.Theme.neutralTextColor : Kirigami.Theme.highlightColor
    readonly property string script: decodeURIComponent(
        Qt.resolvedUrl("../code/reclaim.sh").toString().replace(/^file:\/\//, ""))
    toolTipMainText: "Memory"
    toolTipSubText: ready ? "In use: " + gib(used.value) + " of " + gib(total.value) + " GiB"
        + "\nApplications: " + gib(application.value) + " GiB · Cache: " + gib(cache.value) + " GiB"
        + "\nSwap: " + gib(swap.value) + " GiB"
        + "\nClick to reclaim idle memory. Nothing is closed or deleted."
        : "Memory statistics are unavailable"

    function gib(bytes) {
        return bytes === undefined ? "—" : (Number(bytes) / 1073741824).toFixed(1);
    }
    function free() {
        if (busy)
            return;
        busy = true;
        notice = "";
        runner.connectSource("sh '" + script.replace(/'/g, "'\\''") + "'");
    }
    function finish(output) {
        busy = false;
        const match = /freed_kb=(\d+)/.exec(output);
        if (!match)
            notice = "Unavailable";
        else if (Number(match[1]) < 51200)
            notice = "Already lean";
        else
            notice = "Freed " + (Number(match[1]) / 1048576).toFixed(1) + " GiB";
        noticeTimer.restart();
    }

    Sensors.Sensor { id: percent; sensorId: "memory/physical/usedPercent"; updateRateLimit: 1000 }
    Sensors.Sensor { id: used; sensorId: "memory/physical/used"; updateRateLimit: 1000 }
    Sensors.Sensor { id: total; sensorId: "memory/physical/total" }
    Sensors.Sensor { id: application; sensorId: "memory/physical/application"; updateRateLimit: 2000 }
    Sensors.Sensor { id: cache; sensorId: "memory/physical/cache"; updateRateLimit: 2000 }
    Sensors.Sensor { id: swap; sensorId: "memory/swap/used"; updateRateLimit: 2000 }
    P5Support.DataSource {
        id: runner
        engine: "executable"
        connectedSources: []
        onNewData: (source, data) => {
            disconnectSource(source);
            root.finish(String(data["stdout"] || ""));
        }
    }
    Timer { id: noticeTimer; interval: 5000; onTriggered: root.notice = "" }

    fullRepresentation: Item {
        id: face
        Layout.minimumWidth: Kirigami.Units.gridUnit * 6
        Layout.minimumHeight: Kirigami.Units.gridUnit * 6
        Layout.preferredWidth: Kirigami.Units.gridUnit * 12
        Layout.preferredHeight: Kirigami.Units.gridUnit * 12
        readonly property real side: Math.min(width, height)
        readonly property real stroke: Math.max(6, side * 0.07)
        property real shown: root.level
        Behavior on shown { NumberAnimation { duration: 700; easing.type: Easing.OutCubic } }

        Rectangle {
            id: card
            width: face.side
            height: face.side
            anchors.centerIn: parent
            radius: face.side * 0.16
            color: Qt.alpha(Kirigami.Theme.backgroundColor, mouse.containsMouse ? 0.92 : 0.8)
            border.width: 1
            border.color: Qt.alpha(mouse.containsMouse ? root.levelColor : Kirigami.Theme.textColor,
                mouse.containsMouse ? 0.6 : 0.14)
            scale: mouse.pressed ? 0.97 : 1
            Behavior on color { ColorAnimation { duration: 150 } }
            Behavior on border.color { ColorAnimation { duration: 150 } }
            Behavior on scale { NumberAnimation { duration: 100 } }

            Shape {
                id: dial
                anchors.fill: parent
                preferredRendererType: Shape.CurveRenderer
                readonly property real radius: face.side * 0.36
                // 270° sweep opening downwards, leaving room for the action label.
                ShapePath {
                    strokeColor: Qt.alpha(Kirigami.Theme.textColor, 0.12)
                    strokeWidth: face.stroke
                    fillColor: "transparent"
                    capStyle: ShapePath.RoundCap
                    PathAngleArc {
                        centerX: dial.width / 2; centerY: dial.height / 2
                        radiusX: dial.radius; radiusY: dial.radius
                        startAngle: 135; sweepAngle: 270
                    }
                }
                ShapePath {
                    id: arc
                    strokeColor: root.levelColor
                    strokeWidth: face.stroke
                    fillColor: "transparent"
                    capStyle: ShapePath.RoundCap
                    Behavior on strokeColor { ColorAnimation { duration: 400 } }
                    PathAngleArc {
                        centerX: dial.width / 2; centerY: dial.height / 2
                        radiusX: dial.radius; radiusY: dial.radius
                        startAngle: 135; sweepAngle: Math.max(0.01, 2.7 * face.shown)
                    }
                }
                SequentialAnimation on opacity {
                    running: root.busy
                    loops: Animation.Infinite
                    alwaysRunToEnd: true
                    NumberAnimation { to: 0.35; duration: 600; easing.type: Easing.InOutSine }
                    NumberAnimation { to: 1; duration: 600; easing.type: Easing.InOutSine }
                }
            }
            Column {
                anchors.centerIn: parent
                spacing: 0
                PlasmaComponents.Label {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "RAM"
                    textFormat: Text.PlainText
                    font.pixelSize: Math.max(8, face.side * 0.065)
                    font.letterSpacing: face.side * 0.012
                    font.weight: Font.DemiBold
                    opacity: 0.6
                }
                PlasmaComponents.Label {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: root.ready ? Math.round(face.shown) + "%" : "—"
                    textFormat: Text.PlainText
                    font.pixelSize: Math.max(12, face.side * 0.2)
                    font.weight: Font.Light
                    font.features: { "tnum": 1 }
                }
                PlasmaComponents.Label {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: root.ready ? root.gib(used.value) + " / " + root.gib(total.value) + " GiB" : "Unavailable"
                    textFormat: Text.PlainText
                    font.pixelSize: Math.max(8, face.side * 0.06)
                    font.features: { "tnum": 1 }
                    opacity: 0.75
                }
            }
            PlasmaComponents.Label {
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                anchors.bottomMargin: face.side * 0.075
                text: root.busy ? "Freeing…" : root.notice || "Free up"
                textFormat: Text.PlainText
                font.pixelSize: Math.max(8, face.side * 0.06)
                font.weight: Font.DemiBold
                color: root.notice || root.busy || mouse.containsMouse ? root.levelColor : Kirigami.Theme.textColor
                opacity: root.notice || root.busy || mouse.containsMouse ? 1 : 0.5
                Behavior on opacity { NumberAnimation { duration: 150 } }
            }
            MouseArea {
                id: mouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: root.busy ? Qt.BusyCursor : Qt.PointingHandCursor
                onClicked: root.free()
            }
        }
    }
}
