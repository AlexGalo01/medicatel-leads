# Documentación del Proyecto

Este archivo centraliza y organiza la documentación existente del repositorio.

## Núcleo del proyecto

- `README.md`: guía principal de uso local y Docker.
- `DEVELOPMENT_PLAN.md`: roadmap funcional y técnico por fases.
- `AGENT_TO_DO.md`: siguiente implementación del pipeline (post-demo: limpieza, leads, export).
- `API_CONTRACT.md`: contrato API base entre frontend y backend.

## Diseño y experiencia de usuario

- `DESIGN.md`: sistema visual actualizado (Meta Store + referencias de estilo).
- `FRONTEND_UI_ARCHITECTURE.md`: arquitectura de pantallas y navegación.
- `FRONTEND_DESIGN_TOKENS.md`: tokens de color, tipografía, radios y spacing.
- `FRONTEND_ITERATIONS.md`: entregas por iteración del frontend.

## Integración de búsqueda

- `DIRECTORY_ENRICHMENT_PLAN.md`: directorio amplio + enriquecimiento por entidad (roadmap y estado de implementación).
- `SEARCH.md`: referencia activa de Exa Search (endpoints, parámetros y ejemplos).
- `WEBSETS.md`: referencia de WebSets (actualmente no activa en este flujo).
- `exa-api-setup-prompt.md`: guía amplia de configuración e integración con Exa.

## Backend específico

- `backend/README.md`: ejecución del backend, API y pipeline.

---

## AI CRM — Producto y fases (borrador vivo)

Este bloque resume decisiones de negocio y arquitectura de datos acordadas en conversación; convive con `DEVELOPMENT_PLAN.md` y se irá refinando.

### Alcance fase 1 (prioridad actual)

1. **Búsqueda**: flujo agentico / Exa / pipeline existente.
2. **Importación masiva** (Excel / PDF con listas de médicos): procesamiento por **lotes** (ej. 5 filas) con búsqueda Exa y flujo tipo **enriquecimiento** — prioridad respecto al MVP mínimo a acordar en diseño.
3. **Crear oportunidad** desde candidato(s): persistencia inicial en CRM; **sin** avanzar a etapas posteriores en UI ni en API (solo creación y estado inicial).

### Decisiones acordadas

| Tema | Decisión |
|------|----------|
| Pipeline de etapas | **Único global** para todas las oportunidades (cuando la máquina de estados esté activa). |
| Etapas | **Obligatorias** en el diseño del embudo. |
| `crm_stage_guards` | Reglas **declarativas**; persistidas en **tabla**. |
| Saltar / retroceder | **Administrador** o **dueño** de la oportunidad. |
| Respuesta negativa del doctor | **Opción predefinida** y/o **texto libre**. |
| Fusión de leads | Permitida: mismo médico, **distintas fuentes**; alineado con **enrichment**. |
| Snapshot vs deep-enrich | Los datos de la oportunidad deben poder **actualizarse** tras **deep-enrich** (no solo congelar al crear). |

### Import Excel / PDF (lista de médicos)

- **Objetivo**: subir archivo → extraer entidades → encolar filas → procesar en **lotes** con Exa + flujo tipo enrichment.
- **Excel**: lectura tabular y normalización de columnas.
- **PDF**: extracción de texto / OCR + opción LLM con schema fijo; prever errores y **edición manual** de filas antes de buscar.
- **Cola sugerida**: estado por fila (`pending` / `processing` / `done` / `error`); trazas LangSmith por import y por lote.

### Modelo de datos (orientación)

- **Candidato / lead de búsqueda**: origen del motor (job, Exa, pipeline).
- **Oportunidad CRM**: se crea con acción explícita (**«Crear oportunidad»**); etapas completas y guards se activan **después** de la fase 1.
- Tablas conceptuales: `crm_opportunities`, `crm_pipeline_stages`, `crm_opportunity_stage_history`, `crm_stage_guards` (declarativo), `crm_documents` (fases posteriores). Detalle en conversaciones de arquitectura; migraciones cuando arranque implementación backend.

### Preguntas pendientes (revisar antes de cerrar MVP CRM)

#### Pipeline y guards

- ¿Alguna etapa **opcional** en futuros embudos aunque hoy sea pipeline global único?
- ¿Formato exacto de guards declarativos (tipos: `required_field`, `min_documents`, `outcome_in`, etc.)?

#### Oportunidad vs candidato

- Misma persona promovida dos veces: ¿error, abrir oportunidad existente, o duplicado con aviso?
- ¿Idempotencia al crear oportunidad desde import masivo vs desde búsqueda web?

#### Identidad y deduplicación

- Alcance: ¿global por cuenta o por workspace futuro?
- Prioridad de señales: LinkedIn > email > tel > nombre+ciudad — ¿confirmar?
- ¿Campos excluidos por compliance?

#### Búsqueda

- ¿Un job admite **re-ejecución** / segunda ronda o siempre job nuevo?
- Listado de candidatos: ¿ocultar ya promovidos, marcarlos, o filtrar solo en vista CRM?
- Export CSV: ¿candidatos, oportunidades, o ambos con columna de estado?

