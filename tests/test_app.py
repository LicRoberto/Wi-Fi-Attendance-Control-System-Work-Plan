import os
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.main import TARJETAS, VentanaPrincipal  # noqa: E402
from motor.db import crear_motor, crear_sesion, crear_tablas  # noqa: E402
from motor.reglas import Estado  # noqa: E402
from simulador.datos_demo import DOCENTES, sembrar_demo  # noqa: E402

JUEVES = date(2026, 10, 15)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ventana(qapp):
    engine = crear_motor("sqlite:///:memory:")
    crear_tablas(engine)
    Sesion = crear_sesion(engine)
    with Sesion() as s:
        sembrar_demo(s)
    v = VentanaPrincipal(Sesion, fecha=JUEVES)
    yield v
    v.close()


def test_arranca_vacia(ventana):
    assert ventana.tabla.rowCount() == 0
    assert "Simular" in ventana.lbl_estado.text()


def test_simular_llena_tabla_y_tarjetas(ventana):
    ventana._simular()
    esperado = len(DOCENTES) * 2
    assert ventana.tabla.rowCount() == esperado
    total = sum(int(ventana.tarjetas[e].text()) for e in TARJETAS)
    assert total == esperado


def test_filtro_por_estado(ventana):
    ventana._simular()
    indice = ventana.filtro.findData(Estado.PRESENTE)
    ventana.filtro.setCurrentIndex(indice)
    assert ventana.tabla.rowCount() == int(ventana.tarjetas[Estado.PRESENTE].text())


def test_limpiar_vacia_tabla(ventana):
    ventana._simular()
    ventana._limpiar()
    assert ventana.tabla.rowCount() == 0
