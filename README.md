# LeadGen AI

Motor inteligente de prospección de leads B2B con agentes de IA, búsqueda multicanal (Exa + Brave) y pipeline de enriquecimiento. Encuentra, califica y gestiona leads directamente desde una interfaz web en React.

## Estado actual

- Fase 1 implementada: contratos de datos con `Pydantic` + `SQLModel`.
- Fase 2 implementada con pipeline real: `Planner -> Exa/Brave Search -> Scoring -> Enriquecimiento -> Storage/Export`.
- Documentación de frontend, arquitectura API y referencias de búsqueda disponibles en archivos markdown del proyecto.

## Estructura

- `backend/`: código Python del motor de agentes y API FastAPI.
- `frontend/`: aplicación React con TypeScript y Vite.
- `DESIGN.md`: guía visual principal (componentes, referencia visual).
- `API_CONTRACT.md`: contrato base frontend-backend.
- `FRONTEND_UI_ARCHITECTURE.md`: arquitectura de vistas y layouts React.
- `SEARCH.md`: referencia activa de búsqueda (Exa + Brave) usada por el pipeline.
- `DOCS.md`: índice organizado de todos los archivos Markdown.

## Quick start backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
PYTHONPATH=src python3 -m mle.scripts.init_db
```

## Quick start frontend

```bash
cd frontend
npm install
npm run dev
```

Variable opcional:

```bash
VITE_API_BASE_URL=http://localhost:8000
```

## Docker Compose (recomendado)

Levanta toda la plataforma (PostgreSQL + Backend + Frontend):

```bash
docker compose up --build -d
```

Servicios:

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- Healthcheck backend: `http://localhost:8000/health`
- PostgreSQL: `localhost:5432` (`medicatel/medicatel`)

Comandos útiles:

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
docker compose down
```

Para borrar también los datos de Postgres:

```bash
docker compose down -v
```

## Variables de entorno requeridas

- `DATABASE_URL`
- `EXA_API_KEY` o `BRAVE_API_KEY`
- `GOOGLE_API_KEY`
- `GOOGLE_MODEL` (opcional, default: `gemini-flash-latest`)
- `LANGSMITH_TRACING`
- `LANGSMITH_ENDPOINT`
- `LANGSMITH_API_KEY`
- `LANGSMITH_PROJECT`
- `EXPORT_DIR` (opcional, default: `/app/exports` en Docker)

## Contrato de búsqueda actual

- El frontend y backend usan un input único de búsqueda (`query`) para crear jobs.
- Endpoint de creación:

```json
{
  "query": "directores de compras en empresas manufactureras con perfil LinkedIn activo",
  "contact_channels": ["email", "whatsapp", "linkedin"],
  "notes": "opcional"
}
```

## Nota de seguridad

No subas credenciales reales al repositorio. Usa `.env` local y comparte un `.env.example` sin secretos.
