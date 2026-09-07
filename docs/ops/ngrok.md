# Ops — túnel ngrok (XeniaMAP)

Runbook **privado / local**. No forma parte del producto público.

## Prerrequisito

Stack Docker levantado (frontend en `:5173`):

```bash
cd /path/to/XeniaMAP
docker compose up -d
```

## Túnel

Dominio reservado: `https://xeniamap.ngrok.app` → frontend Vite en `:5173`.

```bash
ngrok http --url=xeniamap.ngrok.app 5173
```

## Comprobar

```bash
# Servicios locales
curl -sS -o /dev/null -w 'local5173:%{http_code}\n' --max-time 3 http://127.0.0.1:5173/
curl -sS -o /dev/null -w 'api:%{http_code}\n' --max-time 3 http://127.0.0.1:8000/health

# Túneles activos del agente ngrok local
curl -sS --max-time 5 http://127.0.0.1:4040/api/tunnels

# URL pública
curl -sS -o /dev/null -w 'public:%{http_code}\n' --max-time 15 \
  -H 'ngrok-skip-browser-warning: 1' https://xeniamap.ngrok.app/
```

Vite permite hosts `*.ngrok.app` / `*.ngrok-free.*` / `*.trycloudflare.com` en `frontend/vite.config.js`.
