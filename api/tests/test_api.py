"""Pruebas de la API de recomendación.

Ejecutar desde la raíz del repositorio:
    python -m pytest api
"""
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import capa2, features
from app.main import app, artefactos, predecir

RAIZ = Path(__file__).resolve().parents[2]
CSV = RAIZ / "dataset_medios_pago_sintetico.csv"
EXCEL = RAIZ / "Validacion_Masiva_1000_Casos_Capa_Recomendacion.xlsx"

PERFILES = ["USR-1385", "USR-1483", "USR-1372"]  # compradores con los tres medios
SIN_CREDITO = "USR-1167"  # comprador de demo sin tarjeta de crédito
TODOS = list(capa2.MEDIOS)
CATEGORIAS = ["restaurant", "grocery", "fuel", "clothing", "pharmacy"]
MONTOS = {"restaurant": 48000, "grocery": 128000, "fuel": 86000, "clothing": 215000, "pharmacy": 33500}


@pytest.fixture(scope="module")
def cliente():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def hora_fija(monkeypatch):
    """Miércoles 4 de noviembre de 2026, 13:00 en Bogotá (no es día de quincena)."""
    monkeypatch.setattr(features, "ahora_bogota", lambda: datetime(2026, 11, 4, 13, 0, tzinfo=features.BOGOTA))


def pedir(cliente, /, **campos):
    # `cliente` es solo posicional: la petición también tiene un campo con ese nombre.
    cuerpo = {"user_id": "USR-1385", "categoria": "restaurant", "monto": 48000}
    cuerpo.update(campos)
    return cliente.post("/v1/recomendacion", json=cuerpo)


# ---------------------------------------------------------------- servicio
def test_health_y_meta(cliente):
    assert cliente.get("/health").json()["status"] == "ok"
    meta = cliente.get("/v1/meta").json()
    assert set(meta["perfiles"]) == {*PERFILES, SIN_CREDITO}
    assert all(meta["perfiles"][p]["medios"] == TODOS for p in PERFILES)
    assert meta["perfiles"][SIN_CREDITO]["medios"] == [capa2.DEBITO, capa2.TRANSFERENCIA]
    assert set(meta["categorias"]) == set(CATEGORIAS)
    assert meta["medios"] == TODOS


# ---------------------------------------------------------------- propiedades de toda respuesta
@pytest.mark.parametrize("perfil", PERFILES)
@pytest.mark.parametrize("categoria", CATEGORIAS)
def test_respuesta_coherente(cliente, perfil, categoria):
    r = pedir(cliente, user_id=perfil, categoria=categoria, monto=MONTOS[categoria])
    assert r.status_code == 200
    d = r.json()
    assert d["disponible"] is True
    assert set(d["propensiones"]) == set(capa2.MEDIOS)
    assert sum(d["propensiones"].values()) == pytest.approx(1.0, abs=1e-3)
    assert d["habito"] == max(d["propensiones"], key=d["propensiones"].get)
    assert set(d["factibles"]) | set(d["excluidos"]) == set(capa2.MEDIOS)
    if d["factibles"]:
        assert d["recomendacion"] in d["factibles"]
        assert d["recomendacion"] == max(d["factibles"], key=d["utilidades"].get)
    assert d["sugerencia_activa"] == (d["recomendacion"] != d["habito"])
    assert d["motivo"]


# ---------------------------------------------------------------- casos de la demo con el modelo actual
def test_incentivo_bajo_no_cambia_el_habito(cliente):
    d = pedir(cliente, user_id="USR-1385", categoria="restaurant", monto=48000).json()
    assert d["contexto"]["incentivo_cop"] == 4800
    assert d["habito"] == capa2.DEBITO
    assert d["recomendacion"] == capa2.DEBITO
    assert d["sugerencia_activa"] is False
    assert d["beneficio_cop"] == 0


def test_incentivo_cambia_la_recomendacion(cliente):
    # Con $48.000 este mismo perfil queda reñido y el resultado depende de la hora; con $145.200 no.
    d = pedir(cliente, user_id="USR-1483", categoria="restaurant", monto=145200).json()
    assert d["contexto"]["incentivo_cop"] == 14500
    assert d["habito"] == capa2.CREDITO
    assert d["recomendacion"] == capa2.TRANSFERENCIA
    assert d["sugerencia_activa"] is True
    assert d["beneficio_cop"] == 14500


