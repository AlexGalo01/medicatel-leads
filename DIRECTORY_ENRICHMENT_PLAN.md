# Plan: Directorio (búsqueda amplia) + enriquecimiento por entidad

Documento de referencia para el roadmap acordado (LangChain/LangSmith, Gemini, Exa). La implementación en código avanza por fases; ver estado en [DOCS.md](DOCS.md).

## Implementado en el repo (inicio)

- **Plan de búsqueda estructurado** (`search_plan`): Gemini devuelve `entity_type`, `geo`, `main_query`, `additional_queries`, `required_channels`, `negative_constraints`, `clarifying_question`, `exa_category`.
- **Varias llamadas Exa** en fase directorio (hasta 5 queries fusionadas por URL).
- **Pipeline demo**: solo `planner_node` → `exa_webset_node` → `search_finalize_node` (vista previa en el job; ver `AGENT_TO_DO.md` para reactivar el resto).
- **Tabla `directory_entries`** y nodo `directory_persist_node` existen pero **no** están en el grafo activo hasta nueva iteración.
- **API** `GET /api/v1/search-jobs/{job_id}/directory-entries` (paginado; vacío en modo demo).
- **Respuesta al crear job**: campo opcional `clarifying_question` para human-in-the-loop futuro.

## Pendiente (siguientes iteraciones)

- Extracción LLM por lotes con confianza por campo y deduplicación fuerte (Fase 3 del plan original).
- Acción «Enriquecer esta fila» con `source_entry_id` y subgrafo multi-query (Fase 4–5).
- Tags/coste agregados en LangSmith por fase (Fase 6).

El texto completo del plan maestro (objetivos, riesgos, diagrama) está en el mensaje de especificación del producto; este archivo resume el encaje con el código.
