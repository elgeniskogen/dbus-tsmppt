import QtQuick 2.0
import Victron.VenusOS 1.0

Page {
    id: root
    title: qsTr("TriStar MPPT Settings")

    GradientListView {
        model: ObjectModel {

            ListTextItem {
                text: qsTr("TriStar MPPT Solar Charger")
                secondaryText: qsTr("Configure Modbus TCP connection")
            }

            ListTextField {
                id: ipAddress
                text: qsTr("IP Address / Hostname")
                placeholderText: qsTr("192.168.1.200")

                VeQuickItem {
                    id: ipItem
                    uid: Global.systemSettings.serviceUid + "/Settings/TristarMPPT/IPAddress"
                }

                textField.text: ipItem.value || ""
                textField.inputMethodHints: Qt.ImhPreferLowercase

                function save() {
                    ipItem.setValue(textField.text)
                }
            }

            ListIntField {
                id: portNumber
                text: qsTr("Modbus TCP Port")

                VeQuickItem {
                    id: portItem
                    uid: Global.systemSettings.serviceUid + "/Settings/TristarMPPT/PortNumber"
                }

                dataItem.uid: portItem.uid
                dataItem.value: portItem.value !== undefined ? portItem.value : 502

                // Valid port range
                numericField.from: 1
                numericField.to: 65535
            }

            ListIntField {
                id: updateInterval
                text: qsTr("Update Interval")
                secondaryText: qsTr("milliseconds")

                VeQuickItem {
                    id: intervalItem
                    uid: Global.systemSettings.serviceUid + "/Settings/TristarMPPT/Interval"
                }

                dataItem.uid: intervalItem.uid
                dataItem.value: intervalItem.value !== undefined ? intervalItem.value : 5000

                // Valid interval range (1-60 seconds)
                numericField.from: 1000
                numericField.to: 60000
                numericField.stepSize: 1000
            }

            ListTextItem {
                text: qsTr("Connection Status")

                VeQuickItem {
                    id: connectionStatus
                    uid: "com.victronenergy.solarcharger.tsmppt/Connected"
                }

                secondaryText: connectionStatus.value === 1 ? qsTr("Connected") : qsTr("Disconnected")
            }

            ListTextItem {
                text: qsTr("Device Model")

                VeQuickItem {
                    id: productName
                    uid: "com.victronenergy.solarcharger.tsmppt/ProductName"
                }

                secondaryText: productName.value || qsTr("Not connected")
                visible: productName.value !== undefined
            }

            ListTextItem {
                text: qsTr("Serial Number")

                VeQuickItem {
                    id: serialNumber
                    uid: "com.victronenergy.solarcharger.tsmppt/Serial"
                }

                secondaryText: serialNumber.value || qsTr("N/A")
                visible: serialNumber.value !== undefined
            }

            ListTextItem {
                text: qsTr("Firmware Version")

                VeQuickItem {
                    id: fwVersion
                    uid: "com.victronenergy.solarcharger.tsmppt/FirmwareVersion"
                }

                secondaryText: fwVersion.value || qsTr("N/A")
                visible: fwVersion.value !== undefined
            }
        }
    }
}