def test_saldo_insuficiente_nunca_recomienda_debito_ni_transferencia(cliente):
    # USR-1483 tiene $150.000 de saldo; la compra es de $215.000 con incentivo de $25.000.
    d = pedir(cliente, user_id="USR-1483", categoria="clothing", monto=215000).json()
    assert d["contexto"]["incentivo_cop"] == 25000
    assert d["factibles"] == [capa2.CREDITO]
    assert d["excluidos"] == {capa2.DEBITO: "saldo_insuficiente", capa2.TRANSFERENCIA: "saldo_insuficiente"}
    assert d["recomendacion"] == capa2.CREDITO
    assert d["beneficio_cop"] == 0


def test_categoria_fuera_del_dominio(cliente):
    d = pedir(cliente, categoria="travel", monto=980000).json()
    assert d["disponible"] is False
    assert d["recomendacion"] is None
    assert "travel" in d["motivo"]


# ---------------------------------------------------------------- validación de entradas
@pytest.mark.parametrize(
    "campos",
    [
        {"monto": 0},
        {"monto": -5000},
        {"monto": 20_000_001},
        {"monto": None},
        {"monto": "abc"},
        {"canal": "EFECTIVO"},
        {"incentivo_cop": -1},
        {"incentivo_cop": 30000},
        {"categoria": ""},
    ],
)
def test_entradas_invalidas(cliente, campos):
    assert pedir(cliente, **campos).status_code == 422


def test_monto_nan_se_rechaza(cliente):
    cuerpo = '{"user_id": "USR-1385", "categoria": "restaurant", "monto": NaN}'
    r = cliente.post("/v1/recomendacion", content=cuerpo, headers={"content-type": "application/json"})
    assert r.status_code == 422


def test_perfil_desconocido(cliente):
    assert pedir(cliente, user_id="USR-0000").status_code == 404


# ---------------------------------------------------------------- datos del comprador enviados por la app
def datos(saldo_cop, uso_cupo, medios=TODOS):
    return {"saldo_cop": saldo_cop, "uso_cupo": uso_cupo, "medios": medios}


@pytest.mark.parametrize("perfil", PERFILES)
@pytest.mark.parametrize("categoria", CATEGORIAS)
def test_enviar_los_datos_del_catalogo_no_cambia_la_respuesta(cliente, perfil, categoria):
    """Con el mismo saldo, cupo y medios el modelo recibe lo mismo y decide lo mismo."""
    guardado = artefactos()["catalogo"]["perfiles"][perfil]
    compra = {"user_id": perfil, "categoria": categoria, "monto": MONTOS[categoria]}
    sin_bloque = pedir(cliente, **compra).json()
    con_bloque = pedir(
        cliente, **compra, cliente=datos(guardado["saldo_cop"], guardado["user_credit_limit_utilization"])
    ).json()
    assert sin_bloque["contexto"].pop("fuente_perfil") == "catalogo"
    assert con_bloque["contexto"].pop("fuente_perfil") == "peticion"
    for respuesta in (sin_bloque, con_bloque):
        respuesta.pop("latencia_ms")
    assert con_bloque == sin_bloque


def test_el_saldo_enviado_manda_sobre_el_catalogo(cliente):
    # En el catálogo USR-1385 tiene $900.000; la app informa $20.000 para una compra de $48.000.
    d = pedir(cliente, cliente=datos(20000, 0.5)).json()
    assert d["contexto"]["saldo_cop"] == 20000
    assert d["excluidos"] == {capa2.DEBITO: "saldo_insuficiente", capa2.TRANSFERENCIA: "saldo_insuficiente"}
    assert d["recomendacion"] == capa2.CREDITO


def test_el_uso_de_cupo_enviado_manda_sobre_el_catalogo(cliente):
    # En el catálogo USR-1483 usa el 15 % del cupo; la app informa el cupo copado.
    d = pedir(cliente, user_id="USR-1483", categoria="fuel", monto=86000, cliente=datos(150000, 1.0)).json()
    assert d["contexto"]["uso_cupo"] == 1.0
    assert d["excluidos"] == {capa2.CREDITO: "cupo_agotado"}
    assert d["recomendacion"] in (capa2.DEBITO, capa2.TRANSFERENCIA)


