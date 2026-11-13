"""API de recomendación de medios de pago — Prompt Solution Client (Grupo 6).

Capa 1: pipeline exportado por el cuaderno (preprocesamiento + XGBoost) -> propensiones.
Capa 2: función de utilidad del cuaderno + reglas de factibilidad -> recomendación.

Ejecutar desde la carpeta api/:
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
import hashlib
import json
import logging
import time
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

import joblib
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import capa2, features
from .schemas import RecomendacionRequest, RecomendacionResponse

BASE = Path(__file__).resolve().parents[1]
MODELO = BASE / "model" / "model_payment_final.pkl"
ETIQUETAS = BASE / "model" / "label_encoder.pkl"
CATALOGO = BASE / "data" / "catalog.json"

logger = logging.getLogger("recomendacion")
if not logger.handlers:
    # Uvicorn solo configura sus propios loggers; sin esto la traza no se imprime.
    _salida = logging.StreamHandler()
    _salida.setFormatter(logging.Formatter("TRAZA:    %(message)s"))
    logger.addHandler(_salida)
    logger.setLevel(logging.INFO)
    logger.propagate = False


@lru_cache(maxsize=1)
def artefactos():
    """Carga el pipeline, las etiquetas y el catálogo una sola vez."""
    pipeline = joblib.load(MODELO)
    clases = [str(c) for c in joblib.load(ETIQUETAS).classes_]
    catalogo = json.loads(CATALOGO.read_text(encoding="utf-8"))
    huella = hashlib.sha256(MODELO.read_bytes()).hexdigest()[:8]
    return {
        "pipeline": pipeline,
        "clases": clases,
        "columnas": list(pipeline.feature_names_in_),
        "catalogo": catalogo,
        "version": f"xgb-v10-{huella}",
    }


@asynccontextmanager
async def lifespan(_app):
    artefactos()  # falla al arrancar, y no en la primera compra, si falta un archivo
    yield


app = FastAPI(
    title="Prompt Solution Client — API de recomendación",
    description="MVP académico con datos sintéticos. La IA sugiere; el comprador decide.",
    version="0.1.0",
    lifespan=lifespan,
)
# La app Flutter en web se sirve desde otro origen; no se usan cookies ni credenciales.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])


@app.exception_handler(RequestValidationError)
async def entrada_invalida(_request, exc):
    # La respuesta por defecto repite el valor recibido y falla al serializar un NaN;
    # aquí solo se informa qué campo está mal y por qué.
    detalle = [{"campo": ".".join(str(p) for p in e["loc"][1:]), "error": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": detalle})


@app.get("/")
def raiz():
    return {"servicio": app.title, "documentacion": "/docs", "estado": "/health"}


@app.get("/health")
def health():
    return {"status": "ok", "modelo_version": artefactos()["version"]}


@app.get("/v1/meta")
def meta():
    """Qué perfiles y categorías conoce la API y con qué parámetros decide."""
    a = artefactos()
    cat = a["catalogo"]
    return {
        "modelo_version": a["version"],
        "medios": a["clases"],
        "fuente_datos": cat["fuente"],
        "perfiles": {
            uid: {"nombre": p["nombre"], "saldo_cop": p["saldo_cop"], "uso_cupo": p["user_credit_limit_utilization"]}
            for uid, p in cat["perfiles"].items()
        },
        "categorias": {
            clave: {"mcc_category": c["mcc_category"], "campania_pct": c["campania_pct"]}
            for clave, c in cat["categorias"].items()
        },
        "capa2": {
            "w_propension": capa2.W1,
            "w_beneficio": capa2.W2,
            "ref_incentivo_cop": capa2.REF_INCENTIVO_COP,
            "incentivo_aplica_a": capa2.MEDIO_INCENTIVO,
            "tope_incentivo_cop": cat["tope_incentivo_cop"],
            "uso_cupo_max": capa2.USO_CUPO_MAX,
        },
    }


@app.post("/v1/recomendacion", response_model=RecomendacionResponse)
def recomendacion(req: RecomendacionRequest):
    inicio = time.perf_counter()
    a = artefactos()
    cat = a["catalogo"]

    perfil = cat["perfiles"].get(req.user_id)
    if perfil is None:
        raise HTTPException(status_code=404, detail=f"Perfil '{req.user_id}' no encontrado. Ver /v1/meta.")

    categoria = cat["categorias"].get(req.categoria.strip().lower())
    if categoria is None:
        # Fuera del dominio de entrenamiento: mejor no opinar que extrapolar.
        return RecomendacionResponse(
            disponible=False,
            motivo=f"El modelo no fue entrenado con comercios de la categoría '{req.categoria}'.",
            perfil=req.user_id,
            modelo_version=a["version"],
            latencia_ms=round((time.perf_counter() - inicio) * 1000, 2),
        )

    if req.incentivo_cop is None:
        incentivo_pct = categoria["campania_pct"]
        incentivo = features.incentivo_campania(req.monto, incentivo_pct, cat["tope_incentivo_cop"])
    else:
        incentivo = float(req.incentivo_cop)
        incentivo_pct = round(min(incentivo / req.monto, 0.20), 2)

    momento = features.ahora_bogota()
    fila = features.construir_fila(
        perfil, categoria, req.monto, req.canal, incentivo, incentivo_pct, momento, a["columnas"]
    )
    probas = a["pipeline"].predict_proba(fila)[0]
    propensiones = {medio: float(p) for medio, p in zip(a["clases"], probas)}

    excluidos = capa2.medios_excluidos(perfil["saldo_cop"], req.monto, perfil["user_credit_limit_utilization"])
    decision = capa2.recomendar(propensiones, incentivo, excluidos)

    respuesta = RecomendacionResponse(
        disponible=True,
        recomendacion=decision["recomendacion"],
        habito=decision["habito"],
        sugerencia_activa=decision["sugerencia_activa"],
        propensiones={m: round(p, 4) for m, p in propensiones.items()},
        utilidades={m: round(u, 4) for m, u in decision["utilidades"].items()},
        factibles=decision["factibles"],
        excluidos=decision["excluidos"],
        beneficio_cop=decision["beneficio_cop"],
        motivo=capa2.motivo(decision, propensiones, incentivo),
        perfil=req.user_id,
        contexto={
            "merchant_id": req.merchant_id,
            "mcc_category": categoria["mcc_category"],
            "monto": req.monto,
            "canal": req.canal,
            "incentivo_cop": incentivo,
            "incentivo_aplica_a": capa2.MEDIO_INCENTIVO if incentivo > 0 else None,
            "saldo_cop": perfil["saldo_cop"],
            "hora": momento.hour,
            "dia_semana": momento.weekday(),
            "dia_quincena": momento.day in features.DIAS_QUINCENA,
        },
        modelo_version=a["version"],
        latencia_ms=round((time.perf_counter() - inicio) * 1000, 2),
    )
    # Trazabilidad: una línea por recomendación con lo que entró y lo que se decidió.
    logger.info(respuesta.model_dump_json())
    return respuesta
