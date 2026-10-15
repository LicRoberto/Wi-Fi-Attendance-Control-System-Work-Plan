from datetime import date

import pytest
from sqlalchemy import func, select

from motor.db import Registro, Usuario, crear_motor, crear_sesion, crear_tablas
from motor.reglas import Estado
from simulador.datos_demo import DOCENTES, sembrar_demo
from simulador.simulador_wifi import limpiar_dia, simular_dia

JUEVES = date(2026, 10, 15)
BLOQUES_POR_DIA = len(DOCENTES) * 2


def _nueva_sesion():
    engine = crear_motor("sqlite:///:memory:")
    crear_tablas(engine)
    return crear_sesion(engine)()


@pytest.fixture
def sesion():
    with _nueva_sesion() as s:
        sembrar_demo(s)
        yield s


def _estados(sesion):
    filas = sesion.execute(
        select(Registro.usuario_id, Registro.bloque_id, Registro.estado)
        .order_by(Registro.bloque_id)
    ).all()
    return [(u, b, e) for u, b, e in filas]


def test_sembrar_demo_crea_docentes_y_no_repite(sesion):
    assert sesion.scalar(select(func.count(Usuario.id))) == len(DOCENTES)
    assert sembrar_demo(sesion) is False
    assert sesion.scalar(select(func.count(Usuario.id))) == len(DOCENTES)


def test_simular_dia_genera_un_registro_por_bloque(sesion):
    conteo = simular_dia(sesion, JUEVES, semilla=1)
    assert sum(conteo.values()) == BLOQUES_POR_DIA
    assert sesion.scalar(select(func.count(Registro.id))) == BLOQUES_POR_DIA


def test_misma_semilla_mismo_resultado():
    resultados = []
    for _ in range(2):
        with _nueva_sesion() as s:
            sembrar_demo(s)
            simular_dia(s, JUEVES, semilla=7)
            resultados.append(_estados(s))
    assert resultados[0] == resultados[1]


def test_escenario_forzado(sesion):
    simular_dia(sesion, JUEVES, semilla=1, escenarios={"mperez": "falta"})
    usuario = sesion.scalar(select(Usuario).where(Usuario.cuenta == "mperez"))
    estados = sesion.scalars(
        select(Registro.estado).where(Registro.usuario_id == usuario.id)
    ).all()
    assert estados and all(e == Estado.FALTA for e in estados)


def test_todos_los_escenarios_producen_estados_validos(sesion):
    simular_dia(sesion, JUEVES, semilla=3)
    estados = set(sesion.scalars(select(Registro.estado)).all())
    assert estados <= {Estado.PRESENTE, Estado.RETARDO, Estado.FALTA, Estado.SALIDA_ANTICIPADA}
    assert Estado.PRESENTE in estados


def test_limpiar_dia_borra_registros(sesion):
    simular_dia(sesion, JUEVES, semilla=1)
    limpiar_dia(sesion, JUEVES)
    assert sesion.scalar(select(func.count(Registro.id))) == 0