def test_un_medio_que_el_comprador_no_tiene_no_se_sugiere(cliente):
    sin_credito = [capa2.DEBITO, capa2.TRANSFERENCIA]
    d = pedir(
        cliente, user_id="USR-1483", categoria="grocery", monto=128000, cliente=datos(150000, 1.0, sin_credito)
    ).json()
    assert d["excluidos"] == {capa2.CREDITO: "sin_producto"}  # no «cupo_agotado»: no tiene tarjeta
    assert d["factibles"] == sin_credito
    assert d["recomendacion"] in sin_credito
    assert d["habito"] in sin_credito
    assert "crédito" not in d["motivo"]
    assert d["contexto"]["medios"] == sin_credito


def test_sin_credito_y_sin_saldo_no_hay_sugerencia(cliente):
    d = pedir(cliente, cliente=datos(1000, 1.0, [capa2.DEBITO, capa2.TRANSFERENCIA])).json()
    assert d["recomendacion"] is None
    assert d["factibles"] == []
    assert d["excluidos"] == {
        capa2.CREDITO: "sin_producto",
        capa2.DEBITO: "saldo_insuficiente",
        capa2.TRANSFERENCIA: "saldo_insuficiente",
    }


def test_perfil_de_demo_sin_tarjeta_de_credito(cliente):
    """Sin el bloque `cliente`, el catálogo ya sabe que este comprador no tiene crédito."""
    d = pedir(cliente, user_id=SIN_CREDITO, categoria="grocery", monto=128000).json()
    assert d["excluidos"] == {capa2.CREDITO: "sin_producto"}
    assert d["recomendacion"] in (capa2.DEBITO, capa2.TRANSFERENCIA)
    assert d["contexto"]["fuente_perfil"] == "catalogo"


@pytest.mark.parametrize(
    "bloque",
    [
        {"saldo_cop": -1, "uso_cupo": 0.5, "medios": TODOS},
        {"saldo_cop": 2_000_000_000, "uso_cupo": 0.5, "medios": TODOS},
        {"saldo_cop": 1000, "uso_cupo": 1.5, "medios": TODOS},
        {"saldo_cop": 1000, "uso_cupo": -0.1, "medios": TODOS},
        {"saldo_cop": 1000, "uso_cupo": 0.5, "medios": []},
        {"saldo_cop": 1000, "uso_cupo": 0.5, "medios": ["EFECTIVO"]},
        {"saldo_cop": 1000, "uso_cupo": 0.5},
        {"saldo_cop": 1000, "medios": TODOS},
        {"uso_cupo": 0.5, "medios": TODOS},
        {"saldo_cop": "mucho", "uso_cupo": 0.5, "medios": TODOS},
    ],
)
def test_datos_del_comprador_invalidos(cliente, bloque):
    assert pedir(cliente, cliente=bloque).status_code == 422


def test_saldo_nan_se_rechaza(cliente):
    cuerpo = (
        '{"user_id": "USR-1385", "categoria": "restaurant", "monto": 48000, '
        '"cliente": {"saldo_cop": NaN, "uso_cupo": 0.5, "medios": ["DEBIT_CARD"]}}'
    )
    r = cliente.post("/v1/recomendacion", content=cuerpo, headers={"content-type": "application/json"})
    assert r.status_code == 422


# ---------------------------------------------------------------- Capa 2
def test_medio_que_no_tiene_prevalece_sobre_saldo_y_cupo():
    excluidos = capa2.medios_excluidos(saldo_cop=50000, monto=100000, uso_cupo=1.0, medios=[capa2.DEBITO])
    assert excluidos == {
        capa2.CREDITO: capa2.SIN_PRODUCTO,
        capa2.TRANSFERENCIA: capa2.SIN_PRODUCTO,
        capa2.DEBITO: capa2.SALDO_INSUFICIENTE,
    }


def test_habito_y_motivo_solo_entre_los_medios_que_tiene():
    # El modelo ve crédito como lo más probable, pero este comprador no tiene tarjeta.
    probas = {capa2.CREDITO: 0.6, capa2.DEBITO: 0.3, capa2.TRANSFERENCIA: 0.1}
    excluidos = capa2.medios_excluidos(500000, 100000, 1.0, medios=[capa2.DEBITO, capa2.TRANSFERENCIA])
    d = capa2.recomendar(probas, 0, excluidos)
    assert d["habito"] == capa2.DEBITO
    assert d["recomendacion"] == capa2.DEBITO
    assert d["sugerencia_activa"] is False
    assert d["cambio_por_factibilidad"] is False
    texto = capa2.motivo(d, probas, 0)
    assert "débito" in texto and "crédito" not in texto


