"""
Wtyczka QGIS do pobierania danych OpenStreetMap dla Olsztyna
"""

from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (QAction, QDialog, QVBoxLayout, QLabel, 
                                 QPushButton, QComboBox, QMessageBox, 
                                 QProgressBar, QGroupBox, QRadioButton)
from qgis.core import (QgsProject, QgsRasterLayer, QgsVectorLayer, 
                       QgsCoordinateReferenceSystem, QgsRectangle)
import os.path


class OlsztynGeoportalDialog(QDialog):
    """Dialog do wyboru warstw OpenStreetMap"""
    
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface  # Zapisz referencję do iface
        self.setWindowTitle("Geoportal Olsztyn - Pobieranie danych")
        self.setMinimumWidth(550)
        
        layout = QVBoxLayout()
        
        # Informacja
        info_label = QLabel("Wybierz warstwę OpenStreetMap dla obszaru Olsztyna:")
        info_label.setStyleSheet("font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(info_label)
        
        # Informacja o źródle - tylko OpenStreetMap
        source_info = QLabel("📍 Źródło danych: OpenStreetMap (wolne dane geograficzne)")
        source_info.setStyleSheet("color: #555; font-style: italic; margin: 5px 0;")
        layout.addWidget(source_info)
        
        # Lista warstw
        layer_label = QLabel("Wybierz rodzaj mapy:")
        layout.addWidget(layer_label)
        
        self.layer_combo = QComboBox()
        layout.addWidget(self.layer_combo)
        
        # Zasięg dla Olsztyna (EPSG:3857 - Web Mercator)
        # Współrzędne dla Olsztyna: 53.78°N, 20.48°E
        # Konwersja z WGS84 do Web Mercator (EPSG:3857)
        # Centrum Olsztyna: lon=20.48, lat=53.78
        # X = 2279852, Y = 7136945
        # Obszar: ~15km x 15km wokół centrum
        self.olsztyn_bbox = "2272000,7129000,2288000,7145000"
        
        # Definicje warstw OpenStreetMap
        self.layers = {
            "Standardowa mapa OSM": {
                "type": "xyz",
                "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                "zmin": 0,
                "zmax": 19,
                "crs": "EPSG:3857",
                "info": "Standardowa mapa OpenStreetMap z pełnymi detalami"
            },
            "OpenTopoMap (topograficzna)": {
                "type": "xyz",
                "url": "https://a.tile.opentopomap.org/{z}/{x}/{y}.png",
                "zmin": 0,
                "zmax": 17,
                "crs": "EPSG:3857",
                "info": "Mapa topograficzna ze szlakiami i warstwicami"
            },
            "CyclOSM (dla rowerzystów)": {
                "type": "xyz",
                "url": "https://a.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png",
                "zmin": 0,
                "zmax": 20,
                "crs": "EPSG:3857",
                "info": "Mapa z wyróżnionymi ścieżkami rowerowymi"
            },
            "Humanitarian (humanitarna)": {
                "type": "xyz",
                "url": "https://a.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png",
                "zmin": 0,
                "zmax": 20,
                "crs": "EPSG:3857",
                "info": "Mapa humanitarna z wyróżnionymi budynkami"
            },
            "Transport": {
                "type": "xyz",
                "url": "https://tile.memomaps.de/tilegen/{z}/{x}/{y}.png",
                "zmin": 0,
                "zmax": 18,
                "crs": "EPSG:3857",
                "info": "Mapa komunikacji publicznej i transportu"
            }
        }
        
        # Wypełnij listę warstw
        for layer_name in self.layers.keys():
            self.layer_combo.addItem(layer_name)
        
        # Przycisk pobierania
        self.download_btn = QPushButton("Pobierz i dodaj warstwę do projektu")
        self.download_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.download_btn.clicked.connect(self.download_layer)
        layout.addWidget(self.download_btn)
        
        # Pasek postępu
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Informacja o CRS i licencji
        crs_info = QLabel(
            "ℹ️ Dane w układzie Web Mercator (EPSG:3857)\n"
            "ℹ️ Licencja: ODbL (Open Database License)\n"
            "ℹ️ © Współtwórcy OpenStreetMap"
        )
        crs_info.setStyleSheet("color: #666; font-size: 10px; margin-top: 10px;")
        layout.addWidget(crs_info)
        
        # Linki do geoportali
        links_label = QLabel(
            '<div style="margin-top: 10px;">'
            '<a href="https://msipmo.olsztyn.eu/imap/">🗺️ Geoportal MSIPMO Olsztyn</a><br/>'
            '<a href="https://mapy.geoportal.gov.pl/">🗺️ Geoportal krajowy GUGiK</a><br/>'
            '<a href="https://www.openstreetmap.org/#map=13/53.78/20.48">🗺️ OpenStreetMap - Olsztyn</a>'
            '</div>'
        )
        links_label.setOpenExternalLinks(True)
        links_label.setStyleSheet("margin-top: 5px;")
        layout.addWidget(links_label)
        
        self.setLayout(layout)
    
    def download_layer(self):
        """Pobiera wybraną warstwę i dodaje do QGIS"""
        selected_layer = self.layer_combo.currentText()
        layer_info = self.layers.get(selected_layer)
        
        if not layer_info:
            QMessageBox.warning(self, "Błąd", "Nie wybrano warstwy.")
            return
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        
        try:
            if layer_info["type"] == "xyz":
                # Budowanie URL dla warstwy XYZ (kafelki)
                url_parts = [
                    f"type=xyz",
                    f"url={layer_info['url']}",
                    f"zmin={layer_info['zmin']}",
                    f"zmax={layer_info['zmax']}",
                    f"crs={layer_info['crs']}"
                ]
                
                url = "&".join(url_parts)
                
                # Tworzenie warstwy rastrowej XYZ
                layer = QgsRasterLayer(url, selected_layer, "wms")
                
                if layer.isValid():
                    # Ustawienie CRS projektu na EPSG:3857 jeśli jest pusty
                    project = QgsProject.instance()
                    if not project.crs().isValid() or project.crs().authid() == '':
                        target_crs = QgsCoordinateReferenceSystem("EPSG:3857")
                        project.setCrs(target_crs)
                        QMessageBox.information(
                            self,
                            "Informacja",
                            "Ustawiono CRS projektu na EPSG:3857 (Web Mercator)"
                        )
                    
                    # Dodanie warstwy do projektu
                    QgsProject.instance().addMapLayer(layer)
                    
                    # Informacja dodatkowa
                    info_text = ""
                    if "info" in layer_info:
                        info_text = f"\n\nℹ️ {layer_info['info']}"
                    
                    # Ustawienie widoku na Olsztyn
                    if self.iface:
                        canvas = self.iface.mapCanvas()
                        
                        # Współrzędne Olsztyna w EPSG:3857 (Web Mercator)
                        bbox_coords = self.olsztyn_bbox.split(',')
                        if len(bbox_coords) == 4:
                            extent = QgsRectangle(
                                float(bbox_coords[0]), float(bbox_coords[1]),
                                float(bbox_coords[2]), float(bbox_coords[3])
                            )
                            
                            # Ustaw CRS canvas na EPSG:3857
                            canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
                            
                            # Ustaw zasięg
                            canvas.setExtent(extent)
                            
                            # Odśwież mapę
                            canvas.refresh()
                            
                            # Dodatkowe wymuszenie centrum
                            canvas.zoomToFeatureExtent(extent)
                    
                    QMessageBox.information(
                        self,
                        "Sukces",
                        f"Warstwa '{selected_layer}' została pomyślnie dodana do projektu.\n\n"
                        f"CRS warstwy: {layer_info['crs']}{info_text}\n\n"
                        f"Widok ustawiony na obszar Olsztyna."
                    )
                    self.accept()
                else:
                    error_msg = layer.error().message() if layer.error() else "Nieznany błąd"
                    QMessageBox.warning(
                        self,
                        "Błąd ładowania warstwy",
                        f"Nie udało się załadować warstwy '{selected_layer}'.\n\n"
                        f"Możliwe przyczyny:\n"
                        f"• Brak połączenia z internetem\n"
                        f"• Serwer kafelków tymczasowo niedostępny\n"
                        f"• Błędny URL serwisu\n\n"
                        f"Szczegóły: {error_msg}\n\n"
                        f"URL: {layer_info['url']}"
                    )
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Błąd",
                f"Wystąpił nieoczekiwany błąd:\n{str(e)}"
            )
        
        finally:
            self.progress_bar.setVisible(False)


