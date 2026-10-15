import socket
import subprocess

CONFIG_RED_TUP = {
    "ssid_institucional": "TUP_Docentes",       # Nombre del Wi-Fi del TUP
    "subred": "192.168.1.0/24",                 # Rango IP de la red del campus
    "puerto_radius_acct": 1813,                 # Puerto de eventos RADIUS Accounting
    "interfaz_red": "wlan0"                     # Interfaz Wi-Fi en Arch Linux (wlan0 / wlp2s0)
}

def obtener_ip_local():
    """Obtiene la IP actual del equipo en la red Wi-Fi."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def obtener_ssid_actual():
    """Detecta el SSID del Wi-Fi al que está conectada la laptop en Arch Linux."""
    try:
        resultado = subprocess.check_output(["iwgetid", "-r"]).decode("utf-8").strip()
        return resultado if resultado else "Desconectado"
    except Exception:
        return "No detectado (Instalar wireless_tools)"