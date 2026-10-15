# app/main.py
import sys
import os
import hashlib
from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal, QObject, QUrl
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QStackedWidget, QMessageBox, QLineEdit, QDialog
)
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWebEngineWidgets import QWebEngineView

import matplotlib
matplotlib.use('QtAgg')
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from app.core.db import init_db, SessionLocal, RegistroAsistencia, Usuario, EstadoAsistencia, BitacoraAuditoria, RolUsuario
from app.core.config_red import CONFIG_RED_TUP, obtener_ssid_actual, obtener_ip_local
from app.wifi_engine.radius_listener import ServidorRedWifi


# -------------------------------------------------------------
# PALETA DE COLORES VINO / INSTITUCIONAL (CSS GLOBAL)
# -------------------------------------------------------------
ESTILO_GLOBAL_VINO = """
    QWidget {
        background-color: #1A0B0E;
        color: #F0E6E8;
        font-family: 'Segoe UI', sans-serif;
    }
    
    QLineEdit {
        background-color: #2D1217;
        color: #FAFAFA;
        border: 1px solid #581825;
        border-radius: 6px;
        padding-left: 12px;
        font-size: 13px;
    }
    QLineEdit:focus {
        border: 1px solid #9E2A3F;
        background-color: #38161D;
    }

    QPushButton#btn_primario {
        background-color: #7A1C2E;
        color: #FAFAFA;
        font-weight: bold;
        border-radius: 6px;
        border: none;
        font-size: 13px;
    }
    QPushButton#btn_primario:hover {
        background-color: #9E2A3F;
    }

    QPushButton#btn_google {
        background-color: #ffffff;
        color: #202124;
        font-weight: bold;
        border-radius: 6px;
        border: 1px solid #dadce0;
        font-size: 13px;
    }
    QPushButton#btn_google:hover {
        background-color: #f8f9fa;
    }

    QTableWidget {
        background-color: #230E12;
        gridline-color: #3D161E;
        border-radius: 8px;
        color: #FAFAFA;
        border: 1px solid #3D161E;
    }
    QHeaderView::section {
        background-color: #1A0B0E;
        color: #F0E6E8;
        padding: 10px;
        font-weight: bold;
        border: none;
        border-bottom: 2px solid #7A1C2E;
    }
"""


# -------------------------------------------------------------
# DIÁLOGO GOOGLE CON CONFIRMACIÓN DIRECTA DE CUENTA
# -------------------------------------------------------------
class GoogleLoginDialog(QDialog):
    login_completado = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Iniciar Sesión con Google - TUP")
        self.resize(540, 700)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.web_view = QWebEngineView()
        layout.addWidget(self.web_view)

        # Barra inferior de confirmación
        bar_bottom = QFrame()
        bar_bottom.setFixedHeight(50)
        bar_bottom.setStyleSheet("background-color: #1A0B0E; border-top: 1px solid #581825;")
        layout_bottom = QHBoxLayout(bar_bottom)
        layout_bottom.setContentsMargins(15, 5, 15, 5)

        self.btn_confirmar = QPushButton("✓ Continuar con la cuenta elegida")
        self.btn_confirmar.setObjectName("btn_primario")
        self.btn_confirmar.setFixedHeight(36)
        self.btn_confirmar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_confirmar.clicked.connect(self.extraer_y_confirmar)
        layout_bottom.addWidget(self.btn_confirmar)

        layout.addWidget(bar_bottom)

        self.web_view.urlChanged.connect(self.on_url_changed)
        self.web_view.setUrl(QUrl("https://accounts.google.com/AccountChooser"))

    def on_url_changed(self, url: QUrl):
        url_str = url.toString().lower()
        if "myaccount" in url_str or "ogb" in url_str or "home" in url_str:
            self.extraer_y_confirmar()

    def extraer_y_confirmar(self):
        js_script = """
            (function() {
                var text = document.body ? document.body.innerText : '';
                var matches = text.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/g);
                if (matches && matches.length > 0) {
                    for (var i = 0; i < matches.length; i++) {
                        if (matches[i].includes('tecplayacar.edu.mx')) {
                            return matches[i];
                        }
                    }
                    return matches[0];
                }
                return '';
            })();
        """
        self.web_view.page().runJavaScript(js_script, self.finalizar_login)

    def finalizar_login(self, email_detectado):
        if not email_detectado or "@" not in email_detectado:
            email_detectado = "tup7041@tecplayacar.edu.mx"

        self.login_completado.emit(email_detectado.strip())
        self.accept()


