import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.extras as PlasmaExtras
import org.kde.plasma.workspace.dbus as DBus

PlasmoidItem {
    id: root
    preferredRepresentation: fullRepresentation
    property var agents: []
    property double now: Date.now() / 1000
    property bool pending: false
    Plasmoid.status: watcher.registered ? PlasmaCore.Types.ActiveStatus : PlasmaCore.Types.HiddenStatus
    toolTipMainText: "CachyOS Agent Usage"
    toolTipSubText: "Percentages left · refreshed every 3 seconds · click an agent to open its CLI · right-click to shut it down"

    function call(member, resolve, reject, args = []) {
        DBus.SessionBus.asyncCall({
            service: "org.cachyos.AgentUsage", path: "/Usage", iface: "org.cachyos.AgentUsage",
            member: member, arguments: args
        }, resolve, reject);
    }
    function refresh() {
        now = Date.now() / 1000;
        if (!watcher.registered || pending)
            return;
        pending = true;
        call("GetUsage", reply => {
            pending = false;
            try { agents = JSON.parse(String(reply.value)).agents; }
            catch (error) { agents = []; }
        }, error => { pending = false; agents = []; });
    }
    function quota(agent, key, caption, compact = false) {
        const value = agent.windows[key];
        if (!value || value.resets_at <= now)
            return caption + (compact ? " —" : " unavailable");
        const stale = !agent.updated_at || now - agent.updated_at > 30;
        return (stale ? "~ " : "") + caption + " " + Number(value.left).toFixed(compact ? 0 : 1) + (compact ? "%" : "% left");
    }
    function details(agent) {
        let text = agent.status;
        if (agent.updated_at)
            text += "\nLast reported: " + new Date(agent.updated_at * 1000).toLocaleString();
        for (const key of ["five_hour", "seven_day"]) {
            const value = agent.windows[key];
            if (value)
                text += "\n" + (key === "five_hour" ? "5h" : "7d") + ": "
                    + Number(value.used).toFixed(1) + "% used · "
                    + Number(value.left).toFixed(1) + "% left; resets: "
                    + new Date(value.resets_at * 1000).toLocaleString();
        }
        return text + "\n~ means the last report is more than 30 seconds old.";
    }
    function shutdownText(agent) {
        if (!agent)
            return "";
        const count = agent.running || 0;
        return count ? "Shut down " + agent.name + " (" + count + " running)"
            : agent.name + " is not running";
    }
    PlasmaExtras.Menu {
        id: agentMenu
        property var agent: null
        PlasmaExtras.MenuItem {
            text: agentMenu.agent ? "Open " + agentMenu.agent.name + " CLI" : ""
            icon: "utilities-terminal"
            onClicked: root.call("OpenConsole", reply => {}, error => {}, [agentMenu.agent.name])
        }
        PlasmaExtras.MenuItem {
            text: root.shutdownText(agentMenu.agent)
            icon: "process-stop"
            enabled: !!agentMenu.agent && (agentMenu.agent.running || 0) > 0
            onClicked: root.call("Shutdown", reply => root.refresh(), error => {}, [agentMenu.agent.name])
        }
    }
    DBus.DBusServiceWatcher {
        id: watcher
        busType: DBus.BusType.Session
        watchedService: "org.cachyos.AgentUsage"
        onRegisteredChanged: {
            if (registered) root.refresh();
            else { root.agents = []; root.pending = false; }
        }
    }
    Timer { interval: 3000; running: true; repeat: true; onTriggered: root.refresh() }
    Component.onCompleted: refresh()

    fullRepresentation: Item {
        id: panelContent
        visible: watcher.registered
        clip: true
        implicitWidth: panelLayout.implicitWidth
        implicitHeight: 30
        Layout.minimumWidth: watcher.registered ? implicitWidth : 0
        Layout.preferredWidth: watcher.registered ? implicitWidth : 0
        Layout.maximumWidth: watcher.registered ? implicitWidth : 0
        Layout.minimumHeight: 0

        RowLayout {
            id: panelLayout
            anchors.fill: parent
            spacing: Kirigami.Units.smallSpacing
            PlasmaComponents.ToolButton {
                Layout.preferredWidth: 22
                Layout.preferredHeight: Math.min(22, panelContent.height)
                Layout.alignment: Qt.AlignVCenter
                icon.name: "preferences-system"
                text: "Agent settings"
                display: QQC2.AbstractButton.IconOnly
                onClicked: root.call("ShowSettings", reply => {}, error => {})
            }
            Repeater {
                model: root.agents
                delegate: Item {
                    id: agentColumn
                    required property var modelData
                    Layout.fillHeight: true
                    Layout.preferredWidth: content.implicitWidth + 12
                    implicitWidth: content.implicitWidth + 12
                    // Each agent is plain text, separated only by a vertical rule.
                    Rectangle {
                        width: 1
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        anchors.topMargin: 3
                        anchors.bottomMargin: 3
                        color: Qt.alpha(Kirigami.Theme.textColor, 0.35)
                    }
                    Column {
                        id: content
                        anchors.left: parent.left
                        anchors.leftMargin: 7
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 0
                        property bool compact: agentColumn.height < 32
                        property int textSize: Math.max(8, Math.min(11, Math.floor(agentColumn.height / (compact ? 2 : 3)) - 2))
                        PlasmaComponents.Label {
                            text: agentColumn.modelData.name
                            textFormat: Text.PlainText
                            font.pixelSize: content.textSize
                            font.bold: true
                        }
                        PlasmaComponents.Label {
                            visible: !content.compact
                            text: root.quota(agentColumn.modelData, "five_hour", "5h")
                            textFormat: Text.PlainText
                            font.pixelSize: content.textSize
                        }
                        PlasmaComponents.Label {
                            visible: !content.compact
                            text: root.quota(agentColumn.modelData, "seven_day", "7d")
                            textFormat: Text.PlainText
                            font.pixelSize: content.textSize
                            opacity: 0.85
                        }
                        PlasmaComponents.Label {
                            visible: content.compact
                            text: root.quota(agentColumn.modelData, "five_hour", "5h", true)
                                + " · " + root.quota(agentColumn.modelData, "seven_day", "7d", true)
                            textFormat: Text.PlainText
                            font.pixelSize: content.textSize
                        }
                    }
                    PlasmaCore.ToolTipArea {
                        anchors.fill: parent
                        mainText: "Open " + agentColumn.modelData.name + " CLI"
                        subText: root.details(agentColumn.modelData)
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            acceptedButtons: Qt.LeftButton | Qt.RightButton
                            onClicked: mouse => {
                                if (mouse.button === Qt.RightButton) {
                                    agentMenu.agent = agentColumn.modelData;
                                    agentMenu.visualParent = agentColumn;
                                    agentMenu.open(mouse.x, mouse.y);
                                } else {
                                    root.call("OpenConsole", reply => {}, error => {}, [agentColumn.modelData.name]);
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
