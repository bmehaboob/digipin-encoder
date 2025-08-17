import os
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDockWidget
from qgis.PyQt.QtCore import pyqtSignal

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'digipin_encoder_dockwidget_base.ui'))

class DIGIPIN_ENCODERDockWidget(QDockWidget, FORM_CLASS):
    
    closed = pyqtSignal()
    
    def __init__(self, parent=None):
        super(DIGIPIN_ENCODERDockWidget, self).__init__(parent)
        self.setupUi(self)
    
    def closeEvent(self, event):
        self.closed.emit()
        super(DIGIPIN_ENCODERDockWidget, self).closeEvent(event)