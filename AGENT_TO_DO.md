# AGENT_TO_DO — Siguiente implementación (post-demo)

Pipeline actual en producción: **solo prebúsqueda + búsqueda (Exa) + cierre con vista previa** (`presearch_and_search_only`). El archivo [`backend/src/mle/orchestration/pipeline.py`](backend/src/mle/orchestration/pipeline.py) es el punto de enganche.

## Objetivo

Reactivar el flujo completo (limpieza, reintento, CRM leads) sin romper el modo demo: idealmente con **flag de configuración** o **dos funciones de grafo** (`run_lead_pipeline` vs `run_lead_pipeline_full`).

## Fase — Limpieza y normalización

| Pieza | Archivo orientativo | Notas |
|--------|---------------------|--------|
| `scoring_cleaning_node` | `backend/src/mle/nodes/scoring_cleaning_node.py` | Construir `GraphLeadItem` desde Exa; **desacoplar score LLM** si no se usa. |
| `lead_purification_node` | `backend/src/mle/nodes/lead_purification_node.py` | Validación email / WhatsApp / URL. |

## Fase — Re-evaluación (segunda búsqueda)

| Pieza | Archivo | Notas |
|--------|---------|--------|
| `contact_retry_node` | `backend/src/mle/nodes/contact_retry_node.py` | Umbral de cobertura; segunda query Exa. |

## Fase — Directorio en BD (opcional, paralelo a leads)

| Pieza | Archivo | Notas |
|--------|---------|--------|
| `directory_persist_node` | `backend/src/mle/nodes/directory_persist_node.py` | Tras Exa; API ya expone `GET .../directory-entries`. |

## Fase — Persistencia y exportación

| Pieza | Archivo | Notas |
|--------|---------|--------|
| `storage_export_node` | `backend/src/mle/nodes/storage_export_node.py` | Postgres + CSV; actualizar job `metadata` (`export_path`, `stored_leads`). |

## Fase — Enriquecimiento por entidad (fuera del grafo principal)

| Pieza | Archivo | Notas |
|--------|---------|--------|
| `deep_enrich_lead` | `backend/src/mle/services/lead_deep_enrich_service.py` | Proponente + revisor; endpoint ya existe. |
| Handoff desde fila de directorio | API + modelo | `source_entry_id`, congelar identidad (plan directorio + enriquecimiento). |

## Frontend- [`frontend/src/pages/JobSearchWorkspacePage.tsx`](frontend/src/pages/JobSearchWorkspacePage.tsx): hoy muestra **vista previa Exa** cuando `pipeline_mode === "presearch_and_search_only"`. Con pipeline completo, restaurar filas solo desde **leads** o combinar ambos.
- Botón **Descargar CSV**: oculto en modo demo; mostrar cuando exista export real.

## Verificación

- Tests: [`backend/tests/test_pipeline.py`](backend/tests/test_pipeline.py) mockea planner + Exa + finalize; añadir test del grafo completo cuando se reactive.
- LangSmith: etiquetar runs por `pipeline_mode` / fase.
