"""
mobil_sync.py
─────────────
Übernimmt, was am Handy (Vanta PDM Mobil) eingetragen wurde.

Warum eine eigene Datei statt direkt in pdm_projects.json:

Die Handy-App und dieses Programm dürften sonst beide dieselbe Datei
schreiben. Wer zuletzt speichert, gewinnt — und hat den anderen
überschrieben. Bei der Datei, auf der die Rechnungen stehen, ist das
keine Option.

Deshalb gilt: **jede Datei hat genau einen Schreiber.**

    pdm_projects.json    schreibt nur der PC
    mobile_changes.json  schreibt nur das Handy

Das Handy legt jede Änderung als eigenen Auftrag mit fester Nummer
(`op_id`) ab: „Zeiteintrag neu", „Kunde geändert" … Der PC arbeitet die
Aufträge in `pdm_projects.json` ein und merkt sich die Nummern unter
`mobil_uebernommen`. So wird kein Auftrag zweimal übernommen, auch wenn
die Datei noch tagelang daneben liegt. Das Handy sieht die Nummern beim
nächsten Laden und räumt seine Datei selbst auf.

Konflikte: Jede Änderung bringt mit, wie der Wert vorher aussah
(`alt`). Hat sich am PC inzwischen genau dieser Wert geändert, wird der
Auftrag NICHT übernommen, sondern unter `mobil_konflikte` vermerkt.
Lieber einmal von Hand nachtragen als stillschweigend eine Änderung vom
PC überschreiben.

Hängt nur an der Standardbibliothek und datenspeicher.py.
"""

import datetime as _dt
import os

try:
    import datenspeicher as DS
except Exception:            # nur für Tests ohne das Programm drumherum
    DS = None

DATEINAME = "mobile_changes.json"
MERKEN = 3000          # so viele übernommene Nummern bleiben gespeichert
KONFLIKTE_MERKEN = 200

ZAHLFELDER = {"stundensatz", "pauschalpreis", "stunden", "pause_min",
              "menge", "preis", "vk", "ek"}
KUNDE_FELDER = ("name", "stundensatz")
PROJEKT_FELDER = ("name", "nummer", "status", "abrechnungstyp",
                  "pauschalpreis", "stundensatz", "beschreibung")
TASK_FELDER = ("name", "status")
ZEIT_FELDER = ("datum", "von", "bis", "pause_min", "stunden", "kommentar")


def pfad_neben(datendatei: str) -> str:
    """mobile_changes.json liegt im selben Ordner wie pdm_projects.json."""
    return os.path.join(os.path.dirname(os.path.abspath(datendatei)),
                        DATEINAME)


# ══════════════════════════════════════════════════════════════════════════
#  Lesen
# ══════════════════════════════════════════════════════════════════════════

def auftraege_lesen(pfad: str) -> list:
    """Die Aufträge aus mobile_changes.json, ältester zuerst.

    Eine fehlende oder unlesbare Datei ist kein Fehler: dann gibt es eben
    nichts zu übernehmen. Die Datei wird hier nie verändert — sie gehört
    dem Handy.
    """
    if not pfad or not os.path.exists(pfad):
        return []
    try:
        if DS is not None:
            daten, fehler = DS.lesen(pfad, {})
            if fehler or daten is None:
                print(f"[mobil_sync] {DATEINAME} nicht lesbar: {fehler}")
                return []
        else:
            import json
            with open(pfad, "r", encoding="utf-8") as f:
                daten = json.load(f)
    except Exception as e:
        print(f"[mobil_sync] {DATEINAME} nicht lesbar: {e}")
        return []
    ops = daten.get("ops") if isinstance(daten, dict) else None
    if not isinstance(ops, list):
        return []
    ops = [o for o in ops if isinstance(o, dict) and o.get("op_id")
           and o.get("typ")]
    return sorted(ops, key=lambda o: str(o.get("zeit", "")))


# ══════════════════════════════════════════════════════════════════════════
#  Suchen
# ══════════════════════════════════════════════════════════════════════════

def _kunde(daten, kid):
    for k in daten.get("kunden", []) or []:
        if str(k.get("id", "")) == str(kid):
            return k
    return None


def _projekt(daten, kid, pid):
    """Projekt über seine Nummer — auch wenn es inzwischen bei einem
    anderen Kunden hängt."""
    k = _kunde(daten, kid)
    kunden = ([k] if k else []) + [x for x in daten.get("kunden", []) or []
                                    if x is not k]
    for kk in kunden:
        for p in kk.get("projekte", []) or []:
            if str(p.get("id", "")) == str(pid):
                return kk, p
    return None, None


