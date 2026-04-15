from __future__ import annotations

import csv
from pathlib import Path
from typing import Any
from uuid import UUID


def export_leads_to_csv(job_id: UUID, leads: list[dict[str, Any]]) -> str:
    export_dir = Path("backend/exports")
    export_dir.mkdir(parents=True, exist_ok=True)

    export_path = export_dir / f"leads_{job_id}.csv"
    columns = [
        "full_name",
        "specialty",
        "country",
        "city",
        "score",
        "score_reasoning",
        "email",
        "whatsapp",
        "linkedin_url",
    ]

    with export_path.open(mode="w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=columns)
        writer.writeheader()
        for lead in leads:
            writer.writerow({column: lead.get(column, "") for column in columns})

    return str(export_path)

