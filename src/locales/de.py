"""German documentation strings for dbnview."""

FIELD_DOC = {
    "length": "Datensatzlänge in Einheiten von 4 Bytes (tatsächliche Bytes = length × 4). Der Decoder springt damit "
              "zum nächsten Datensatz.",
    "rtype": "Datensatztyp (record type); bestimmt das Layout der folgenden Felder, z. B. 0xA0 = MBO, 0xB1 = CMBP-1.",
    "publisher_id": "Nummer der Datenquelle = dataset + Handelsplatz (venue), z. B. 30 = OPRA.PILLAR.OPRA, "
                    "1 = GLBX.MDP3.GLBX.",
    "instrument_id": "Numerische Instrument-ID, vergeben vom Handelsplatz/von Databento. Für die Zuordnung zu einem "
                     "symbol werden die symbology mappings in den metadata benötigt (datumsabhängig).",
    "ts_event": "Ereigniszeit in der Matching-Engine des Handelsplatzes, UNIX-Epoch-Nanosekunden (UTC). In den "
                "gesampelten cbbo/bbo-Schemas ist es die Zeit des letzten Trades, undefiniert, wenn es keinen Trade "
                "gab; bei ohlcv ist es die Startzeit des Balkens.",
    "ts_recv": "Zeitpunkt, zu dem der Capture-Server von Databento die Nachricht empfangen hat, UNIX-Epoch-Nanosekunden "
               "(UTC). Databentos primärer Indexzeitstempel; Dateien sind danach sortiert. In den gesampelten Schemas "
               "-1s / -1m ist es der auf Sekunde/Minute ausgerichtete Sampling-Zeitpunkt.",
    "ts_in_delta": "Um wie viele Nanosekunden die Sendezeit des Handelsplatzes vor ts_recv liegt "
                   "(ts_recv − sending time des Handelsplatzes).",
    "ts_out": "Sendezeit des Databento-Gateways (wird nur bei Live-Daten mit aktiviertem ts_out als letzte 8 Bytes an "
              "jeden Datensatz angehängt).",
    "sequence": "Nachrichten-Sequenznummer des Handelsplatzes (venue sequence number); damit lassen sich Paketverluste "
                "erkennen.",
    "price": "Preis als Festkommazahl: tatsächlicher Wert = Ganzzahl ÷ 1e9. INT64_MAX (9223372036854775807) bedeutet "
             "undefiniert. MBO = Orderpreis; trades/tbbo = Ausführungspreis; mbp = Preis des Ereignisses; "
             "cbbo/bbo = Preis des letzten Trades.",
    "size": "Menge (Aktien/Kontrakte). MBO = Ordermenge des Ereignisses; bei einer Löschung (C) die gelöschte Menge.",
    "action": "Ereignistyp: A Hinzufügen, C Löschen, M Ändern, R Orderbuch leeren, T Trade, F Ausführung (fill), "
              "N keiner.",
    "side": "B = Käufer/Bid, A = Verkäufer/Ask, N = keine. Bei Trades (T) die aggressive Seite (aggressor): "
            "B = aggressiver Kauf.",
    "flags": "Bit-Flags: 128 LAST (letzter Datensatz desselben Ereignisses), 64 TOB (Top-of-Book-Nachricht), "
             "32 SNAPSHOT (aus einem Snapshot), 16 MBP (aus aggregierten Preisstufen synthetisiert), 8 BAD_TS_RECV, "
             "4 MAYBE_BAD_BOOK (möglicher Paketverlust), 2 PUBLISHER_SPECIFIC.",
    "depth": "Von diesem Ereignis betroffene Stufe der Orderbuchtiefe (0 = bester Preis).",
    "order_id": "Order-ID (vom Handelsplatz vergeben); A / M / C / F derselben Order teilen sich diese ID.",
    "channel_id": "Multicast-Kanal-ID des Handelsplatzes.",
    "open": "Eröffnungskurs des Balkens (Festkomma 1e-9).", "high": "Höchstkurs des Balkens.",
    "low": "Tiefstkurs des Balkens.", "close": "Schlusskurs des Balkens.",
    "volume": "Volumen des Balkens.",
    "ts_ref": "Referenzzeit, auf die sich die Statistik bezieht (z. B. der Handelstag eines Settlement-Preises).",
    "quantity": "Statistische Menge (z. B. Open Interest, Volumen); der maximale Ganzzahlwert bedeutet undefiniert.",
    "stat_type": "Statistiktyp: 1 Eröffnungskurs, 3 Settlement-Preis, 4/5 Tagestief/-hoch, 6 Cleared Volume, "
                 "9 Open Interest, 11 Schlusskurs … (siehe „Formathinweise“).",
    "update_action": "1 = neu, 2 = löschen (Widerruf einer zuvor veröffentlichten Statistik).",
    "stat_flags": "Handelsplatzspezifische Statistik-Flags.",
    "raw_symbol": "Originalsymbol des Handelsplatzes, z. B. bei OPRA \"SPY   260116C00690000\" (Root mit Leerzeichen "
                  "auf 6 Zeichen aufgefüllt + YYMMDD + C/P + Strike×1000 als achtstellige Zahl).",
    "expiration": "Verfallszeitpunkt (UNIX ns).", "activation": "Notierungs-/Handelsbeginn (UNIX ns).",
    "strike_price": "Ausübungspreis (Festkomma 1e-9).",
    "instrument_class": "Instrumentklasse: C Call, P Put, F Future, K Aktie, S Future-Spread …",
    "underlying": "Symbol des Basiswerts.", "underlying_id": "instrument_id des Basiswerts.",
    "min_price_increment": "Minimale Preisänderung (Tick-Größe, Festkomma 1e-9).",
    "contract_multiplier": "Kontraktmultiplikator (z. B. 100 bei US-Aktienoptionen).",
    "display_factor": "Multiplikator für angezeigte Preise (Festkomma 1e-9).",
    "unit_of_measure_qty": "Menge der Kontrakteinheit (Festkomma 1e-9).",
    "security_type": "Wertpapiertyp, z. B. OOF, FUT, OPT.",
    "asset": "Asset-Code.", "currency": "Notierungswährung.", "exchange": "MIC des Handelsplatzes.",
    "high_limit_price": "Obere Preisgrenze (Limit-up).", "low_limit_price": "Untere Preisgrenze (Limit-down).",
    "stype_in_symbol": "Beim Abonnieren verwendetes Symbol (Eingabe-Symbology).",
    "stype_out_symbol": "Zugeordnetes Ausgabesymbol (meist das raw symbol).",
    "start_ts": "Beginn der Gültigkeit dieses Mappings.", "end_ts": "Ende der Gültigkeit dieses Mappings.",
    "msg": "Text der Systemnachricht (Heartbeat, Abo-Bestätigung …).", "err": "Text der Fehlermeldung.",
    "code": "Nachrichtencode.",
    "is_last": "Ob dies die letzte Fehlermeldung ist.",
    "is_trading": "Handel möglich: Y / N / ~ (unbekannt).", "is_quoting": "Quotierung möglich: Y / N / ~.",
    "is_short_sell_restricted": "Leerverkaufsbeschränkung: Y / N / ~.",
    "reason": "Code für den Grund der Statusänderung.", "trading_event": "Code eines zusätzlichen Handelsereignisses.",
    "ref_price": "Referenzpreis der Auktion.", "paired_qty": "Gepaarte Menge.",
    "total_imbalance_qty": "Gesamte Ungleichgewichtsmenge.",
    "auction_type": "Auktionstyp.",
    "_rec": "(Vom Viewer hinzugefügt) Laufende Nummer dieses Datensatzes in der Datei, beginnend bei 0.",
    "symbol": "(Vom Viewer hinzugefügt) Über die metadata mappings aus instrument_id ermitteltes Symbol.",
}

