import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AlertCircle, CheckCircle, Loader2, Upload } from "lucide-react";
import { previewImportOpportunitiesXlsx, importOpportunitiesXlsx } from "../../../api";
import type { DirectoryStep } from "../../../types";

interface ImportExcelModalProps {
  isOpen: boolean;
  directoryId: string;
  steps: DirectoryStep[];
  onClose: () => void;
}

type Step = "upload" | "preview" | "success";

export function ImportExcelModal({ isOpen, directoryId, steps, onClose }: ImportExcelModalProps) {
  const [step, setStep] = useState<Step>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [previewRows, setPreviewRows] = useState<any[]>([]);
  const [targetStepId, setTargetStepId] = useState<string>("");
  const [importResult, setImportResult] = useState<{
    created: number;
    skipped: number;
    errors: Array<{ row: number; reason: string }>;
  } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      setFile(files[0]);
    }
  };

  const handlePreview = async () => {
    if (!file) return;
    setLoading(true);
    try {
      const result = await previewImportOpportunitiesXlsx(file);
      setPreviewRows(result.rows);
      setStep("preview");
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : "Error desconocido";
      alert(`Error: ${errorMsg}`);
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmImport = async () => {
    if (!file) return;
    setLoading(true);
    try {
      console.log("[ImportExcel] Starting import with targetStepId:", targetStepId);
      const result = await importOpportunitiesXlsx(file, directoryId, targetStepId || undefined);
      console.log("[ImportExcel] Import result:", result);
      setImportResult(result);
      setStep("success");
      // Refresh board
      console.log("[ImportExcel] Invalidating query for directory-items:", directoryId);
      await queryClient.invalidateQueries({ queryKey: ["directory-items", directoryId] });
      console.log("[ImportExcel] Query invalidated");
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : "Error desconocido";
      console.error("[ImportExcel] Error:", errorMsg);
      alert(`Error: ${errorMsg}`);
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setStep("upload");
    setFile(null);
    setPreviewRows([]);
    setImportResult(null);
    setTargetStepId("");
    if (fileInputRef.current) fileInputRef.current.value = "";
    onClose();
  };

  if (!isOpen) return null;

  const validRows = previewRows.filter((r) => r.valid);
  const invalidRows = previewRows.filter((r) => !r.valid);

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: "rgba(0,0,0,0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
        padding: 20,
      }}
    >
      <div
        style={{
          background: "var(--c-card-bg)",
          borderRadius: 12,
          boxShadow: "0 20px 25px -5px rgba(0,0,0,0.1)",
          maxWidth: 700,
          width: "100%",
          maxHeight: "90vh",
          overflow: "auto",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: "20px",
            borderBottom: "1px solid #E2E8F0",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "#0F172A" }}>
            Importar Oportunidades
          </h2>
          <button
            type="button"
            onClick={handleClose}
            disabled={loading}
            style={{
              border: "none",
              background: "transparent",
              color: "#94A3B8",
              cursor: loading ? "not-allowed" : "pointer",
              fontSize: 20,
              padding: 0,
              width: 24,
              height: 24,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            ×
          </button>
        </div>

        {/* Content */}
        <div style={{ padding: "20px", flex: 1, display: "flex", flexDirection: "column", gap: 16 }}>
          {step === "upload" && (
            <>
              <div>
                <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 8 }}>
                  Archivo Excel *
                </label>
                <div
                  style={{
                    position: "relative",
                    border: "2px dashed #E2E8F0",
                    borderRadius: 8,
                    padding: 20,
                    textAlign: "center",
                    background: "#FAFAFA",
                    cursor: loading ? "not-allowed" : "pointer",
                  }}
                  onClick={() => !loading && fileInputRef.current?.click()}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".xlsx,.xls"
                    onChange={handleFileSelect}
                    disabled={loading}
                    style={{ display: "none" }}
                  />
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
                    <Upload size={24} style={{ color: "#94A3B8" }} />
                    <div>
                      <p style={{ margin: "0 0 4px", fontSize: 13, fontWeight: 600, color: "#0F172A" }}>
                        {file ? file.name : "Haz clic o arrastra un archivo"}
                      </p>
                      <p style={{ margin: 0, fontSize: 12, color: "#64748B" }}>Formato: .xlsx</p>
                    </div>
                  </div>
                </div>
              </div>
              <p style={{ margin: 0, fontSize: 12, color: "#64748B", lineHeight: 1.5 }}>
                Esperadas: Nombre, Especialidad, Ciudad, Teléfono, Correo, Respondió, Status, Comentarios.
              </p>
            </>
          )}

          {step === "preview" && (
            <>
              <div style={{ background: "var(--color-surface-alt)", border: "1px solid #E2E8F0", borderRadius: 8, padding: 12 }}>
                <p style={{ margin: "0 0 8px", fontSize: 12, fontWeight: 600, color: "#374151" }}>
                  Resumen de importación
                </p>
                <div style={{ display: "flex", gap: 16, fontSize: 13 }}>
                  <div>
                    <span style={{ color: "#64748B", fontWeight: 500 }}>Filas válidas:</span>
                    <span style={{ color: "#10B981", fontWeight: 600, marginLeft: 6 }}>{validRows.length}</span>
                  </div>
                  {invalidRows.length > 0 && (
                    <div>
                      <span style={{ color: "#64748B", fontWeight: 500 }}>Filas con error:</span>
                      <span style={{ color: "#EF4444", fontWeight: 600, marginLeft: 6 }}>{invalidRows.length}</span>
                    </div>
                  )}
                </div>
              </div>

              <div>
                <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 8 }}>
                  Mover a estado *
                </label>
                <select
                  value={targetStepId}
                  onChange={(e) => setTargetStepId(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "8px 12px",
                    border: "1px solid #E2E8F0",
                    borderRadius: 8,
                    fontSize: 13,
                    color: "#374151",
                    background: "var(--c-card-bg)",
                    outline: "none",
                  }}
                >
                  <option value="">Selecciona un estado...</option>
                  {steps.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </div>

              {invalidRows.length > 0 && (
                <div style={{ background: "#FEF2F2", border: "1px solid #FECACA", borderRadius: 8, padding: 12 }}>
                  <p style={{ margin: "0 0 8px", fontSize: 12, fontWeight: 600, color: "#DC2626" }}>
                    Errores encontrados:
                  </p>
                  <ul style={{ margin: 0, padding: "0 0 0 20px", fontSize: 12, color: "#64748B", lineHeight: 1.6 }}>
                    {invalidRows.slice(0, 3).map((row, idx) => (
                      <li key={idx}>
                        Fila {row.row}: {row.error}
                      </li>
                    ))}
                    {invalidRows.length > 3 && <li>+ {invalidRows.length - 3} más</li>}
                  </ul>
                </div>
              )}

              <div style={{ maxHeight: 300, overflow: "auto", border: "1px solid #E2E8F0", borderRadius: 8 }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                  <thead style={{ background: "var(--color-surface-alt)", position: "sticky", top: 0 }}>
                    <tr>
                      <th style={{ padding: "8px", textAlign: "left", fontWeight: 600, color: "#374151", borderBottom: "1px solid #E2E8F0" }}>Nombre</th>
                      <th style={{ padding: "8px", textAlign: "left", fontWeight: 600, color: "#374151", borderBottom: "1px solid #E2E8F0" }}>Especialidad</th>
                      <th style={{ padding: "8px", textAlign: "left", fontWeight: 600, color: "#374151", borderBottom: "1px solid #E2E8F0" }}>Ciudad</th>
                      <th style={{ padding: "8px", textAlign: "left", fontWeight: 600, color: "#374151", borderBottom: "1px solid #E2E8F0" }}>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {validRows.slice(0, 10).map((row, idx) => (
                      <tr key={idx} style={{ borderBottom: "1px solid #E2E8F0" }}>
                        <td style={{ padding: "8px", color: row.valid ? "#0F172A" : "#EF4444" }}>{row.title}</td>
                        <td style={{ padding: "8px", color: "#64748B" }}>{row.specialty || "—"}</td>
                        <td style={{ padding: "8px", color: "#64748B" }}>{row.city || "—"}</td>
                        <td style={{ padding: "8px", fontSize: 11, color: "#64748B" }}>{row.stage_label || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {validRows.length > 10 && (
                  <div style={{ padding: "8px", textAlign: "center", fontSize: 11, color: "#64748B", borderTop: "1px solid #E2E8F0" }}>
                    + {validRows.length - 10} más filas
                  </div>
                )}
              </div>
            </>
          )}

          {step === "success" && importResult && (
            <>
              {importResult.created > 0 || importResult.skipped === 0 ? (
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12, padding: "20px 0" }}>
                  <div style={{ width: 48, height: 48, borderRadius: "50%", background: "#F0FDF4", display: "flex", alignItems: "center", justifyContent: "center" }}>
                    <CheckCircle size={28} color="#10B981" />
                  </div>
                  <div style={{ textAlign: "center" }}>
                    <p style={{ margin: "0 0 4px", fontSize: 15, fontWeight: 600, color: "#0F172A" }}>
                      Importación completada
                    </p>
                    <p style={{ margin: 0, fontSize: 13, color: "#64748B" }}>
                      {importResult.created} {importResult.created === 1 ? "oportunidad" : "oportunidades"} creada{importResult.created === 1 ? "" : "s"}
                      {importResult.skipped > 0 ? `, ${importResult.skipped} omitida${importResult.skipped === 1 ? "" : "s"}` : ""}
                    </p>
                  </div>
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12, padding: "20px 0" }}>
                  <div style={{ width: 48, height: 48, borderRadius: "50%", background: "#FEF2F2", display: "flex", alignItems: "center", justifyContent: "center" }}>
                    <AlertCircle size={28} color="#DC2626" />
                  </div>
                  <div style={{ textAlign: "center" }}>
                    <p style={{ margin: "0 0 4px", fontSize: 15, fontWeight: 600, color: "#0F172A" }}>
                      No se crearon oportunidades
                    </p>
                    <p style={{ margin: 0, fontSize: 13, color: "#64748B" }}>Verifica el formato del archivo</p>
                  </div>
                </div>
              )}

              {importResult.errors.length > 0 && (
                <div style={{ background: "#FEF2F2", border: "1px solid #FECACA", borderRadius: 8, padding: 12 }}>
                  <p style={{ margin: "0 0 8px", fontSize: 12, fontWeight: 600, color: "#DC2626" }}>
                    Filas con error ({importResult.errors.length}):
                  </p>
                  <ul style={{ margin: 0, padding: "0 0 0 20px", fontSize: 12, color: "#64748B", lineHeight: 1.6 }}>
                    {importResult.errors.slice(0, 5).map((err, idx) => (
                      <li key={idx}>
                        Fila {err.row}: {err.reason}
                      </li>
                    ))}
                    {importResult.errors.length > 5 && <li>+ {importResult.errors.length - 5} más</li>}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            padding: "16px 20px",
            borderTop: "1px solid #E2E8F0",
            display: "flex",
            alignItems: "center",
            justifyContent: "flex-end",
            gap: 8,
          }}
        >
          {step === "success" ? (
            <button
              type="button"
              onClick={handleClose}
              style={{
                padding: "8px 16px",
                background: "#2563EB",
                color: "white",
                border: "none",
                borderRadius: 8,
                fontSize: 13,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Cerrar
            </button>
          ) : (
            <>
              <button
                type="button"
                onClick={handleClose}
                disabled={loading}
                style={{
                  padding: "8px 16px",
                  background: "transparent",
                  color: "#64748B",
                  border: "1px solid #E2E8F0",
                  borderRadius: 8,
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: loading ? "not-allowed" : "pointer",
                }}
              >
                Cancelar
              </button>
              {step === "upload" && (
                <button
                  type="button"
                  onClick={handlePreview}
                  disabled={!file || loading}
                  style={{
                    padding: "8px 16px",
                    background: !file ? "#CBD5E1" : "#2563EB",
                    color: "white",
                    border: "none",
                    borderRadius: 8,
                    fontSize: 13,
                    fontWeight: 600,
                    cursor: !file || loading ? "not-allowed" : "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                >
                  {loading && <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} />}
                  Ver preview
                </button>
              )}
              {step === "preview" && (
                <button
                  type="button"
                  onClick={handleConfirmImport}
                  disabled={validRows.length === 0 || !targetStepId || loading}
                  style={{
                    padding: "8px 16px",
                    background: validRows.length === 0 || !targetStepId ? "#CBD5E1" : "#10B981",
                    color: "white",
                    border: "none",
                    borderRadius: 8,
                    fontSize: 13,
                    fontWeight: 600,
                    cursor: validRows.length === 0 || !targetStepId || loading ? "not-allowed" : "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                  title={!targetStepId ? "Selecciona un estado" : ""}
                >
                  {loading && <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} />}
                  Importar {validRows.length} {validRows.length === 1 ? "oportunidad" : "oportunidades"}
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
