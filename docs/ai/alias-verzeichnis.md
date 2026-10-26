# Alias-Verzeichnis: Papier, Autor und digitales Altschema

Stand: 2026-08-20

Dieselben Felder tragen in drei Namensräumen verschiedene Namen, und die
Symbole unterscheiden sich zwischen digitaler und handgezeichneter Form. Diese
Datei hält die Zuordnung fest. Sie ist ein Nachschlagewerk, kein Zielschema; die
Papierstruktur steht in der [`Papierlegende`](papierlegende.md), das aktuelle
Modell im [`Datenmodell`](data-model.md).

Die Spalte „digital" bezeichnet ein **abgelöstes** Obsidian-Schema derselben
Routine, aus dem die heutige Papierform entstanden ist. Es wird nicht mehr
gepflegt und dient nur noch als Quelle für Symbol- und Namenszuordnungen.
Privates Vokabular wird ausschließlich lokal konfiguriert; siehe [`README`](../../README.md#daily-use).

Statusangaben:

- **bestätigt** — vom Autor ausdrücklich bestätigt,
- **abgeleitet** — aus paarweise vorliegenden Daten des Altschemas rekonstruiert,
- **offen** — ungeklärt, nicht zum Raten verwenden.

## Tagesscores der Kopfzeile

Maßgeblich ist die **Position**, nicht Name oder Symbol. Wo Papier- und
Digitalsymbol auseinandergehen, ist ausschließlich die Papierform relevant.

| # | Bedeutung | Autor | digitaler Key | digitales Symbol | Papierform | Status |
| ---: | --- | --- | --- | :---: | --- | --- |
| 1 | Ausblick | Ausblick | `outlook` | 🔮 Wahrsagekugel | **stilisiertes Stundenglas** | bestätigt, weicht ab |
| 2 | Schlafqualität | Schlaf | `sleep` | 💤 | `Zzz` (Schriftzug) | bestätigt |
| 3 | Engagement | **Ehrenamt** | `commitment` | ⛑️ Helm mit weißem Kreuz | **unausgefülltes Plus, nur Konturen** | bestätigt, weicht ab |
| 4 | Sozial | | `social` | ♥️ | Herz | bestätigt |
| 5 | Weiterbildung | | `learning` | 📚 | aufgeschlagenes Buch (zwei Bögen) | bestätigt, weicht ab |
| 6 | Sport | | `sports` | 👟 | Sportschuh | bestätigt |
| 7 | Gesundheit | | `health` | 🍎 | Apfel (Kreis mit Stiel) | bestätigt |
| 8 | Todo | | `todo` | ⏱️ | Stoppuhr | bestätigt |
| 9 | Arbeit | | `work` | 💼 | Koffer / Tasche mit Henkel | bestätigt |
| 10 | Brokeness | | `brokeness` | ⚠️ | Dach / Winkel (`^`) | bestätigt, weicht ab |
| 11 | Disziplin und Effizienz | | `discipline` | ⚙️ | zwei verbundene Zahnräder | bestätigt, weicht ab |
| 12 | Planung und Organisation | | `organisation` | 💭 | Gedankenblase | bestätigt |
| 13 | Impact und Impression | | `impact` | 💣 | Bombe mit Zündschnur | bestätigt |
| 14 | Energie | | `energy` | ⚡ | Blitz | bestätigt |
| 15 | Spaß und Freude | | `fun` | 🎉 | Partytröte mit Konfetti | bestätigt |
| 16 | Habittrackerzahl | | `routine` | 🔁 | Kreispfeil / Zählersymbol | bestätigt |
| 17 | Gesamtgefühl | | `feeling` | 🙂 | Smiley | bestätigt |

Die Zuordnung aller 17 Symbole ist nun vollständig anhand der echten Papierzeichnungen bestätigt.

**Fünf von 17 Symbolen weichen bestätigt vom Altschema-Emoji ab** (Ausblick, Ehrenamt, Weiterbildung, Brokeness, Disziplin). Die Emojis sind deshalb für einen
Prompt nur ein grober Hinweis und niemals ein Erkennungsmerkmal.

## Formularfelder der linken Seite

| Papierlabel | digitaler Key | Status |
| --- | --- | --- |
| Datum (ohne Label) | `dateAdded` | abgeleitet |
| Tagesmotto (ohne Label) | `qotd` | bestätigt |
| `VvV:` | `makeItBetter` | abgeleitet |
| `Lernziel:` | `learningGoal` | abgeleitet |
| `Eat the Frog:` | `eatTheFrog` | abgeleitet |
| `Tagesfreude:` | `lookingForward` | bestätigt |
| `LFT:` | — | nur auf Papier |
| `SelbstV:` | `methodGoal` | bestätigt |
| `SG:` | `socialGoal` | abgeleitet |
| `Neu:` | `newExperience` | abgeleitet |
| `Mot:` | `motivation` | abgeleitet |
| `TIL:` | `todayILearned` | abgeleitet |
| `BT:` | `bestThing` | abgeleitet |
| `+:` | `special` | abgeleitet |
| `TR:` | `timeRecap` | abgeleitet |
| `Prios:` | — | nur auf Papier |
| `Fun:` | — | nur auf Papier |
| `Stören:`, `Schön:`, `dankbar:` | — | nur auf Papier |
| `ToDos:` | — | nur auf Papier |
| Tageserlebnis (ohne Label) | Abschnitt `# Tagesablauf` | abgeleitet |
| `Pro:` | Abschnitt `## Pro` | bestätigt |
| `Cons:` bzw. `Contra:` | Abschnitt `## Contra` | bestätigt |

### Entfallene und nur auf Papier bestehende Felder

- `smallReward` beziehungsweise „Belohnung" ist **entfallen**. Es existiert nur
  im Altschema und hat auf Papier keine Entsprechung mehr.
- `LFT:` hat keine Entsprechung im Altschema. `lookingForward` gehört zu
  `Tagesfreude:`, obwohl beide Papierfelder inhaltlich nahe beieinanderliegen.
- Die Zuordnung der Formularfelder und die Papierformen der 17 Scoresymbole
  sind vollständig geklärt.

## Nicht Teil des Daily-Flows

Zentrale Habit- und Erlebnistracker gehören nicht zum unterstützten Daily-Flow.
Ihre persönlichen Definitionen sind nicht Teil dieser öffentlichen Dokumentation
und dürfen nicht aus den Tagesscores abgeleitet werden.
