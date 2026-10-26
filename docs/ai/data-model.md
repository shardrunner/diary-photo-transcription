# Datenmodell

Gemini liefert eine fotozentrierte Beobachtung. Lokaler Code ergänzt Provenienz,
gruppiert sicher datierte Einträge und rendert die Ausgabe.

Die Tagesdoppelseite besteht aus drei Beobachtungsklassen mit unterschiedlichen
Fehlermodi. Schemaversion 2 trennt sie; Version 1 hatte alles auf `paragraphs`
und frei beschriftete `marks` abgebildet. Die Papierstruktur steht in der
[`Papierlegende`](papierlegende.md).

Modellantworten müssen Schemaversion 2 verwenden; andere Versionen werden abgelehnt.
Neue Requests beziehen Schema- und Promptversion aus der implementierten Version,
nicht aus überschreibbaren Konfigurationswerten. Historische Provenienz bleibt erhalten.

| Klasse | Quelle | Feld |
| --- | --- | --- |
| Formularfelder | linke Seite | `fields`, `absentLabels` |
| Tagesscores | Kopfzeile rechts | `scores` |
| Fließtext | rechte Seite, Fortsetzung links | `paragraphs` |

## Modellantwort

```json
{
  "schemaVersion": 2,
  "photoOverview": {
    "tags": ["sparse_page", "morning_routine_skipped"],
    "note": "Knappe sichtbare Beobachtung."
  },
  "layout": {
    "followsExpectedLayout": false,
    "deviationNote": "Der Text wird links fortgesetzt."
  },
  "entries": [
    {
      "date": "2040-01-02",
      "dateCertainty": "certain",
      "fields": [
        {
          "label": "Prios",
          "rawLabelText": "Prios:",
          "items": [
            {"text": "Erster Punkt", "completion": "fulfilled", "struckThrough": false},
            {"text": "Zweiter Punkt", "completion": "unmarked", "struckThrough": false}
          ]
        }
      ],
      "absentLabels": ["VvV", "Lernziel", "…"],
      "scores": [
        {"position": 1, "symbolDescription": "Stundenglas", "state": "struck_through"},
        {"position": 3, "symbolDescription": "Konturen-Plus", "state": "written",
         "rawValue": "4", "value": 4},
        {"position": 16, "symbolDescription": "Kreispfeil", "state": "written",
         "rawValue": "9/10", "value": 9}
      ],
      "paragraphs": [
        "Erster synthetischer Absatz.",
        "Zweiter Absatz mit ⟦unsicher: Beispiel⟧."
      ],
      "crossedOutCorrectionsOmitted": false,
      "visualNotes": []
    }
  ],
  "visualNotes": []
}
```

## Formularfelder

`label` stammt aus einer geschlossenen Liste von 24 Papierlabels. `rawLabelText`
enthält den wörtlich geschriebenen Labeltext und fängt Schreibvarianten wie
`Cons:` gegenüber `Contra:` auf; bei den drei unbeschrifteten Bestandteilen
Datum, Tagesmotto und Tageserlebnis fehlt er.

`fields` und `absentLabels` müssen zusammen **jedes** Label genau einmal
abdecken. Das ist der Grund für die scheinbar redundante Absent-Liste: Ohne sie
lässt sich „Feld war nicht auf der Seite" nicht von „Modell hat es übersehen"
unterscheiden, und Vollständigkeit wäre lokal nicht nachrechenbar.

`completion` gehört an den einzelnen Listenpunkt, nicht an das Feld. `unmarked`
bedeutet **nicht bewertet** und darf nie als Misserfolg gelesen werden.
Ein sichtbares leeres Feld hat `items=[]`, nicht `absentLabels`. Es bleibt im
Markdown ausdrücklich sichtbar; eine leere Summary-Property ist `""`, nicht `null`.

## Tagesscores

Auf dem Papier stehen nur handgezeichnete Symbole; ihre Bedeutung existiert
ausschließlich in der Legende. Das Modell meldet deshalb `position`,
`symbolDescription` und den Wert, aber **keine Bedeutung** — die Zuordnung
Position zu Bedeutung übernimmt lokaler Code.

`state` trennt „Wert vorhanden" von „durchgestrichen", „leer" und „unlesbar".
Dieser Zustand ist die zentrale Anforderung: Fehlt er, füllt das Modell Lücken
auf, indem es nachfolgende Werte vorzieht, und verschiebt damit die gesamte
Zeile. Ein solcher Fall ist real aufgetreten und in [`API-PoC`](api-poc.md)
dokumentiert.

