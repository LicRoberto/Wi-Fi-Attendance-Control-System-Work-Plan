from datetime import datetime

import pytest

from motor.reglas import (
    Estado,
    Reglas,
    es_duplicado,
    evaluar_llegada,
    evaluar_salida,
    retardos_a_faltas,
)

INICIO = datetime(2026, 10, 14, 8, 0)
FIN = datetime(2026, 10, 14, 10, 0)


def hora(h: int, m: int) -> datetime:
    return datetime(2026, 10, 14, h, m)


# ---- Tabla de ejemplo del plan de trabajo (seccion 3.1) ----
@pytest.mark.parametrize(
    "llegada, esperado",
    [
        (hora(7, 58), Estado.PRESENTE),   # antes del inicio
        (hora(8, 7), Estado.PRESENTE),    # dentro de la tolerancia
        (hora(8, 15), Estado.RETARDO),    # paso la tolerancia, antes del limite
        (None, Estado.FALTA),             # sin evento
    ],
)
def test_tabla_del_plan(llegada, esperado):
    assert evaluar_llegada(INICIO, llegada).estado == esperado


# ---- Limites exactos (inclusivos) ----
@pytest.mark.parametrize(
    "llegada, esperado",
    [
        (hora(8, 0), Estado.PRESENTE),
        (hora(8, 10), Estado.PRESENTE),   # justo en la tolerancia
        (hora(8, 11), Estado.RETARDO),
        (hora(8, 30), Estado.RETARDO),    # justo en el limite
        (hora(8, 31), Estado.FALTA),
    ],
)
def test_limites_exactos(llegada, esperado):
    assert evaluar_llegada(INICIO, llegada).estado == esperado


def test_resultado_explica_el_motivo():
    r = evaluar_llegada(INICIO, hora(8, 15))
    assert r.minutos == 15
    assert "tolerancia" in r.motivo


def test_reglas_personalizadas():
    reglas = Reglas(tolerancia_min=5, limite_falta_min=15)
    assert evaluar_llegada(INICIO, hora(8, 7), reglas).estado == Estado.RETARDO
    assert evaluar_llegada(INICIO, hora(8, 16), reglas).estado == Estado.FALTA


# ---- Salida ----
def test_salida_normal():
    assert evaluar_salida(FIN, hora(10, 0)).estado == Estado.PRESENTE


def test_salida_dentro_de_tolerancia():
    assert evaluar_salida(FIN, hora(9, 52)).estado == Estado.PRESENTE


def test_salida_anticipada():
    r = evaluar_salida(FIN, hora(9, 30))
    assert r.estado == Estado.SALIDA_ANTICIPADA
    assert r.minutos == 30


def test_salida_despues_del_fin():
    assert evaluar_salida(FIN, hora(10, 5)).estado == Estado.PRESENTE


# ---- Antiduplicados (RF-05) ----
def test_primer_evento_no_es_duplicado():
    assert es_duplicado(None, hora(8, 0)) is False


def test_evento_dentro_de_la_ventana_es_duplicado():
    assert es_duplicado(hora(8, 0), hora(8, 10)) is True


def test_evento_fuera_de_la_ventana_no_es_duplicado():
    assert es_duplicado(hora(8, 0), hora(8, 15)) is False


# ---- Retardos acumulados ----
@pytest.mark.parametrize(
    "retardos, esperado",
    [(0, (0, 0)), (2, (0, 2)), (3, (1, 0)), (7, (2, 1))],
)
def test_retardos_a_faltas(retardos, esperado):
    assert retardos_a_faltas(retardos) == esperado


def test_retardos_negativos_fallan():
    with pytest.raises(ValueError):
        retardos_a_faltas(-1)


# ---- Validacion de reglas ----
def test_limite_debe_ser_mayor_que_tolerancia():
    with pytest.raises(ValueError):
        Reglas(tolerancia_min=20, limite_falta_min=10)


def test_retardos_por_falta_minimo_uno():
    with pytest.raises(ValueError):
        Reglas(retardos_por_falta=0)
