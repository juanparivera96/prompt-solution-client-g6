"""Construye la fila de entrada del modelo a partir de lo que envía la app.

La app solo conoce comprador, categoría del comercio, monto y canal. El resto de
variables se completa con el catálogo de demo (perfil del comprador y valores
típicos del comercio) y con la fecha y hora de Bogotá.
"""
from datetime import datetime, timedelta, timezone

import pandas as pd

BOGOTA = timezone(timedelta(hours=-5))  # Colombia no tiene horario de verano
DIAS_QUINCENA = (14, 15, 29, 30, 31)  # los mismos días que usa el generador
RATIO_MIN, RATIO_MAX = 0.5, 8.0  # rango de user_balance_account_ratio visto en entrenamiento


def ahora_bogota():
    return datetime.now(BOGOTA)


def incentivo_campania(monto, pct, tope_cop):
    """Valor del incentivo en COP, con la misma regla del generador."""
    return float(round(min(monto * pct, tope_cop), -2))


def construir_fila(perfil, categoria, monto, canal, incentivo_cop, incentivo_pct, momento, columnas):
    """Devuelve un DataFrame de una fila con las columnas en el orden que espera el preprocesador."""
    ratio = perfil["saldo_cop"] / monto
    fila = {
        "user_avg_ticket_size": perfil["user_avg_ticket_size"],
        "user_cashback_responsiveness": perfil["user_cashback_responsiveness"],
        "user_credit_limit_utilization": perfil["user_credit_limit_utilization"],
        # Se acota al rango de entrenamiento; la factibilidad usa el saldo real, no este valor.
        "user_balance_account_ratio": round(min(max(ratio, RATIO_MIN), RATIO_MAX), 2),
        "mcc_code": categoria["mcc_code"],
        "mcc_category": categoria["mcc_category"],
        "merchant_avg_ticket_size": categoria["merchant_avg_ticket_size"],
        "merchant_accepts_installment": categoria["merchant_accepts_installment"],
        "merchant_tx_volume_30d": categoria["merchant_tx_volume_30d"],
        "tx_amount": float(monto),
        "tx_hour": momento.hour,
        "tx_day_of_week": momento.weekday(),
        "tx_channel": canal,
        "is_payroll_day": momento.day in DIAS_QUINCENA,
        "incentive_active_flag": incentivo_cop > 0,
        "incentive_pct": incentivo_pct if incentivo_cop > 0 else 0.0,
        "incentive_value_cop": float(incentivo_cop),
    }
    return pd.DataFrame([fila])[list(columnas)]
