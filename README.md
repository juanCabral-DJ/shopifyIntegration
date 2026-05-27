# Middleware de Integracion Shopify - ERP/POS

Backend FastAPI para sincronizar datos entre Shopify, un sistema externo ERP/POS/SE y una base de datos intermedia de integracion. La responsabilidad del proyecto es actuar como middleware desacoplado: recibe webhooks, ejecuta sincronizaciones programadas/manuales, mantiene mappings idempotentes y deja trazabilidad de cada operacion.

## Que sincroniza

- Productos, variantes, SKU, precio, estado, tags/categorias e inventario.
- Ordenes de Shopify y sus estados.
- Facturacion desde ordenes sincronizadas.
- Clientes.
- Sucursales/locations e inventario por sucursal.
- Webhooks, eventos pendientes, logs y reintentos.

## Stack

- Python 3.13
- FastAPI
- PostgreSQL
- SQLAlchemy async
- Alembic
- Shopify Admin API
- Cliente HTTP para el sistema externo
- Redis opcional para broker/cache operativo

## Estructura principal

```text
app/
  api/
    routers/              # Endpoints HTTP y webhooks
  application/
    services/             # Casos de uso de sincronizacion
    transformers/         # Transformaciones entre Shopify y SE
    normalization.py      # Helpers de normalizacion reutilizables
    ports.py              # Interfaces/puertos de aplicacion
  domain/
    models/               # Modelos SQLAlchemy y tablas de integracion
  infrastructure/
    repositories/         # Persistencia
    se/                   # Adaptador sistema externo
    shopify/              # Adaptador Shopify
  main.py
workers/
  jobs.py                 # Jobs asincronos reutilizables
alembic/
  versions/               # Migraciones de base de datos
docs/
  architecture_refactor.md
```

## Arquitectura actual

La arquitectura esta organizada por capas:

- `API/Webhooks`: valida requests, HMAC y delega.
- `Application`: orquesta sincronizacion, idempotencia y mappings.
- `Domain`: modelos y tablas de integracion.
- `Infrastructure`: clientes Shopify/SE y repositorios.
- `Workers`: jobs de sincronizacion, reconciliacion y reintentos.

Servicios ya separados:

- `ProductSyncService`: sincroniza productos desde el SE hacia Shopify.
- `BranchSyncService`: sincroniza sucursales del SE con Shopify Locations.
- `MiddlewareService`: fachada temporal de compatibilidad para endpoints existentes.

Mas detalle en [docs/architecture_refactor.md](docs/architecture_refactor.md).

## Tablas de integracion

Tablas legacy operativas:

- `event_inbox`
- `event_outbox`
- `map_order_ids`
- `map_sku_variant`
- `map_cliente_customer`
- `map_invoices`
- `map_recibos`
- `map_sucursales_locations`
- `sync_runs`
- `webhook_events`

Tablas canonicas nuevas para el refactor enterprise:

- `product_mapping`
- `variant_mapping`
- `order_mapping`
- `customer_mapping`
- `inventory_mapping`
- `branch_mapping`
- `sync_logs`
- `failed_jobs`

Cada mapping canonico incluye identificadores internos/externos, identificadores Shopify, `sync_status`, timestamps, `last_sync_at`, `source_hash` y `version`.

## 1. Configurar variables de entorno

Copia el ejemplo:

```powershell
Copy-Item .env.example .env
```

