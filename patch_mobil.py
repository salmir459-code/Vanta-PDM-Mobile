"""
patch_mobil.py — bindet mobil_sync.py in Vanta PDM ein.

Aufruf im Programmordner (dort, wo pdm_shell.py liegt):

    python patch_mobil.py

Was geändert wird:
  project_manager.py
    • load_data(): übernimmt beim Laden die Änderungen vom Handy
    • save_data(): übernimmt vor jedem Speichern die Änderungen vom Handy,
      damit der PC nie einen Stand ohne sie schreibt
  pdm_shell.py (Bereich Zeit)
    • schaut alle 15 Sekunden nach, ob am Handy etwas eingetragen wurde,
      und zeigt es sofort an

Jede Ersetzung prüft vorher, dass die Stelle genau einmal vorkommt. Passt
etwas nicht, bricht das Skript ab, BEVOR eine Datei geschrieben wird.
Von beiden Dateien wird vorher eine Kopie *.vor_mobil angelegt.
"""

import datetime
import os
import shutil
import sys

HIER = os.path.dirname(os.path.abspath(__file__))

AENDERUNGEN = {
    "project_manager.py": [
        (
            "import leistungen as LST\n",
            "import leistungen as LST\nimport mobil_sync as MS\n",
        ),
        (
            "        daten = {\"kunden\": []}\n    return daten\n",
            "        daten = {\"kunden\": []}\n"
            "    # Was am Handy eingetragen wurde (mobile_changes.json), gleich\n"
            "    # mit übernehmen. Nicht nach einem Datenschaden: dann könnte ein\n"
            "    # leerer Rückfall-Stand samt Handy-Änderungen gespeichert werden.\n"
            "    if not letzte_meldung:\n"
            "        try:\n"
            "            n, k, _ = MS.einarbeiten(daten, MS.pfad_neben(DATA_FILE))\n"
            "            if n or k:\n"
            "                save_data(daten)\n"
            "        except Exception as e:\n"
            "            print(f\"[project_manager] Handy-Änderungen: {e}\")\n"
            "    return daten\n",
        ),
        (
            "    ok, fehler = DS.schreiben(DATA_FILE, data, einzug=2)\n",
            "    # Vor dem Schreiben die Handy-Änderungen einarbeiten — `data` ist\n"
            "    # der Stand, den die Oberfläche im Speicher hält. So schreibt der\n"
            "    # PC nie eine Datei, in der ein am Handy erfasster Eintrag fehlt.\n"
            "    try:\n"
            "        MS.einarbeiten(data, MS.pfad_neben(DATA_FILE))\n"
            "    except Exception as e:\n"
            "        print(f\"[project_manager] Handy-Änderungen: {e}\")\n"
            "    ok, fehler = DS.schreiben(DATA_FILE, data, einzug=2)\n",
        ),
    ],
    "pdm_shell.py": [
        (
            "import project_manager as PM\n",
            "import project_manager as PM\nimport mobil_sync as MS\n",
        ),
        (
            "            QTimer.singleShot(0, self._datenschaden_melden)\n\n"
            "    def _datenschaden_melden(self):\n",
            "            QTimer.singleShot(0, self._datenschaden_melden)\n"
            "        # Am Handy Eingetragenes ohne Neustart anzeigen: alle 15 s\n"
            "        # nachsehen, ob mobile_changes.json neuer geworden ist.\n"
            "        self._mobil_stempel = MS.stempel(MS.pfad_neben(PM.DATA_FILE))\n"
            "        self._mobil_timer = QTimer(self)\n"
            "        self._mobil_timer.timeout.connect(self._mobil_pruefen)\n"
            "        self._mobil_timer.start(15000)\n\n"
            "    def _mobil_pruefen(self):\n"
            "        pfad = MS.pfad_neben(PM.DATA_FILE)\n"
            "        stempel = MS.stempel(pfad)\n"
            "        if stempel is None or stempel == self._mobil_stempel:\n"
            "            return\n"
            "        # Nicht unter einem offenen Dialog umbauen: der hält Verweise\n"
            "        # auf Einträge, die beim Neuaufbau ersetzt würden. Beim\n"
            "        # nächsten Durchlauf ist der Dialog zu.\n"
            "        from PyQt6.QtWidgets import QApplication\n"
            "        if (QApplication.activeModalWidget() is not None\n"
            "                or QApplication.activePopupWidget() is not None):\n"
            "            return\n"
            "        self._mobil_stempel = stempel\n"
            "        n, k, _ = MS.einarbeiten(self._data, pfad)\n"
            "        if not (n or k):\n"
            "            return\n"
            "        self._save()\n"
            "        self._fill_kunden()\n"
            "        self._fill_projekte()\n"
            "        self._fill_detail()\n"
            "        text = f\"Vom Handy übernommen: {n} Änderung(en)\"\n"
            "        if k:\n"
            "            text += f\" · {k} nicht übernommen (am Handy unter Einstellungen)\"\n"
            "        self.status.emit(text)\n\n"
            "    def _datenschaden_melden(self):\n",
        ),
    ],
}


def main():
    neu = {}
    for datei, schritte in AENDERUNGEN.items():
        pfad = os.path.join(HIER, datei)
        if not os.path.exists(pfad):
            sys.exit(f"✗ {datei} nicht gefunden — das Skript muss im "
                     f"Programmordner liegen.")
        with open(pfad, "rb") as f:
            crlf = b"\r\n" in f.read(4096)
        with open(pfad, "r", encoding="utf-8") as f:
            text = f.read()          # Zeilenenden hier immer \n
        if "import mobil_sync as MS" in text:
            print(f"• {datei}: schon eingebunden, bleibt unverändert.")
            continue
        for alt, ersatz in schritte:
            n = text.count(alt)
            if n != 1:
                sys.exit(f"✗ {datei}: erwartete Stelle kommt {n}× statt 1× vor:\n"
                         f"{alt[:120]!r}\n→ Nichts wurde geändert. Bitte die "
                         f"aktuelle {datei} an Claude schicken.")
            text = text.replace(alt, ersatz, 1)
        # Test vor dem Schreiben: lässt sich das Ergebnis übersetzen?
        compile(text, datei, "exec")
        neu[datei] = (text, crlf)

    if not os.path.exists(os.path.join(HIER, "mobil_sync.py")):
        sys.exit("✗ mobil_sync.py fehlt im Programmordner. Nichts wurde "
                 "geändert.")

    for datei, (text, crlf) in neu.items():
        pfad = os.path.join(HIER, datei)
        kopie = pfad + ".vor_mobil"
        if os.path.exists(kopie):        # ältere Kopie nicht überschreiben
            kopie = pfad + ".vor_mobil_" + datetime.datetime.now().strftime(
                "%Y%m%d_%H%M%S")
        shutil.copy2(pfad, kopie)
        # Zeilenenden so lassen, wie sie waren (Windows: \r\n)
        with open(pfad, "w", encoding="utf-8",
                  newline="\r\n" if crlf else "\n") as f:
            f.write(text)
        print(f"✓ {datei} angepasst (Kopie: {os.path.basename(kopie)})")
    print("Fertig. Vanta PDM neu starten.")


if __name__ == "__main__":
    main()