def test_incentivo_en_un_medio_que_no_tiene():
    probas = {capa2.CREDITO: 0.6, capa2.DEBITO: 0.3, capa2.TRANSFERENCIA: 0.1}
    excluidos = capa2.medios_excluidos(500000, 100000, 0.2, medios=[capa2.CREDITO, capa2.DEBITO])
    d = capa2.recomendar(probas, 10000, excluidos)
    assert d["recomendacion"] == capa2.CREDITO
    assert d["beneficio_cop"] == 0
    assert "no tienes ese medio de pago" in capa2.motivo(d, probas, 10000)


def test_cupo_agotado_excluye_credito():
    excluidos = capa2.medios_excluidos(saldo_cop=300000, monto=100000, uso_cupo=0.90)
    assert excluidos == {capa2.CREDITO: capa2.CUPO_AGOTADO}
    probas = {capa2.CREDITO: 0.7, capa2.DEBITO: 0.2, capa2.TRANSFERENCIA: 0.1}
    d = capa2.recomendar(probas, 0, excluidos)
    assert d["recomendacion"] == capa2.DEBITO
    assert d["cambio_por_factibilidad"] is True


def test_sin_medios_factibles_no_hay_sugerencia():
    excluidos = capa2.medios_excluidos(saldo_cop=50000, monto=100000, uso_cupo=0.95)
    probas = {capa2.CREDITO: 0.4, capa2.DEBITO: 0.3, capa2.TRANSFERENCIA: 0.3}
    d = capa2.recomendar(probas, 10000, excluidos)
    assert d["recomendacion"] is None
    assert d["sugerencia_activa"] is False
    assert "fondos" in capa2.motivo(d, probas, 10000)


def test_ejemplo_del_documento_de_la_capa2():
    # Funcion_utilidad_Capa2.pdf: compra de $139.800 con $7.000 de incentivo en transferencia.
    probas = {capa2.CREDITO: 0.09, capa2.DEBITO: 0.56, capa2.TRANSFERENCIA: 0.34}
    d = capa2.recomendar(probas, 7000)
    assert d["utilidades"][capa2.DEBITO] == pytest.approx(0.2800)
    assert d["utilidades"][capa2.TRANSFERENCIA] == pytest.approx(0.4033, abs=1e-4)
    assert d["utilidades"][capa2.CREDITO] == pytest.approx(0.0450)
    assert d["recomendacion"] == capa2.TRANSFERENCIA


@pytest.mark.parametrize("perfil", PERFILES)
def test_contrafactual_del_incentivo(cliente, perfil):
    """Misma compra, incentivo creciente: una vez gana la transferencia, no se devuelve."""
    recomendaciones = []
    for incentivo in (0, 2000, 5000, 10000, 15000, 20000):
        d = pedir(cliente, user_id=perfil, categoria="restaurant", monto=100000, incentivo_cop=incentivo).json()
        assert d["contexto"]["incentivo_cop"] == incentivo
        recomendaciones.append(d["recomendacion"])
    primera = next((i for i, r in enumerate(recomendaciones) if r == capa2.TRANSFERENCIA), None)
    assert primera is not None, recomendaciones
    assert all(r == capa2.TRANSFERENCIA for r in recomendaciones[primera:]), recomendaciones


# ---------------------------------------------------------------- paridad con el cuaderno
@pytest.mark.skipif(not (CSV.exists() and EXCEL.exists()), reason="requiere el CSV y el Excel generados por el cuaderno")
def test_paridad_con_el_excel_del_cuaderno():
    """Sin reglas de factibilidad, la Capa 2 de la API da lo mismo que el cuaderno en los 1.000 casos."""
    import pandas as pd
    from sklearn.model_selection import train_test_split

    a = artefactos()
    df = pd.read_csv(CSV)
    y = df["target_chosen_payment_method"]
    _, x_test, _, _ = train_test_split(df[a["columnas"]], y, test_size=0.20, random_state=42, stratify=y)
    probas = predecir(a, x_test)
    esperado = pd.read_excel(EXCEL)

    habitos, recomendaciones = [], []
    for fila, incentivo in zip(probas, x_test["incentive_value_cop"]):
        d = capa2.recomendar(dict(zip(a["clases"], fila)), incentivo)
        habitos.append(d["habito"])
        recomendaciones.append(d["recomendacion"])

    assert len(recomendaciones) == 1000
    assert habitos == list(esperado["prediccion_ml_habito"])
    assert recomendaciones == list(esperado["recomendacion_utilidad"])
