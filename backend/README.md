# Medicatel Lead Engine Backend

Base inicial de Fase 1:

- Configuracion desde `.env`
- Modelos SQLModel para `search_jobs` y `leads`
- Esquemas Pydantic para contratos de datos
- Estado base para LangGraph
- Repositorio asincrono de leads

## Instalacion

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Inicializar base de datos

```bash
PYTHONPATH=src python -m mle.scripts.init_db
```

`init_db` crea tablas que faltan, pero **no añade columnas nuevas** a tablas ya creadas. Con **PostgreSQL**, al arrancar la API se ejecuta además un `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` para `opportunities.profile_overrides` (ver [`src/mle/db/base.py`](src/mle/db/base.py)); basta **reiniciar el contenedor `backend`** para aplicar el cambio en bases ya existentes.

Si prefieres aplicar la migración a mano o tu motor no es Postgres, usa los scripts en [`sql/`](sql/).

### Migración: `opportunities.profile_overrides`

Script: [`sql/001_opportunities_profile_overrides.sql`](sql/001_opportunities_profile_overrides.sql).

Con el servicio `postgres` del [`docker-compose.yml`](../docker-compose.yml) en marcha:

```bash
docker compose exec postgres psql -U medicatel -d medicatel -c "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS profile_overrides JSONB NOT NULL DEFAULT '{}'::jsonb;"
```

O desde el archivo (desde la **raíz del repo**, donde está `docker-compose.yml`):

```bash
docker compose exec -T postgres psql -U medicatel -d medicatel < backend/sql/001_opportunities_profile_overrides.sql
```

Comprobación rápida tras migrar:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/v1/opportunities
```

Debe responder `200` (no `500` por columna inexistente).

## Ejecutar nodos de ejemplo

```bash
PYTHONPATH=src python -m mle.scripts.run_planner_demo
PYTHONPATH=src python -m mle.scripts.run_exa_node_demo
PYTHONPATH=src python -m mle.scripts.run_pipeline_demo
PYTHONPATH=src python -m mle.scripts.run_storage_demo
```

## Ejecutar pruebas basicas

```bash
PYTHONPATH=src python -m unittest discover -s tests -p "test_*.py"
```

## Levantar API real

```bash
PYTHONPATH=src python -m mle.scripts.run_api
```

API base: `http://localhost:8000`

- Health: `GET /health`
- Crear job: `POST /api/v1/search-jobs`
- Estado job: `GET /api/v1/search-jobs/{job_id}`
- Listar leads: `GET /api/v1/leads?job_id=...`
- Detalle lead: `GET /api/v1/leads/{lead_id}`
- Exportar CSV: `POST /api/v1/leads/export`

Payload de creacion de job (busqueda unica):

```json
{
  "query": "doctores de honduras con whatsapp y email",
  "contact_channels": ["email", "whatsapp", "linkedin"],
  "notes": "opcional"
}
```

El pipeline de busqueda usa Exa Search API normal y guarda metadata:

- `search_type`
- `request_id`
- `results_count`

Referencia del endpoint en uso:

- Base URL: `https://api.exa.ai`
- Search: `POST /search`

Variables opcionales recomendadas:

- `GOOGLE_MODEL` (default: `gemini-flash-latest`; evita `gemini-1.5-flash-latest`, retirado en la API)
- `EXPORT_DIR` (default: `/app/exports` en Docker)
