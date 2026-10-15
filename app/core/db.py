from datetime import datetime, time, date
from enum import Enum
from typing import Optional, List
from sqlalchemy import create_engine, ForeignKey, String, Integer, DateTime, Time, Date, Boolean, Enum as SQLEnum, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

class Base(DeclarativeBase):
    pass

class RolUsuario(str, Enum):
    ADMIN = "administrador"
    RH = "rh_supervisor"
    DOCENTE = "docente_personal"
    AUDITOR = "auditor"

class EstadoAsistencia(str, Enum):
    PRESENTE = "presente"
    RETARDO = "retardo"
    FALTA = "falta"
    SALIDA_ANTICIPADA = "salida_anticipada"
    JUSTIFICADO = "justificado"
    EN_REVISION = "en_revision"

class EstadoSolicitud(str, Enum):
    PENDIENTE = "pendiente"
    APROBADO = "aprobado"
    RECHAZADO = "rechazado"

class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    num_empleado: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    nombre_completo: Mapped[str] = mapped_column(String(150), nullable=False)
    correo: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    rol: Mapped[RolUsuario] = mapped_column(SQLEnum(RolUsuario), default=RolUsuario.DOCENTE, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    bloques_horario: Mapped[List["BloqueHorario"]] = relationship(back_populates="usuario")
    asistencias: Mapped[List["RegistroAsistencia"]] = relationship(back_populates="usuario")
class Zona(Base):
    __tablename__ = "zonas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False) # ej. "Aula 102", "Oficina RH"
    edificio: Mapped[str] = mapped_column(String(100), nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(String(255))

    antenas: Mapped[List["AntenaAP"]] = relationship(back_populates="zona")

class AntenaAP(Base):
    __tablename__ = "antenas_ap"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mac_ap: Mapped[str] = mapped_column(String(17), unique=True, nullable=False) # Identificador BSSID del AP
    nombre_ap: Mapped[str] = mapped_column(String(100), nullable=False)
    zona_id: Mapped[int] = mapped_column(ForeignKey("zonas.id"), nullable=False)

    zona: Mapped["Zona"] = relationship(back_populates="antenas")

class BloqueHorario(Base):
    __tablename__ = "bloques_horario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    zona_id: Mapped[int] = mapped_column(ForeignKey("zonas.id"), nullable=False)
    dia_semana: Mapped[int] = mapped_column(Integer, nullable=False) # 0=Lunes, 6=Domingo
    hora_inicio: Mapped[time] = mapped_column(Time, nullable=False)
    hora_fin: Mapped[time] = mapped_column(Time, nullable=False)

    usuario: Mapped["Usuario"] = relationship(back_populates="bloques_horario")
    zona: Mapped["Zona"] = relationship()

class RegistroAsistencia(Base):
    __tablename__ = "registros_asistencia"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    zona_id: Mapped[int] = mapped_column(ForeignKey("zonas.id"), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    hora_llegada: Mapped[Optional[datetime]] = mapped_column(DateTime)
    hora_salida: Mapped[Optional[datetime]] = mapped_column(DateTime)
    estado: Mapped[EstadoAsistencia] = mapped_column(SQLEnum(EstadoAsistencia), nullable=False)
    minutos_permanencia: Mapped[int] = mapped_column(Integer, default=0)

    usuario: Mapped["Usuario"] = relationship(back_populates="asistencias")
    zona: Mapped["Zona"] = relationship()

class BitacoraAuditoria(Base):
    __tablename__ = "bitacora_auditoria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    usuario_id: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"))
    accion: Mapped[str] = mapped_column(String(100), nullable=False)
    detalle: Mapped[str] = mapped_column(Text, nullable=False)

DATABASE_URL = "sqlite:///asistencia.db"
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    init_db()
    print("Base de datos inicializada correctamente.")