Edita `.env` con tus valores:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/shopifyPayments
SHOPIFY_SHOP=your-dev-store.myshopify.com
SHOPIFY_API_VERSION=2026-01
SHOPIFY_CLIENT_ID=replace_with_app_client_id
SHOPIFY_CLIENT_SECRET=replace_with_app_client_secret
SHOPIFY_ACCESS_TOKEN=shpat_replace_me
SHOPIFY_WEBHOOK_SECRET=replace_with_shopify_webhook_secret
APP_URL=https://your-ngrok-domain.ngrok-free.app
SE_BASE_URL=https://se-api.example.com
SE_API_KEY=replace_with_external_system_api_key
SE_COMPANY_CODE=1
REDIS_URL=redis://localhost:6379/0
```

## 2. Configurar Shopify

1. Crea una tienda de desarrollo en Shopify Partners.
2. Crea una app custom en `Settings > Apps and sales channels > Develop apps`.
3. Asigna estos scopes:

```text
read_orders, write_orders
read_customers, write_customers
read_products, write_products
read_inventory, write_inventory
read_locations, write_locations
read_fulfillments, write_fulfillments
read_merchant_managed_fulfillment_orders, write_merchant_managed_fulfillment_orders
read_third_party_fulfillment_orders, write_third_party_fulfillment_orders
```

4. Instala la app.
5. Copia el Admin API access token en `SHOPIFY_ACCESS_TOKEN`.
6. Copia el webhook signing secret en `SHOPIFY_WEBHOOK_SECRET`.
7. Define `APP_URL` con una URL publica, por ejemplo ngrok.

Instalacion OAuth mantenida:

```http
GET /auth/install?shop=<tu-tienda>.myshopify.com
GET /auth/callback
```

`/auth/install` redirige a Shopify con los scopes requeridos. `/auth/callback` valida `state` y HMAC de OAuth antes de intercambiar el `code` por el Admin API access token.

Webhooks recomendados:

```text
orders/create           -> https://<dominio>/webhooks/orders/create
orders/updated          -> https://<dominio>/webhooks/orders/updated
orders/paid             -> https://<dominio>/webhooks/orders/paid
orders/cancelled        -> https://<dominio>/webhooks/orders/cancelled
refunds/create          -> https://<dominio>/webhooks/refunds/create
fulfillments/create     -> https://<dominio>/webhooks/fulfillments/create
customers/create        -> https://<dominio>/webhooks/customers/create
customers/update        -> https://<dominio>/webhooks/customers/update
inventory_levels/update -> https://<dominio>/webhooks/inventory-levels/update
inventory_items/update  -> https://<dominio>/webhooks/inventory-items/update
products/update         -> https://<dominio>/webhooks/products/update
```

## 3. Configurar el sistema externo

El adaptador SE usa `SE_BASE_URL`, `SE_API_KEY` y `SE_COMPANY_CODE`.

Endpoints usados por el cliente:

- `POST /api/Minvitm/get`
- `POST /api/Mfacpre/get`
- `POST /api/Madmimg/get`
- `POST /api/Factura/Insertar`
- `POST /api/Factura/GetFacturas`
- `POST /api/madmsuc/get`
- `POST /api/mcxccte/get`
- `GET /api/Minvfismovil/getfisico`
- `POST /api/inventario/fisico`

## 4. Levantar con Docker

```powershell
docker compose up --build
```

La API queda disponible en:

```text
http://localhost:8000
```

Swagger/OpenAPI:

```text
http://localhost:8000/docs
```

Nota: revisa `docker-compose.yml`; la imagen de PostgreSQL crea `shopifyPayments`, pero el `DATABASE_URL` del servicio `app` apunta a `shopify_payments`. Alinea ambos nombres antes de usar Docker en un ambiente limpio.

## 5. Levantar sin Docker

Crear/activar entorno virtual:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Instalar dependencias:

```powershell
python -m pip install -r requirements.txt
```

Ejecutar migraciones:

```powershell
python scripts/run_migrations.py
```

Sembrar metodos de pago offline:

```powershell
python scripts/seed_payment_methods.py
```

Levantar servidor:

```powershell
uvicorn app.main:app --reload
```

Si `uvicorn` no esta en el PATH:

```powershell
.\venv\Scripts\uvicorn.exe app.main:app --reload
```

## 6. Verificar salud del servicio

```http
GET /health
GET /ready
```

Respuesta esperada de `/ready`:

```json
{
  "status": "ok",
  "checks": {
    "database": "ok",
    "redis": "configured",
    "external_system": "configured"
  }
}
```

## 7. Paso a paso de uso recomendado

### Paso 1: sincronizar sucursales

```http
POST /sync/branches
```

Esto obtiene sucursales del SE, crea o encuentra Shopify Locations y actualiza mappings de sucursales.

### Paso 2: sincronizar clientes

```http
POST /sync/customers
```

Esto llena mappings cliente externo -> Shopify customer.

### Paso 3: sincronizar taxonomia

```http
POST /sync/taxonomy
```

Esto sincroniza familias/marcas con colecciones/tags de Shopify.

### Paso 4: sincronizar productos

En segundo plano:

```http
POST /sync/products
```

Esperando resultado en el request:

```http
POST /sync/products?wait=true
```

Body opcional para compania:

```json
1
```

El servicio usa mappings antes de crear, busca variantes por SKU para evitar duplicados y registra el resultado en `sync_runs` y `event_outbox`.

### Paso 5: sincronizar precios

```http
POST /sync/prices
```

Actualiza el precio registrado en el mapping. La actualizacion directa en Shopify queda preparada por outbox/servicios de sincronizacion.

### Paso 6: sincronizar inventario

```http
POST /sync/inventory
```

Body opcional:

```json
1
```

Actualiza inventory levels en Shopify usando el location por defecto o el primer mapping de sucursal con location.

### Paso 7: sincronizar imagenes

```http
POST /sync/images
Content-Type: application/json

