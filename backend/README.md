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

- `GOOGLE_MODEL` (default: `gemini-1.5-flash-latest`)
- `EXPORT_DIR` (default: `/app/exports` en Docker)
