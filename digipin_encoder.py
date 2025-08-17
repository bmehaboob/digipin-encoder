# DIGIPIN ENCODER - A QGIS plugin for encoding and decoding DIGIPINs using India Post's API
# Copyright (C) 2025 Beig Mehaboob
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
import os
import re
from qgis.PyQt.QtCore import (QSettings, QTranslator, QCoreApplication, 
                             Qt, QTimer, QUrl)
from qgis.PyQt.QtGui import QIcon, QDesktopServices
from qgis.PyQt.QtWidgets import (QAction, QMessageBox, QProgressDialog, 
                                QApplication, QMenu, QInputDialog, QDialog, 
                                QDialogButtonBox, QListWidget, QVBoxLayout)
from qgis.core import (QgsProject, QgsPointXY, QgsGeometry, QgsFeature, 
                      QgsField, QgsCoordinateTransform, 
                      QgsCoordinateReferenceSystem, QgsWkbTypes, 
                      QgsMapLayer, QgsVectorLayer, QgsSettings)
from qgis.gui import QgsMapToolEmitPoint, QgsVertexMarker
from qgis.utils import iface
import requests
from PyQt5.QtCore import QVariant
from PyQt5.QtWidgets import QToolButton
from PyQt5.QtWidgets import QAbstractItemView  # For selection mode

from .digipin_encoder_dockwidget import DIGIPIN_ENCODERDockWidget
import os.path

