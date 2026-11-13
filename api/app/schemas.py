"""Contrato de la API (entrada y salida)."""
from typing import Literal, Optional

from pydantic import BaseModel, Field

MONTO_MAX_COP = 20_000_000  # rango de monto definido en el Ciclo 1
INCENTIVO_MAX_COP = 25_000  # tope del generador

Canal = Literal["QR_STATIC", "QR_DYNAMIC", "E_COMMERCE_GATEWAY", "POS_PHYSICAL"]


class RecomendacionRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=40, description="Perfil del comprador (ver /v1/meta).")
    categoria: str = Field(min_length=1, max_length=40, description="Categoría del comercio leída del QR.")
    monto: float = Field(gt=0, le=MONTO_MAX_COP, allow_inf_nan=False, description="Monto de la compra en COP.")
    canal: Canal = "QR_DYNAMIC"
    merchant_id: Optional[str] = Field(default=None, max_length=60, description="Solo para trazabilidad.")
    incentivo_cop: Optional[float] = Field(
        default=None,
        ge=0,
        le=INCENTIVO_MAX_COP,
        allow_inf_nan=False,
        description="Reemplaza el incentivo de la campaña. Solo para pruebas contrafactuales.",
    )


class RecomendacionResponse(BaseModel):
    disponible: bool = Field(description="False si el modelo no cubre esta compra; la app usa sus reglas.")
    recomendacion: Optional[str] = None
    habito: Optional[str] = Field(default=None, description="Medio más probable según la Capa 1.")
    sugerencia_activa: bool = False
    propensiones: dict[str, float] = {}
    utilidades: dict[str, float] = {}
    factibles: list[str] = []
    excluidos: dict[str, str] = {}
    beneficio_cop: float = 0.0
    motivo: str
    perfil: Optional[str] = None
    contexto: dict = {}
    modelo_version: str
    latencia_ms: float
