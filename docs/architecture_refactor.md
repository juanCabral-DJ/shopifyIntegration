# Arquitectura de Integracion Shopify ERP/POS

## Objetivo

El backend queda orientado a una sola responsabilidad: sincronizar datos entre Shopify, el sistema externo y una base intermedia de integracion. La base intermedia es la fuente de verdad para mappings, idempotencia, estado de sincronizacion, auditoria y recuperacion ante fallos.

## Responsabilidades por capa

### API / Webhooks

- Verifica HMAC y autenticacion.
- Normaliza headers y payload minimo.
- Encola o delega a servicios de aplicacion.
- No contiene reglas de negocio ni transformaciones ERP/Shopify.

### Application

- Orquesta casos de uso de sincronizacion.
- Resuelve idempotencia usando mappings antes de crear registros.
- Calcula hashes/versiones para detectar cambios.
- Coordina retries, logs, outbox e inbox.

Servicios actuales:

- `ProductSyncService`: upsert de productos Shopify desde catalogo externo.
- `BranchSyncService`: mapeo de sucursales externas con Shopify Locations.
- `MiddlewareService`: fachada de compatibilidad para endpoints existentes. Debe seguir adelgazando hasta delegar todo.

### Domain

- Modelos de negocio y tablas de integracion.
- No llama APIs externas.
- No conoce FastAPI ni httpx.

Tablas canonicas nuevas:

- `product_mapping`
- `variant_mapping`
- `order_mapping`
- `customer_mapping`
- `inventory_mapping`
- `branch_mapping`
- `sync_logs`
- `failed_jobs`

`webhook_events`, `event_inbox`, `event_outbox` y `sync_runs` ya existian y siguen como soporte operacional.

### Infrastructure

- Adaptadores concretos de Shopify Admin API y sistema externo.
- Repositorios SQLAlchemy.
- Manejo de paginacion, rate limit y errores HTTP.

### Workers / Jobs

- Ejecutan sincronizacion incremental y reconciliacion.
- Procesan outbox/inbox.
- Reintentan `failed_jobs` con backoff.

## Anti-patterns encontrados

- `MiddlewareService` mezclaba orquestacion, transformacion, llamadas HTTP, reglas de factura, mappings e inventario.
- Algunos helpers de normalizacion vivian dentro de un servicio concreto, dificultando reuso y test unitario.
- Existen tablas legacy con nombres acoplados al SE (`map_sku_variant`, `map_sucursales_locations`). Se agregan tablas canonicas para migrar progresivamente sin romper operacion.
- Los routers ya delegaban parte de la logica, pero los webhooks aun crean servicios concretos manualmente. El siguiente paso es una factory/container de dependencias por caso de uso.

## Reglas de idempotencia

- Producto: buscar primero por `external_product_id`, luego por `shopify_product_id`, luego por SKU/variant.
- Variante: `external_variant_id`, `shopify_variant_id` y `shopify_inventory_item_id` son claves naturales.
- Orden: `shopify_order_id` y `external_order_id` deben ser unicos.
- Inventario: clave compuesta `external_product_id + external_variant_id + external_branch_id`.
- Webhooks: almacenar evento antes de procesar; si el mismo evento llega de nuevo, consultar mapping/outbox antes de crear.

## Flujo realtime

1. Shopify envia webhook.
2. API valida HMAC.
3. Se registra `webhook_events` y `event_inbox`.
4. Servicio de aplicacion resuelve mapping.
5. Se crea/actualiza entidad o se genera `event_outbox`.
6. Worker procesa outbox y actualiza `sync_logs`.

## Flujo programado

1. Job incremental obtiene cambios desde sistema externo o Shopify.
2. Normaliza registros.
3. Calcula hash por entidad.
4. Si el hash no cambia, omite.
5. Si cambia, ejecuta upsert idempotente.
6. Actualiza mapping, `last_sync_at`, `sync_status` y `sync_logs`.

## Proximos pasos recomendados

1. Migrar `sync_inventory`, `sync_customers`, `sync_catalog_taxonomy` y facturacion a servicios dedicados.
2. Crear repositorios canonicos para las nuevas tablas.
3. Implementar workers reales para `event_outbox`, `failed_jobs` e incremental sync.
4. Sustituir `MiddlewareService` por una factory de casos de uso.
5. Agregar locks por entidad para evitar carreras en producto/orden/inventario.