def _task(projekt, tid):
    for t in (projekt or {}).get("tasks", []) or []:
        if str(t.get("id", "")) == str(tid):
            return t
    return None


def _eintrag(task, eid):
    for e in (task or {}).get("zeiteintraege", []) or []:
        if str(e.get("id", "")) == str(eid):
            return e
    return None


# ══════════════════════════════════════════════════════════════════════════
#  Werte
# ══════════════════════════════════════════════════════════════════════════

def _zahl(w, standard=0.0):
    if isinstance(w, bool):
        return standard
    if isinstance(w, (int, float)):
        return float(w)
    t = str(w or "").strip().replace(" ", "")
    if not t:
        return standard
    if "," in t and "." in t:
        t = t.replace(".", "")
    try:
        return float(t.replace(",", "."))
    except ValueError:
        return standard


def _wert(feld, w):
    if feld == "pause_min":
        return int(round(_zahl(w)))
    if feld in ZAHLFELDER:
        return round(_zahl(w), 2)
    return str(w if w is not None else "").strip() if feld != "kommentar" \
        and feld != "beschreibung" else str(w if w is not None else "")


def _gleich(feld, a, b) -> bool:
    if feld in ZAHLFELDER:
        return abs(_zahl(a) - _zahl(b)) < 0.005
    return str(a if a is not None else "").strip() == \
        str(b if b is not None else "").strip()


def _stunden(von, bis, pause):
    """Dieselbe Rechnung wie project_manager.calc_stunden (auch über
    Mitternacht)."""
    try:
        fh, fm = map(int, str(von).split(":"))
        th, tm = map(int, str(bis).split(":"))
    except Exception:
        return None
    mins = (th * 60 + tm) - (fh * 60 + fm) - int(_zahl(pause))
    if mins < 0:
        mins += 24 * 60
    return round(mins / 60, 2)


def _datum_ok(s) -> bool:
    try:
        _dt.datetime.strptime(str(s), "%d.%m.%Y")
        return True
    except ValueError:
        return False


def _saubere_zeit(e: dict) -> dict:
    aus = {f: _wert(f, e.get(f)) for f in ZEIT_FELDER}
    aus["id"] = str(e.get("id", "")).strip()
    if aus["von"] and aus["bis"] and aus["von"] != aus["bis"]:
        h = _stunden(aus["von"], aus["bis"], aus["pause_min"])
        if h is not None:
            aus["stunden"] = h
    return aus


class Konflikt(Exception):
    pass


def _aendern(ziel: dict, neu: dict, alt: dict, felder, was: str):
    """Felder nur übernehmen, wenn sie am PC noch so sind wie das Handy sie
    kannte. Sonst den ganzen Auftrag als Konflikt zurückweisen."""
    neu = {f: v for f, v in (neu or {}).items() if f in felder}
    if not neu:
        return
    for f, v in neu.items():
        jetzt = ziel.get(f)
        if _gleich(f, jetzt, v):
            continue                       # steht schon so da
        if f in (alt or {}) and not _gleich(f, jetzt, alt[f]):
            raise Konflikt(f"{was}: „{f}“ wurde am PC inzwischen geändert "
                           f"(PC: {jetzt!r}, Handy wollte: {v!r}).")
    for f, v in neu.items():
        ziel[f] = _wert(f, v)


# ══════════════════════════════════════════════════════════════════════════
#  Einen Auftrag ausführen
# ══════════════════════════════════════════════════════════════════════════

