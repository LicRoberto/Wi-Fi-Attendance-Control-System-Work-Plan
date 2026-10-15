from datetime import time
from app.core.db import init_db, SessionLocal, Usuario, Zona, AntenaAP, BloqueHorario, RolUsuario

def cargar_datos_institucionales():
    init_db()
    db = SessionLocal()
    
    # 1. Crear Aulas / Zonas del TUP
    aula_101 = Zona(nombre="Aula 101 - Sistemas", edificio="Edificio A", descripcion="Planta baja, ala norte")
    aula_102 = Zona(nombre="Aula 102 - Redes", edificio="Edificio A", descripcion="Planta baja, ala sur")
    db.add_all([aula_101, aula_102])
    db.commit()

    # 2. Registrar las Antenas Wi-Fi (AP) reales colocadas en esas aulas
    ap_aula101 = AntenaAP(mac_ap="AA:BB:CC:11:22:33", nombre_ap="AP-Aula101-TUP", zona_id=aula_101.id)
    ap_aula102 = AntenaAP(mac_ap="AA:BB:CC:44:55:66", nombre_ap="AP-Aula102-TUP", zona_id=aula_102.id)
    db.add_all([ap_aula101, ap_aula102])
    db.commit()

    # 3. Registrar un Docente Real
    docente = Usuario(
        num_empleado="DOC-2026-01",
        nombre_completo="Prof. Roberto Gómez",
        correo="roberto.gomez@tup.edu.mx",
        password_hash="hash_seguro_123",
        rol=RolUsuario.DOCENTE
    )
    db.add(docente)
    db.commit()

    # 4. Asignarle Horario en el Aula 101 (Lunes a Viernes de 07:00 a 15:00)
    for dia in range(5):  # 0=Lunes, 4=Viernes
        bloque = BloqueHorario(
            usuario_id=docente.id,
            zona_id=aula_101.id,
            dia_semana=dia,
            hora_inicio=time(7, 0),
            hora_fin=time(15, 0)
        )
        db.add(bloque)
    
    db.commit()
    db.close()
    print("Datos de la red e institución TUP cargados exitosamente.")

if __name__ == "__main__":
    cargar_datos_institucionales()