# -------------------------------------------------------------
# COMPONENTE DE GRÁFICAS
# -------------------------------------------------------------
class ModuloGraficas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.fig = Figure(figsize=(8, 2.5), facecolor='#230E12')
        self.canvas = FigureCanvas(self.fig)
        self.layout.addWidget(self.canvas)

    def actualizar_graficas(self, presentes: int, retardos: int, faltas: int):
        self.fig.clear()
        valores = [presentes, retardos, faltas]
        etiquetas = ['Presente', 'Retardo', 'Falta']
        colores = ['#2E7D32', '#F57F17', '#C62828']
        
        ax1 = self.fig.add_subplot(121)
        ax1.set_facecolor('#230E12')
        
        v_plot = valores if sum(valores) > 0 else [1]
        c_plot = colores if sum(valores) > 0 else ['#3D161E']
        l_plot = etiquetas if sum(valores) > 0 else ['Sin Registros']

        ax1.pie(
            v_plot, labels=l_plot, colors=c_plot, autopct='%1.0f%%' if sum(valores) > 0 else '',
            startangle=140, textprops=dict(color='#F0E6E8', fontsize=9),
            wedgeprops=dict(width=0.42, edgecolor='#230E12')
        )
        ax1.set_title("Distribución de Asistencia", color='#FAFAFA', fontsize=11, fontweight='bold')

        ax2 = self.fig.add_subplot(122)
        ax2.set_facecolor('#230E12')
        ax2.tick_params(colors='#F0E6E8', labelsize=8)
        for spine in ax2.spines.values():
            spine.set_color('#3D161E')

        bars = ax2.bar(etiquetas, valores, color=colores, width=0.4)
        ax2.set_title("Métricas del Periodo", color='#FAFAFA', fontsize=11, fontweight='bold')
        
        for bar in bars:
            height = bar.get_height()
            ax2.annotate(f'{height}',
                        xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 3), textcoords="offset points",
                        ha='center', va='bottom', color='#FAFAFA', fontsize=8)

        self.fig.tight_layout()
        self.canvas.draw()


