PROMPT_VERSION = 10

EXTRACTION_PROMPT = """Transkribiere ausschließlich den sichtbaren Inhalt dieses
Tagebuchfotos in die vorgegebene Struktur. Das Foto zeigt eine Doppelseite: links
ein handschriftliches Formular, rechts eine Symbolzeile mit Zahlenwerten und
darunter Fließtext.

Quellentreue:
- Übernimm Schreibweise, Grammatik, Interpunktion, Wortwahl und Absatzgrenzen unverändert.
- Rate nie. Verwende exakt ⟦unleserlich⟧ oder ⟦unsicher: LESART⟧.
- Erfinde nichts und fasse nichts zusammen (keine Phantom-Abkürzungen wie "d.h.").
- Beschreibe nur Sichtbares, ohne psychologische Deutung.

1. Formularfelder der linken Seite
Melde JEDES Label der 24 vorgegebenen Labels genau einmal: entweder als Eintrag in
fields (wenn vorhanden) oder als Wert in absentLabels (wenn nicht vorhanden).
Beide Listen sind Pflichtfelder und müssen zusammen die 24 Labels vollständig abdecken.
Eine ausgelassene Morgenroutine ist normal; dann fehlen viele Felder der linken Seite
(setze dann tag "morning_routine_skipped").

- rawLabelText: der Labeltext, wie er wörtlich auf dem Papier steht, samt
  Doppelpunkt (z.B. "VvV:", "Eat the Frog:", "Lernziel:", "Prios:", "Fun:", "Stören:",
  "Schön:", "dankbar:", "SelbstV:", "SG:", "LFT:", "Neu:", "Mot:", "TIL:", "BT:",
  "+:", "TR:", "Pro:", "Contra:"). Weicht die
  Schreibweise ab (z.B. "Contra:" statt "Cons"), schreibe die tatsächliche Form hierher
  und ordne sie dem passenden Standard-Label zu.
- Drei Bestandteile tragen KEIN geschriebenes Label und werden nur über ihre Lage
  erkannt. Lass rawLabelText dort weg (null):
  - "Datum": oberste Zeile, ganz links (im Format YYYY-MM-DD). Wenn auf dem
    Papier nur Tag und Monat notiert sind (z.B. "07.08." oder "7.7."), nimm
    das konfigurierte Korpusjahr an. Ohne Korpusjahr bleibt das Datum unbekannt.
  - "Tagesmotto": oberste Zeile, rechts vom Datum (z.B. "TH"). Fehlt sehr häufig.
  - "Tageserlebnis": horizontal zentrierter Block in der Seitenmitte mit Listenpunkten.
- items: ein Eintrag pro Listenpunkt bzw. ein einzelner Eintrag bei einzeiligen Feldern.
  Ein sichtbares, aber leeres Feld bleibt in fields mit items=[]; es ist NICHT absent.
- completion gehört an den EINZELNEN Listenpunkt, nicht an das Feld. Ein Haken
  hinter dem Text ist "fulfilled", ein Kreuz "not_fulfilled", keine Markierung
  "unmarked". Fehlende Markierung bedeutet NICHT "nicht geschafft".

2. Symbolzeile der rechten Seite (Tagesscores)
Wenn eine Scorezeile vorhanden ist, melde ALLE 17 Positionen in aufsteigender
Reihenfolge. Sind nur einzelne Symbole gezeichnet (z.B. nur Kreispfeil und Smiley
oben rechts), ist die Zeile vorhanden: melde ebenfalls alle 17 Positionen, nicht
gezeichnete als state="empty" (Deviation note im layout angeben). Fehlt die
Scorezeile komplett (z.B. bei reinem Fließtext), setze scores=[] (Deviation note
im layout angeben). Erfinde keine leeren Positionen.

- position ist die Stelle in der Zeile von links, genau 1 bis 17.
- ACHTUNG BEI DER VERTIKALEN AUSRICHTUNG:
  - Position 1 ist das Symbol ganz links (stilisiertes Stundenglas). Steht darunter
    ein Schrägstrich, Kreuz, Strich oder Punkt (z.B. "./." oder "/"), ist dies
    der Wert für Position 1: state="struck_through", rawValue=null, value=null.
    Die erste darauffolgende Zahl (z.B. 4) gehört bereits zu Position 2!
    Verschiebe NIEMALS Werte nach links, um nicht-erfasste Positionen aufzufüllen!
  - Position 17 ist das Symbol ganz rechts (Smiley). Direkt darunter steht ebenfalls
    ein Zahlenwert von 0 bis 6 (z.B. 4): trage ihn als state="written", rawValue="4",
    value=4 ein.
- symbolDescription beschreibt knapp das Symbol (inklusive Emoji als visueller Anker):
  1: stilisiertes Stundenglas ⏳
  2: Zzz (Schlaf) 💤
  3: unausgefülltes Plus nur in Konturen (+)
  4: Herz ♥️
  5: aufgeschlagenes Buch / zwei Bögen 📖
  6: Sportschuh 👟
  7: Apfel mit Stiel 🍎
  8: Stoppuhr ⏱️
  9: Koffer / Tasche mit Henkel 💼
  10: Dach / Winkel (^) 📐
  11: zwei verbundene Zahnräder ⚙️⚙️
  12: Gedankenblase 💭
  13: Bombe mit Zündschnur 💣
  14: Blitz ⚡
  15: Partytröte mit Konfetti 🎉
  16: Kreispfeil / Zählersymbol (Habittrackerzahl) 🔁
  17: Smiley (Gesamtbefinden) 🙂
- state sagt, warum eine Position einen Wert hat oder nicht:
  "written" mit Wert, "struck_through" bei durchgestrichenem/nicht-erfasstem Wert,
  "empty" wenn nichts dasteht, "illegible" wenn unlesbar.
- rawValue ist der Wert genau wie geschrieben, value als ganze Zahl.
- Der Wertebereich für Position 1-15 und 17 ist STRENG 0 bis 6. Werte wie 7, 8, 9 sind
  an diesen Positionen UNMÖGLICH (häufige Verwechslung: geschwungene handschriftliche 4,
  3 oder 0 nicht als 8 lesen!).
  Einzige Ausnahme für Werte > 6 ist Position 16 (Habittrackerzahl als ganze Zahl, z.B. 9 oder 11).
- Diese Zeile ist NICHT der zentrale Habittracker mit X-Matrix.

3. Fließtext, Namen und Symbole
Unter der Symbolzeile folgt freier Text in Absätzen. Läuft er in freien
Bereichen der linken Seite weiter, gehört diese Fortsetzung in derselben
Lesereihenfolge dazu (setze dann tag "overflow_to_left_page"). Gib ihn in paragraphs aus.

- Handgezeichnete Symbole im Text: Der Autor zeichnet gelegentlich Symbole wie ☀️ (Sonne,
  oft als Kreis mit seitlichen Strahlen wie -O-). Diese als Unicode-Emoji transkribieren.
  Keine Smileys erfinden, wenn nur Punkte/Gedankenstriche dastehen.

Streichungen:
- In der ToDo-Liste bedeutet eine Streichung ERLEDIGT: Text übernehmen, struckThrough=true.
- In der Symbolzeile bedeutet eine Streichung NICHT ERFASST: state="struck_through".
- Überall sonst ist eine Streichung eine Korrektur: auslassen, crossedOutCorrectionsOmitted=true.

Gib vor dem Abschluss das vollständig validierte JSON gemäß Schema aus.
"""


def refinement_prompt(targets: list[str], base_prompt: str) -> str:
    """Second-pass prompt: re-read flagged places, return the full observation again."""
    return (
        "Du bist ein Experte für deutsche Handschriften in Tagebüchern.\n"
        "In einem ersten Extraktionslauf dieses Fotos wurden folgende Stellen "
        "als unsicher/unleserlich markiert:\n"
        + "\n".join(f"- {target}" for target in targets)
        + "\n\nBitte untersuche die entsprechenden Stellen auf dem Foto "
        "mit höchster Aufmerksamkeit.\n"
        "Prüfe anhand der Schriftzüge, Buchstabenformen und des Kontexts, "
        "ob du diese Passagen sicher auflösen kannst.\n"
        "Gib die vollständige Transkription des Tages im vorgegebenen JSON-Schema zurück. "
        "Löse unsichere Stellen auf, wenn die Lesart nun klar ist "
        "(verwende ⟦unleserlich⟧ nur dann, wenn ein Wort physisch unlesbar ist).\n\n"
        "--- BASIS-EXTRAKTIONSREGELN ---\n" + base_prompt
    )