{
  "invitm_codigo": 123
}
```

### Paso 8: probar una orden Shopify

1. Crea una orden de prueba en Shopify.
2. Shopify envia `orders/create`.
3. El backend valida HMAC.
4. Se registra `webhook_events`.
5. Se registra `event_inbox`.
6. Se crea/actualiza mapping de orden.
7. Se crea un evento `Factura.Insertar` en `event_outbox`.

Consultar eventos:

```http
GET /events
GET /webhooks/logs
```

Consultar mappings:

```http
GET /mappings/orders
GET /mappings/skus
GET /mappings/customers
GET /mappings/branches
GET /mappings/families
GET /mappings/brands
```

Consultar corridas:

```http
GET /sync/runs
GET /sync/runs?sync_type=products
```

## 8. Reintentos

Reintentar la generacion de factura desde una orden sincronizada:

```http
POST /orders/{shopify_order_id}/retry
```

El patron esperado es que los fallos queden en `event_outbox`, `sync_logs` o `failed_jobs`, y luego sean procesados por workers con backoff.

## 9. Jobs disponibles

En [workers/jobs.py](workers/jobs.py) existen funciones asincronas reutilizables:

- `product_sync_job`
- `price_sync_job`
- `inventory_sync_job`
- `inventory_reconcile_job`
- `image_sync_job`
- `customer_sync_job`
- `branch_sync_job`
- `taxonomy_sync_job`
- `insert_invoice_job`

Estas funciones reciben un servicio configurado y pueden conectarse a Celery, RQ, APScheduler, cron o un worker propio.

## 10. Ejecutar pruebas

En PowerShell:

```powershell
$env:PYTHONPATH='.'
.\venv\Scripts\pytest.exe tests -p no:cacheprovider
```

El flag `-p no:cacheprovider` evita problemas de permisos con carpetas cacheadas por OneDrive.

Resultado esperado actual:

```text
34 passed
```

## 11. Comandos utiles

Ver migracion actual:

```powershell
alembic current
```

Aplicar migraciones:

```powershell
alembic upgrade head
```

Crear una migracion nueva:

```powershell
alembic revision -m "descripcion"
```

Ejecutar import check sin escribir `__pycache__`:

```powershell
$env:PYTHONPATH='.'
$env:PYTHONDONTWRITEBYTECODE='1'
.\venv\Scripts\python.exe -B -c "import app.main; print('ok')"
```

## 12. Reglas operativas importantes

- Nunca crear productos u ordenes sin consultar mappings primero.
- Mantener todos los procesos idempotentes.
- Usar SKU, Shopify variant id e IDs externos como claves naturales.
- Registrar eventos antes de procesarlos.
- Respetar paginacion y rate limits de Shopify.
- Mantener controllers delgados; la logica vive en servicios de aplicacion.
- Usar `sync_runs`, `event_inbox`, `event_outbox`, `sync_logs` y `failed_jobs` para trazabilidad.
- Para multi-sucursal, siempre resolver `external_branch_id` contra `shopify_location_id`.

## Estado del refactor

Completado:

- Separacion inicial de servicios de productos y sucursales.
- Normalizacion reutilizable.
- Puertos/interfaces de aplicacion.
- Tablas canonicas de mapping e integracion.
- Documentacion de arquitectura.

Pendiente recomendado:

- Extraer inventario, clientes, taxonomia y facturacion a servicios dedicados.
- Crear repositorios especificos para tablas canonicas.
- Implementar worker real para outbox, failed jobs y reconciliacion incremental.
- Agregar locks por entidad para control de concurrencia.
- Migrar gradualmente desde tablas `map_*` legacy hacia las tablas canonicas.