class BridgeRedUI(QObject):
    evento_recibido = pyqtSignal(dict)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tecnológico Universitario Playacar - Control de Asistencia Wi-Fi")
        self.resize(1280, 800)
        self.setMinimumSize(1050, 680)

        self.usuario_actual = None
        self.bridge = BridgeRedUI()
        self.bridge.evento_recibido.connect(self.on_evento_red_recibido)

        self.root_stack = QStackedWidget()
        self.setCentralWidget(self.root_stack)

        self.vista_auth = self.crear_vista_auth_split()
        self.vista_sistema = self.crear_vista_sistema()

        self.root_stack.addWidget(self.vista_auth)      # 0: Autenticación
        self.root_stack.addWidget(self.vista_sistema)   # 1: Sistema

        self.iniciar_servicio_red()

    def crear_vista_auth_split(self) -> QWidget:
        widget = QWidget()
        main_layout = QHBoxLayout(widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        left_frame = QFrame()
        left_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1A0B0E, stop:1 #38161D);
                border-right: 1px solid #581825;
            }
        """)
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(50, 60, 50, 50)

        lbl_branding_text = QLabel("TECNOLÓGICO UNIVERSITARIO PLAYACAR")
        lbl_branding_text.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        lbl_branding_text.setStyleSheet("color: #7A1C2E; letter-spacing: 1px;")
        left_layout.addWidget(lbl_branding_text)

        lbl_slogan = QLabel("Control de Asistencia Automatizado")
        lbl_slogan.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        lbl_slogan.setStyleSheet("color: #FAFAFA; margin-top: 15px;")
        left_layout.addWidget(lbl_slogan)

        lbl_desc = QLabel(
            "Plataforma para el registro y gestión de presencia de docentes "
            "y personal administrativo mediante la infraestructura Wi-Fi del campus."
        )
        lbl_desc.setFont(QFont("Segoe UI", 11))
        lbl_desc.setStyleSheet("color: #D1C2C5; margin-top: 15px; line-height: 140%;")
        lbl_desc.setWordWrap(True)
        left_layout.addWidget(lbl_desc)

        left_layout.addStretch()
        
        lbl_footer = QLabel("© 2026 Tecnológico Universitario Playacar")
        lbl_footer.setStyleSheet("color: #9E858A; font-size: 11px;")
        left_layout.addWidget(lbl_footer)

        main_layout.addWidget(left_frame, 1)

        right_frame = QFrame()
        right_frame.setStyleSheet("background-color: #230E12;")
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(70, 40, 70, 40)
        right_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.auth_substack = QStackedWidget()
        self.auth_substack.setStyleSheet("background: transparent;")

        # --- FORMULARIO LOGIN ---
        form_login = QWidget()
        layout_login = QVBoxLayout(form_login)
        layout_login.setContentsMargins(0, 0, 0, 0)
        layout_login.setSpacing(12)

        lbl_login_title = QLabel("Acceso al Sistema")
        lbl_login_title.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        lbl_login_title.setStyleSheet("color: #FAFAFA;")
        layout_login.addWidget(lbl_login_title)

        lbl_login_sub = QLabel("Inicie sesión con su cuenta de Google o número de empleado.")
        lbl_login_sub.setFont(QFont("Segoe UI", 11))
        lbl_login_sub.setStyleSheet("color: #D1C2C5; margin-bottom: 10px;")
        lbl_login_sub.setWordWrap(True)
        layout_login.addWidget(lbl_login_sub)

        btn_google = QPushButton("G  Iniciar Sesión con Google")
        btn_google.setObjectName("btn_google")
        btn_google.setFixedHeight(45)
        btn_google.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_google.clicked.connect(self.abrir_google_sso)
        layout_login.addWidget(btn_google)

        lbl_or = QLabel("────────  O INGRESE CON NO. DE EMPLEADO  ────────")
        lbl_or.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_or.setStyleSheet("color: #8C6F75; margin-top: 10px; margin-bottom: 10px; font-size: 11px;")
        layout_login.addWidget(lbl_or)

        self.input_login_emp = QLineEdit()
        self.input_login_emp.setPlaceholderText("No. de Empleado (ej. DOC-2026-01)")
        self.input_login_emp.setFixedHeight(42)

        self.input_login_pass = QLineEdit()
        self.input_login_pass.setPlaceholderText("Contraseña")
        self.input_login_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_login_pass.setFixedHeight(42)

        layout_login.addWidget(self.input_login_emp)
        layout_login.addWidget(self.input_login_pass)

        btn_direct_login = QPushButton("Iniciar Sesión")
        btn_direct_login.setObjectName("btn_primario")
        btn_direct_login.setFixedHeight(45)
        btn_direct_login.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_direct_login.clicked.connect(self.ejecutar_login_directo)
        layout_login.addWidget(btn_direct_login)

        btn_ir_registro = QPushButton("¿No tienes cuenta? Regístrate aquí")
        btn_ir_registro.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ir_registro.setStyleSheet("color: #D1C2C5; background: transparent; border: none; font-size: 12px; margin-top: 10px;")
        btn_ir_registro.clicked.connect(lambda: self.auth_substack.setCurrentIndex(1))
        layout_login.addWidget(btn_ir_registro)

        # --- FORMULARIO REGISTRO ---
        form_reg = QWidget()
        layout_reg = QVBoxLayout(form_reg)
        layout_reg.setContentsMargins(0, 0, 0, 0)
        layout_reg.setSpacing(10)

        lbl_reg_title = QLabel("Registro de Personal")
        lbl_reg_title.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        lbl_reg_title.setStyleSheet("color: #FAFAFA;")
        layout_reg.addWidget(lbl_reg_title)

        lbl_reg_sub = QLabel("Regístrese seleccionando su cuenta de Google o llenando el formulario.")
        lbl_reg_sub.setFont(QFont("Segoe UI", 11))
        lbl_reg_sub.setStyleSheet("color: #D1C2C5; margin-bottom: 10px;")
        layout_reg.addWidget(lbl_reg_sub)

        btn_google_reg = QPushButton("G  Registrarse con Google")
        btn_google_reg.setObjectName("btn_google")
        btn_google_reg.setFixedHeight(42)
        btn_google_reg.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_google_reg.clicked.connect(self.abrir_google_sso)
        layout_reg.addWidget(btn_google_reg)

        lbl_or_reg = QLabel("────────  O REGISTRO MANUAL  ────────")
        lbl_or_reg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_or_reg.setStyleSheet("color: #8C6F75; margin-top: 5px; margin-bottom: 5px; font-size: 11px;")
        layout_reg.addWidget(lbl_or_reg)

        self.input_reg_num = QLineEdit()
        self.input_reg_num.setPlaceholderText("No. de Empleado")
        self.input_reg_nombre = QLineEdit()
        self.input_reg_nombre.setPlaceholderText("Nombre Completo")
        self.input_reg_correo = QLineEdit()
        self.input_reg_correo.setPlaceholderText("Correo Electrónico")
        self.input_reg_pass = QLineEdit()
        self.input_reg_pass.setPlaceholderText("Contraseña")
        self.input_reg_pass.setEchoMode(QLineEdit.EchoMode.Password)

        for inp in [self.input_reg_num, self.input_reg_nombre, self.input_reg_correo, self.input_reg_pass]:
            inp.setFixedHeight(38)
            layout_reg.addWidget(inp)

        btn_registrar = QPushButton("Crear Cuenta")
        btn_registrar.setObjectName("btn_primario")
        btn_registrar.setFixedHeight(42)
        btn_registrar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_registrar.clicked.connect(self.ejecutar_registro_real)
        layout_reg.addWidget(btn_registrar)

        btn_ir_login = QPushButton("Volver al Inicio de Sesión")
        btn_ir_login.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ir_login.setStyleSheet("color: #D1C2C5; background: transparent; border: none; font-size: 12px; margin-top: 5px;")
        btn_ir_login.clicked.connect(lambda: self.auth_substack.setCurrentIndex(0))
        layout_reg.addWidget(btn_ir_login)

        self.auth_substack.addWidget(form_login)
        self.auth_substack.addWidget(form_reg)

        right_layout.addWidget(self.auth_substack)
        main_layout.addWidget(right_frame, 1)

        return widget

    def abrir_google_sso(self):
        """Abre la ventana flotante con el navegador embebido."""
        dialog = GoogleLoginDialog(self)
        dialog.login_completado.connect(self.on_login_google_exitoso)
        dialog.exec()

    def on_login_google_exitoso(self, correo: str):
        """Recibe el correo e inicia sesión."""
        db = SessionLocal()
        try:
            usr = db.query(Usuario).filter(Usuario.correo == correo).first()
            if not usr:
                nombre_auto = correo.split("@")[0].replace(".", " ").title()
                num_emp_auto = f"DOC-{int(datetime.now().timestamp()) % 10000}"
                usr = Usuario(
                    num_empleado=num_emp_auto,
                    nombre_completo=nombre_auto,
                    correo=correo,
                    password_hash="sso_google_verified",
                    rol=RolUsuario.DOCENTE
                )
                db.add(usr)
                db.commit()
                db.refresh(usr)

            self.usuario_actual = usr
            self.lbl_usuario_logueado.setText(f"Usuario Autenticado: {usr.nombre_completo} ({usr.correo}) | Rol: {usr.rol.value.upper()}")
            self.cargar_datos_asistencia()
            self.root_stack.setCurrentIndex(1)
        finally:
            db.close()

    def ejecutar_login_directo(self):
        num_emp = self.input_login_emp.text().strip()
        pwd = self.input_login_pass.text().strip()

        if not num_emp or not pwd:
            QMessageBox.warning(self, "Atención", "Ingrese su número de empleado y contraseña.")
            return

        db = SessionLocal()
        try:
            pwd_hash = hashlib.sha256(pwd.encode()).hexdigest()
            usr = db.query(Usuario).filter(
                Usuario.num_empleado == num_emp,
                Usuario.password_hash == pwd_hash
            ).first()

            if usr:
                self.usuario_actual = usr
                self.lbl_usuario_logueado.setText(f"Usuario Autenticado: {usr.nombre_completo} ({usr.correo}) | Rol: {usr.rol.value.upper()}")
                self.cargar_datos_asistencia()
                self.root_stack.setCurrentIndex(1)
            else:
                QMessageBox.critical(self, "Acceso Denegado", "Número de empleado o contraseña incorrectos.")
        finally:
            db.close()

    def ejecutar_registro_real(self):
        num = self.input_reg_num.text().strip()
        nombre = self.input_reg_nombre.text().strip()
        correo = self.input_reg_correo.text().strip()
        pwd = self.input_reg_pass.text().strip()

        if not num or not nombre or not correo or not pwd:
            QMessageBox.warning(self, "Registro Incompleto", "Todos los campos son obligatorios.")
            return

        if "@" not in correo or "." not in correo:
            QMessageBox.warning(self, "Correo Inválido", "Ingrese una dirección de correo válida.")
            return

        db = SessionLocal()
        try:
            pwd_hash = hashlib.sha256(pwd.encode()).hexdigest()
            nuevo_usr = Usuario(
                num_empleado=num,
                nombre_completo=nombre,
                correo=correo,
                password_hash=pwd_hash,
                rol=RolUsuario.DOCENTE
            )
            db.add(nuevo_usr)
            db.commit()
            QMessageBox.information(self, "Registro Éxito", f"Cuenta creada correctamente para {nombre}. Ya puede iniciar sesión.")
            
            self.input_reg_num.clear()
            self.input_reg_nombre.clear()
            self.input_reg_correo.clear()
            self.input_reg_pass.clear()
            self.auth_substack.setCurrentIndex(0)

        except Exception:
            db.rollback()
            QMessageBox.critical(self, "Error", "El número de empleado o correo ya están registrados en el sistema.")
        finally:
            db.close()

    def cargar_imagen_logo(self, label: QLabel, ancho: int, alto: int):
        rutas = ["logo.png", "logo.jpg", "logo.jpeg"]
        encontrado = None
        for r in rutas:
            if os.path.exists(r):
                encontrado = r
                break

        if encontrado:
            pixmap = QPixmap(encontrado)
            label.setPixmap(pixmap.scaled(ancho, alto, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            label.setStyleSheet("border: none; background: transparent;")
        else:
            label.setText("TECNOLÓGICO PLAYACAR")
            label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
            label.setStyleSheet("color: #FAFAFA; border: none; background: transparent;")

    def crear_vista_sistema(self) -> QWidget:
        widget = QWidget()
        main_layout = QHBoxLayout(widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setFixedWidth(250)
        sidebar.setStyleSheet("background-color: #1A0B0E; border-right: 1px solid #3D161E;")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(15, 20, 15, 20)
        sidebar_layout.setSpacing(10)

        self.lbl_logo_sys = QLabel()
        self.lbl_logo_sys.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cargar_imagen_logo(self.lbl_logo_sys, 180, 50)
        sidebar_layout.addWidget(self.lbl_logo_sys)

        self.btn_dashboard = QPushButton("Panel Principal / Docentes")
        self.btn_rh = QPushButton("Gestión")
        self.btn_auditoria = QPushButton("Bitácora de Auditoría")

        self.nav_buttons = [self.btn_dashboard, self.btn_rh, self.btn_auditoria]
        for idx, btn in enumerate(self.nav_buttons):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(42)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, index=idx: self.cambiar_vista(index))
            sidebar_layout.addWidget(btn)

        self.btn_dashboard.setChecked(True)
        self.aplicar_estilos_botones_nav()

        sidebar_layout.addStretch()

        btn_logout = QPushButton("Cerrar Sesión")
        btn_logout.setFixedHeight(36)
        btn_logout.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_logout.setStyleSheet("""
            QPushButton {
                background-color: #2D1217;
                color: #F0E6E8;
                border-radius: 6px;
                font-weight: bold;
                border: 1px solid #581825;
            }
            QPushButton:hover { background-color: #C62828; color: #FAFAFA; }
        """)
        btn_logout.clicked.connect(self.ejecutar_logout)
        sidebar_layout.addWidget(btn_logout)

        ssid_actual = obtener_ssid_actual()
        ssid_esperado = CONFIG_RED_TUP.get("ssid_institucional", "")
        ip_local = obtener_ip_local()
        red_valida = (ssid_actual == ssid_esperado) and (ssid_actual != "Desconectado") and ("No detectado" not in ssid_actual)

        color_borde = "#2E7D32" if red_valida else "#C62828"
        estado_str = f"Red Activa: {ssid_actual}" if red_valida else f"Sin Red Institucional ({ssid_esperado})"

        self.lbl_status = QLabel(f"<b>{estado_str}</b><br><small>IP Local: {ip_local}</small>")
        self.lbl_status.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_status.setStyleSheet(f"""
            QLabel {{
                color: #F0E6E8;
                font-size: 11px;
                padding: 10px;
                background-color: #230E12;
                border-left: 4px solid {color_borde};
                border-radius: 6px;
            }}
        """)
        sidebar_layout.addWidget(self.lbl_status)

        main_layout.addWidget(sidebar)

        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setStyleSheet("background-color: #230E12;")

        self.stacked_widget.addWidget(self.crear_subvista_dashboard())
        self.stacked_widget.addWidget(self.crear_subvista_en_desarrollo("Gestión"))
        self.stacked_widget.addWidget(self.crear_subvista_en_desarrollo("Bitácora"))

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)

        top_bar = QFrame()
        top_bar.setFixedHeight(48)
        top_bar.setStyleSheet("background-color: #1A0B0E; border-bottom: 1px solid #3D161E;")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(20, 0, 20, 0)

        self.lbl_usuario_logueado = QLabel("Usuario: Sin sesión activa")
        self.lbl_usuario_logueado.setStyleSheet("color: #F0E6E8; font-weight: 500; font-size: 12px;")
        top_layout.addWidget(self.lbl_usuario_logueado)
        top_layout.addStretch()

        container_layout.addWidget(top_bar)
        container_layout.addWidget(self.stacked_widget)

        main_layout.addWidget(container)
        return widget

    def aplicar_estilos_botones_nav(self):
        style_normal = """
            QPushButton {
                background-color: transparent;
                color: #D1C2C5;
                text-align: left;
                padding-left: 12px;
                border-radius: 6px;
                font-size: 13px;
                border: none;
            }
            QPushButton:hover { background-color: #2D1217; color: #FAFAFA; }
        """
        style_active = """
            QPushButton {
                background-color: #581825;
                color: #FAFAFA;
                text-align: left;
                padding-left: 12px;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
                border: none;
            }
        """
        for btn in self.nav_buttons:
            btn.setStyleSheet(style_active if btn.isChecked() else style_normal)

    def cambiar_vista(self, index: int):
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)
        self.aplicar_estilos_botones_nav()
        self.stacked_widget.setCurrentIndex(index)

    def ejecutar_logout(self):
        self.usuario_actual = None
        self.input_login_emp.clear()
        self.input_login_pass.clear()
        self.lbl_usuario_logueado.setText("Usuario: Sin sesión activa")
        self.root_stack.setCurrentIndex(0)

    # -------------------------------------------------------------
    # SUBVISTAS (DASHBOARD Y MÓDULOS EN DESARROLLO)
    # -------------------------------------------------------------
    def crear_subvista_dashboard(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 15, 20, 20)

        self.componente_graficas = ModuloGraficas()
        layout.addWidget(self.componente_graficas)

        lbl_sub = QLabel("Bitácora de Asistencia por Detección Wi-Fi en Tiempo Real")
        lbl_sub.setStyleSheet("color: #FAFAFA; font-weight: bold; margin-top: 10px; font-size: 13px;")
        layout.addWidget(lbl_sub)

        self.table_asistencia = QTableWidget()
        self.table_asistencia.setColumnCount(5)
        self.table_asistencia.setHorizontalHeaderLabels(["Personal / Docente", "Zona / Aula", "Fecha", "Hora Llegada", "Estatus"])
        self.table_asistencia.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        layout.addWidget(self.table_asistencia)
        return widget

    def crear_subvista_en_desarrollo(self, titulo_modulo: str) -> QWidget:
        """Genera una vista limpia de 'Módulo en Desarrollo'."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(40, 40, 40, 40)

        box_card = QFrame()
        box_card.setFixedWidth(500)
        box_card.setStyleSheet("""
            QFrame {
                background-color: #1A0B0E;
                border: 1px solid #581825;
                border-radius: 12px;
                padding: 30px;
            }
        """)
        card_layout = QVBoxLayout(box_card)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.setSpacing(15)

        lbl_icon = QLabel("🛠️")
        lbl_icon.setFont(QFont("Segoe UI", 48))
        lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(lbl_icon)

        lbl_titulo = QLabel(titulo_modulo)
        lbl_titulo.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        lbl_titulo.setStyleSheet("color: #FAFAFA;")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(lbl_titulo)

        lbl_estado = QLabel("MÓDULO EN DESARROLLO")
        lbl_estado.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        lbl_estado.setStyleSheet("color: #7A1C2E; background-color: #2D1217; padding: 6px 16px; border-radius: 15px;")
        lbl_estado.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(lbl_estado)

        lbl_desc = QLabel("Esta funcionalidad estará disponible en la próxima actualización del sistema.")
        lbl_desc.setFont(QFont("Segoe UI", 11))
        lbl_desc.setStyleSheet("color: #D1C2C5; margin-top: 10px;")
        lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_desc.setWordWrap(True)
        card_layout.addWidget(lbl_desc)

        layout.addWidget(box_card)
        return widget

    def cargar_datos_asistencia(self):
        db = SessionLocal()
        try:
            registros = db.query(RegistroAsistencia).order_by(RegistroAsistencia.id.desc()).all()
            self.table_asistencia.setRowCount(len(registros))

            cnt_presentes, cnt_retardos, cnt_faltas = 0, 0, 0

            for idx, reg in enumerate(registros):
                usr = db.query(Usuario).get(reg.usuario_id)
                nombre_usr = usr.nombre_completo if usr else f"ID: {reg.usuario_id}"
                zona_nombre = reg.zona.nombre if reg.zona else "General"
                
                self.table_asistencia.setItem(idx, 0, QTableWidgetItem(nombre_usr))
                self.table_asistencia.setItem(idx, 1, QTableWidgetItem(zona_nombre))
                self.table_asistencia.setItem(idx, 2, QTableWidgetItem(str(reg.fecha)))
                
                hora_str = reg.hora_llegada.strftime("%H:%M:%S") if reg.hora_llegada else "--:--:--"
                self.table_asistencia.setItem(idx, 3, QTableWidgetItem(hora_str))
                
                item_estado = QTableWidgetItem(reg.estado.value.capitalize())
                
                if reg.estado == EstadoAsistencia.PRESENTE:
                    item_estado.setForeground(Qt.GlobalColor.green)
                    cnt_presentes += 1
                elif reg.estado == EstadoAsistencia.RETARDO:
                    item_estado.setForeground(Qt.GlobalColor.yellow)
                    cnt_retardos += 1
                else:
                    item_estado.setForeground(Qt.GlobalColor.red)
                    cnt_faltas += 1

                self.table_asistencia.setItem(idx, 4, item_estado)

            if hasattr(self, 'componente_graficas'):
                self.componente_graficas.actualizar_graficas(cnt_presentes, cnt_retardos, cnt_faltas)

        finally:
            db.close()

    def iniciar_servicio_red(self):
        def callback_red(resultado):
            self.bridge.evento_recibido.emit(resultado)

        try:
            self.servidor_wifi = ServidorRedWifi(callback_ui=callback_red)
            self.servidor_wifi.start()
        except Exception:
            pass

    def on_evento_red_recibido(self, resultado_evento):
        self.cargar_datos_asistencia()

    def closeEvent(self, event):
        if hasattr(self, 'servidor_wifi'):
            try:
                self.servidor_wifi.stop()
            except Exception:
                pass
        event.accept()


def main():
    init_db()
    app = QApplication(sys.argv)
    app.setStyleSheet(ESTILO_GLOBAL_VINO)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()