#### Usuarios y auditoría

- ¿Multi-usuario y roles (vendedor, supervisor, admin)?
- ¿Nota obligatoria en cada transición o solo en algunas etapas?
- ¿Historial inmutable o editable?

#### Documentos (fases posteriores)

- v1: ¿solo checkbox «recibido» o subida a storage desde el inicio?
- Tipos de documento: enum fijo vs etiquetas libres.
- ¿Quién valida el documento?

#### Arquitectura

- ¿Misma Postgres para búsqueda + CRM o API entre servicios desde el día 1?
- ¿Eventos / notificaciones en los primeros meses?

#### UI

- ¿Prioridad **desktop** vs **móvil**?
- ¿**Kanban** por etapas vs **lista + detalle**?

---

## Workspace de búsqueda (dos columnas) — implementado

Pantalla tipo referencia Websets/Clay: **tabla a la izquierda**, **criterios y enriquecimientos a la derecha**, con el job en ejecución o completado.

### Rutas

| Ruta | Comportamiento |
|------|----------------|
| `/search` | Formulario de búsqueda; al crear el job navega a `/jobs/:jobId` con **estado** en React Router. |
| `/jobs/:jobId` | **`JobSearchWorkspacePage`**: polling del estado del job, tabla de leads, panel lateral. |
| `/jobs/:jobId/leads` | Redirección a `/jobs/:jobId` (compatibilidad con enlaces antiguos). |
| `/leads/:leadId` | Detalle de oportunidad (sin cambio). |

**Estado pasado desde `/search`:** `searchLabel`, `contactChannels`, `searchFocus`, `notes` (tipado en `JobSearchLocationState` en [`frontend/src/pages/JobSearchWorkspacePage.tsx`](frontend/src/pages/JobSearchWorkspacePage.tsx)). Si se abre el job directamente por URL sin estado, el panel de criterios muestra un título genérico.

### UI

- **Cabecera:** estado del job, progreso, etapa actual; enlace «Nueva búsqueda»; **Descargar CSV** cuando el job está completado.
- **Pipeline:** franja colapsable con pasos resumidos (plan → Exa → … → listo).
- **Columna principal:** toolbar (Filtrar / Ordenar / Añadir enriquecimiento como *stub* deshabilitado), tabla con avatar inicial, nombre, especialidad, ciudad, enlace de perfil, badge de evidencia, score, CTA «Ver oportunidad».
- **Columna lateral (sticky en desktop):** consulta de solo lectura, *chips* de enfoque y canales, bloque «Enriquecimientos» alineado a canales, «Más resultados» 25/100 (*stub*), pie con métricas (`total` leads / extraídos / fuentes).
- **Carga:** filas *skeleton* mientras el job está `pending` o `running` y aún no hay filas en API.

### Mapeo datos Exa ↔ API ↔ UI (v1)

En playground, **Exa** (`type=deep`, `category=people`, etc.) devuelve `output.content`, `output.grounding` (citas agregadas) y `results[]` con `highlights` por URL. **El pipeline actual** del backend persiste leads al finalizar etapas; **no** expone en tiempo real ese JSON al frontend.

Por tanto, la tabla del workspace se alimenta de **`GET /api/v1/leads?job_id=…`**:

- **Badge «Match» / refs (v1 pragmática):** si el lead tiene `linkedin_url` o `primary_source_url`, se muestra **1 ref.**; si no, «Sin fuente». No se usa aún el conteo real de citas por persona desde `grounding`.
- **Mejora futura (v2):** persistir por lead fragmentos de `grounding` o `exa_result_json` y/o exponer `criteria_tags` desde `GET /search-jobs/:id` para el panel derecho sin depender solo del estado de navegación.

### Mock en Pencil (`.pen`)

En [`designs.pen`](designs.pen) hay un frame **«Workspace Busqueda»** (dos columnas: tabla de ejemplo con filas tipo psicólogas en Honduras + panel de criterios, enriquecimientos y métricas), generado vía **Pencil MCP** (`batch_design`). Ábrelo en Cursor con la extensión Pencil para iterar. La **captura automática** (`get_screenshot`) puede fallar si el contexto del editor no está activo; en ese caso usa la vista previa de Pencil en el IDE.

La implementación definitiva sigue siendo [`JobSearchWorkspacePage.tsx`](frontend/src/pages/JobSearchWorkspacePage.tsx) (incluye **Descargar CSV** al completar el job).

---

## Próximo paso: CRM y refinamiento UX

**Hecho en esta iteración:** shell del workspace de búsqueda y documentación de limitaciones de datos.

**Pendiente (producto):** import Excel/PDF, «Crear oportunidad» desde detalle, criterios derivados desde backend, badges de evidencia por grounding, streaming o resultados parciales durante el job.

### Referencias en repo

- `DESIGN.md`, `FRONTEND_UI_ARCHITECTURE.md`, `FRONTEND_DESIGN_TOKENS.md`, `FRONTEND_ITERATIONS.md`.
- Estilos workspace: [`frontend/src/styles.css`](frontend/src/styles.css) (bloque «Búsqueda workspace»).