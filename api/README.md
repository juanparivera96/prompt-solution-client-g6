# API de recomendación — Prompt Solution Client

Servicio que expone el modelo de dos capas para la app Flutter. Es un MVP académico: todos los datos son sintéticos y no hay autenticación.

```
App Flutter ──► POST /v1/recomendacion ──► Capa 1 (model_payment_final.pkl) ──► Capa 2 (utilidad + factibilidad)
```

- **Capa 1:** el pipeline exportado por `DataPreparation_PromptSolutionClient.ipynb` estima la probabilidad de que el comprador use crédito, débito o transferencia.
- **Capa 2:** la función de utilidad del cuaderno (`0,5·P + 0,5·incentivo/15.000`). La API agrega una regla: un medio que el comprador no tiene o con el que no puede pagar se descarta antes de elegir.

La API no cambia el modelo: usa el mismo `.pkl`, las mismas 17 variables y la misma fórmula. Lo que decide es de dónde salen los datos del comprador (`app/perfiles.py`).

## Correr en local

Desde la raíz del repositorio:

```bash
pip install -r api/requirements-dev.txt
```

```bash
python -m uvicorn app.main:app --app-dir api --host 127.0.0.1 --port 8000
```

La documentación interactiva queda en `http://127.0.0.1:8000/docs`.

Para probar desde un celular físico en la misma red Wi-Fi, usar `--host 0.0.0.0` y la IP del computador.

## Probar

```bash
python -m pytest api
```

```bash
curl -X POST http://127.0.0.1:8000/v1/recomendacion -H "Content-Type: application/json" -d "{\"user_id\":\"USR-1483\",\"categoria\":\"restaurant\",\"monto\":145200}"
```

## Contrato

`POST /v1/recomendacion`

| Campo | Tipo | Descripción |
|---|---|---|
| `user_id` | texto | Perfil del comprador. Ver `GET /v1/meta`. |
| `categoria` | texto | `restaurant`, `grocery`, `fuel`, `clothing` o `pharmacy`. Otra categoría devuelve `disponible: false`. |
| `monto` | número | Monto en COP, mayor que 0 y hasta 20.000.000. |
| `canal` | texto | `QR_DYNAMIC` (por defecto), `QR_STATIC`, `POS_PHYSICAL` o `E_COMMERCE_GATEWAY`. |
| `merchant_id` | texto | Opcional, solo para trazabilidad. |
| `incentivo_cop` | número | Opcional. Reemplaza el incentivo de la campaña; sirve para pruebas contrafactuales. |
| `cliente` | objeto | Opcional. Datos financieros del comprador que conoce la app. Si falta, se usan los del catálogo. |

El bloque `cliente` lleva tres campos, todos obligatorios cuando se envía:

| Campo | Tipo | Descripción |
|---|---|---|
| `saldo_cop` | número | Saldo disponible en COP, de 0 a 1.000.000.000. |
| `uso_cupo` | número | Fracción del cupo de crédito en uso, de 0 a 1. Sin tarjeta de crédito se envía 1. |
| `medios` | lista | Medios que tiene el comprador: `CREDIT_CARD_BANK`, `DEBIT_CARD`, `DIRECT_ACCOUNT_TRANSFER`. Al menos uno. |

```bash
curl -X POST http://127.0.0.1:8000/v1/recomendacion -H "Content-Type: application/json" -d "{\"user_id\":\"USR-1167\",\"categoria\":\"grocery\",\"monto\":320000,\"cliente\":{\"saldo_cop\":600000,\"uso_cupo\":1,\"medios\":[\"DEBIT_CARD\",\"DIRECT_ACCOUNT_TRANSFER\"]}}"
```

Qué sale de dónde:

- **De `cliente`, o del catálogo si falta:** el saldo, el uso del cupo y los medios. El saldo y el uso del cupo son variables del modelo y también alimentan la factibilidad.
- **Siempre del catálogo, por `user_id`:** el ticket medio y la sensibilidad al cashback. Son variables de comportamiento que la app no conoce; en producción saldrían del historial del comprador.

Sin el bloque `cliente` la respuesta es la de siempre, así que una app que no lo envía sigue funcionando. Con el mismo saldo, cupo y medios del catálogo la respuesta es idéntica: lo comprueba `test_enviar_los_datos_del_catalogo_no_cambia_la_respuesta`.

La respuesta incluye `recomendacion`, `habito` (medio más probable entre los que tiene el comprador), `propensiones`, `utilidades`, `factibles`, `excluidos` (con el motivo: `sin_producto`, `saldo_insuficiente` o `cupo_agotado`), `beneficio_cop`, `motivo` (una frase para mostrar al comprador), `contexto` (las variables que se usaron), `modelo_version` y `latencia_ms`. En `contexto` van el saldo, el uso del cupo y los medios con los que se decidió, y `fuente_perfil` dice si salieron de la petición (`peticion`) o del catálogo (`catalogo`).

Otros endpoints: `GET /health` y `GET /v1/meta` (perfiles, categorías y parámetros de la Capa 2).

## Qué es supuesto de la demo

Está en `data/catalog.json`, que se genera con `python api/scripts/build_catalog.py`:

- **Perfiles:** cuatro compradores del CSV. Sus variables de perfil son las del dataset; el saldo en pesos es un supuesto, y también lo es que el cuarto (`USR-1167`) no tenga tarjeta de crédito. Para ese caso se eligió un comprador con el cupo en 0,90, el máximo del dataset.
- **Sin tarjeta de crédito:** la app envía `uso_cupo` en 1. El modelo nunca vio un valor mayor que 0,90 y responde igual con 0,90 que con 1, así que trata a ese comprador como a uno con el cupo copado. Solo 43 de las 5.000 filas del dataset están en ese nivel.
- **Comercio:** la app solo envía la categoría. El ticket promedio y el volumen son las medianas de esa categoría en el CSV.
- **Campañas:** un incentivo fijo por categoría (restaurantes 10 %, supermercados 5 %, ropa 15 %, tope de $25.000). Aplica a transferencia, igual que en el generador.
- **Factibilidad:** un medio que el comprador no tiene se descarta; saldo menor que el monto descarta débito y transferencia; uso del cupo de 90 % o más descarta crédito.
- **Confianza en la app:** la API cree el saldo que envía la app. Es aceptable en la demo; con usuarios reales el saldo debe salir del banco, consultado con el usuario autenticado. Ese cambio se hace en `app/perfiles.py` sin tocar el modelo ni la Capa 2.

## Desplegar gratis en Render

1. Subir el repositorio a GitHub con la carpeta `api/` y `render.yaml`.
2. En Render: **New → Blueprint** y elegir el repositorio. El archivo `render.yaml` ya define el servicio en el plan gratuito.
3. Al terminar queda una URL `https://<nombre>.onrender.com`. Probar `https://<nombre>.onrender.com/health`.

El plan gratuito apaga el servicio tras 15 minutos sin uso y tarda cerca de un minuto en volver. Antes de presentar, abrir `/health` para despertarlo.

## Si se reentrena el modelo

Copiar los nuevos `model_payment_final.pkl` y `label_encoder.pkl` a `api/model/`, mantener en `requirements.txt` las versiones con las que se entrenó y correr las pruebas. Los casos marcados como «casos de la demo» en `tests/test_api.py` dependen del modelo actual y pueden necesitar ajuste.
