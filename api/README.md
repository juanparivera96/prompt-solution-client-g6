# API de recomendación — Prompt Solution Client

Servicio que expone el modelo de dos capas para la app Flutter. Es un MVP académico: todos los datos son sintéticos y no hay autenticación.

```
App Flutter ──► POST /v1/recomendacion ──► Capa 1 (model_payment_final.pkl) ──► Capa 2 (utilidad + factibilidad)
```

- **Capa 1:** el pipeline exportado por `DataPreparation_PromptSolutionClient.ipynb` estima la probabilidad de que el comprador use crédito, débito o transferencia.
- **Capa 2:** la función de utilidad del cuaderno (`0,5·P + 0,5·incentivo/15.000`). La API agrega una regla: un medio que el comprador no puede pagar se descarta antes de elegir.

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

La respuesta incluye `recomendacion`, `habito` (medio más probable), `propensiones`, `utilidades`, `factibles`, `excluidos` (con el motivo), `beneficio_cop`, `motivo` (una frase para mostrar al comprador), `contexto` (las variables que se usaron), `modelo_version` y `latencia_ms`.

Otros endpoints: `GET /health` y `GET /v1/meta` (perfiles, categorías y parámetros de la Capa 2).

## Qué es supuesto de la demo

Está en `data/catalog.json`, que se genera con `python api/scripts/build_catalog.py`:

- **Perfiles:** tres compradores del CSV. Sus variables de perfil son las del dataset; el saldo en pesos es un supuesto.
- **Comercio:** la app solo envía la categoría. El ticket promedio y el volumen son las medianas de esa categoría en el CSV.
- **Campañas:** un incentivo fijo por categoría (restaurantes 10 %, supermercados 5 %, ropa 15 %, tope de $25.000). Aplica a transferencia, igual que en el generador.
- **Factibilidad:** saldo menor que el monto descarta débito y transferencia; uso del cupo de 90 % o más descarta crédito.

## Desplegar gratis en Render

1. Subir el repositorio a GitHub con la carpeta `api/` y `render.yaml`.
2. En Render: **New → Blueprint** y elegir el repositorio. El archivo `render.yaml` ya define el servicio en el plan gratuito.
3. Al terminar queda una URL `https://<nombre>.onrender.com`. Probar `https://<nombre>.onrender.com/health`.

El plan gratuito apaga el servicio tras 15 minutos sin uso y tarda cerca de un minuto en volver. Antes de presentar, abrir `/health` para despertarlo.

## Si se reentrena el modelo

Copiar los nuevos `model_payment_final.pkl` y `label_encoder.pkl` a `api/model/`, mantener en `requirements.txt` las versiones con las que se entrenó y correr las pruebas. Los casos marcados como «casos de la demo» en `tests/test_api.py` dependen del modelo actual y pueden necesitar ajuste.