def _ausfuehren(daten: dict, op: dict) -> str:
    """Führt einen Auftrag aus. → kurzer Text, was passiert ist.
    Wirft Konflikt, wenn er nicht sicher übernommen werden kann."""
    typ = op.get("typ")

    if typ == "kunde_neu":
        k = dict(op.get("kunde") or {})
        kid = str(k.get("id", "")).strip()
        if not kid or not str(k.get("name", "")).strip():
            raise Konflikt("Neuer Kunde ohne Namen oder Nummer.")
        if _kunde(daten, kid):
            return "Kunde war schon da"
        daten.setdefault("kunden", []).append({
            "id": kid, "name": _wert("name", k.get("name")),
            "stundensatz": _wert("stundensatz", k.get("stundensatz", 0)),
            "projekte": []})
        return f"Kunde „{k.get('name')}“ angelegt"

    if typ == "kunde_aendern":
        k = _kunde(daten, op.get("kunde_id"))
        if not k:
            raise Konflikt("Der Kunde existiert am PC nicht mehr.")
        _aendern(k, op.get("neu"), op.get("alt"), KUNDE_FELDER,
                 f"Kunde {k.get('name')}")
        return f"Kunde „{k.get('name')}“ geändert"

    if typ == "projekt_neu":
        k = _kunde(daten, op.get("kunde_id"))
        if not k:
            raise Konflikt("Der Kunde für das neue Projekt fehlt am PC.")
        p = dict(op.get("projekt") or {})
        pid = str(p.get("id", "")).strip()
        if not pid or not str(p.get("name", "")).strip():
            raise Konflikt("Neues Projekt ohne Namen oder Nummer.")
        if _projekt(daten, None, pid)[1]:
            return "Projekt war schon da"
        neu = {f: _wert(f, p.get(f, "")) for f in PROJEKT_FELDER}
        neu["status"] = neu["status"] or "aktiv"
        neu["abrechnungstyp"] = (neu["abrechnungstyp"]
                                 if neu["abrechnungstyp"] in ("stundensatz",
                                                              "pauschal")
                                 else "stundensatz")
        neu.update({"id": pid,
                    "erstellt": _dt.datetime.now().strftime("%d.%m.%Y %H:%M"),
                    "rechnung_nr": "", "rechnung_pos": "", "ordner": "",
                    "tasks": [], "zahlungen": [], "rechnungen": []})
        k.setdefault("projekte", []).append(neu)
        return f"Projekt „{neu['name']}“ angelegt"

    k, p = _projekt(daten, op.get("kunde_id"), op.get("projekt_id"))
    if not p:
        raise Konflikt("Das Projekt existiert am PC nicht mehr.")
    pname = p.get("nummer") or p.get("name")

    if typ == "projekt_aendern":
        _aendern(p, op.get("neu"), op.get("alt"), PROJEKT_FELDER,
                 f"Projekt {pname}")
        return f"Projekt {pname} geändert"

    if typ == "task_neu":
        t = dict(op.get("task") or {})
        tid = str(t.get("id", "")).strip()
        if not tid or not str(t.get("name", "")).strip():
            raise Konflikt("Neuer Task ohne Namen oder Nummer.")
        if _task(p, tid):
            return "Task war schon da"
        p.setdefault("tasks", []).append({
            "id": tid, "name": _wert("name", t.get("name")),
            "status": _wert("status", t.get("status")) or "aktiv",
            "zeiteintraege": []})
        return f"Task „{t.get('name')}“ in {pname} angelegt"

    if typ == "kalkulation_setzen":
        try:
            import kalkulation as KALK
            norm = KALK.normalisieren
        except Exception:
            norm = lambda x: [dict(y) for y in (x or []) if isinstance(y, dict)]
        roh = p.get("kalkulation") if isinstance(p.get("kalkulation"), dict) \
            else {}
        jetzt = norm(roh.get("positionen"))
        if norm(op.get("alt")) != jetzt and norm(op.get("positionen")) != jetzt:
            raise Konflikt(f"Kalkulation {pname}: wurde am PC inzwischen "
                           f"geändert.")
        # Nur Positionen und Stand ersetzen. Stückzahl, Aufschlag und der
        # Schalter Stück/Packung gehören der Kalkulation am PC und bleiben.
        neu = dict(roh) if isinstance(roh, dict) else {}
        neu["stand"] = _dt.date.today().strftime("%d.%m.%Y")
        neu["positionen"] = norm(op.get("positionen"))
        p["kalkulation"] = neu
        return f"Kalkulation {pname} übernommen"

    t = _task(p, op.get("task_id"))
    if not t:
        raise Konflikt(f"Der Task existiert in {pname} am PC nicht mehr.")

    if typ == "task_aendern":
        _aendern(t, op.get("neu"), op.get("alt"), TASK_FELDER,
                 f"Task {t.get('name')}")
        return f"Task „{t.get('name')}“ geändert"

    if typ == "zeit_neu":
        e = _saubere_zeit(op.get("eintrag") or {})
        if not e["id"]:
            raise Konflikt("Zeiteintrag ohne Nummer.")
        if not _datum_ok(e["datum"]):
            raise Konflikt(f"Zeiteintrag mit ungültigem Datum „{e['datum']}“.")
        if _eintrag(t, e["id"]):
            return "Zeiteintrag war schon da"
        t.setdefault("zeiteintraege", []).append(e)
        return (f"{str(e['stunden']).replace('.', ',')} h am {e['datum']} "
                f"in {pname}")

    if typ == "zeit_aendern":
        e = _eintrag(t, op.get("eintrag_id"))
        if not e:
            raise Konflikt("Der Zeiteintrag wurde am PC gelöscht.")
        neu = dict(op.get("neu") or {})
        _aendern(e, neu, op.get("alt"), ZEIT_FELDER,
                 f"Zeiteintrag {e.get('datum')} in {pname}")
        if e.get("von") and e.get("bis") and e["von"] != e["bis"]:
            h = _stunden(e["von"], e["bis"], e.get("pause_min", 0))
            if h is not None:
                e["stunden"] = h
        return f"Zeiteintrag {e.get('datum')} in {pname} geändert"

    if typ == "zeit_loeschen":
        e = _eintrag(t, op.get("eintrag_id"))
        if not e:
            return "Zeiteintrag war schon gelöscht"
        alt = op.get("alt") or {}
        for f in ZEIT_FELDER:
            if f in alt and not _gleich(f, e.get(f), alt[f]):
                raise Konflikt(f"Zeiteintrag {e.get('datum')} in {pname}: "
                               f"wurde am PC geändert, deshalb nicht gelöscht.")
        t["zeiteintraege"] = [x for x in t.get("zeiteintraege", [])
                              if x is not e]
        return f"Zeiteintrag {e.get('datum')} in {pname} gelöscht"

    raise Konflikt(f"Unbekannte Änderung „{typ}“ — bitte Vanta PDM "
                   f"aktualisieren.")


