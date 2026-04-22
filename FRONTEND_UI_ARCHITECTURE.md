# Frontend UI Architecture (React + Vite)

## Objetivo
Definir la arquitectura de interfaz para operar el `Medicatel Lead Engine` desde una SPA en React.

## Stack propuesto
- React 18 + TypeScript
- Vite
- React Router
- TanStack Query (manejo de estado servidor)
- Zustand o Context API (estado UI local)

## Estructura de rutas
- `/` -> redirección a `/search`
- `/search` -> creación de job de prospección
- `/jobs/:jobId` -> **workspace de búsqueda** (tabla + panel de criterios; polling del job y de leads)
- `/jobs/:jobId/leads` -> redirección a `/jobs/:jobId` (compatibilidad)
- `/leads/:leadId` -> detalle del lead

## Vistas principales

### 1) SearchView
**Propósito:** iniciar búsqueda de leads.

**Elementos:**
- Formulario con campos:
  - `specialty`
  - `country`
  - `city`
  - `contactChannels` (email, whatsapp, linkedin)
  - `notes`
- Botón primario `Crear búsqueda`.

**Comportamiento:**
- `POST /search-jobs`
- En éxito: navegar a `/jobs/:jobId`
- En error: mostrar banner con mensaje accionable.

### 2) JobSearchWorkspaceView (`JobSearchWorkspacePage`)
**Propósito:** monitorear el job y ver **resultados en tabla** en la misma pantalla (layout dos columnas).

**Elementos:**
- Estado del job, progreso, etapa; pipeline colapsable.
- Tabla de leads (polling `GET /leads` mientras `running`).
- Panel lateral: criterios (texto + chips desde estado de navegación), enriquecimientos, métricas.

**Comportamiento:**
- Polling ~1,5s `GET /search-jobs/:jobId`; leads cada ~2,5s si el job no terminó.
- En `completed`: última carga de leads; sin redirección automática a otra ruta.

### 3) LeadsResultsView (histórico)
La vista dedicada de solo lista con filtros CSV fue **retirada**; filtros y exportación CSV pueden reintroducirse dentro del workspace en una iteración posterior.

### 4) LeadDetailView
**Propósito:** trazabilidad completa del lead.

**Elementos:**
- Perfil de contacto.
- Score y justificación.
- Evidencias/citas de origen.
- Estado de validación manual.

## Estados transversales de UI
- Loading: skeletons por vista.
- Empty: mensajes y CTA para volver a buscar.
- Error: componente reutilizable con acción de reintento.
- Success: feedback no intrusivo para acciones clave.

## Arquitectura de carpetas sugerida
```txt
src/
  app/
    router/
    providers/
  pages/
    SearchView/
    JobExecutionView/
    LeadsResultsView/
    LeadDetailView/
  features/
    jobs/
      api/
      components/
      hooks/
      types/
    leads/
      api/
      components/
      hooks/
      types/
  shared/
    ui/
    layout/
    utils/
    styles/
```