LEVEL = {
    "best": "Beste Stufe (Stufe 1)",
    "nth": "Stufe {n}",
    "bid": "Bid",
    "ask": "Ask",
    "px": "{lvl}: {side}-Preis (Festkomma 1e-9; undefiniert = INT64_MAX).",
    "sz": "{lvl}: Gesamtmenge auf der {side}-Seite.",
    "ct": "{lvl}: Anzahl der Orders auf der {side}-Seite.",
    "pb": "{lvl}: Handelsplatz (publisher_id), von dem der {side}-Preis stammt. In konsolidierten Daten sieht man "
          "daran, wer die NBBO stellt.",
}

RESERVED = "Reservierte bzw. der Ausrichtung dienende Füllbytes; keine Daten."

SCHEMA_DOC = {
    "mbo": "Market by Order (L3): je ein Datensatz pro Hinzufügen/Ändern/Löschen/Ausführen jeder einzelnen Order; "
           "ermöglicht die vollständige Rekonstruktion des Orderbuchs.",
    "mbp-1": "Beste Stufe (L1): ein Datensatz pro Ereignis, das den besten Bid/Ask ändert oder einen Trade erzeugt, "
             "mit den besten Bid/Ask-Preisen und -Mengen nach dem Ereignis.",
    "mbp-10": "Top 10 Stufen (L2): ein Datensatz pro Orderbuchänderung, mit Preisen, Mengen und Orderanzahlen der "
              "10 Bid/Ask-Stufen nach dem Ereignis.",
    "tbbo": "Trades + bester Bid/Ask vor dem Trade (trades with BBO): eine Zeile pro Trade.",
    "trades": "Einzelne Trades (Tick für Tick): eine Zeile pro Trade.",
    "ohlcv-1s": "Sekundenbalken; ein Datensatz existiert nur, wenn im Intervall gehandelt wurde; ts_event ist der "
                "Beginn des Intervalls.",
    "ohlcv-1m": "Minutenbalken; ein Datensatz existiert nur, wenn im Intervall gehandelt wurde; ts_event ist der "
                "Beginn des Intervalls.",
    "ohlcv-1h": "Stundenbalken.", "ohlcv-1d": "Tagesbalken (UTC-Tagesgrenzen).",
    "ohlcv-eod": "Tagesbalken, begrenzt durch den Handelsschluss des Handelsplatzes.",
    "definition": "Instrumentdefinitionen: Verfall, Ausübungspreis, Multiplikator, Tick-Größe, Basiswert … (gut "
                  "geeignet, um die Kontraktspezifikationen von OPRA-Optionen auszulesen).",
    "statistics": "Vom Handelsplatz veröffentlichte Statistiken: Eröffnungs-/Schlusskurs, Settlement-Preis, Open "
                  "Interest, Volumen …; Unterscheidung über stat_type.",
    "status": "Änderungen des Handelsstatus: Unterbrechung, Wiederaufnahme, Eröffnung, Schluss, "
              "Leerverkaufsbeschränkungen usw.",
    "imbalance": "Informationen zum Kauf-/Verkaufsungleichgewicht in Auktionen.",
    "cmbp-1": "Über Handelsplätze konsolidiertes L1 (consolidated MBP-1): ein Datensatz bei jeder Quote-Änderung an "
              "einem beliebigen Handelsplatz, mit der konsolidierten NBBO und den Handelsplätzen, die den besten Preis "
              "stellen (bid_pb / ask_pb). Sehr großes Datenvolumen.",
    "cbbo-1s": "Sekündlich gesampelte konsolidierte NBBO: nur Instrumente mit einem Quote-Update in dieser Sekunde "
               "haben einen Datensatz (forward-fill erforderlich). price / size / ts_event beziehen sich auf den letzten "
               "Trade, der lange zurückliegen kann.",
    "cbbo-1m": "Minütlich gesampelte konsolidierte NBBO: nur Instrumente mit einem Quote-Update in dieser Minute "
               "haben einen Datensatz (forward-fill erforderlich). price / size / ts_event beziehen sich auf den letzten "
               "Trade, der lange zurückliegen kann; undefiniert, falls nie gehandelt wurde.",
    "tcbbo": "Trades + konsolidierte NBBO vor dem Trade: eine Zeile pro Trade.",
    "bbo-1s": "L1 eines einzelnen Handelsplatzes, sekündlich gesampelt.",
    "bbo-1m": "L1 eines einzelnen Handelsplatzes, minütlich gesampelt.",
}

