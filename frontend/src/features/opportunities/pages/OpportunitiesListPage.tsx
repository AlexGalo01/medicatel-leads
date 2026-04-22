import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ChevronRight, Loader2 } from "lucide-react";

import { listOpportunities } from "../../../api";
import { Badge } from "../../../components/ui/badge";
import { Card } from "../../../components/ui/card";
import { Select } from "../../../components/ui/select";
import { OPPORTUNITY_STAGES_ORDER, opportunityStageLabel } from "../model/stages";
import type { OpportunityStageKey } from "../../../types";

function formatUpdated(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("es-HN", { dateStyle: "short", timeStyle: "short" });
}

export function OpportunitiesListPage(): JSX.Element {
  const [stageFilter, setStageFilter] = useState<string>("");

  const listQuery = useQuery({
    queryKey: ["opportunities", stageFilter],
    queryFn: () => listOpportunities({ stage: stageFilter || undefined }),
  });

  const items = listQuery.data?.items ?? [];

  const stageOptions = useMemo(
    () => OPPORTUNITY_STAGES_ORDER.map((k) => ({ value: k, label: opportunityStageLabel[k] })),
    [],
  );

  return (
    <div className="opportunities-page">
      <Card className="panel opportunities-page-header">
        <div>
          <h1 className="opportunities-page-title">Oportunidades</h1>

        </div>
        <label className="opportunities-filter">
          <span className="muted-text">Filtrar por fase</span>
          <Select
            className="opportunities-filter-select"
            value={stageFilter}
            onChange={(e) => setStageFilter(e.target.value)}
            aria-label="Filtrar oportunidades por fase"
          >
            <option value="">Todas</option>
            {stageOptions.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </label>
      </Card>

      <Card className="panel opportunities-table-wrap">
        {listQuery.isLoading ? (
          <p className="muted-text opportunities-loading">
            <Loader2 className="spin" size={18} aria-hidden /> Cargando…
          </p>
        ) : null}
        {listQuery.isError ? (
          <p className="error-text">No se pudo cargar la lista. Intenta de nuevo.</p>
        ) : null}
        {!listQuery.isLoading && !listQuery.isError && items.length === 0 ? (
          <p className="muted-text opportunities-empty">
            No hay oportunidades. Crea una desde el detalle de un resultado Exa (botón «Crear oportunidad»).
          </p>
        ) : null}
        {!listQuery.isLoading && items.length > 0 ? (
          <table className="opportunities-table">
            <thead>
              <tr>
                <th scope="col">Título</th>
                <th scope="col">Fase</th>
                <th scope="col">Responsable</th>
                <th scope="col">Actualizado</th>
                <th scope="col">
                  <span className="visually-hidden">Acción</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.opportunity_id}>
                  <td>
                    <strong>{row.title || "Sin título"}</strong>
                  </td>
                  <td>
                    <Badge className="opportunities-stage-pill" variant="muted">
                      {opportunityStageLabel[row.stage as OpportunityStageKey] ?? row.stage}
                      {row.stage === "response" && row.response_outcome ? (
                        <span className="muted-text opportunities-stage-sub">
                          {" "}
                          · {row.response_outcome}
                        </span>
                      ) : null}
                    </Badge>
                  </td>
                  <td className="muted-text opportunities-owner-cell">
                    {row.owner ? row.owner.display_name : "—"}
                  </td>
                  <td className="muted-text">{formatUpdated(row.updated_at)}</td>
                  <td>
                    <Link className="cta-button opportunities-row-link" to={`/opportunities/${row.opportunity_id}`}>
                      Abrir
                      <ChevronRight size={14} aria-hidden />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </Card>
    </div>
  );
}
