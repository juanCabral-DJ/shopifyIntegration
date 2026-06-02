# Shopify Worker en Kubernetes

Estos manifiestos levantan Redis privado dentro del cluster y un worker `arq`.

## 1. Construir y publicar la imagen

```bash
docker build -f Dockerfile.worker -t your-registry/shopify-worker:latest .
docker push your-registry/shopify-worker:latest
```

Actualiza `k8s/worker.yaml` y reemplaza:

```text
your-registry/shopify-worker:latest
```

por la imagen real.

## 2. Configurar secretos

Edita `k8s/redis.yaml`:

```text
REDIS_PASSWORD
```

Edita `k8s/worker.yaml`:

```text
DATABASE_URL
SHOPIFY_SHOP
SHOPIFY_ACCESS_TOKEN
SHOPIFY_WEBHOOK_SECRET
SHOPIFY_CLIENT_ID
SHOPIFY_CLIENT_SECRET
APP_URL
SE_BASE_URL
SE_API_KEY
```

No uses el `.env` directamente como imagen ni lo subas al registry.

## 3. Aplicar en el cluster

```bash
kubectl apply -f k8s/redis.yaml
kubectl apply -f k8s/worker.yaml
```

## 4. Revisar estado y logs

```bash
kubectl get pods
kubectl logs deployment/shopify-worker -f
kubectl logs deployment/shopify-redis -f
```

## Nota sobre Render

El código actual del API no encola jobs en Redis; el worker usa cron. Por eso Redis puede quedarse privado dentro del cluster y Render no necesita apuntar a este Redis por ahora.

Si luego el API de Render empieza a encolar jobs en Redis, entonces Render también debe poder acceder al mismo Redis. En ese caso no uses un `ClusterIP` privado; necesitas una conexión privada entre Render y el cluster o exponer Redis de forma segura con password, TLS/firewall y acceso restringido.
