"""Ventana principal del Sistema de Control de Asistencia Wi-Fi (TUP).

Ejecutar desde la carpeta del proyecto:
    python -m app.main
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QMainWindow, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)
from sqlalchemy import select

from motor.db import (
    Bloque, Registro, Usuario, crear_motor, crear_sesion, crear_tablas,
)
from motor.reglas import Estado
from simulador.datos_demo import sembrar_demo
from simulador.simulador_wifi import limpiar_dia, simular_dia

RUTA_DB = Path(__file__).resolve().parent.parent / "asistencia.db"

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

ETIQUETAS = {
    Estado.PRESENTE: "Presente",
    Estado.RETARDO: "Retardo",
    Estado.FALTA: "Falta",
    Estado.SALIDA_ANTICIPADA: "Salida anticipada",
    Estado.JUSTIFICADO: "Justificado",
}
COLORES = {
    Estado.PRESENTE: "#22c55e",
    Estado.RETARDO: "#f59e0b",
    Estado.FALTA: "#ef4444",
    Estado.SALIDA_ANTICIPADA: "#a78bfa",
    Estado.JUSTIFICADO: "#38bdf8",
}
TARJETAS = (Estado.PRESENTE, Estado.RETARDO, Estado.FALTA, Estado.SALIDA_ANTICIPADA)

ESTILOS = """
QMainWindow, QWidget#raiz { background: #0f172a; }
QLabel { color: #e2e8f0; }
QLabel#titulo { font-size: 24px; font-weight: 700; color: #f8fafc; }
QLabel#subtitulo { font-size: 13px; color: #94a3b8; }
QLabel#estado { font-size: 12px; color: #64748b; }
QFrame#tarjeta { background: #1e293b; border-radius: 12px; }
QLabel#tarjeta_titulo { font-size: 12px; color: #94a3b8; }
QLabel#tarjeta_valor { font-size: 30px; font-weight: 700; color: #f8fafc; }
QPushButton {
    background: #38bdf8; color: #0f172a; border: none; border-radius: 8px;
    padding: 9px 18px; font-weight: 600;
}
QPushButton:hover { background: #7dd3fc; }
QPushButton#secundario { background: #334155; color: #e2e8f0; }
QPushButton#secundario:hover { background: #475569; }
QComboBox {
    background: #1e293b; color: #e2e8f0; border: 1px solid #334155;
    border-radius: 8px; padding: 7px 12px; min-width: 170px;
}
QComboBox QAbstractItemView {
    background: #1e293b; color: #e2e8f0; selection-background-color: #334155;
}
QTableWidget {
    background: #1e293b; alternate-background-color: #233147; color: #e2e8f0;
    border: none; border-radius: 12px; gridline-color: transparent;
    selection-background-color: #334155; selection-color: #f8fafc;
}
QHeaderView::section {
    background: #0f172a; color: #94a3b8; border: none;
    padding: 10px 8px; font-weight: 600;
}
QTableWidget::item { padding: 6px; }
QScrollBar:vertical { background: #1e293b; width: 10px; margin: 0; border-radius: 5px; }
QScrollBar::handle:vertical { background: #475569; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #64748b; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""


def fecha_larga(f: date) -> str:
    return f"{DIAS[f.weekday()].capitalize()}, {f.day} de {MESES[f.month - 1]} de {f.year}"


class VentanaPrincipal(QMainWindow):
    def __init__(self, fabrica_sesion, fecha: date | None = None):
        super().__init__()
        self.Sesion = fabrica_sesion
        self.fecha = fecha or date.today()
        self.tarjetas: dict[Estado, QLabel] = {}

        self.setWindowTitle("Control de Asistencia Wi-Fi · TUP")
        self.resize(1150, 720)
        self.setMinimumSize(900, 560)
        self._construir()
        self.refrescar()

    # ---------- Construccion de la interfaz ----------
    def _construir(self) -> None:
        raiz = QWidget(objectName="raiz")
        self.setCentralWidget(raiz)
        capa = QVBoxLayout(raiz)
        capa.setContentsMargins(28, 24, 28, 20)
        capa.setSpacing(18)

        # Encabezado
        cabecera = QHBoxLayout()
        textos = QVBoxLayout()
        textos.setSpacing(2)
        textos.addWidget(QLabel("Control de asistencia", objectName="titulo"))
        textos.addWidget(QLabel(fecha_larga(self.fecha), objectName="subtitulo"))
        cabecera.addLayout(textos)
        cabecera.addStretch()

        btn_simular = QPushButton("Simular día")
        btn_simular.clicked.connect(self._simular)
        btn_limpiar = QPushButton("Limpiar", objectName="secundario")
        btn_limpiar.clicked.connect(self._limpiar)
        cabecera.addWidget(btn_limpiar)
        cabecera.addWidget(btn_simular)
        capa.addLayout(cabecera)

        # Tarjetas de resumen
        fila = QHBoxLayout()
        fila.setSpacing(14)
        for estado in TARJETAS:
            fila.addWidget(self._tarjeta(estado))
        capa.addLayout(fila)

        # Filtro
        barra = QHBoxLayout()
        barra.addWidget(QLabel("Mostrar:"))
        self.filtro = QComboBox()
        self.filtro.addItem("Todos", None)
        for estado in ETIQUETAS:
            self.filtro.addItem(ETIQUETAS[estado], estado)
        self.filtro.currentIndexChanged.connect(self.refrescar)
        barra.addWidget(self.filtro)
        barra.addStretch()
        self.lbl_estado = QLabel("", objectName="estado")
        barra.addWidget(self.lbl_estado)
        capa.addLayout(barra)

        # Tabla
        self.tabla = QTableWidget(0, 6)
        self.tabla.setHorizontalHeaderLabels(
            ["Docente", "Zona", "Horario", "Llegada", "Estado", "Detalle"]
        )
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(40)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setShowGrid(False)
        cab = self.tabla.horizontalHeader()
        cab.setSectionResizeMode(QHeaderView.Interactive)
        cab.setStretchLastSection(True)
        for col, ancho in enumerate((210, 180, 120, 90, 150)):
            self.tabla.setColumnWidth(col, ancho)
        capa.addWidget(self.tabla, 1)

    def _tarjeta(self, estado: Estado) -> QFrame:
        marco = QFrame(objectName="tarjeta")
        marco.setStyleSheet(
            f"QFrame#tarjeta {{ border-left: 5px solid {COLORES[estado]}; }}"
        )
        capa = QVBoxLayout(marco)
        capa.setContentsMargins(18, 14, 18, 14)
        capa.setSpacing(2)
        capa.addWidget(QLabel(ETIQUETAS[estado], objectName="tarjeta_titulo"))
        valor = QLabel("0", objectName="tarjeta_valor")
        capa.addWidget(valor)
        self.tarjetas[estado] = valor
        return marco

    # ---------- Datos ----------
    def refrescar(self) -> None:
        filtro = self.filtro.currentData()
        with self.Sesion() as s:
            filas = s.execute(
                select(Registro, Usuario, Bloque)
                .join(Usuario, Registro.usuario_id == Usuario.id)
                .join(Bloque, Registro.bloque_id == Bloque.id)
                .where(Registro.fecha == self.fecha)
                .order_by(Bloque.hora_inicio, Usuario.nombre)
            ).all()

            conteo = {e: 0 for e in TARJETAS}
            visibles = []
            for reg, usuario, bloque in filas:
                if reg.estado in conteo:
                    conteo[reg.estado] += 1
                if filtro is None or reg.estado == filtro:
                    visibles.append((
                        usuario.nombre,
                        bloque.zona.nombre if bloque.zona else "Virtual",
                        f"{bloque.hora_inicio:%H:%M} - {bloque.hora_fin:%H:%M}",
                        f"{reg.llegada:%H:%M}" if reg.llegada else "-",
                        reg.estado,
                        reg.motivo,
                    ))

        for estado, etiqueta in self.tarjetas.items():
            etiqueta.setText(str(conteo[estado]))

        self.tabla.setRowCount(len(visibles))
        for fila, (nombre, zona, horario, llegada, estado, motivo) in enumerate(visibles):
            valores = (nombre, zona, horario, llegada, ETIQUETAS[estado], motivo)
            for col, texto in enumerate(valores):
                item = QTableWidgetItem(texto)
                item.setToolTip(texto)
                if col in (2, 3):
                    item.setTextAlignment(Qt.AlignCenter)
                if col == 4:
                    item.setForeground(QColor(COLORES[estado]))
                    fuente = QFont()
                    fuente.setBold(True)
                    item.setFont(fuente)
                self.tabla.setItem(fila, col, item)

        if not filas:
            self.lbl_estado.setText("Sin registros. Pulsa «Simular día» para generar la demo.")
        else:
            self.lbl_estado.setText(f"{len(visibles)} de {len(filas)} registros")

    # ---------- Acciones ----------
    def _simular(self) -> None:
        with self.Sesion() as s:
            limpiar_dia(s, self.fecha)
            simular_dia(s, self.fecha)
        self.refrescar()

    def _limpiar(self) -> None:
        with self.Sesion() as s:
            limpiar_dia(s, self.fecha)
        self.refrescar()


def main() -> None:
    engine = crear_motor(f"sqlite:///{RUTA_DB}")
    crear_tablas(engine)
    Sesion = crear_sesion(engine)
    with Sesion() as s:
        sembrar_demo(s)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(ESTILOS)
    ventana = VentanaPrincipal(Sesion)
    ventana.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
