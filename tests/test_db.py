from datetime import date, datetime, time

import pytest
from sqlalchemy.exc import IntegrityError

from motor.db import (
    Antena, Bitacora, Bloque, Fuente, Modalidad, Registro, Rol, Usuario, Zona,
    crear_motor, crear_sesion, crear_tablas, registrar_bitacora,
)
from motor.reglas import Estado


@pytest.fixture
def sesion():
    engine = crear_motor("sqlite:///:memory:")
    crear_tablas(engine)
    with crear_sesion(engine)() as s:
        yield s


def _datos_base(s):
    zona = Zona(nombre="Aula 3")
    s.add(zona)
    s.flush()
    antena = Antena(identificador="AP-AULA-3", zona_id=zona.id)
    docente = Usuario(cuenta="perez", nombre="Prof. Pérez", rol=Rol.DOCENTE)
    s.add_all([antena, docente])
    s.flush()
    bloque = Bloque(
        usuario_id=docente.id, zona_id=zona.id, dia_semana=2,
        hora_inicio=time(8, 0), hora_fin=time(10, 0),
    )
    s.add(bloque)
    s.commit()
    return zona, antena, docente, bloque


def test_crea_y_relaciona_datos_base(sesion):
    zona, antena, docente, bloque = _datos_base(sesion)
    assert antena.zona.nombre == "Aula 3"
    assert bloque.usuario.cuenta == "perez"
    assert bloque.modalidad == Modalidad.PRESENCIAL
    assert docente.activo is True


def test_cuenta_unica(sesion):
    sesion.add(Usuario(cuenta="perez", nombre="A"))
    sesion.commit()
    sesion.add(Usuario(cuenta="perez", nombre="B"))
    with pytest.raises(IntegrityError):
        sesion.commit()


def test_guarda_registro_con_estado(sesion):
    _, _, docente, bloque = _datos_base(sesion)
    reg = Registro(
        usuario_id=docente.id, bloque_id=bloque.id, fecha=date(2026, 10, 14),
        llegada=datetime(2026, 10, 14, 8, 15), estado=Estado.RETARDO, minutos=15,
        motivo="Pasó la tolerancia", fuente=Fuente.SIMULADOR,
    )
    sesion.add(reg)
    sesion.commit()
    guardado = sesion.get(Registro, reg.id)
    assert guardado.estado == Estado.RETARDO
    assert guardado.fuente == Fuente.SIMULADOR


def test_un_registro_por_usuario_bloque_y_fecha(sesion):
    _, _, docente, bloque = _datos_base(sesion)
    datos = dict(
        usuario_id=docente.id, bloque_id=bloque.id, fecha=date(2026, 10, 14),
        estado=Estado.PRESENTE, fuente=Fuente.WIFI,
    )
    sesion.add(Registro(**datos))
    sesion.commit()
    sesion.add(Registro(**datos))
    with pytest.raises(IntegrityError):
        sesion.commit()


def test_llaves_foraneas_activas(sesion):
    sesion.add(Antena(identificador="AP-X", zona_id=999))
    with pytest.raises(IntegrityError):
        sesion.commit()


def test_bitacora_agrega_lineas(sesion):
    registrar_bitacora(sesion, "sistema", "registro_creado", "perez 8:07 presente")
    sesion.commit()
    assert sesion.query(Bitacora).count() == 1


def test_bitacora_no_se_edita(sesion):
    linea = registrar_bitacora(sesion, "sistema", "registro_creado")
    sesion.commit()
    linea.detalle = "alterado"
    with pytest.raises(PermissionError):
        sesion.commit()


def test_bitacora_no_se_borra(sesion):
    linea = registrar_bitacora(sesion, "sistema", "registro_creado")
    sesion.commit()
    sesion.delete(linea)
    with pytest.raises(PermissionError):
        sesion.commit()
