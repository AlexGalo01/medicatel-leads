import { FormEvent, useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Globe, Instagram, Linkedin, Loader2, Search } from "lucide-react";

import { createSearchJob } from "../api";
import { defaultChannelsForFocus, getRotatedSuggestions } from "../data/searchSuggestions";
import type { SearchFocus } from "../types";

const CHANNEL_OPTIONS: { id: string; label: string }[] = [
  { id: "email", label: "Email" },
  { id: "whatsapp", label: "WhatsApp" },
  { id: "linkedin", label: "LinkedIn" },
];

export function SearchPage(): JSX.Element {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [notes, setNotes] = useState("");
  const [searchFocus, setSearchFocus] = useState<SearchFocus>("general");
  const [contactChannels, setContactChannels] = useState<string[]>(() => defaultChannelsForFocus("general"));

  const suggestionPool = useMemo(() => getRotatedSuggestions(searchFocus, 6), [searchFocus]);

  const createJobMutation = useMutation({
    mutationFn: createSearchJob,
    onSuccess: (data) => navigate(`/jobs/${data.job_id}`),
  });

  const onFocusChange = (next: SearchFocus): void => {
    setSearchFocus(next);
    setContactChannels(defaultChannelsForFocus(next));
  };

  const toggleChannel = (channelId: string): void => {
    setContactChannels((prev) => {
      if (prev.includes(channelId)) {
        const next = prev.filter((c) => c !== channelId);
        return next.length > 0 ? next : prev;
      }
      return [...prev, channelId];
    });
  };

  const onSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    createJobMutation.mutate({
      query: query.trim(),
      notes: notes.trim() || undefined,
      contact_channels: contactChannels,
      search_focus: searchFocus,
    });
  };

  return (
    <section className="search-hero">
      <div className="search-hero-card">
        <div className="hero-title-block">
          <h2 className="search-hero-title">Encuentra leads médicos de alta calidad</h2>
          <p className="muted-text search-hero-subtitle">
            Describe tu búsqueda o elige una sugerencia. Priorizamos contacto verificable según los canales que marques.
          </p>
        </div>

        <div className="search-focus-bar" role="group" aria-label="Enfoque de búsqueda">
          <button
            type="button"
            className={`search-focus-option${searchFocus === "linkedin" ? " is-active" : ""}`}
            onClick={() => onFocusChange("linkedin")}
          >
            <Linkedin className="search-focus-icon" aria-hidden />
            <span>LinkedIn</span>
          </button>
          <button
            type="button"
            className={`search-focus-option${searchFocus === "instagram" ? " is-active" : ""}`}
            onClick={() => onFocusChange("instagram")}
          >
            <Instagram className="search-focus-icon" aria-hidden />
            <span>Instagram</span>
          </button>
          <button
            type="button"
            className={`search-focus-option${searchFocus === "general" ? " is-active" : ""}`}
            onClick={() => onFocusChange("general")}
          >
            <Globe className="search-focus-icon" aria-hidden />
            <span>General</span>
          </button>
        </div>

        <form className="search-form-main" onSubmit={onSubmit}>
          <div className="search-input-row">
            <input
              className="search-input-large"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Ej.: ginecólogos en San Pedro Sula con consultorio y contacto directo"
              required
              minLength={3}
              maxLength={500}
              aria-label="Consulta de búsqueda"
            />
            <button className="search-submit-btn" type="submit" disabled={createJobMutation.isPending}>
              {createJobMutation.isPending ? (
                <>
                  <Loader2 className="search-submit-icon spin" aria-hidden />
                  <span>Buscando…</span>
                </>
              ) : (
                <>
                  <Search className="search-submit-icon" aria-hidden />
                  <span>Buscar</span>
                </>
              )}
            </button>
          </div>

          <fieldset className="search-channel-fieldset">
            <legend className="search-channel-legend">Canales de contacto</legend>
            <div className="search-channel-pills">
              {CHANNEL_OPTIONS.map((ch) => (
                <label key={ch.id} className="search-channel-label">
                  <input
                    type="checkbox"
                    checked={contactChannels.includes(ch.id)}
                    onChange={() => toggleChannel(ch.id)}
                  />
                  <span>{ch.label}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <div className="search-suggestions-block">
            <p className="search-suggestions-heading">Sugerencias para hoy</p>
            <div className="search-suggestion-chips">
              {suggestionPool.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className="search-suggestion-chip"
                  onClick={() => setQuery(item.fullPrompt)}
                >
                  {item.category ? <span className="search-suggestion-cat">{item.category}</span> : null}
                  <span className="search-suggestion-label">{item.shortLabel}</span>
                </button>
              ))}
            </div>
          </div>

          <label className="notes-label search-notes">
            Contexto opcional
            <textarea
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="Exclusiones (listados tipo Excel), tono, zona geográfica extra o criterios de calidad"
              maxLength={500}
            />
          </label>

          {createJobMutation.isError ? (
            <p className="error-text">No se pudo crear el job. Revisa que el backend esté activo.</p>
          ) : null}
        </form>
      </div>
    </section>
  );
}
