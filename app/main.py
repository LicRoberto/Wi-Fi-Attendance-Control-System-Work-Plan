import sys
from datetime import datetime
import qdarktheme
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QMessageBox
)
from PyQt6.QtGui import QFont

from app.core.db import init_db, SessionLocal, RegistroAsistencia, Usuario, EstadoAsistencia
from app.core.config_red import CONFIG_RED_TUP, obtener_ssid_actual, obtener_ip_local
from app.wifi_engine.radius_listener import ServidorRedWifi

class BridgeRedUI(QObject):
    evento_recibido = pyqtSignal(dict)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sistema de Control de Asistencia Wi-Fi - TUP")
        self.resize(1150, 720)
        self.bridge = BridgeRedUI()
        self.bridge.evento_recibido.connect(self.on_evento_red_recibido)
        self.init_ui()
        self.cargar_datos()
        self.iniciar_servicio_red()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        sidebar = QFrame()
        sidebar.setStyleSheet("background-color: #181825; min-width: 240px; max-width: 240px;")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(15, 20, 15, 20)

        lbl_logo = QLabel("TUP Wi-Fi")
        lbl_logo.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        lbl_logo.setStyleSheet("color: #89b4fa; margin-bottom: 20px;")
        sidebar_layout.addWidget(lbl_logo)

        self.btn_dashboard = QPushButton("Panel / Docentes")
        self.btn_rh = QPushButton("Gestión")
        self.btn_auditoria = QPushButton("Bitácora Auditoría")
        
        for btn in [self.btn_dashboard, self.btn_rh, self.btn_auditoria]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #cdd6f4;
                    text-align: left;
                    padding: 12px;
                    border-radius: 8px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #313244;
                    color: #89b4fa;
                }
            """)
            sidebar_layout.addWidget(btn)

        sidebar_layout.addStretch()

        ssid = obtener_ssid_actual()
        ip_local = obtener_ip_local()

        self.lbl_status = QLabel(
            f"🟢 <b>Servicio de Red Activo</b><br>"
            f"SSID: <span style='color:#89b4fa;'>{ssid}</span><br>"
            f"IP: <span style='color:#a6e3a1;'>{ip_local}</span><br>"
            f"Puerto UDP: {CONFIG_RED_TUP['puerto_radius_acct']}"
        )
        self.lbl_status.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_status.setStyleSheet("color: #cdd6f4; font-size: 11px; padding: 10px; background: #11111b; border-radius: 8px;")
        sidebar_layout.addWidget(self.lbl_status)

        main_layout.addWidget(sidebar)
        content_area = QFrame()
        content_area.setStyleSheet("background-color: #1e1e2e;")
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(25, 25, 25, 25)
        lbl_header = QLabel("Control de Asistencia Automatizado por Proximidad Wi-Fi")
        lbl_header.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        lbl_header.setStyleSheet("color: #cdd6f4;")
        content_layout.addWidget(lbl_header)
        cards_layout = QHBoxLayout()
        self.card_presentes = self.crear_tarjeta("Presentes Hoy", "0", "#a6e3a1")
        self.card_retardos = self.crear_tarjeta("Retardos", "0", "#f9e2af")
        self.card_faltas = self.crear_tarjeta("Faltas / Ausencias", "0", "#f38ba8")
        cards_layout.addWidget(self.card_presentes)
        cards_layout.addWidget(self.card_retardos)
        cards_layout.addWidget(self.card_faltas)
        content_layout.addLayout(cards_layout)
        lbl_tabla_titulo = QLabel("<b>Registros de Asistencia en Tiempo Real:</b>")
        lbl_tabla_titulo.setStyleSheet("color: #bac2de; margin-top: 15px;")
        content_layout.addWidget(lbl_tabla_titulo)
        
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Empleado / Docente", "Zona / Aula", "Fecha", "Hora Llegada", "Estado"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #181825;
                gridline-color: #313244;
                border-radius: 10px;
                color: #cdd6f4;
            }
            QHeaderView::section {
                background-color: #313244;
                color: #89b4fa;
                padding: 10px;
                font-weight: bold;
                border: none;
            }
            QTableWidget::item {
                padding: 8px;
            }
        """)
        content_layout.addWidget(self.table)

        main_layout.addWidget(content_area)

    def crear_tarjeta(self, titulo: str, valor: str, color_hex: str) -> QFrame:
        card = QFrame()
        card.setObjectName("card_frame")
        card.setStyleSheet(f"""
            QFrame#card_frame {{
                background-color: #181825;
                border-radius: 12px;
                border-left: 6px solid {color_hex};
                padding: 15px;
            }}
        """)
        layout = QVBoxLayout(card)
        
        lbl_title = QLabel(titulo)
        lbl_title.setStyleSheet("color: #a6adc8; font-size: 13px;")
        
        lbl_val = QLabel(valor)
        lbl_val.setObjectName("val_label")
        lbl_val.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        lbl_val.setStyleSheet(f"color: {color_hex};")
        
        layout.addWidget(lbl_title)
        layout.addWidget(lbl_val)
        return card

    def actualizar_valor_tarjeta(self, card: QFrame, nuevo_valor: str):
        val_label = card.findChild(QLabel, "val_label")
        if val_label:
            val_label.setText(nuevo_valor)

    def cargar_datos(self):
        """Carga el historial de asistencias desde SQLite en la tabla."""
        db = SessionLocal()
        try:
            registros = db.query(RegistroAsistencia).order_by(RegistroAsistencia.id.desc()).all()
            self.table.setRowCount(len(registros))

            cnt_presentes = 0
            cnt_retardos = 0
            cnt_faltas = 0

            for idx, reg in enumerate(registros):
                usr = db.query(Usuario).get(reg.usuario_id)
                nombre_usr = usr.nombre_completo if usr else f"ID: {reg.usuario_id}"
                zona_nombre = reg.zona.nombre if reg.zona else "General"
                
                self.table.setItem(idx, 0, QTableWidgetItem(nombre_usr))
                self.table.setItem(idx, 1, QTableWidgetItem(zona_nombre))
                self.table.setItem(idx, 2, QTableWidgetItem(str(reg.fecha)))
                
                hora_str = reg.hora_llegada.strftime("%H:%M:%S") if reg.hora_llegada else "--:--:--"
                self.table.setItem(idx, 3, QTableWidgetItem(hora_str))
                
                estado_texto = reg.estado.value.capitalize()
                item_estado = QTableWidgetItem(estado_texto)
                
                # Asignar color al texto del estado
                if reg.estado == EstadoAsistencia.PRESENTE:
                    item_estado.setForeground(Qt.GlobalColor.green)
                    cnt_presentes += 1
                elif reg.estado == EstadoAsistencia.RETARDO:
                    item_estado.setForeground(Qt.GlobalColor.yellow)
                    cnt_retardos += 1
                else:
                    item_estado.setForeground(Qt.GlobalColor.red)
                    cnt_faltas += 1

                self.table.setItem(idx, 4, item_estado)

            self.actualizar_valor_tarjeta(self.card_presentes, str(cnt_presentes))
            self.actualizar_valor_tarjeta(self.card_retardos, str(cnt_retardos))
            self.actualizar_valor_tarjeta(self.card_faltas, str(cnt_faltas))

        finally:
            db.close()

    def iniciar_servicio_red(self):
        """Inicia el servidor de escucha de eventos Wi-Fi en segundo plano."""
        def callback_red(resultado):
            self.bridge.evento_recibido.emit(resultado)

        self.servidor_wifi = ServidorRedWifi(callback_ui=callback_red)
        self.servidor_wifi.start()

    def on_evento_red_recibido(self, resultado_evento):
        """Método invocado automáticamente cuando la red registra la cercanía de un usuario."""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Evento de red detectado:", resultado_evento)
        self.cargar_datos()

    def closeEvent(self, event):
        """Asegura detener los sockets al cerrar la ventana."""
        if hasattr(self, 'servidor_wifi'):
            self.servidor_wifi.stop()
        event.accept()

def main():
    init_db()
    app = QApplication(sys.argv)
    qdarktheme.setup_theme("dark")
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()