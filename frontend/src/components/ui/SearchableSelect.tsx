import { useState, useRef, useEffect } from "react";
import { ChevronDown } from "lucide-react";

interface SearchableSelectProps {
  value: string;
  onChange: (value: string) => void;
  options: Array<{ id: string; name: string }>;
  placeholder?: string;
  label?: string;
  required?: boolean;
  ariaLabel?: string;
}

export function SearchableSelect({
  value,
  onChange,
  options,
  placeholder = "Buscar...",
  label,
  required,
  ariaLabel,
}: SearchableSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtered = options.filter((opt) =>
    opt.name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const selectedOption = options.find((opt) => opt.id === value);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [isOpen]);

  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

  return (
    <div ref={containerRef} className="searchable-select-wrapper">
      {label && <label className="searchable-select-label">{label}</label>}
      <div className="searchable-select-container">
        <button
          type="button"
          className="searchable-select-button"
          onClick={() => setIsOpen(!isOpen)}
          aria-label={ariaLabel}
          aria-expanded={isOpen}
        >
          <span className={selectedOption ? "" : "placeholder"}>
            {selectedOption?.name || "— Elige un directorio —"}
          </span>
          <ChevronDown size={16} className={`chevron ${isOpen ? "open" : ""}`} aria-hidden />
        </button>

        {isOpen && (
          <div className="searchable-select-menu">
            <input
              ref={inputRef}
              type="text"
              className="searchable-select-input"
              placeholder={placeholder}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  setIsOpen(false);
                }
              }}
            />
            <ul className="searchable-select-list">
              {filtered.length > 0 ? (
                filtered.map((opt) => (
                  <li key={opt.id}>
                    <button
                      type="button"
                      className={`searchable-select-item ${value === opt.id ? "selected" : ""}`}
                      onClick={() => {
                        onChange(opt.id);
                        setIsOpen(false);
                        setSearchTerm("");
                      }}
                    >
                      {opt.name}
                    </button>
                  </li>
                ))
              ) : (
                <li className="searchable-select-empty">No hay directorios que coincidan</li>
              )}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
