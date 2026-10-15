from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class Estado(str, Enum):
    PRESENTE = "presente"
    RETARDO = "retardo"
    FALTA = "falta"
    SALIDA_ANTICIPADA = "salida_anticipada"
    JUSTIFICADO = "justificado"  # lo asigna una resolucion de RH, no el calculo


@dataclass(frozen=True)
class Reglas:
    """Parametros configurables (los define RH o direccion)."""

    tolerancia_min: int = 10        # hasta aqui despues del inicio sigue siendo "presente"
    limite_falta_min: int = 30      # despues de aqui ya es "falta"
    tolerancia_salida_min: int = 10  # margen para salir antes del fin del bloque
    retardos_por_falta: int = 3     # cuantos retardos equivalen a una falta
    ventana_duplicados_min: int = 15  # RF-05: eventos repetidos dentro de esta ventana se ignoran

    def __post_init__(self) -> None:
        if self.tolerancia_min < 0:
            raise ValueError("tolerancia_min no puede ser negativa")
        if self.limite_falta_min <= self.tolerancia_min:
            raise ValueError("limite_falta_min debe ser mayor que tolerancia_min")
        if self.tolerancia_salida_min < 0:
            raise ValueError("tolerancia_salida_min no puede ser negativa")
        if self.retardos_por_falta < 1:
            raise ValueError("retardos_por_falta debe ser al menos 1")
        if self.ventana_duplicados_min < 0:
            raise ValueError("ventana_duplicados_min no puede ser negativa")


@dataclass(frozen=True)
class Resultado:
    """Estado calculado mas el 'por que' (para explicarselo al usuario)."""

    estado: Estado
    minutos: int  # minutos de diferencia respecto al inicio (llegada) o al fin (salida)
    motivo: str


def _min(delta: timedelta) -> int:
    return int(delta.total_seconds() // 60)


def evaluar_llegada(
    inicio_bloque: datetime,
    llegada: datetime | None,
    reglas: Reglas = Reglas(),
) -> Resultado:
    """Decide presente, retardo o falta segun la hora de llegada.

    llegada=None significa que no hubo ningun evento en la zona del usuario.
    """
    if llegada is None:
        return Resultado(Estado.FALTA, 0, "No apareció en su zona durante el bloque")

    tarde = _min(llegada - inicio_bloque)

    if tarde <= 0:
        return Resultado(Estado.PRESENTE, tarde, "Llegó antes del inicio del bloque")
    if tarde <= reglas.tolerancia_min:
        return Resultado(
            Estado.PRESENTE, tarde,
            f"Dentro de la tolerancia de {reglas.tolerancia_min} minutos",
        )
    if tarde <= reglas.limite_falta_min:
        return Resultado(
            Estado.RETARDO, tarde,
            f"Pasó la tolerancia de {reglas.tolerancia_min} minutos, "
            f"pero llegó antes del límite de {reglas.limite_falta_min}",
        )
    return Resultado(
        Estado.FALTA, tarde,
        f"Llegó después del límite de {reglas.limite_falta_min} minutos",
    )


def evaluar_salida(
    fin_bloque: datetime,
    salida: datetime,
    reglas: Reglas = Reglas(),
) -> Resultado:
    """Decide si salio antes de tiempo (mas alla de la tolerancia de salida)."""
    antes = _min(fin_bloque - salida)

    if antes <= reglas.tolerancia_salida_min:
        return Resultado(Estado.PRESENTE, antes, "Cumplió su bloque")
    return Resultado(
        Estado.SALIDA_ANTICIPADA, antes,
        f"Salió {antes} minutos antes del fin; la tolerancia es de "
        f"{reglas.tolerancia_salida_min}",
    )


def es_duplicado(
    ultimo_evento: datetime | None,
    nuevo_evento: datetime,
    reglas: Reglas = Reglas(),
) -> bool:
    """RF-05: True si el nuevo evento cae dentro de la ventana del anterior."""
    if ultimo_evento is None:
        return False
    return abs(nuevo_evento - ultimo_evento) < timedelta(minutes=reglas.ventana_duplicados_min)


def retardos_a_faltas(num_retardos: int, reglas: Reglas = Reglas()) -> tuple[int, int]:
    """Convierte retardos acumulados en faltas.

    Devuelve (faltas_equivalentes, retardos_restantes).
    Ejemplo con 3 retardos = 1 falta: 7 retardos -> (2, 1).
    """
    if num_retardos < 0:
        raise ValueError("num_retardos no puede ser negativo")
    return divmod(num_retardos, reglas.retardos_por_falta)

#Marca de AZAU