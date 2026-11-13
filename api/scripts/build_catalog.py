"""Genera api/data/catalog.json a partir del dataset sintético v10.

El catálogo reemplaza, para la demo, lo que en producción vendría del banco:
  - perfiles: compradores reales del CSV (sus variables de perfil) + un saldo supuesto
  - categorías: valores típicos del comercio por categoría (medianas del CSV)
  - campañas: incentivo fijo por categoría, con el mismo tope del generador

Uso (desde la raíz del repositorio):
    python api/scripts/build_catalog.py
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / "dataset_medios_pago_sintetico.csv"
OUT = ROOT / "api" / "data" / "catalog.json"

# Clave que envía la app (categoría del QR) -> categoría del modelo y campaña de demo.
# El generador solo crea incentivos en restaurantes, supermercados y ropa, con
# porcentajes de 5, 10, 15 o 20 %; aquí se fija uno por categoría para que la demo sea estable.
CATEGORIAS = {
    "restaurant": {"mcc_category": "Restaurantes", "campania_pct": 0.10},
    "grocery": {"mcc_category": "Supermercados", "campania_pct": 0.05},
    "fuel": {"mcc_category": "Estaciones de Servicio", "campania_pct": 0.0},
    "clothing": {"mcc_category": "Tiendas de Ropa", "campania_pct": 0.15},
    "pharmacy": {"mcc_category": "Farmacias", "campania_pct": 0.0},
}

# Compradores del CSV usados como perfiles de demo. El saldo es un supuesto:
# el dataset solo trae la razón saldo/monto de cada transacción.
PERFILES = {
    "USR-1385": {"nombre": "Saldo holgado", "saldo_cop": 900000},
    "USR-1483": {"nombre": "Saldo ajustado", "saldo_cop": 150000},
    "USR-1372": {"nombre": "Busca cashback", "saldo_cop": 400000},
}

TOPE_INCENTIVO_COP = 25000  # mismo tope del generador


def main():
    df = pd.read_csv(CSV)

    categorias = {}
    for clave, cfg in CATEGORIAS.items():
        sub = df[df.mcc_category == cfg["mcc_category"]]
        categorias[clave] = {
            "mcc_category": cfg["mcc_category"],
            "mcc_code": int(sub.mcc_code.iloc[0]),
            "merchant_avg_ticket_size": float(sub.merchant_avg_ticket_size.median()),
            "merchant_tx_volume_30d": int(round(sub.merchant_tx_volume_30d.median())),
            "merchant_accepts_installment": bool(sub.merchant_accepts_installment.iloc[0]),
            "campania_pct": cfg["campania_pct"],
        }

    perfiles = {}
    for user_id, cfg in PERFILES.items():
        fila = df[df.user_id == user_id].iloc[0]
        perfiles[user_id] = {
            "nombre": cfg["nombre"],
            "user_avg_ticket_size": float(fila.user_avg_ticket_size),
            "user_cashback_responsiveness": float(fila.user_cashback_responsiveness),
            "user_credit_limit_utilization": float(fila.user_credit_limit_utilization),
            "saldo_cop": cfg["saldo_cop"],
        }

    catalogo = {
        "fuente": "dataset_medios_pago_sintetico.csv (v10, datos sintéticos)",
        "tope_incentivo_cop": TOPE_INCENTIVO_COP,
        "incentivo_aplica_a": "DIRECT_ACCOUNT_TRANSFER",
        "categorias": categorias,
        "perfiles": perfiles,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(catalogo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Catálogo escrito en {OUT}")


if __name__ == "__main__":
    main()