STYPE_DOC = {
    "instrument_id": "Numerische instrument_id",
    "raw_symbol": "Originalsymbol des Handelsplatzes (z. B. ESH4, SPY   260116C00690000)",
    "parent": "Elternsymbol: ein Symbol wird zu einer ganzen Reihe von Kontrakten expandiert, z. B. QQQ.OPT = alle "
              "QQQ-Optionen, ES.FUT = alle ES-Futures",
    "continuous": "Fortlaufender Kontrakt, z. B. ES.v.0 = der nach Volumen erstplatzierte ES-Future, ES.c.0 = der "
                  "kalendarisch nächste Kontrakt",
    "nasdaq_symbol": "Nasdaq-Symbol", "cms_symbol": "CMS-Symbol", "isin": "ISIN", "us_code": "CUSIP", "figi": "FIGI",
}

ENUMS = [
    ("action", [("A", "Add: neue Order/Quote"), ("C", "Cancel: Löschung (teilweise oder vollständig)"),
                ("M", "Modify: Preis oder Menge ändern"),
                ("R", "Clear: Orderbuch leeren (häufig am Anfang eines Snapshots)"),
                ("T", "Trade: Ausführung (aggressive Seite)"), ("F", "Fill: Ausführungsmeldung der passiven Seite"),
                ("N", "None: keine Aktion (z. B. nur flags aktualisiert)")]),
    ("side", [("B", "Bid: Kaufseite"), ("A", "Ask: Verkaufsseite"),
              ("N", "None (z. B. Trades ohne Seite, gesampelte Datensätze)")]),
    ("flags (Bits)", [("128", "LAST: wird ein Ereignis des Handelsplatzes auf mehrere Datensätze aufgeteilt, ist es nur "
                              "beim letzten gesetzt; beim Rekonstruieren des Orderbuchs den Zustand erst nach LAST lesen"),
                      ("64", "TOB: Top-of-Book-Nachricht (ersetzt die gesamte Preisstufe)"),
                      ("32", "SNAPSHOT: aus einem Snapshot/Replay"),
                      ("16", "MBP: aus aggregierten Preisstufendaten synthetisiert"),
                      ("8", "BAD_TS_RECV: ts_recv ist ungenau"),
                      ("4", "MAYBE_BAD_BOOK: möglicher Paketverlust, Orderbuch eventuell fehlerhaft"),
                      ("2", "PUBLISHER_SPECIFIC: handelsplatzspezifisch")]),
    ("stat_type", [("1", "Eröffnungskurs"), ("2", "Indikativer Eröffnungskurs"), ("3", "Settlement-Preis"),
                   ("4", "Tagestief"), ("5", "Tageshoch"), ("6", "Cleared Volume"), ("7", "Niedrigster Ask"),
                   ("8", "Höchster Bid"), ("9", "Open Interest"), ("10", "Fixing-Preis"), ("11", "Schlusskurs"),
                   ("12", "Veränderung zum Vortag"), ("13", "VWAP"), ("14", "Volatilität"), ("15", "Delta")]),
    ("Undefinierte Werte (Sentinels)", [("INT64_MAX", "Preis undefiniert 9223372036854775807 (angezeigt als —)"),
                                        ("UINT64_MAX", "Zeitstempel undefiniert 18446744073709551615"),
                                        ("UINT32_MAX", "Menge undefiniert 4294967295")]),
]

