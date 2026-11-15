"""De dónde salen los datos del comprador.

Es el único punto que cambia si cambia la fuente: hoy son el catálogo de demo y lo
que envía la app; más adelante, una base de datos consultada con el usuario
autenticado. El modelo y la Capa 2 reciben siempre el mismo diccionario.
"""
from . import capa2

CATALOGO = "catalogo"
PETICION = "peticion"


def obtener_perfil(catalogo, user_id, cliente=None):
    """Devuelve el perfil con el que se decide, o None si el comprador no existe.

    Las variables de comportamiento (ticket medio, sensibilidad al cashback) salen
    siempre del catálogo. El saldo, el uso del cupo y los medios salen de `cliente`
    cuando la app los envía, porque es ella la que conoce los productos del comprador.
    """
    base = catalogo["perfiles"].get(user_id)
    if base is None:
        return None
    perfil = dict(base, medios=base.get("medios", list(capa2.MEDIOS)), fuente=CATALOGO)
    if cliente is not None:
        perfil.update(
            saldo_cop=cliente.saldo_cop,
            user_credit_limit_utilization=cliente.uso_cupo,
            medios=[m for m in capa2.MEDIOS if m in cliente.medios],
            fuente=PETICION,
        )
    return perfil