class OlsztynGeoportal:
    """Główna klasa wtyczki QGIS"""
    
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = 'Geoportal Olsztyn'
        self.toolbar = self.iface.addToolBar('Geoportal Olsztyn')
        self.toolbar.setObjectName('GeoportalOlsztyn')
    
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
        parent=None
    ):
        """Dodaje akcję do wtyczki"""
        
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
            self.iface.addPluginToWebMenu(
                self.menu,
                action
            )
        
        self.actions.append(action)
        return action
    
    def initGui(self):
        """Inicjalizacja GUI wtyczki"""
        
        icon_path = ':/plugins/olsztyn_geoportal/icon.png'
        self.add_action(
            icon_path,
            text='Pobierz dane z Geoportalu Olsztyna',
            callback=self.run,
            parent=self.iface.mainWindow()
        )
    
    def unload(self):
        """Usuwa wtyczkę i czyści GUI"""
        for action in self.actions:
            self.iface.removePluginWebMenu(
                'Geoportal Olsztyn',
                action
            )
            self.iface.removeToolBarIcon(action)
        del self.toolbar
    
    def run(self):
        """Uruchamia wtyczkę"""
        dialog = OlsztynGeoportalDialog(self.iface)
        dialog.exec_()


def classFactory(iface):
    """Funkcja wymagana przez QGIS do załadowania wtyczki"""
    return OlsztynGeoportal(iface)