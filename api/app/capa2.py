"""Capa 2: función de utilidad y reglas de factibilidad.

La utilidad es la del cuaderno DataPreparation (celda «FASE 5.3»):
    U(medio) = W1 · P(medio) + W2 · B(medio)
    B = incentivo_cop / REF_INCENTIVO_COP solo para el medio al que aplica el incentivo
Lo único que se agrega aquí es la factibilidad: un medio que el comprador no tiene o
con el que no puede pagar se elimina del conjunto de opciones antes de elegir el de
mayor utilidad.
"""

CREDITO = "CREDIT_CARD_BANK"
DEBITO = "DEBIT_CARD"
TRANSFERENCIA = "DIRECT_ACCOUNT_TRANSFER"
MEDIOS = (CREDITO, DEBITO, TRANSFERENCIA)
NOMBRE = {CREDITO: "crédito", DEBITO: "débito", TRANSFERENCIA: "transferencia"}

W1 = 0.50  # peso de la propensión (hábito)
W2 = 0.50  # peso del beneficio
REF_INCENTIVO_COP = 15000.0  # valor de referencia para normalizar el incentivo
MEDIO_INCENTIVO = TRANSFERENCIA  # el generador solo asocia el incentivo a la transferencia
USO_CUPO_MAX = 0.90  # desde este uso del cupo se considera que el crédito no está disponible

SIN_PRODUCTO = "sin_producto"
SALDO_INSUFICIENTE = "saldo_insuficiente"
CUPO_AGOTADO = "cupo_agotado"


def utilidades(propensiones, incentivo_cop):
    """Utilidad de cada medio según la fórmula del cuaderno."""
    resultado = {}
    for medio, p in propensiones.items():
        beneficio = incentivo_cop / REF_INCENTIVO_COP if (medio == MEDIO_INCENTIVO and incentivo_cop > 0) else 0.0
        resultado[medio] = W1 * p + W2 * beneficio
    return resultado


def medios_excluidos(saldo_cop, monto, uso_cupo, medios=MEDIOS):
    """Medios que el comprador no puede usar en esta compra, con el motivo.

    `medios` son los que el comprador tiene; por defecto, los tres.
    """
    excluidos = {m: SIN_PRODUCTO for m in MEDIOS if m not in medios}
    if saldo_cop < monto:
        excluidos.setdefault(DEBITO, SALDO_INSUFICIENTE)
        excluidos.setdefault(TRANSFERENCIA, SALDO_INSUFICIENTE)
    if uso_cupo >= USO_CUPO_MAX:
        excluidos.setdefault(CREDITO, CUPO_AGOTADO)
    return excluidos


def recomendar(propensiones, incentivo_cop, excluidos=None):
    """Aplica la Capa 2 y devuelve la decisión con todo lo necesario para explicarla.

    Con `excluidos` vacío reproduce exactamente la recomendación del cuaderno.
    """
    excluidos = excluidos or {}
    u = utilidades(propensiones, incentivo_cop)
    # El hábito y la comparación son entre los medios que el comprador tiene: no se
    # le dice «lo más probable es que pagues con crédito» a quien no tiene tarjeta.
    propios = [m for m in propensiones if excluidos.get(m) != SIN_PRODUCTO]
    habito = max(propios, key=propensiones.get) if propios else None
    factibles = [m for m in propensiones if m not in excluidos]
    recomendacion = max(factibles, key=u.get) if factibles else None
    sin_restricciones = max(propios, key=u.get) if propios else None
    return {
        "recomendacion": recomendacion,
        "habito": habito,
        "sugerencia_activa": recomendacion is not None and recomendacion != habito,
        "utilidades": u,
        "factibles": factibles,
        "excluidos": excluidos,
        "beneficio_cop": float(incentivo_cop) if (recomendacion == MEDIO_INCENTIVO and incentivo_cop > 0) else 0.0,
        "cambio_por_factibilidad": recomendacion != sin_restricciones,
    }


def _cop(valor):
    return "$" + f"{int(round(valor)):,}".replace(",", ".")


def _pct(p):
    return f"{round(p * 100)} %"


def motivo(decision, propensiones, incentivo_cop):
    """Explicación en una frase de por qué se recomienda ese medio."""
    rec, habito, excluidos = decision["recomendacion"], decision["habito"], decision["excluidos"]
    if rec is None:
        return "No encontramos un medio con fondos suficientes para esta compra."

    if decision["cambio_por_factibilidad"]:
        sin_saldo = [NOMBRE[m] for m in (DEBITO, TRANSFERENCIA) if excluidos.get(m) == SALDO_INSUFICIENTE]
        if sin_saldo:
            return f"Tu saldo no cubre esta compra con {' ni '.join(sin_saldo)}, por eso te sugerimos {NOMBRE[rec]}."
        return f"Tu cupo de crédito está casi lleno, por eso te sugerimos {NOMBRE[rec]}."

    if incentivo_cop > 0 and MEDIO_INCENTIVO in excluidos:
        impedimento = (
            "no tienes ese medio de pago"
            if excluidos[MEDIO_INCENTIVO] == SIN_PRODUCTO
            else "tu saldo no cubre esta compra"
        )
        return (
            f"Te sugerimos {NOMBRE[rec]}, tu medio más probable ({_pct(propensiones[rec])}). "
            f"Hay un incentivo de {_cop(incentivo_cop)} por {NOMBRE[MEDIO_INCENTIVO]}, pero {impedimento}."
        )

    hay_incentivo = incentivo_cop > 0
    if rec != habito:
        return (
            f"Lo más probable es que pagues con {NOMBRE[habito]} ({_pct(propensiones[habito])}), "
            f"pero con {NOMBRE[rec]} ahorras {_cop(incentivo_cop)} por el incentivo del comercio."
        )
    if rec == MEDIO_INCENTIVO and hay_incentivo:
        return (
            f"Te sugerimos {NOMBRE[rec]}: es tu medio más probable ({_pct(propensiones[rec])}) "
            f"y además ahorras {_cop(incentivo_cop)} por el incentivo del comercio."
        )
    if hay_incentivo:
        return (
            f"Te sugerimos {NOMBRE[rec]}, tu medio más probable ({_pct(propensiones[rec])}). "
            f"El incentivo de {_cop(incentivo_cop)} por {NOMBRE[MEDIO_INCENTIVO]} no compensa el cambio."
        )
    return (
        f"Te sugerimos {NOMBRE[rec]}: es tu medio más probable para esta compra "
        f"({_pct(propensiones[rec])}) y no hay incentivos activos."
    )
