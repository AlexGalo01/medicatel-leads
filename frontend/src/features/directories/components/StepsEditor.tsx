import { GripVertical, Plus, Trash2, Circle, CheckCircle2, XCircle } from "lucide-react";
import {
  DndContext,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import { SortableContext, useSortable, verticalListSortingStrategy, arrayMove } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

export interface EditableStep {
  /** id local (uuid para nuevos, id real para existentes) */
  key: string;
  /** id real del backend si el step ya existe */
  id?: string;
  name: string;
  is_terminal: boolean;
  is_won: boolean;
}

type StepKind = "progress" | "won" | "lost";

function kindOf(step: EditableStep): StepKind {
  if (!step.is_terminal) return "progress";
  return step.is_won ? "won" : "lost";
}

function applyKind(step: EditableStep, kind: StepKind): Partial<EditableStep> {
  if (kind === "progress") return { is_terminal: false, is_won: false };
  if (kind === "won") return { is_terminal: true, is_won: true };
  return { is_terminal: true, is_won: false };
}

const KIND_OPTIONS: { value: StepKind; label: string }[] = [
  { value: "progress", label: "Paso" },
  { value: "won", label: "Ganado" },
  { value: "lost", label: "Perdido" },
];

interface StepsEditorProps {
  steps: EditableStep[];
  onChange: (steps: EditableStep[]) => void;
}

function KindIcon({ kind }: { kind: StepKind }): JSX.Element {
  if (kind === "won") return <CheckCircle2 size={14} aria-hidden className="steps-kind-icon steps-kind-icon--won" />;
  if (kind === "lost") return <XCircle size={14} aria-hidden className="steps-kind-icon steps-kind-icon--lost" />;
  return <Circle size={14} aria-hidden className="steps-kind-icon steps-kind-icon--progress" />;
}

function StepRow({
  index,
  step,
  onPatch,
  onRemove,
}: {
  index: number;
  step: EditableStep;
  onPatch: (patch: Partial<EditableStep>) => void;
  onRemove: () => void;
}): JSX.Element {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: step.key,
  });
  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };
  const kind = kindOf(step);
  return (
    <li ref={setNodeRef} style={style} className={`steps-editor-row steps-editor-row--${kind}`}>
      <button
        type="button"
        className="steps-editor-handle"
        aria-label="Reordenar"
        {...attributes}
        {...listeners}
      >
        <GripVertical size={14} aria-hidden />
      </button>
      <span className="steps-editor-index">{index + 1}</span>
      <KindIcon kind={kind} />
      <input
        type="text"
        className="steps-editor-name-input"
        value={step.name}
        onChange={(e) => onPatch({ name: e.target.value })}
        placeholder="Nombre del paso"
        maxLength={120}
      />
      <select
        className="steps-editor-kind-select"
        value={kind}
        onChange={(e) => onPatch(applyKind(step, e.target.value as StepKind))}
        aria-label="Tipo de step"
      >
        {KIND_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      <button
        type="button"
        className="steps-editor-delete"
        onClick={onRemove}
        aria-label="Borrar step"
      >
        <Trash2 size={14} aria-hidden />
      </button>
    </li>
  );
}

export function StepsEditor({ steps, onChange }: StepsEditorProps): JSX.Element {
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));

  const addStep = () => {
    onChange([
      ...steps,
      {
        key: `new-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        name: "",
        is_terminal: false,
        is_won: false,
      },
    ]);
  };

  const patchStep = (idx: number, patch: Partial<EditableStep>) => {
    onChange(steps.map((s, i) => (i === idx ? { ...s, ...patch } : s)));
  };

  const removeStep = (idx: number) => {
    onChange(steps.filter((_, i) => i !== idx));
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const from = steps.findIndex((s) => s.key === active.id);
    const to = steps.findIndex((s) => s.key === over.id);
    if (from < 0 || to < 0) return;
    onChange(arrayMove(steps, from, to));
  };

  return (
    <div className="steps-editor">
      <div className="steps-editor-head">
        <div>
          <h3 className="steps-editor-title">Flow de pasos</h3>
          <p className="steps-editor-help muted-text">
            <strong>Paso</strong>: fase intermedia del proceso.{" "}
            <strong>Ganado</strong>: oportunidad cerrada con éxito.{" "}
            <strong>Perdido</strong>: oportunidad cerrada sin éxito.
            Arrastra para reordenar.
          </p>
        </div>
      </div>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={steps.map((s) => s.key)} strategy={verticalListSortingStrategy}>
          <ol className="steps-editor-list">
            {steps.map((s, idx) => (
              <StepRow
                key={s.key}
                index={idx}
                step={s}
                onPatch={(patch) => patchStep(idx, patch)}
                onRemove={() => removeStep(idx)}
              />
            ))}
          </ol>
        </SortableContext>
      </DndContext>
      <button type="button" className="steps-editor-add" onClick={addStep}>
        <Plus size={14} aria-hidden /> Agregar paso
      </button>
    </div>
  );
}
