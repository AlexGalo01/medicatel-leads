# Medicatel Lead Engine (MLE)

Motor de prospeccion inteligente de leads para sector salud, con arquitectura de agentes y una interfaz web en React.

## Estado actual

- Fase 1 implementada: contratos de datos con `Pydantic` + `SQLModel`.
- Fase 2 iniciada: `Planner Node` y `Exa Webset Node` asincronos.
- Documentacion de frontend y contrato API disponibles en archivos markdown del proyecto.

## Estructura

- `backend/`: codigo Python del motor de agentes.
- `DEVELOPMENT_PLAN.md`: roadmap maestro.
- `DESIGN.md`: guia visual inspirada en Coinbase.
- `API_CONTRACT.md`: contrato base frontend-backend.
- `FRONTEND_UI_ARCHITECTURE.md`: arquitectura de vistas React.
- `FRONTEND_DESIGN_TOKENS.md`: tokens de diseno para UI.
- `FRONTEND_ITERATIONS.md`: plan incremental de entregas frontend.

## Quick start backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
PYTHONPATH=src python3 -m mle.scripts.init_db
```

## Ejecutar demos de nodos

```bash
cd backend
source .venv/bin/activate
PYTHONPATH=src python3 -m mle.scripts.run_planner_demo
PYTHONPATH=src python3 -m mle.scripts.run_exa_node_demo
```

## Variables de entorno requeridas

- `DATABASE_URL`
- `EXA_API_KEY`
- `GOOGLE_API_KEY`
- `LANGSMITH_TRACING`
- `LANGSMITH_ENDPOINT`
- `LANGSMITH_API_KEY`
- `LANGSMITH_PROJECT`

## Nota de seguridad

No subas credenciales reales al repositorio. Usa `.env` local y comparte un `.env.example` sin secretos.
