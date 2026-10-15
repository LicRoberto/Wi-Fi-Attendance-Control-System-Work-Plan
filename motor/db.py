from __future__ import annotations

import enum
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text, Time,
    UniqueConstraint, create_engine, event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker,
)

from motor.reglas import Estado


class Rol(str, enum.Enum):
    ADMINISTRADOR = "administrador"
    RH = "rh"
    DOCENTE = "docente"  # docente o personal
    AUDITOR = "auditor"


class Modalidad(str, enum.Enum):
    PRESENCIAL = "presencial"  # se registra por Wi-Fi y zona
    VIRTUAL = "virtual"        # se registra desde la plataforma de la clase


class Fuente(str, enum.Enum):
    WIFI = "wifi"
    SIMULADOR = "simulador"
    VIRTUAL = "virtual"
    MANUAL = "manual"  # correccion aprobada por RH


class Base(DeclarativeBase):
    pass


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    cuenta: Mapped[str] = mapped_column(String(80), unique=True)  # cuenta personal de Wi-Fi
    nombre: Mapped[str] = mapped_column(String(120))
    rol: Mapped[Rol] = mapped_column(Enum(Rol, native_enum=False), default=Rol.DOCENTE)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    bloques: Mapped[list[Bloque]] = relationship(back_populates="usuario")


class Zona(Base):
    __tablename__ = "zonas"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), unique=True)  # "Aula 3", "Sala de maestros"

    antenas: Mapped[list[Antena]] = relationship(back_populates="zona")


class Antena(Base):
    """Punto de acceso (AP). Cada antena pertenece a una zona."""

    __tablename__ = "antenas"

    id: Mapped[int] = mapped_column(primary_key=True)
    identificador: Mapped[str] = mapped_column(String(80), unique=True)  # nombre o MAC del AP
    zona_id: Mapped[int] = mapped_column(ForeignKey("zonas.id"))

    zona: Mapped[Zona] = relationship(back_populates="antenas")


class Bloque(Base):
    """Un bloque de horario de un usuario (clase o turno), repetido cada semana."""

    __tablename__ = "bloques"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    zona_id: Mapped[int | None] = mapped_column(ForeignKey("zonas.id"))  # None si es virtual
    dia_semana: Mapped[int] = mapped_column(Integer)  # 0 = lunes ... 6 = domingo
    hora_inicio: Mapped[time] = mapped_column(Time)
    hora_fin: Mapped[time] = mapped_column(Time)
    modalidad: Mapped[Modalidad] = mapped_column(
        Enum(Modalidad, native_enum=False), default=Modalidad.PRESENCIAL
    )

    usuario: Mapped[Usuario] = relationship(back_populates="bloques")
    zona: Mapped[Zona | None] = relationship()


class Registro(Base):
    """Resultado de asistencia de un usuario en un bloque, en una fecha."""

    __tablename__ = "registros"
    __table_args__ = (UniqueConstraint("usuario_id", "bloque_id", "fecha"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    bloque_id: Mapped[int] = mapped_column(ForeignKey("bloques.id"))
    fecha: Mapped[date] = mapped_column(Date)
    llegada: Mapped[datetime | None] = mapped_column(DateTime)
    salida: Mapped[datetime | None] = mapped_column(DateTime)
    ultimo_evento: Mapped[datetime | None] = mapped_column(DateTime)  # para antiduplicados
    estado: Mapped[Estado] = mapped_column(Enum(Estado, native_enum=False))
    minutos: Mapped[int] = mapped_column(Integer, default=0)
    motivo: Mapped[str] = mapped_column(Text, default="")
    fuente: Mapped[Fuente] = mapped_column(Enum(Fuente, native_enum=False))


class Bitacora(Base):
    """Historial de acciones. Solo se agrega: nunca se edita ni se borra."""

    __tablename__ = "bitacora"

    id: Mapped[int] = mapped_column(primary_key=True)
    momento: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    actor: Mapped[str] = mapped_column(String(80))  # cuenta de quien hizo la accion, o "sistema"
    accion: Mapped[str] = mapped_column(String(80))
    detalle: Mapped[str] = mapped_column(Text, default="")


@event.listens_for(Bitacora, "before_update")
@event.listens_for(Bitacora, "before_delete")
def _bitacora_inmutable(mapper, connection, target):
    raise PermissionError("La bitácora es de solo-agregar: no se puede editar ni borrar")


def registrar_bitacora(sesion: Session, actor: str, accion: str, detalle: str = "") -> Bitacora:
    """Agrega una linea a la bitacora (no hace commit, lo hace quien llama)."""
    linea = Bitacora(actor=actor, accion=accion, detalle=detalle)
    sesion.add(linea)
    return linea


# ---------- Conexion ----------

def crear_motor(url: str = "sqlite:///asistencia.db") -> Engine:
    engine = create_engine(url)

    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


def crear_tablas(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def crear_sesion(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
