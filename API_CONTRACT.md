# API Contract (Frontend <-> Backend)

## Base
- Content-Type: `application/json`
- Prefix sugerido: `/api/v1`

## Error envelope
```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "Solicitud inválida",
    "details": {}
  }
}
```

## 1) Crear job de búsqueda
### `POST /api/v1/search-jobs`

Request:
```json
{
  "specialty": "Cardiología",
  "country": "Honduras",
  "city": "Tegucigalpa",
  "contactChannels": ["email", "whatsapp", "linkedin"],
  "notes": "Clínicas privadas con presencia digital"
}
```

Response `202 Accepted`:
```json
{
  "jobId": "job_123",
  "status": "pending",
  "createdAt": "2026-04-15T12:00:00Z"
}
```

## 2) Estado del job
### `GET /api/v1/search-jobs/{jobId}`

Response `200 OK`:
```json
{
  "jobId": "job_123",
  "status": "running",
  "progress": 45,
  "metrics": {
    "sourcesVisited": 120,
    "leadsExtracted": 34,
    "leadsScored": 20
  },
  "currentStage": "scoring",
  "updatedAt": "2026-04-15T12:03:00Z"
}
```

## 3) Listado de leads por job
### `GET /api/v1/leads?jobId={jobId}&minScore=7&sort=score_desc&page=1&pageSize=20`

Response `200 OK`:
```json
{
  "items": [
    {
      "leadId": "lead_1",
      "fullName": "Dra. Ana Pérez",
      "specialty": "Cardiología",
      "city": "Tegucigalpa",
      "score": 9.1,
      "contacts": {
        "email": "ana@example.com",
        "whatsapp": "+50499999999",
        "linkedin": "https://linkedin.com/in/example"
      },
      "primarySourceUrl": "https://example.com/profile"
    }
  ],
  "page": 1,
  "pageSize": 20,
  "total": 34
}
```

## 4) Detalle de lead
### `GET /api/v1/leads/{leadId}`

Response `200 OK`:
```json
{
  "leadId": "lead_1",
  "fullName": "Dra. Ana Pérez",
  "specialty": "Cardiología",
  "score": 9.1,
  "scoreReasoning": "Coincidencia fuerte en especialidad y contacto verificable.",
  "contacts": {
    "email": "ana@example.com",
    "whatsapp": "+50499999999",
    "linkedin": "https://linkedin.com/in/example"
  },
  "sources": [
    {
      "url": "https://example.com/profile",
      "title": "Perfil profesional",
      "confidence": "high"
    }
  ],
  "metadata": {
    "langsmithTraceId": "trace_001"
  }
}
```

## 5) Exportación
### `POST /api/v1/leads/export`

Request:
```json
{
  "jobId": "job_123",
  "format": "csv",
  "filters": {
    "minScore": 7.5
  }
}
```

Response `200 OK`:
```json
{
  "downloadUrl": "https://example.com/exports/job_123.csv",
  "expiresAt": "2026-04-16T12:00:00Z"
}
```

## Status codes esperados
- `200 OK`: lectura/acción exitosa
- `202 Accepted`: job aceptado y en cola
- `400 Bad Request`: validación fallida
- `404 Not Found`: recurso inexistente
- `409 Conflict`: estado inválido para operación
- `500 Internal Server Error`: fallo inesperado