# ══════════════════════════════════════════════════════════════════════════
#  Alles einarbeiten
# ══════════════════════════════════════════════════════════════════════════

def einarbeiten(daten: dict, pfad: str) -> tuple:
    """Übernimmt neue Aufträge vom Handy in `daten` (wird verändert).

    → (anzahl_übernommen, anzahl_konflikte, meldungen)
    Speichern muss der Aufrufer — so landet alles in EINEM Schreibvorgang.
    """
    if not isinstance(daten, dict):
        return 0, 0, []
    ops = auftraege_lesen(pfad)
    if not ops:
        return 0, 0, []
    erledigt = daten.setdefault("mobil_uebernommen", [])
    konflikte = daten.setdefault("mobil_konflikte", [])
    bekannt = set(map(str, erledigt)) | {str(k.get("op_id")) for k in konflikte
                                          if isinstance(k, dict)}
    n_ok = n_k = 0
    meldungen = []
    for op in ops:
        oid = str(op["op_id"])
        if oid in bekannt:
            continue
        try:
            text = _ausfuehren(daten, op)
            erledigt.append(oid)
            n_ok += 1
            meldungen.append(text)
        except Konflikt as e:
            konflikte.append({"op_id": oid, "typ": op.get("typ"),
                              "zeit": op.get("zeit", ""), "grund": str(e),
                              "am": _dt.datetime.now().strftime(
                                  "%d.%m.%Y %H:%M")})
            n_k += 1
            meldungen.append("Nicht übernommen: " + str(e))
        except Exception as e:           # nie das Programm abstürzen lassen
            konflikte.append({"op_id": oid, "typ": op.get("typ"),
                              "zeit": op.get("zeit", ""),
                              "grund": f"Fehler beim Übernehmen: {e}",
                              "am": _dt.datetime.now().strftime(
                                  "%d.%m.%Y %H:%M")})
            n_k += 1
        bekannt.add(oid)
    # Listen begrenzen, damit pdm_projects.json nicht endlos wächst.
    # Alte Nummern kann das Handy längst nicht mehr haben: es räumt seine
    # Datei nach jedem Laden auf.
    if len(erledigt) > MERKEN:
        del erledigt[:len(erledigt) - MERKEN]
    if len(konflikte) > KONFLIKTE_MERKEN:
        del konflikte[:len(konflikte) - KONFLIKTE_MERKEN]
    if n_ok or n_k:
        print(f"[mobil_sync] {n_ok} Änderung(en) vom Handy übernommen"
              + (f", {n_k} Konflikt(e)" if n_k else ""))
    return n_ok, n_k, meldungen


def stempel(pfad: str):
    """Änderungszeit der Handy-Datei — zum billigen Nachsehen per Timer."""
    try:
        return os.path.getmtime(pfad)
    except OSError:
        return None
