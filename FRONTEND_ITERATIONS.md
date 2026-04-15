# Frontend Delivery Iterations

## Iteración 1: MVP funcional
**Objetivo:** flujo de punta a punta para ejecutar una búsqueda y visualizar resultados.

### Entregables
- Bootstrap del proyecto `Vite + React + TypeScript`.
- Rutas base: `search`, `job execution`, `results`, `lead detail`.
- Integración de API para:
  - crear job
  - consultar estado
  - listar leads
- Tabla básica de resultados.
- Estados `loading`, `empty`, `error`.

### Criterio de salida
- Un usuario puede crear un job, seguir su progreso y ver leads en tabla.

## Iteración 2: calidad de producto
**Objetivo:** mejorar usabilidad operativa para equipo comercial.

### Entregables
- Filtros avanzados y ordenamiento persistente.
- Vista de detalle de lead con fuentes y justificación del score.
- Exportación de leads por filtros.
- Skeleton loaders y mensajes de error accionables.
- Manejo de estados de red intermitente.

### Criterio de salida
- Operación diaria posible sin soporte técnico constante.

## Iteración 3: pulido visual Coinbase-inspired
**Objetivo:** elevar consistencia visual, confianza y legibilidad.

### Entregables
- Implementación completa de tokens de diseño.
- Layout con secciones claras/oscuras según guía.
- CTAs con estilo pill y estados hover/focus definidos.
- Revisión responsive en breakpoints clave.
- Ajustes de accesibilidad (contraste, foco, navegación teclado).

### Criterio de salida
- UI consistente, estable y alineada a la dirección visual definida en `DESIGN.md`.
