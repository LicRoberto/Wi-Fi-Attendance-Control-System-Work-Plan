"""Servicio de eventos: junta las reglas con la base de datos.

Sigue la logica del plan (seccion 3.1):
  1. Llega un evento: una cuenta aparece en una antena.
  2. Si la antena no es de la zona asignada a esa persona, se ignora.
  3. Si no hay un bloque de horario activo, se ignora.
  4. Si ya hay un registro en la ventana antiduplicados, no se crea otro.
  5. Se compara la hora con el inicio del bloque y se asigna el estado.
  6. Se guarda y se deja huella en la bitacora.

Supuesto sobre los eventos reales: mientras la persona sigue conectada, el
controlador Wi-Fi manda actualizaciones periodicas (cada 10 minutos o menos).
La ultima vez que se le vio ("salida") sirve para detectar salida anticipada
cuando se cierra el bloque.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from motor.db import (
    Antena, Bloque, Fuente, Modalidad, Registro, Usuario, registrar_bitacora,
)
from motor.reglas import (
    Estado, Reglas, es_duplicado, evaluar_llegada, evaluar_salida,
)

ANTICIPACION_MIN = 30  # cuanto antes del inicio se acepta que llegue


@dataclass(frozen=True)
class ResultadoEvento:
    registrado: bool          # True si el evento creo o confirmo presencia
    motivo: str               # por que se registro o se ignoro
    registro: Registro | None = None


def _inicio_fin(bloque: Bloque, fecha: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(fecha, bloque.hora_inicio),
        datetime.combine(fecha, bloque.hora_fin),
    )


def _bloque_activo(
    sesion: Session,
    usuario: Usuario,
    zona_id: int,
    momento: datetime,
    anticipacion_min: int,
) -> Bloque | None:
    candidatos = sesion.scalars(
        select(Bloque).where(
            Bloque.usuario_id == usuario.id,
            Bloque.zona_id == zona_id,
            Bloque.modalidad == Modalidad.PRESENCIAL,
            Bloque.dia_semana == momento.weekday(),
        )
    ).all()

    dentro, por_empezar = [], []
    for b in candidatos:
        inicio, fin = _inicio_fin(b, momento.date())
        if inicio <= momento <= fin:
            dentro.append((inicio, b))
        elif inicio - timedelta(minutes=anticipacion_min) <= momento < inicio:
            por_empezar.append((inicio, b))

    if dentro:
        return max(dentro, key=lambda x: x[0])[1]   # el que empezo mas recientemente
    if por_empezar:
        return min(por_empezar, key=lambda x: x[0])[1]  # el proximo a empezar
    return None


def _buscar_registro(sesion: Session, usuario_id: int, bloque_id: int, fecha: date):
    return sesion.scalar(
        select(Registro).where(
            Registro.usuario_id == usuario_id,
            Registro.bloque_id == bloque_id,
            Registro.fecha == fecha,
        )
    )


def procesar_evento(
    sesion: Session,
    cuenta: str,
    antena: str,
    momento: datetime,
    reglas: Reglas = Reglas(),
    fuente: Fuente = Fuente.WIFI,
    anticipacion_min: int = ANTICIPACION_MIN,
) -> ResultadoEvento:
    """Procesa un evento 'la cuenta X aparecio en la antena Y a esta hora'."""
    usuario = sesion.scalar(select(Usuario).where(Usuario.cuenta == cuenta))
    if usuario is None or not usuario.activo:
        return ResultadoEvento(False, "Cuenta desconocida o inactiva")

    ap = sesion.scalar(select(Antena).where(Antena.identificador == antena))
    if ap is None:
        return ResultadoEvento(False, "Antena desconocida")

    bloque = _bloque_activo(sesion, usuario, ap.zona_id, momento, anticipacion_min)
    if bloque is None:
        return ResultadoEvento(False, "Fuera de su zona u horario")

    fecha = momento.date()
    registro = _buscar_registro(sesion, usuario.id, bloque.id, fecha)

    if registro is None:
        inicio, _ = _inicio_fin(bloque, fecha)
        r = evaluar_llegada(inicio, momento, reglas)
        registro = Registro(
            usuario_id=usuario.id, bloque_id=bloque.id, fecha=fecha,
            llegada=momento, salida=momento, ultimo_evento=momento,
            estado=r.estado, minutos=r.minutos, motivo=r.motivo, fuente=fuente,
        )
        sesion.add(registro)
        registrar_bitacora(
            sesion, "sistema", "registro_creado",
            f"{cuenta} · {momento:%H:%M} · {r.estado.value}",
        )
        sesion.commit()
        return ResultadoEvento(True, r.motivo, registro)

    # Ya tiene registro: actualizamos la ultima vez que se le vio.
    registro.salida = max(registro.salida or momento, momento)

    if es_duplicado(registro.ultimo_evento, momento, reglas):
        sesion.commit()
        return ResultadoEvento(False, "Evento duplicado (ventana antiduplicados)", registro)

    registro.ultimo_evento = momento
    sesion.commit()
    return ResultadoEvento(True, "Presencia confirmada", registro)


def cerrar_bloque(
    sesion: Session,
    bloque: Bloque,
    fecha: date,
    reglas: Reglas = Reglas(),
    fuente: Fuente = Fuente.WIFI,
) -> Registro:
    """Cierra un bloque: crea la falta si nunca llego o detecta salida anticipada.

    Es seguro llamarlo mas de una vez: no repite correcciones.
    """
    inicio, fin = _inicio_fin(bloque, fecha)
    registro = _buscar_registro(sesion, bloque.usuario_id, bloque.id, fecha)

    if registro is None:
        r = evaluar_llegada(inicio, None, reglas)
        registro = Registro(
            usuario_id=bloque.usuario_id, bloque_id=bloque.id, fecha=fecha,
            estado=r.estado, minutos=r.minutos, motivo=r.motivo, fuente=fuente,
        )
        sesion.add(registro)
        registrar_bitacora(
            sesion, "sistema", "falta_registrada",
            f"{bloque.usuario.cuenta} · bloque {bloque.hora_inicio:%H:%M}",
        )
    elif registro.estado in (Estado.PRESENTE, Estado.RETARDO) and registro.salida:
        s = evaluar_salida(fin, registro.salida, reglas)
        if s.estado == Estado.SALIDA_ANTICIPADA:
            registro.estado = Estado.SALIDA_ANTICIPADA
            registro.minutos = s.minutos
            registro.motivo = f"{registro.motivo}. {s.motivo}"
            registrar_bitacora(
                sesion, "sistema", "salida_anticipada",
                f"{bloque.usuario.cuenta} · salió {registro.salida:%H:%M}",
            )

    sesion.commit()
    return registro


def cerrar_dia(
    sesion: Session,
    fecha: date,
    reglas: Reglas = Reglas(),
    fuente: Fuente = Fuente.WIFI,
) -> list[Registro]:
    """Cierra todos los bloques presenciales del dia (fin de jornada)."""
    bloques = sesion.scalars(
        select(Bloque)
        .join(Usuario, Bloque.usuario_id == Usuario.id)
        .where(
            Usuario.activo.is_(True),
            Bloque.modalidad == Modalidad.PRESENCIAL,
            Bloque.dia_semana == fecha.weekday(),
        )
        .order_by(Bloque.hora_inicio, Bloque.id)
    ).all()
    return [cerrar_bloque(sesion, b, fecha, reglas, fuente) for b in bloques]
