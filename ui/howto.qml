/*
 * Copyright 2020 by Aditya Mehra <aix.m@outlook.com>
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *    http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 */

import QtQuick 2.9
import QtQuick.Controls 2.3 as Controls
import QtQuick.Layouts 1.3
import org.kde.kirigami 2.8 as Kirigami
import QtGraphicalEffects 1.0
import Mycroft 1.0 as Mycroft

Mycroft.Delegate {
    property var imageSource: sessionData.imgLink
    property var title: sessionData.title
    property var caption: sessionData.caption
    property bool hasTitle: sessionData.title.length > 0 ? true : false
    property bool hasCaption: sessionData.caption.length > 0 ? true : false

    Component.onCompleted: {
        comicView.forceActiveFocus()
    }

    RowLayout {
        anchors.fill: parent

        Controls.RoundButton {
            id: previousButton
            Layout.minimumWidth: Kirigami.Units.iconSizes.small
            Layout.minimumHeight: width
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.maximumWidth: Kirigami.Units.gridUnit * 3
            Layout.maximumHeight: width
            Layout.alignment: Qt.AlignVCenter
            focus: false
            icon.source: "images/leftarrow.svg"
            KeyNavigation.right: nextButton

            background: Rectangle {
                Kirigami.Theme.colorSet: Kirigami.Theme.Button
                radius: width
                color: previousButton.activeFocus ? Kirigami.Theme.highlightColor : Qt.rgba(0.2, 0.2, 0.2, 1)
                layer.enabled: true
                layer.effect: DropShadow {
                    horizontalOffset: 1
                    verticalOffset: 2
                }
            }

            onClicked: {
                triggerGuiEvent('skill-how-to.jarbasskills.prev', {})
            }

            Keys.onReturnPressed: {
                clicked()
            }
        }

        Kirigami.Heading {
            id: HowToTitle
            visible: hasTitle
            enabled: hasTitle
            Layout.fillWidth: true
            Layout.preferredHeight: paintedHeight + Kirigami.Units.largeSpacing
            level: 3
            text: sessionData.title
            wrapMode: Text.Wrap
            font.family: "Noto Sans"
            font.weight: Font.Bold
        }

        Image {
            id: stepView
            Layout.fillWidth: true
            Layout.fillHeight: true
            autoTransform: true
            mipmap: true
            smooth: true
            fillMode: Image.PreserveAspectFit
            source: imageSource
            focus: true
            KeyNavigation.right: nextButton
            KeyNavigation.left: previousButton

            Rectangle {
                id: systemImageCaptionBox
                visible: hasCaption
                enabled: hasCaption
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                height: systemImageCaption.paintedHeight
                color: "#95000000"

                Kirigami.Heading {
                    id: systemImageCaption
                    level: 2
                    anchors.left: parent.left
                    anchors.leftMargin: Kirigami.Units.largeSpacing
                    anchors.right: parent.right
                    anchors.rightMargin: Kirigami.Units.largeSpacing
                    anchors.verticalCenter: parent.verticalCenter
                    text: sessionData.caption
                    wrapMode: Text.Wrap
                    font.family: "Noto Sans"
                    font.weight: Font.Bold
                }
            }
        }

        Controls.RoundButton {
            id: nextButton
            Layout.minimumWidth: Kirigami.Units.iconSizes.small
            Layout.minimumHeight: width
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.maximumWidth: Kirigami.Units.gridUnit * 3
            Layout.maximumHeight: width
            Layout.alignment: Qt.AlignVCenter
            focus: false
            icon.source: "images/rightarrow.svg"
            KeyNavigation.left: previousButton

            background: Rectangle {
                Kirigami.Theme.colorSet: Kirigami.Theme.Button
                radius: width
                color: nextButton.activeFocus ? Kirigami.Theme.highlightColor : Qt.rgba(0.2, 0.2, 0.2, 1)
                layer.enabled: true
                layer.effect: DropShadow {
                    horizontalOffset: 1
                    verticalOffset: 2
                }
            }

            onClicked: {
                triggerGuiEvent('skill-how-to.jarbasskills.next', {})
            }

            Keys.onReturnPressed: {
                clicked()
            }
        }
    }
}