class DIGIPIN_ENCODER:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'DIGIPIN_ENCODER_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        self.actions = []
        self.menu = self.tr(u'&DIGIPIN_ENCODER')
        self.toolbar = self.iface.addToolBar(u'DIGIPIN_ENCODER')
        self.toolbar.setObjectName(u'DIGIPIN_ENCODER')
        
        # Plugin components
        self.dockwidget = None
        self.map_tool = None
        self.marker = None
        self.validation_marker = None
        
        # API configuration
        self.api_base = "https://api.geospatialkeeda.site"
        self.api_key = ""  # Add your API key here if needed

    def tr(self, message):
        return QCoreApplication.translate('DIGIPIN_ENCODER', message)

    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), 'icon.png')
        
        # Main plugin action - shows/hides the dock widget
        self.dock_action = self.add_action(
            icon_path,
            text=self.tr(u'DIGIPIN_ENCODER'),
            callback=self.run,
            parent=self.iface.mainWindow())
        
        # Create dock widget (initially hidden)
        self.dockwidget = DIGIPIN_ENCODERDockWidget()
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dockwidget)
        self.dockwidget.hide()
        
        # Add tooltips
        self.dockwidget.getDigipinButton.setToolTip(self.tr("Click to activate map tool and select a point for DIGIPIN encoding"))
        self.dockwidget.processLayerButton.setToolTip(self.tr("Process the active vector layer to add DIGIPIN data"))
        self.dockwidget.batchProcessButton.setToolTip(self.tr("Batch process multiple selected vector layers to add DIGIPIN data"))
        self.dockwidget.clearGetDigipinButton.setToolTip(self.tr("Clear Get DIGIPIN results"))
        self.dockwidget.clearDecodeButton.setToolTip(self.tr("Clear Decode DIGIPIN input"))
        
        # Connect signals
        self.dockwidget.getDigipinButton.clicked.connect(self.activate_digipin_tool)
        self.dockwidget.processLayerButton.clicked.connect(self.process_layer)
        self.dockwidget.copyAllButton.clicked.connect(self.copy_to_clipboard)
        self.dockwidget.copyDigipinButton.clicked.connect(lambda: self.copy_individual('digipin'))
        self.dockwidget.copyLatButton.clicked.connect(lambda: self.copy_individual('latitude'))
        self.dockwidget.copyLonButton.clicked.connect(lambda: self.copy_individual('longitude'))
        self.dockwidget.copyMapButton.clicked.connect(lambda: self.copy_individual('map_link'))
        self.dockwidget.openMapButton.clicked.connect(self.open_in_maps)
        self.dockwidget.clearGetDigipinButton.clicked.connect(self.clear_get_digipin)
        self.dockwidget.clearDecodeButton.clicked.connect(self.clear_decode_digipin)
        self.dockwidget.decodeButton.clicked.connect(self.decode_digipin)
        self.dockwidget.validateButton.clicked.connect(self.validate_digipin)
        self.dockwidget.batchProcessButton.clicked.connect(self.batch_process_layers)
        self.dockwidget.closed.connect(self.on_dockwidget_close)
        self.dockwidget.instructionsTextEdit.anchorClicked.connect(self.handle_link_clicked)

    def handle_link_clicked(self, url):
        """Handle clicks on hyperlinks in instructionsTextEdit"""
        QDesktopServices.openUrl(url)

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&DIGIPIN_ENCODER'),
                action)
            self.iface.removeToolBarIcon(action)
        
        # Remove the dock widget
        if self.dockwidget:
            self.iface.removeDockWidget(self.dockwidget)
            self.dockwidget = None
        
        # Remove the toolbar
        del self.toolbar

    def run(self):
        """Show/hide the dock widget"""
        if self.dockwidget.isVisible():
            self.dockwidget.hide()
        else:
            self.dockwidget.show()
            self.dockwidget.raise_()

    def on_dockwidget_close(self):
        """Handle dock widget close event"""
        self.deactivate_digipin_tool()
        self.clear_validation_marker()

    def activate_digipin_tool(self):
        """Activate the map tool to get DIGIPIN from clicked point"""
        if self.map_tool is None:
            self.map_tool = QgsMapToolEmitPoint(self.iface.mapCanvas())
            self.map_tool.canvasClicked.connect(self.handle_map_click)
        
        self.iface.mapCanvas().setMapTool(self.map_tool)
        
        if self.marker is None:
            self.marker = QgsVertexMarker(self.iface.mapCanvas())
            self.marker.setColor(Qt.red)
            self.marker.setIconSize(12)
            self.marker.setPenWidth(2)
        
        self.dockwidget.statusLabel.setText(self.tr("Click on the map to get DIGIPIN"))
        self.dockwidget.getDigipinButton.setStyleSheet("background-color: #4CAF50; color: white;")

    def deactivate_digipin_tool(self):
        """Deactivate the map tool"""
        if self.map_tool:
            self.iface.mapCanvas().unsetMapTool(self.map_tool)
        
        if self.marker:
            self.iface.mapCanvas().scene().removeItem(self.marker)
            self.marker = None
        
        if self.dockwidget:
            self.dockwidget.getDigipinButton.setStyleSheet("")
        self.clear_validation_marker()

    def clear_validation_marker(self):
        """Remove the validation marker from the map canvas"""
        if self.validation_marker:
            self.iface.mapCanvas().scene().removeItem(self.validation_marker)
            self.validation_marker = None

    def handle_map_click(self, point, button):
        """Handle map click to get DIGIPIN"""
        try:
            # Transform to WGS84 if needed
            canvas_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
            if canvas_crs.authid() != 'EPSG:4326':
                transform_context = QgsProject.instance().transformContext()
                xform = QgsCoordinateTransform(
                    canvas_crs,
                    QgsCoordinateReferenceSystem('EPSG:4326'),
                    transform_context)
                point = xform.transform(point)
            
            # Update marker position
            if self.marker:
                self.marker.setCenter(point)
            
            # Get DIGIPIN from API
            lat, lon = point.y(), point.x()
            digipin = self.get_digipin_from_coords(lat, lon)
            
            if digipin:
                # Update UI
                self.dockwidget.digipinLineEdit.setText(digipin)
                self.dockwidget.latLineEdit.setText(f"{lat:.6f}")
                self.dockwidget.lonLineEdit.setText(f"{lon:.6f}")
                self.dockwidget.mapLinkLineEdit.setText(f"https://www.google.com/maps?q={lat},{lon}")
                self.dockwidget.statusLabel.setText(self.tr("DIGIPIN retrieved successfully"))
                
                # Enable all relevant buttons
                self.dockwidget.copyAllButton.setEnabled(True)
                self.dockwidget.openMapButton.setEnabled(True)
                self.dockwidget.copyDigipinButton.setEnabled(True)
                self.dockwidget.copyLatButton.setEnabled(True)
                self.dockwidget.copyLonButton.setEnabled(True)
                self.dockwidget.copyMapButton.setEnabled(True)
            else:
                self.dockwidget.statusLabel.setText(self.tr("Failed to get DIGIPIN"))
        
        except Exception as e:
            self.dockwidget.statusLabel.setText(self.tr(f"Error: {str(e)}"))

    def get_digipin_from_coords(self, lat, lon):
        """Get DIGIPIN from coordinates using API"""
        try:
            # Construct URL with proper parameters
            url = f"{self.api_base}/api/digipin/encode"
            print(f"Requesting DIGIPIN from: {url} with lat={lat}, lon={lon}")  # Debug log

            # Prepare payload for POST request
            payload = {"latitude": lat, "longitude": lon}
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["x-api-key"] = self.api_key

            # Send POST request
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()  # Raises exception for 4xx/5xx errors

            # Parse response
            data = response.json()
            digipin = data.get("digipin")
            if digipin:
                print(f"Received DIGIPIN: {digipin}")  # Debug log
                return digipin
            else:
                self.dockwidget.statusLabel.setText(self.tr("API returned no DIGIPIN"))
                return None

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                self.dockwidget.statusLabel.setText(self.tr("API Error: Endpoint not found. Check internet or contact support at admin@geospatialkeeda.site"))
            else:
                self.dockwidget.statusLabel.setText(self.tr(f"API Error: {str(e)}"))
            print(f"HTTP Error: {str(e)}")  # Debug log
            return None
        except requests.exceptions.RequestException as e:
            self.dockwidget.statusLabel.setText(self.tr(f"API Connection Error: {str(e)}"))
            print(f"Connection Error: {str(e)}")  # Debug log
            return None
        except ValueError as e:  # Catch JSON decode errors
            self.dockwidget.statusLabel.setText(self.tr(f"API Response Error: Invalid JSON - {str(e)}"))
            print(f"JSON Error: {str(e)} with response: {response.text}")  # Debug log with raw response
            return None

    def process_layer(self):
        """Process selected vector layer to add DIGIPIN information"""
        layer = self.iface.activeLayer()
        if not layer:
            QMessageBox.warning(self.dockwidget, "No Layer", "Please select a vector layer first")
            return
        
        if layer.type() != QgsMapLayer.VectorLayer:
            QMessageBox.warning(self.dockwidget, "Invalid Layer", "Selected layer is not a vector layer")
            return
        
        # Check geometry type
        geom_type = layer.geometryType()
        
        if geom_type not in (QgsWkbTypes.PointGeometry, QgsWkbTypes.PolygonGeometry):
            QMessageBox.warning(self.dockwidget, "Unsupported Type", 
                              "Only point and polygon layers are supported")
            return
        
        # Ask for confirmation for polygon layers
        if geom_type == QgsWkbTypes.PolygonGeometry:
            reply = QMessageBox.question(
                self.dockwidget,
                "Confirm Processing",
                "This is a polygon layer. DIGIPINs will be generated using point-on-surface method.\n\n"
                "Would you like to continue?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
        
        # Check if layer is in WGS84 or needs transformation
        layer_crs = layer.crs()
        transform_needed = layer_crs.authid() != 'EPSG:4326'
        if transform_needed:
            transform_context = QgsProject.instance().transformContext()
            xform = QgsCoordinateTransform(
                layer_crs,
                QgsCoordinateReferenceSystem('EPSG:4326'),
                transform_context)
        
        # Add new fields if they don't exist
        layer.beginEditCommand("Add DIGIPIN fields")
        provider = layer.dataProvider()
        fields_to_add = []
        
        if layer.fields().indexFromName('digipin') == -1:
            fields_to_add.append(QgsField('digipin', QVariant.String))
        if layer.fields().indexFromName('latitude') == -1:
            fields_to_add.append(QgsField('latitude', QVariant.Double, len=10, prec=6))
        if layer.fields().indexFromName('longitude') == -1:
            fields_to_add.append(QgsField('longitude', QVariant.Double, len=10, prec=6))
        if layer.fields().indexFromName('google_map') == -1:
            fields_to_add.append(QgsField('google_map', QVariant.String, len=255))
        if geom_type == QgsWkbTypes.PolygonGeometry and layer.fields().indexFromName('digipin_note') == -1:
            fields_to_add.append(QgsField('digipin_note', QVariant.String, len=100))
        
        if fields_to_add:
            provider.addAttributes(fields_to_add)
            layer.updateFields()
        
        # Process features
        total_features = layer.featureCount()
        progress = QProgressDialog(
            "Processing layer...", 
            "Cancel", 
            0, 
            total_features, 
            self.dockwidget)
        progress.setWindowTitle("DIGIPIN Processing")
        progress.setWindowModality(Qt.WindowModal)
        
        processed_count = 0
        layer.beginEditCommand("Process DIGIPIN encoding")
        for i, feature in enumerate(layer.getFeatures()):
            if progress.wasCanceled():
                layer.destroyEditCommand()
                break
            
            progress.setValue(i)
            QApplication.processEvents()
            
            geom = feature.geometry()
            if geom.isEmpty():
                continue
            
            # Get point based on geometry type
            if geom_type == QgsWkbTypes.PointGeometry:
                point = geom.asPoint()
                note = None
            else:  # Polygon geometry
                point = geom.pointOnSurface().asPoint()
                note = "DIGIPIN generated from point-on-surface"
            
            # Transform if needed
            if transform_needed:
                point = xform.transform(point)
            
            lat, lon = point.y(), point.x()
            
            # Get DIGIPIN
            digipin = self.get_digipin_from_coords(lat, lon)
            if not digipin:
                continue
            
            # Update feature attributes
            attrs = {}
            digipin_idx = layer.fields().indexFromName('digipin')
            if digipin_idx != -1:
                attrs[digipin_idx] = digipin
            lat_idx = layer.fields().indexFromName('latitude')
            if lat_idx != -1:
                attrs[lat_idx] = lat
            lon_idx = layer.fields().indexFromName('longitude')
            if lon_idx != -1:
                attrs[lon_idx] = lon
            map_idx = layer.fields().indexFromName('google_map')
            if map_idx != -1:
                attrs[map_idx] = f"https://www.google.com/maps?q={lat},{lon}"
            if note and layer.fields().indexFromName('digipin_note') != -1:
                note_idx = layer.fields().indexFromName('digipin_note')
                attrs[note_idx] = note
            
            if attrs:
                provider.changeAttributeValues({feature.id(): attrs})
                processed_count += 1
        
        progress.setValue(total_features)
        layer.endEditCommand()
        
        # Show completion message with processing note
        if geom_type == QgsWkbTypes.PolygonGeometry:
            msg = (f"Processed {processed_count} polygon features using point-on-surface method.\n\n"
                  "Note: DIGIPINs were generated for representative points within each polygon.\n"
                  "A 'digipin_note' field was added to document this processing method.")
        else:
            msg = f"Successfully processed {processed_count} point features"
        
        QMessageBox.information(self.dockwidget, "Processing Complete", msg)
        self.dockwidget.statusLabel.setText(f"Processed {layer.name()}")

    def batch_process_layers(self):
        """Process multiple selected vector layers to add DIGIPIN information"""
        # Get all layers from the project
        all_layers = QgsProject.instance().mapLayers().values()
        vector_layers = [layer for layer in all_layers if layer.type() == QgsMapLayer.VectorLayer]
        
        if not vector_layers:
            QMessageBox.warning(self.dockwidget, "No Vector Layers", 
                              "No vector layers found in the project")
            return
        
        # Create a dialog to select layers
        dialog = QDialog(self.dockwidget)
        dialog.setWindowTitle("Select Layers for Batch Processing")
        dialog.resize(400, 300)
        
        # Set up layout
        layout = QVBoxLayout()
        
        # Add list widget for layer selection with multi-selection enabled
        list_widget = QListWidget(dialog)
        list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)  # Enable multiple selection
        for layer in vector_layers:
            list_widget.addItem(layer.name())
        layout.addWidget(list_widget)
        
        # Add button box
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, dialog)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        dialog.setLayout(layout)
        
        if dialog.exec_() == QDialog.Accepted:
            selected_items = list_widget.selectedItems()
            if not selected_items:
                QMessageBox.warning(self.dockwidget, "No Selection", 
                                  "Please select at least one layer")
                return
            
            layers = [layer for layer in vector_layers if layer.name() in [item.text() for item in selected_items]]
            total_layers = len(layers)
            progress = QProgressDialog(
                "Processing layers...", 
                "Cancel", 
                0, 
                total_layers, 
                self.dockwidget)
            progress.setWindowTitle("Batch DIGIPIN Processing")
            progress.setWindowModality(Qt.WindowModal)
            
            processed_count = 0
            for i, layer in enumerate(layers):
                if progress.wasCanceled():
                    break
                
                progress.setValue(i)
                QApplication.processEvents()
                
                geom_type = layer.geometryType()
                if geom_type not in (QgsWkbTypes.PointGeometry, QgsWkbTypes.PolygonGeometry):
                    self.dockwidget.statusLabel.setText(self.tr(f"Skipping {layer.name()}: Unsupported geometry type"))
                    continue
                
                # Ask for confirmation for polygon layers
                if geom_type == QgsWkbTypes.PolygonGeometry:
                    reply = QMessageBox.question(
                        self.dockwidget,
                        "Confirm Processing",
                        f"This is a polygon layer ({layer.name()}). DIGIPINs will be generated using point-on-surface method.\n\n"
                        "Would you like to continue?",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    if reply == QMessageBox.No:
                        continue
                
                # Check if layer is in WGS84 or needs transformation
                layer_crs = layer.crs()
                transform_needed = layer_crs.authid() != 'EPSG:4326'
                if transform_needed:
                    transform_context = QgsProject.instance().transformContext()
                    xform = QgsCoordinateTransform(
                        layer_crs,
                        QgsCoordinateReferenceSystem('EPSG:4326'),
                        transform_context)
                
                # Add new fields if they don't exist
                layer.beginEditCommand("Add DIGIPIN fields")
                provider = layer.dataProvider()
                fields_to_add = []
                if layer.fields().indexFromName('digipin') == -1:
                    fields_to_add.append(QgsField('digipin', QVariant.String))
                if layer.fields().indexFromName('latitude') == -1:
                    fields_to_add.append(QgsField('latitude', QVariant.Double, len=10, prec=6))
                if layer.fields().indexFromName('longitude') == -1:
                    fields_to_add.append(QgsField('longitude', QVariant.Double, len=10, prec=6))
                if layer.fields().indexFromName('google_map') == -1:
                    fields_to_add.append(QgsField('google_map', QVariant.String, len=255))
                if geom_type == QgsWkbTypes.PolygonGeometry and layer.fields().indexFromName('digipin_note') == -1:
                    fields_to_add.append(QgsField('digipin_note', QVariant.String, len=100))
                
                if fields_to_add:
                    provider.addAttributes(fields_to_add)
                    layer.updateFields()
                layer.endEditCommand()
                
                # Start editing
                layer.beginEditCommand("Process DIGIPIN encoding")
                
                # Process features
                total_features = layer.featureCount()
                layer_progress = QProgressDialog(
                    f"Processing {layer.name()}...", 
                    "Cancel", 
                    0, 
                    total_features, 
                    self.dockwidget)
                layer_progress.setWindowModality(Qt.WindowModal)
                
                feature_count = 0
                for feature in layer.getFeatures():
                    if layer_progress.wasCanceled():
                        layer.destroyEditCommand()
                        break
                    
                    geom = feature.geometry()
                    if geom.isEmpty():
                        continue
                    
                    # Get point based on geometry type
                    if geom_type == QgsWkbTypes.PointGeometry:
                        point = geom.asPoint()
                        note = None
                    else:  # Polygon geometry
                        point = geom.pointOnSurface().asPoint()
                        note = "DIGIPIN generated from point-on-surface"
                    
                    # Transform if needed
                    if transform_needed:
                        point = xform.transform(point)
                    
                    lat, lon = point.y(), point.x()
                    
                    # Get DIGIPIN
                    digipin = self.get_digipin_from_coords(lat, lon)
                    if not digipin:
                        continue
                    
                    # Update feature attributes
                    attrs = {}
                    digipin_idx = layer.fields().indexFromName('digipin')
                    if digipin_idx != -1:
                        attrs[digipin_idx] = digipin
                    lat_idx = layer.fields().indexFromName('latitude')
                    if lat_idx != -1:
                        attrs[lat_idx] = lat
                    lon_idx = layer.fields().indexFromName('longitude')
                    if lon_idx != -1:
                        attrs[lon_idx] = lon
                    map_idx = layer.fields().indexFromName('google_map')
                    if map_idx != -1:
                        attrs[map_idx] = f"https://www.google.com/maps?q={lat},{lon}"
                    if note and layer.fields().indexFromName('digipin_note') != -1:
                        note_idx = layer.fields().indexFromName('digipin_note')
                        attrs[note_idx] = note
                    
                    if attrs:
                        provider.changeAttributeValues({feature.id(): attrs})
                        feature_count += 1
                
                layer_progress.setValue(total_features)
                layer.endEditCommand()
                
                processed_count += 1
            
            progress.setValue(total_layers)
            
            # Show completion message
            QMessageBox.information(self.dockwidget, "Batch Processing Complete", 
                                  f"Successfully processed {processed_count} out of {total_layers} layers")
            self.dockwidget.statusLabel.setText(self.tr("Batch processing complete"))
        else:
            self.dockwidget.statusLabel.setText(self.tr("Batch processing canceled"))

    def copy_to_clipboard(self):
        """Copy current DIGIPIN information to clipboard"""
        digipin = self.dockwidget.digipinLineEdit.text()
        lat = self.dockwidget.latLineEdit.text()
        lon = self.dockwidget.lonLineEdit.text()
        map_link = self.dockwidget.mapLinkLineEdit.text()
        
        if digipin:
            clipboard = QApplication.clipboard()
            clipboard.setText(
                f"DIGIPIN: {digipin}\n"
                f"Coordinates: {lat}, {lon}\n"
                f"Map: {map_link}"
            )
            self.dockwidget.statusLabel.setText(self.tr("Copied to clipboard"))
            # Flash the button to provide feedback
            original_style = self.dockwidget.copyAllButton.styleSheet()
            self.dockwidget.copyAllButton.setStyleSheet("background-color: #4CAF50; color: white;")
            QTimer.singleShot(300, lambda: self.dockwidget.copyAllButton.setStyleSheet(original_style))

    def copy_individual(self, field):
        """Copy individual field to clipboard"""
        if field == 'digipin':
            text = self.dockwidget.digipinLineEdit.text()
            button = self.dockwidget.copyDigipinButton
        elif field == 'latitude':
            text = self.dockwidget.latLineEdit.text()
            button = self.dockwidget.copyLatButton
        elif field == 'longitude':
            text = self.dockwidget.lonLineEdit.text()
            button = self.dockwidget.copyLonButton
        elif field == 'map_link':
            text = self.dockwidget.mapLinkLineEdit.text()
            button = self.dockwidget.copyMapButton
        else:
            return
        
        if text:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            self.dockwidget.statusLabel.setText(self.tr(f"Copied {field}"))
            # Flash the button
            original_style = button.styleSheet()
            button.setStyleSheet("background-color: #4CAF50; color: white;")
            QTimer.singleShot(300, lambda: button.setStyleSheet(original_style))

    def clear_get_digipin(self):
        """Clear results from the Get DIGIPIN section"""
        self.dockwidget.digipinLineEdit.clear()
        self.dockwidget.latLineEdit.clear()
        self.dockwidget.lonLineEdit.clear()
        self.dockwidget.mapLinkLineEdit.clear()
        self.dockwidget.copyAllButton.setEnabled(False)
        self.dockwidget.openMapButton.setEnabled(False)
        self.dockwidget.copyDigipinButton.setEnabled(False)
        self.dockwidget.copyLatButton.setEnabled(False)
        self.dockwidget.copyLonButton.setEnabled(False)
        self.dockwidget.copyMapButton.setEnabled(False)
        self.dockwidget.statusLabel.setText(self.tr("Get DIGIPIN cleared"))
        self.deactivate_digipin_tool()

    def clear_decode_digipin(self):
        """Clear results from the Decode DIGIPIN section"""
        self.dockwidget.decodeDigipinLineEdit.clear()
        self.dockwidget.statusLabel.setText(self.tr("Decode DIGIPIN cleared"))
        self.clear_validation_marker()

    def decode_digipin(self):
        """Decode a DIGIPIN to coordinates using API"""
        digipin = self.dockwidget.decodeDigipinLineEdit.text().strip()
        if not digipin:
            self.dockwidget.statusLabel.setText(self.tr("Please enter a DIGIPIN to decode"))
            return
        
        # Validate DIGIPIN format (3-3-4 segments with hyphens)
        if not re.match(r'^[A-Z0-9]{3}-[A-Z0-9]{3}-[A-Z0-9]{4}$', digipin):
            QMessageBox.warning(self.dockwidget, "Invalid DIGIPIN", 
                              "DIGIPIN must be in the format XXX-XXX-XXXX (e.g., 469-999-3CPM)")
            return
        
        try:
            url = f"{self.api_base}/api/digipin/decode"
            print(f"Decoding DIGIPIN from: {url} with digipin={digipin}")  # Debug log
            payload = {"digipin": digipin.replace('-', '')}
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["x-api-key"] = self.api_key

            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()

            # Preprocess and parse response
            raw_response = response.text
            if raw_response.startswith('(') and raw_response.endswith(')'):
                raw_response = '{' + raw_response[1:-1] + '}'  # Convert (key:value,...) to {key:value,...}
            try:
                data = response.json() if not raw_response.startswith('{') else eval(raw_response)  # Fallback to eval for malformed JSON
            except ValueError:
                import json
                # Attempt to parse as a string with key-value pairs
                data = {}
                pairs = raw_response.strip('()').split(',')
                for pair in pairs:
                    if ':' in pair:
                        key, value = pair.split(':', 1)
                        data[key.strip('"')] = value.strip('"')
            
            lat = data.get("latitude")
            lon = data.get("longitude")
            if lat and lon:
                self.dockwidget.latLineEdit.setText(f"{float(lat):.6f}")
                self.dockwidget.lonLineEdit.setText(f"{float(lon):.6f}")
                self.dockwidget.mapLinkLineEdit.setText(f"https://www.google.com/maps?q={float(lat)},{float(lon)}")
                self.dockwidget.statusLabel.setText(self.tr("DIGIPIN decoded successfully"))
                # Enable buttons
                self.dockwidget.copyAllButton.setEnabled(True)
                self.dockwidget.openMapButton.setEnabled(True)
                self.dockwidget.copyLatButton.setEnabled(True)
                self.dockwidget.copyLonButton.setEnabled(True)
                self.dockwidget.copyMapButton.setEnabled(True)
            else:
                self.dockwidget.statusLabel.setText(self.tr("Invalid DIGIPIN or no coordinates returned"))
        except requests.exceptions.HTTPError as e:
            self.dockwidget.statusLabel.setText(self.tr(f"API Error: {str(e)}"))
            print(f"HTTP Error: {str(e)}")
        except requests.exceptions.RequestException as e:
            self.dockwidget.statusLabel.setText(self.tr(f"API Connection Error: {str(e)}"))
            print(f"Connection Error: {str(e)}")
        except ValueError as e:
            self.dockwidget.statusLabel.setText(self.tr(f"API Response Error: Invalid JSON - {str(e)}. Raw response: {response.text}"))
            print(f"JSON Error: {str(e)} with response: {response.text}")  # Debug log with raw response
        except Exception as e:
            self.dockwidget.statusLabel.setText(self.tr(f"Unexpected error: {str(e)}"))
            print(f"Unexpected Error: {str(e)}")

    def validate_digipin(self):
        """Validate a DIGIPIN using API and zoom map to location"""
        digipin = self.dockwidget.decodeDigipinLineEdit.text().strip()
        if not digipin:
            self.dockwidget.statusLabel.setText(self.tr("Please enter a DIGIPIN to validate"))
            return
        
        # Validate DIGIPIN format (3-3-4 segments with hyphens)
        if not re.match(r'^[A-Z0-9]{3}-[A-Z0-9]{3}-[A-Z0-9]{4}$', digipin):
            QMessageBox.warning(self.dockwidget, "Invalid DIGIPIN", 
                              "DIGIPIN must be in the format XXX-XXX-XXXX (e.g., 469-999-3CPM)")
            return
        
        try:
            url = f"{self.api_base}/api/digipin/decode"
            print(f"Validating DIGIPIN from: {url} with digipin={digipin}")  # Debug log
            payload = {"digipin": digipin.replace('-', '')}
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["x-api-key"] = self.api_key

            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()

            # Preprocess and parse response
            raw_response = response.text
            if raw_response.startswith('(') and raw_response.endswith(')'):
                raw_response = '{' + raw_response[1:-1] + '}'  # Convert (key:value,...) to {key:value,...}
            try:
                data = response.json() if not raw_response.startswith('{') else eval(raw_response)  # Fallback to eval for malformed JSON
            except ValueError:
                import json
                # Attempt to parse as a string with key-value pairs
                data = {}
                pairs = raw_response.strip('()').split(',')
                for pair in pairs:
                    if ':' in pair:
                        key, value = pair.split(':', 1)
                        data[key.strip('"')] = value.strip('"')
            
            lat = data.get("latitude")
            lon = data.get("longitude")
            if lat is not None and lon is not None:
                # Update UI with validation results
                self.dockwidget.decodeDigipinLineEdit.setText(digipin)  # Keep original DIGIPIN
                self.dockwidget.latLineEdit.setText(f"{float(lat):.6f}")
                self.dockwidget.lonLineEdit.setText(f"{float(lon):.6f}")
                self.dockwidget.mapLinkLineEdit.setText(f"https://www.google.com/maps?q={float(lat)},{float(lon)}")
                self.dockwidget.statusLabel.setText(self.tr("DIGIPIN validated successfully"))

                # Enable buttons
                self.dockwidget.copyAllButton.setEnabled(True)
                self.dockwidget.openMapButton.setEnabled(True)
                self.dockwidget.copyDigipinButton.setEnabled(True)
                self.dockwidget.copyLatButton.setEnabled(True)
                self.dockwidget.copyLonButton.setEnabled(True)
                self.dockwidget.copyMapButton.setEnabled(True)

                # Zoom map to location
                canvas = self.iface.mapCanvas()
                canvas_crs = canvas.mapSettings().destinationCrs()
                point = QgsPointXY(float(lon), float(lat))
                if canvas_crs.authid() != 'EPSG:4326':
                    transform_context = QgsProject.instance().transformContext()
                    xform = QgsCoordinateTransform(
                        QgsCoordinateReferenceSystem('EPSG:4326'),
                        canvas_crs,
                        transform_context)
                    point = xform.transform(point)

                # Remove existing validation marker
                self.clear_validation_marker()

                # Add new validation marker
                self.validation_marker = QgsVertexMarker(canvas)
                self.validation_marker.setCenter(point)
                self.validation_marker.setColor(Qt.green)
                self.validation_marker.setIconSize(12)
                self.validation_marker.setPenWidth(2)

                # Center and zoom the map
                canvas.setCenter(point)
                canvas.zoomScale(1000)  # Approximate zoom level 16
                canvas.refresh()
                print(f"Map centered at {lat}, {lon} with zoom scale 1000")  # Debug log
            else:
                self.dockwidget.statusLabel.setText(self.tr("Invalid DIGIPIN or no coordinates returned"))
                print("API returned no valid coordinates")  # Debug log
        except requests.exceptions.HTTPError as e:
            self.dockwidget.statusLabel.setText(self.tr(f"API Error: {str(e)}"))
            print(f"HTTP Error: {str(e)}")  # Debug log
        except requests.exceptions.RequestException as e:
            self.dockwidget.statusLabel.setText(self.tr(f"API Connection Error: {str(e)}"))
            print(f"Connection Error: {str(e)}")  # Debug log
        except ValueError as e:
            self.dockwidget.statusLabel.setText(self.tr(f"API Response Error: Invalid JSON - {str(e)}. Raw response: {response.text}"))
            print(f"JSON Error: {str(e)} with response: {response.text}")  # Debug log with raw response
        except Exception as e:
            self.dockwidget.statusLabel.setText(self.tr(f"Unexpected error: {str(e)}"))
            print(f"Unexpected Error: {str(e)}")  # Debug log

    def open_in_maps(self):
        """Open current location in Google Maps"""
        map_link = self.dockwidget.mapLinkLineEdit.text()
        if map_link:
            try:
                success = QDesktopServices.openUrl(QUrl(map_link))
                if not success:
                    QMessageBox.warning(self.dockwidget, "Error", 
                                      f"Failed to open Google Maps URL: {map_link}. Please check the URL or your browser settings.")
                    self.dockwidget.statusLabel.setText(self.tr(f"Failed to open Google Maps URL"))
            except Exception as e:
                QMessageBox.warning(self.dockwidget, "Error", 
                                  f"Error opening Google Maps URL: {str(e)}")
                self.dockwidget.statusLabel.setText(self.tr(f"Error opening Google Maps URL: {str(e)}"))