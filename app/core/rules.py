from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.core.db import RegistroAsistencia, BloqueHorario, AntenaAP, EstadoAsistencia, BitacoraAuditoria

VENTANA_TOLERANCIA_MINUTOS = 15
VENTANA_ANTI_DUPLICADOS_MINUTOS = 5

def procesar_evento_wifi(db: Session, usuario_id: int, mac_ap: str, timestamp: datetime):
    antena = db.query(AntenaAP).filter(AntenaAP.mac_ap == mac_ap).first()
    if not antena:
        return {"status": "ignorado", "reason": "Antena AP no registrada en el sistema"}

    dia_semana = timestamp.weekday()
    hora_actual = timestamp.time()
    bloque = db.query(BloqueHorario).filter(
        BloqueHorario.usuario_id == usuario_id,
        BloqueHorario.zona_id == antena.zona_id,
        BloqueHorario.dia_semana == dia_semana,
        BloqueHorario.hora_inicio <= hora_actual,
        BloqueHorario.hora_fin >= hora_actual
    ).first()

    if not bloque:
        return {"status": "ignorado", "reason": "No hay bloque de horario activo en esta zona"}

    fecha_hoy = timestamp.date()

    registro_existente = db.query(RegistroAsistencia).filter(
        RegistroAsistencia.usuario_id == usuario_id,
        RegistroAsistencia.fecha == fecha_hoy
    ).first()

    if registro_existente:
        if registro_existente.hora_llegada and (timestamp - registro_existente.hora_llegada) < timedelta(minutes=VENTANA_ANTI_DUPLICADOS_MINUTOS):
            return {"status": "duplicado", "reason": "Evento dentro de la ventana anti-duplicados"}
        
        registro_existente.hora_salida = timestamp
        if registro_existente.hora_llegada:
            registro_existente.minutos_permanencia = int((timestamp - registro_existente.hora_llegada).total_seconds() / 60)
        db.commit()
        return {"status": "actualizado", "estado": registro_existente.estado}

    hora_inicio_dt = datetime.combine(fecha_hoy, bloque.hora_inicio)
    limite_tolerancia = hora_inicio_dt + timedelta(minutes=VENTANA_TOLERANCIA_MINUTOS)

    if timestamp <= limite_tolerancia:
        estado = EstadoAsistencia.PRESENTE
    else:
        estado = EstadoAsistencia.RETARDO

    nuevo_registro = RegistroAsistencia(
        usuario_id=usuario_id,
        zona_id=antena.zona_id,
        fecha=fecha_hoy,
        hora_llegada=timestamp,
        estado=estado
    )
    db.add(nuevo_registro)
    bitacora = BitacoraAuditoria(
        usuario_id=usuario_id,
        accion="REGISTRO_WIFI_AUTOMATICO",
        detalle=f"Asistencia marcada como {estado.value} en la zona {antena.zona.nombre} vía AP {antena.nombre_ap}"
    )
    db.add(bitacora)
    db.commit()

    return {"status": "registrado", "estado": estado.value}