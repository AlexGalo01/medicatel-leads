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
- `/jobs/:jobId` -> estado de ejecución del job
- `/jobs/:jobId/leads` -> resultados (tabla)
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

### 2) JobExecutionView
**Propósito:** monitorear progreso.

**Elementos:**
- Estado general (`pending`, `running`, `completed`, `error`)
- Barra de progreso y métricas.
- Log resumido por etapas.

**Comportamiento:**
- Polling cada 3-5 segundos con `GET /search-jobs/:jobId`
- En `completed`: habilitar CTA a resultados.

### 3) LeadsResultsView
**Propósito:** revisar y operar leads.

**Elementos:**
- Tabla con columnas:
  - nombre
  - especialidad
  - score
  - email
  - whatsapp
  - linkedin
  - fuente principal
- Filtros por score, ciudad, canal de contacto disponible.
- Ordenamiento por score y fecha.
- Exportación.

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
