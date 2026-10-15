"""Datos de demostracion: zonas, antenas, docentes y horarios.

Los bloques se crean para los 7 dias de la semana, asi la demo funciona
cualquier dia en que se abra la app.
"""

from __future__ import annotations

from datetime import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from motor.db import Antena, Bloque, Modalidad, Rol, Usuario, Zona, registrar_bitacora

ZONAS = [
    "Aula 1", "Aula 2", "Aula 3", "Aula 4",
    "Laboratorio de cómputo", "Laboratorio de redes",
]

# (cuenta, nombre, zona, [(inicio, fin), ...])
DOCENTES = [
    ("mperez", "Mtra. Laura Pérez", "Aula 1", [(time(8, 0), time(10, 0)), (time(10, 30), time(12, 30))]),
    ("jramirez", "Ing. Jorge Ramírez", "Aula 2", [(time(8, 0), time(10, 0)), (time(12, 0), time(14, 0))]),
    ("ahernandez", "Lic. Ana Hernández", "Aula 3", [(time(9, 0), time(11, 0)), (time(11, 30), time(13, 30))]),
    ("cgomez", "Dr. Carlos Gómez", "Laboratorio de cómputo", [(time(8, 0), time(10, 0)), (time(10, 0), time(12, 0))]),
    ("sdiaz", "Mtra. Sofía Díaz", "Aula 4", [(time(10, 0), time(12, 0)), (time(12, 30), time(14, 30))]),
    ("rtorres", "Ing. Rafael Torres", "Laboratorio de redes", [(time(8, 30), time(10, 30)), (time(11, 0), time(13, 0))]),
    ("vcastillo", "Lic. Valeria Castillo", "Aula 1", [(time(13, 0), time(15, 0)), (time(15, 0), time(17, 0))]),
    ("emedina", "Mtro. Eduardo Medina", "Aula 3", [(time(14, 0), time(16, 0)), (time(16, 30), time(18, 30))]),
]


def sembrar_demo(sesion: Session) -> bool:
    """Crea los datos de demo si la base esta vacia. Devuelve True si los creo."""
    if sesion.scalar(select(Usuario.id).limit(1)) is not None:
        return False

    zonas: dict[str, Zona] = {}
    for nombre in ZONAS:
        z = Zona(nombre=nombre)
        sesion.add(z)
        zonas[nombre] = z
    sesion.flush()

    for i, nombre in enumerate(ZONAS, start=1):
        sesion.add(Antena(identificador=f"AP-{i:02d}", zona_id=zonas[nombre].id))

    for cuenta, nombre, zona, horarios in DOCENTES:
        u = Usuario(cuenta=cuenta, nombre=nombre, rol=Rol.DOCENTE)
        sesion.add(u)
        sesion.flush()
        for dia in range(7):
            for inicio, fin in horarios:
                sesion.add(Bloque(
                    usuario_id=u.id, zona_id=zonas[zona].id, dia_semana=dia,
                    hora_inicio=inicio, hora_fin=fin, modalidad=Modalidad.PRESENCIAL,
                ))

    registrar_bitacora(sesion, "sistema", "demo_creada", "Datos de demostración")
    sesion.commit()
    return True