Prompt v10: Ist die Zeile sichtbar, müssen alle 17 Positionen gemeldet werden.
Sind nur einzelne Symbole gezeichnet (z.B. nur Kreispfeil und Smiley), gilt die
Zeile als vorhanden; nicht gezeichnete Positionen sind `empty`. Fehlt sie
vollständig, gilt `scores=[]` mit Layout-Abweichungsnotiz. Keine 17 leeren
Positionen erfinden.
Werte liegen zwischen 0 und 6; einzige Ausnahme ist Position 16, ein Zähler in
Bruchschreibweise. Dezimalwerte kommen nie vor.

## Text und Einträge

`paragraphs` enthält ausschließlich den Fließtext in logischer Lesereihenfolge.
Schreibweise, Grammatik, Interpunktion und Absatzgrenzen bleiben erhalten. Läuft
der Text in freie Bereiche der linken Seite, gehört die Fortsetzung dazu.

Unsicherheit wird als `⟦unleserlich⟧` oder `⟦unsicher: LESART⟧` markiert.
Streichungen haben drei Bedeutungen und werden nur im Korrekturfall ausgelassen;
Details in der Papierlegende. Auch Marker in Rohlabels, Symbolbeschreibungen und
visuellen Notizen werden für Review berücksichtigt.

Ein Foto kann keinen, einen oder mehrere datierte Einträge enthalten. Ohne
sichtbaren Eintrag bleibt `entries` leer. Ein Eintrag ohne Felder, Scores und
Absätze ist kein gültiger Erfolg.

Nur sicher datierte Einträge werden nach Kalendertag gruppiert. Ein fehlendes
Datum ist die einzige meldepflichtige Auslassung der linken Seite; solche
Einträge erscheinen in `review.json`, aber in keiner Tagesdatei. Ein gesetztes
Datum ohne nichtleeres Standard-Datumfeld erhält zusätzlich `unsupported_date`;
es bleibt exportierbar, da das Datum andernorts sichtbar sein kann. Der Review
prüft diese Evidenz, statt valide freie Datumsangaben pauschal abzulehnen.

## Provenienz und Ausgabe

Lokaler Code speichert in `run.json` Fotopfad, SHA-256, Modell-, SDK-, Prompt- und
Schemaversion sowie Tokenverbrauch. Die rohe Modellantwort (`raw.json`) bleibt neben
den abgeleiteten Dateien erhalten und ist eine Modellbeobachtung, keine verifizierte
Ground Truth.

### Trennung: Maschinendaten (`raw.json`) vs. Obsidian-Tagesnotiz (`YYYY-MM-DD.md`)

- **`raw.json` (Maschinell)**: Enthält die vollständigen Rohdaten inklusive
  Symbolbeschreibungen (`symbolDescription`), Layoutabweichungen (`deviationNote`)
  und lückenloser Erfassung aller 24 Labels (`fields` und `absentLabels`).
- **`YYYY-MM-DD.md` (Mensch / Obsidian)**: Für die persönliche Nutzung und das Obsidian-Vault optimiert.
  - **Nichtautoritative YAML-Zusammenfassungen** für Bases/Dataview:
    `summaryAuthority: non-authoritative`. Unterschiedliche beobachtete Felditems
    (einschließlich Grenzen/Markierungen) oder Scorezustände/Rohwerte ergeben
    `null`; betroffene Properties stehen in `summaryConflicts`. Eine Zusammenfassung
    ersetzt weder einzelne Quellen noch `raw.json`.
  - **Quellen-/zustandsbewusster Body**: Mehrere Einträge bleiben in Reihenfolge
    als `Quelle 1`, `Quelle 2`, … getrennt. Formularlisten behalten Itemgrenzen,
    Completion und Streichungszustand; komplexe oder quellenspezifische Felder
    werden auch dann dargestellt, wenn eine Frontmatter-Zusammenfassung existiert.
    Nur ein einzelnes unmarkiertes, nicht gestrichenes Summary-Item ohne Rohlabel
    darf bei einem einzelnen Eintrag ausschließlich in der Property stehen.

### Frontmatter-Properties

```yaml
---
date: '2040-01-02' # fictional example
tags: daily
type: daily
meta_type: note
meta_project: tagebuch
meta_source: gemini-3.8-flash
meta_generator: ai
schemaVersion: 2
sources:
  - photoPath: private/source/<foto>.jpg
    photoSha256: <hash>
    model: gemini-3.8-flash
    sdkVersion: 2.18.1
    promptVersion: 9
    schemaVersion: 2
summaryAuthority: non-authoritative
summaryConflicts: []
qotd: null
makeItBetter: ⟦unleserlich⟧
learningGoal: null
eatTheFrog: null
lookingForward: null
methodGoal: null
socialGoal: null
newExperience: null
motivation: null
todayILearned: Synthetisches Lernbeispiel
bestThing: Ein Papiermodell gebaut.
special: Beispiel mit ⟦unleserlich⟧
timeRecap: null
outlook: null
sleep: 4
commitment: 0
social: 6
learning: 1
sports: 1
health: 2
todo: 4
work: 2
brokeness: 4
discipline: 2
organisation: 1
impact: 4
energy: 4
fun: 3
routine: 9
feeling: 4
---
```

