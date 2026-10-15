from datetime import date, datetime, time, timedelta

import pytest
from sqlalchemy import select

from motor.db import (
    Antena, Bitacora, Bloque, Fuente, Modalidad, Registro, Usuario, Zona,
    crear_motor, crear_sesion, crear_tablas,
)
from motor.reglas import Estado
from motor.servicio import cerrar_bloque, cerrar_dia, procesar_evento

MIERCOLES = date(2026, 10, 14)  # weekday() == 2


def hora(h, m, fecha=MIERCOLES):
    return datetime(fecha.year, fecha.month, fecha.day, h, m)


@pytest.fixture
def sesion():
    engine = crear_motor("sqlite:///:memory:")
    crear_tablas(engine)
    with crear_sesion(engine)() as s:
        yield s


@pytest.fixture
def mundo(sesion):
    aula3, aula4 = Zona(nombre="Aula 3"), Zona(nombre="Aula 4")
    sesion.add_all([aula3, aula4])
    sesion.flush()
    sesion.add_all([
        Antena(identificador="AP-AULA-3", zona_id=aula3.id),
        Antena(identificador="AP-AULA-4", zona_id=aula4.id),
    ])
    perez = Usuario(cuenta="perez", nombre="Prof. Pérez")
    sesion.add(perez)
    sesion.flush()
    bloque = Bloque(
        usuario_id=perez.id, zona_id=aula3.id, dia_semana=2,
        hora_inicio=time(8, 0), hora_fin=time(10, 0),
    )
    sesion.add(bloque)
    sesion.commit()
    return perez, bloque


def _registros(sesion):
    return sesion.scalars(select(Registro)).all()


def test_llegada_dentro_de_tolerancia_es_presente(sesion, mundo):
    r = procesar_evento(sesion, "perez", "AP-AULA-3", hora(8, 7))
    assert r.registrado is True
    assert r.registro.estado == Estado.PRESENTE
    assert r.registro.llegada == hora(8, 7)


def test_llegada_tarde_es_retardo(sesion, mundo):
    r = procesar_evento(sesion, "perez", "AP-AULA-3", hora(8, 15))
    assert r.registro.estado == Estado.RETARDO
    assert r.registro.minutos == 15


def test_llegada_despues_del_limite_es_falta(sesion, mundo):
    r = procesar_evento(sesion, "perez", "AP-AULA-3", hora(8, 45))
    assert r.registro.estado == Estado.FALTA


def test_llegada_anticipada_cuenta_como_presente(sesion, mundo):
    r = procesar_evento(sesion, "perez", "AP-AULA-3", hora(7, 35))
    assert r.registro.estado == Estado.PRESENTE


def test_demasiado_temprano_se_ignora(sesion, mundo):
    r = procesar_evento(sesion, "perez", "AP-AULA-3", hora(7, 20))
    assert r.registrado is False
    assert _registros(sesion) == []


def test_antena_de_otra_zona_se_ignora(sesion, mundo):
    r = procesar_evento(sesion, "perez", "AP-AULA-4", hora(8, 5))
    assert r.registrado is False
    assert "zona" in r.motivo
    assert _registros(sesion) == []


def test_cuenta_o_antena_desconocida(sesion, mundo):
    assert procesar_evento(sesion, "nadie", "AP-AULA-3", hora(8, 5)).registrado is False
    assert procesar_evento(sesion, "perez", "AP-XX", hora(8, 5)).registrado is False


def test_fuera_de_horario_o_dia_se_ignora(sesion, mundo):
    assert procesar_evento(sesion, "perez", "AP-AULA-3", hora(11, 0)).registrado is False
    jueves = date(2026, 10, 15)
    assert procesar_evento(sesion, "perez", "AP-AULA-3", hora(8, 5, jueves)).registrado is False


def test_bloque_virtual_no_se_registra_por_wifi(sesion, mundo):
    _, bloque = mundo
    bloque.modalidad = Modalidad.VIRTUAL
    sesion.commit()
    assert procesar_evento(sesion, "perez", "AP-AULA-3", hora(8, 5)).registrado is False


def test_evento_duplicado_no_crea_otro_registro(sesion, mundo):
    procesar_evento(sesion, "perez", "AP-AULA-3", hora(8, 0))
    r = procesar_evento(sesion, "perez", "AP-AULA-3", hora(8, 10))
    assert r.registrado is False
    assert "duplicado" in r.motivo
    registros = _registros(sesion)
    assert len(registros) == 1
    assert registros[0].salida == hora(8, 10)  # pero si actualiza la ultima vez visto


def test_evento_posterior_confirma_presencia(sesion, mundo):
    procesar_evento(sesion, "perez", "AP-AULA-3", hora(8, 0))
    r = procesar_evento(sesion, "perez", "AP-AULA-3", hora(8, 20))
    assert r.registrado is True
    assert r.registro.salida == hora(8, 20)


def test_registro_deja_huella_en_bitacora(sesion, mundo):
    procesar_evento(sesion, "perez", "AP-AULA-3", hora(8, 7))
    lineas = sesion.scalars(select(Bitacora)).all()
    assert any(l.accion == "registro_creado" for l in lineas)


def test_cerrar_bloque_sin_eventos_es_falta(sesion, mundo):
    _, bloque = mundo
    reg = cerrar_bloque(sesion, bloque, MIERCOLES)
    assert reg.estado == Estado.FALTA
    assert reg.llegada is None
    lineas = sesion.scalars(select(Bitacora)).all()
    assert any(l.accion == "falta_registrada" for l in lineas)


def test_bloque_completo_queda_presente(sesion, mundo):
    _, bloque = mundo
    t = hora(8, 0)
    while t < hora(10, 0):
        procesar_evento(sesion, "perez", "AP-AULA-3", t)
        t += timedelta(minutes=10)
    reg = cerrar_bloque(sesion, bloque, MIERCOLES)
    assert reg.estado == Estado.PRESENTE


def test_salida_anticipada_al_cerrar(sesion, mundo):
    _, bloque = mundo
    for m in (0, 20, 40, 60):
        procesar_evento(sesion, "perez", "AP-AULA-3", hora(8, 0) + timedelta(minutes=m))
    reg = cerrar_bloque(sesion, bloque, MIERCOLES)
    assert reg.estado == Estado.SALIDA_ANTICIPADA
    assert reg.minutos == 60
    assert reg.salida == hora(9, 0)


def test_cerrar_dos_veces_no_duplica(sesion, mundo):
    _, bloque = mundo
    cerrar_bloque(sesion, bloque, MIERCOLES)
    cerrar_bloque(sesion, bloque, MIERCOLES)
    assert len(_registros(sesion)) == 1


def test_cerrar_dia_cubre_todos_los_bloques(sesion, mundo):
    perez, _ = mundo
    zona = sesion.scalar(select(Zona).where(Zona.nombre == "Aula 3"))
    sesion.add(Bloque(
        usuario_id=perez.id, zona_id=zona.id, dia_semana=2,
        hora_inicio=time(12, 0), hora_fin=time(14, 0),
    ))
    sesion.commit()
    registros = cerrar_dia(sesion, MIERCOLES)
    assert len(registros) == 2
    assert all(r.estado == Estado.FALTA for r in registros)


def test_fuente_se_guarda(sesion, mundo):
    r = procesar_evento(sesion, "perez", "AP-AULA-3", hora(8, 0), fuente=Fuente.SIMULADOR)
    assert r.registro.fuente == Fuente.SIMULADOR
