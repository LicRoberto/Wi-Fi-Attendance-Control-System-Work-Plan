"""Simulador de eventos Wi-Fi.

Finge ser el servidor RADIUS / controlador Wi-Fi: manda eventos del tipo
"la cuenta X aparecio en la antena Y a las HH:MM" para probar el sistema y
para la demostracion, sin necesidad de antenas reales.

En produccion este modulo se reemplaza por la fuente real y el resto del
sistema no cambia.
"""

from __future__ import annotations

import random
from collections import Counter
from datetime import date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from motor.db import Antena, Bloque, Fuente, Modalidad, Registro, Usuario
from motor.reglas import Reglas
from motor.servicio import cerrar_dia, procesar_evento

ESCENARIOS = ("puntual", "retardo", "falta", "salida_anticipada")
PESOS = (55, 20, 10, 15)
INTERVALO_MIN = 10  # cada cuanto "reporta" el Wi-Fi que la persona sigue conectada


def _llegada_y_limite(bloque, fecha, escenario, reglas, rng):
    inicio = datetime.combine(fecha, bloque.hora_inicio)
    fin = datetime.combine(fecha, bloque.hora_fin)

    if escenario == "puntual":
        return inicio - timedelta(minutes=rng.randint(0, 5)), fin
    if escenario == "retardo":
        minutos = rng.randint(reglas.tolerancia_min + 2, reglas.limite_falta_min - 2)
        return inicio + timedelta(minutes=minutos), fin
    # salida anticipada: llega a tiempo y se va entre 25 y 50 minutos antes
    llegada = inicio + timedelta(minutes=rng.randint(0, 8))
    return llegada, fin - timedelta(minutes=rng.randint(25, 50))


def eventos_de_bloque(bloque, fecha, escenario, reglas, rng):
    """Lista de momentos en que el Wi-Fi 've' a la persona durante el bloque."""
    if escenario == "falta":
        return []
    llegada, limite = _llegada_y_limite(bloque, fecha, escenario, reglas, rng)
    momentos, t = [], llegada
    while t < limite:
        momentos.append(t)
        t += timedelta(minutes=INTERVALO_MIN)
    return momentos


def limpiar_dia(sesion: Session, fecha: date) -> None:
    """Borra los registros de asistencia de un dia (la bitacora no se toca)."""
    sesion.execute(delete(Registro).where(Registro.fecha == fecha))
    sesion.commit()


def simular_dia(
    sesion: Session,
    fecha: date,
    reglas: Reglas = Reglas(),
    semilla: int | None = None,
    escenarios: dict[str, str] | None = None,
) -> Counter:
    """Simula un dia completo de asistencia y lo cierra.

    escenarios: opcional, {cuenta: escenario} para forzar el de una persona.
    Devuelve cuantos bloques hubo de cada escenario.
    """
    rng = random.Random(semilla)
    escenarios = escenarios or {}

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

    eventos: list[tuple[datetime, str, str]] = []
    conteo: Counter = Counter()

    for b in bloques:
        antena = sesion.scalar(select(Antena).where(Antena.zona_id == b.zona_id))
        if antena is None:
            continue
        escenario = escenarios.get(b.usuario.cuenta) or rng.choices(ESCENARIOS, PESOS)[0]
        conteo[escenario] += 1
        for momento in eventos_de_bloque(b, fecha, escenario, reglas, rng):
            eventos.append((momento, b.usuario.cuenta, antena.identificador))

    for momento, cuenta, ap in sorted(eventos):
        procesar_evento(sesion, cuenta, ap, momento, reglas, fuente=Fuente.SIMULADOR)

    cerrar_dia(sesion, fecha, reglas, fuente=Fuente.SIMULADOR)
    return conteo