TIPS = [
    "Preise sind immer Ganzzahl ÷ 1e9; 9223372036854775807 bedeutet „kein Wert“ und darf nicht direkt als Preis "
    "verwendet werden.",
    "Alle Zeiten sind UTC-Nanosekunden; die regulären US-Handelszeiten 09:30–16:00 ET = 14:30–21:00 UTC "
    "(Sommerzeit 13:30–20:00). Die Zeitzone lässt sich in der Werkzeugleiste umschalten.",
    "ts_recv ist die Zeit, nach der die Datei sortiert ist; ts_event ist die Zeit des Handelsplatzes und kann "
    "ungeordnet oder undefiniert sein.",
    "In MBO verändern T/F das Orderbuch nicht; die eigentliche Mengenreduktion erfolgt durch das nachfolgende C/M. "
    "Beim Rekonstruieren des Orderbuchs ist ein Ereignis erst vollständig, wenn flags LAST enthält.",
    "Die instrument_id bei OPRA kann sich täglich ändern; über mehrere Tage hinweg nach symbol abgleichen, nicht "
    "nach id.",
    "Die gesampelten Schemas -1s / -1m enthalten nur bei Updates einen Datensatz, daher selbst forward-fill anwenden; "
    "price/size sind der „letzte Trade“, nicht die Trades im jeweiligen Intervall.",
    "DBN v1 → v2 → v3: symbol-Länge 22 → 71; InstrumentDef 360 → 400 → 520 bytes; quantity in StatMsg wurde in v3 "
    "von i32 auf i64 geändert (64 → 80 bytes). Dieser Viewer wechselt automatisch anhand der Version im Header.",
    ".zst komprimiert den gesamten Stream, daher kann nicht beliebig in die Mitte gesprungen werden; um den hinteren "
    "Teil einer Datei anzusehen, muss von Anfang an dekodiert werden (mit dem Zeitfilter nur die benötigten Zeilen "
    "behalten).",
]


# --- added after the docs audit: remaining stat_type codes and the corrected statistics sentinel
def _patch():
    extra = ['Auktionspreis (außer offizieller Eröffnung/Schluss)', 'Obere Preisgrenze', 'Untere Preisgrenze', 'Blockhandelsvolumen', 'Indikativer Schlusskurs', 'MWCB-Stufe 1 (7 %)', 'MWCB-Stufe 2 (13 %)', 'MWCB-Stufe 3 (20 %)', 'Auktionskorridor Referenzpreis', 'Auktionskorridor Obergrenze', 'Auktionskorridor Untergrenze', 'Börsenspezifisches Volumen 1', 'Börsenspezifischer Preis 1']
    for title, rows in ENUMS:
        codes = [c for c, _ in rows]
        if "15" in codes and "16" not in codes:
            rows.extend((str(c), d) for c, d in zip([16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 10001, 10002], extra))
        if "UINT32_MAX" in codes:
            i = codes.index("UINT32_MAX")
            rows[i] = ('INT32_MAX / INT64_MAX', 'statistics-quantity undefiniert (INT32_MAX in v1/v2, INT64_MAX in v3)')


_patch()
