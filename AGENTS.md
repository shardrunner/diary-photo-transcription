# AGENTS.md

Persönliche CLI: Tagebuchfotos → quellengetreue Transkription → Obsidian-Tagesnotizen.
Primär für den eigenen Gebrauch, sekundär ein öffentliches Portfolio-Projekt.
Ein Nutzer, lokale Dateien, keine parallelen Prozesse: einfach halten.

## Ablauf

```bash
uv run diary-photo-transcription batch                  # neue Fotos aus private/source (kostet)
uv run diary-photo-transcription review [--refine]      # Unsicherheiten; --refine kostet
uv run diary-photo-transcription approve|reject --run-dir private/output/<run> --revision <id>
uv run diary-photo-transcription select --date YYYY-MM-DD --run <run>   # nur bei Konkurrenz
uv run diary-photo-transcription export
```

Details: `README.md` (Nutzung, Datenschutz, Kosten), `docs/ai/data-model.md`
(Schema, Run-Layout), `docs/ai/papierlegende.md` (Papiervorlage).

## Regeln für Transkription und Prompt

- Quellentreue: Schreibweise, Grammatik, Interpunktion, Absätze und Reihenfolge unverändert.
- Unlesbares `⟦unleserlich⟧`, unsichere Lesarten `⟦unsicher: LESART⟧`; nie raten.
- Streichungen: ToDo = erledigt, Scorezeile = nicht erfasst, sonst Korrektur (auslassen).
- Datum von der Seite, nie aus dem Dateinamen.
- Menschliche Freigabe bleibt: Refinements nie automatisch übernehmen, keine automatische Auswahl.

## Kosten und Privates

- Jeder `batch`/`review --refine`-Request kostet (~0,055 USD pro Seite, meist
  Thinking). Bezahlte Requests nur gezielt und mit Nutzerzustimmung ausführen.
- `private/` und `.env` nie committen; keine Tagebuchinhalte in Code, Tests oder Doku.

## Entwicklung

```bash
uv run pytest -x && uv run ruff check . && uv run pyrefly check
```

Tests laufen offline (`FakeGemini` in `tests/conftest.py`). Nach Änderungen
relevante Tests ausführen und mit Conventional Commits committen.
