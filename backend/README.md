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