### Struktur des Markdown-Bodys

Der Aufbau orientiert sich an der visuellen Struktur des Papiertagebuchs und der Obsidian-Vorlage:

1. **`# Stats`**: Pro Eintrag eine 17-Spalten-Emoji-Tabelle mit `rawValue`
   (etwa `9/10`, nicht nur `9`), `❔` für `struck_through`,
   `⟦unleserlich⟧` für `illegible` und Freiraum für `empty`.
   Ohne Scorezeile entfällt die Tabelle. Frontmatter enthält nur konfliktfreie
   numerische Werte im Zustand `written`, sonst `null`.
2. **`# Tagesablauf`**: Aus `Tageserlebnis` als nummerierte Liste (`1. ...`, `2. ...`).
3. **`# Plan`**: Prioritäten (`Prios:`) und Aufgaben (`ToDos:`) als Checklisten.
   Items tragen zusätzlich den wörtlichen Completion-Zustand (`fulfilled`,
   `not_fulfilled`, `unmarked`) und gegebenenfalls `(durchgestrichen)`.
   Ein leeres Kästchen allein bedeutet deshalb nicht Misserfolg. Diese expliziten
   Zustände gelten auch für Tagesablauf, Formular- und sonstige Feldlisten.
4. **`# Gedanken`**:
   - `## Pro` / `## Contra`: Listen aus den Gegenüberstellungsfeldern.
   - `## Beobachtungen`: Freie Felder wie `Stören:`, `Schön:`, `Dankbar:`, `LFT:`.
   - `## Erlebnis`: Quellentreuer handschriftlicher Fließtext (`paragraphs`).
5. **`## Besonderheiten`**: Sichtbare Randnotizen und Besonderheiten (`visual_notes`).

`# Formular` ergänzt insbesondere sichtbare Datumsfelder und Summary-Felder,
deren Grenzen/Markierungen/Rohlabels sonst verloren gingen. Absätze und
Unsicherheitsmarker bleiben erhalten; ausgelassene Korrekturen werden vermerkt.
Quelltext wird für literale Markdown-/HTML-/Obsidian-Darstellung escaped, damit
Kommentare, Wikilinks oder Mathematiknotation keine geschriebenen Wörter verbergen.
Mehrzeilige Items bleiben einzelne Items. JSON/YAML behalten den ursprünglichen Text.

### Runs, Revisionen und Auswahl

```text
private/output/
  <foto16>-<config16>[-rerun-<uuid>]/   # veröffentlichter Run
    interaction.json   # vollständige Providerantwort, vor Validierung gespeichert
    raw.json  run.json  prompt.txt  review.json  YYYY-MM-DD.md
    revisions/<uuid>/  # Refinement, gleiche Dateien + parentRawSha256 in run.json
    decisions.json     # {"active": <uuid>|null, "decisions": {<uuid>: approved|rejected}}
  .staging-<uuid>/     # im Aufbau, wird nie gelesen
  .failed-<uuid>/      # abgelehnte Antwort samt Evidenz, wird nie gelesen
  selections.json      # {"YYYY-MM-DD": "<run>"} für Daten mit mehreren Runs
```

Ein Run entsteht in `.staging-*` und wird erst nach vollständigem Schreiben
umbenannt; ein sichtbarer Run ist damit immer vollständig. Scheitert Status-,
Usage- oder Schemaprüfung, wird das Staging zu `.failed-*` und ein neuer
Paid-Versuch bleibt möglich. Unbekannte sichtbare Verzeichnisse im Output sind
ein Fehler.

`review --refine` schreibt eine Revision, solange keine offene existiert; sie nutzt
Modell, Thinking-Level und Auflösung des Runs und das aktuelle lokale Vokabular.
`approve` aktiviert sie, sofern ihr Parent (`parentRawSha256`) noch aktiv ist;
`reject` protokolliert nur. Review, Eval, Auswahl und Export lesen immer die
aktive Revision. Eine Auswahl nennt nur den Run und folgt dessen aktiver Revision;
verschwindet das Datum dort, schlägt der Export fehl, bis die Auswahl mit
`select --clear` entfernt oder neu gesetzt wird.

`export` schreibt je Datum genau eine Notiz in den konfigurierten Vault-Ordner.
Mehrdeutige Daten ohne Auswahl brechen vor dem Schreiben ab; abweichende
Vault-Notizen werden ohne `--force` nicht überschrieben (Nonzero-Exit).
