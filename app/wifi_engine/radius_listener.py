import socket
import threading
from datetime import datetime
from sqlalchemy.orm import Session
from app.core.db import SessionLocal, Usuario, AntenaAP
from app.core.rules import procesar_evento_wifi
from app.core.config_red import CONFIG_RED_TUP

class ServidorRedWifi(threading.Thread):
    def __init__(self, callback_ui=None):
        super().__init__()
        self.daemon = True
        self.running = True
        self.callback_ui = callback_ui
        self.port = CONFIG_RED_TUP["puerto_radius_acct"]

    def run(self):
        """Escucha paquetes de red en tiempo real (RADIUS / Syslog de la antena Wi-Fi)."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind(("0.0.0.0", self.port))
            print(f" Escuchador de Red Wi-Fi activo en el puerto {self.port}...")
            
            while self.running:
                data, addr = sock.recvfrom(2048)
                mensaje = data.decode("utf-8", errors="ignore")
                self.procesar_paquete_red(mensaje, addr[0])
        except Exception as e:
            print(f"Error en servidor de red Wi-Fi: {e}")
        finally:
            sock.close()

    def procesar_paquete_red(self, raw_data: str, ip_origen: str):
        """
        Interpreta la solicitud de la red real:
        Identifica al usuario por su cuenta (User-Name) y la antena AP por su MAC/BSSID (Called-Station-Id).
        """
        db: Session = SessionLocal()
        try:
            num_empleado = None
            mac_ap = None

            for linea in raw_data.split("\n"):
                if "User-Name" in linea:
                    num_empleado = linea.split("=")[1].strip().replace('"', '')
                if "Called-Station-Id" in linea:
                    mac_ap = linea.split("=")[1].strip().split(":")[0].replace('"', '')

            if num_empleado and mac_ap:
                usuario = db.query(Usuario).filter(Usuario.num_empleado == num_empleado).first()
                if usuario:
                    res = procesar_evento_wifi(
                        db=db,
                        usuario_id=usuario.id,
                        mac_ap=mac_ap,
                        timestamp=datetime.now()
                    )
                    if self.callback_ui:
                        self.callback_ui(res)
        finally:
            db.close()

    def stop(self):
        self.running = False