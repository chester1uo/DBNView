"""Spanish documentation strings for dbnview."""

FIELD_DOC = {
    "length": "Longitud del registro en unidades de 4 bytes (bytes reales = length × 4). El decodificador la usa para "
              "saltar al siguiente registro.",
    "rtype": "Tipo de registro (record type); determina la disposición de los campos siguientes, p. ej. 0xA0 = MBO, "
             "0xB1 = CMBP-1.",
    "publisher_id": "Identificador de la fuente de datos = dataset + mercado (venue), p. ej. 30 = OPRA.PILLAR.OPRA, "
                    "1 = GLBX.MDP3.GLBX.",
    "instrument_id": "ID numérico del instrumento asignado por el mercado/Databento. Para traducirlo a un symbol hay que "
                     "consultar las symbology mappings de los metadata (dependen de la fecha).",
    "ts_event": "Hora del evento en el motor de casamiento del mercado, nanosegundos desde la época UNIX (UTC). En los "
                "schemas muestreados cbbo/bbo es la hora de la última operación, indefinida si no ha habido ninguna; "
                "en ohlcv es la hora de inicio de la barra.",
    "ts_recv": "Hora a la que el servidor de captura de Databento recibió el mensaje, nanosegundos desde la época UNIX "
               "(UTC). Es la marca de tiempo de índice principal de Databento; los archivos están ordenados por ella. "
               "En los schemas muestreados -1s / -1m es el instante de muestreo alineado al segundo/minuto.",
    "ts_in_delta": "Cuántos nanosegundos antes de ts_recv envió el mercado el mensaje (ts_recv − sending time del mercado).",
    "ts_out": "Hora de envío del gateway de Databento (solo se añade como los últimos 8 bytes de cada registro en datos "
              "live con ts_out activado).",
    "sequence": "Número de secuencia del mensaje del mercado (venue sequence number); sirve para detectar paquetes perdidos.",
    "price": "Precio en punto fijo: valor real = entero ÷ 1e9. INT64_MAX (9223372036854775807) indica indefinido. "
             "MBO = precio de la orden; trades/tbbo = precio de la operación; mbp = precio del evento; "
             "cbbo/bbo = precio de la última operación.",
    "size": "Cantidad (acciones/contratos). MBO = cantidad de la orden en ese evento; en una cancelación (C), la "
            "cantidad cancelada.",
    "action": "Tipo de evento: A alta, C cancelación, M modificación, R vaciado del libro, T operación, F ejecución "
              "(fill), N ninguno.",
    "side": "B = compra/bid, A = venta/ask, N = ninguno. En operaciones (T) indica el lado agresor (aggressor): "
            "B = compra agresiva.",
    "flags": "Indicadores de bits: 128 LAST (último registro del mismo evento), 64 TOB (mensaje top-of-book), "
             "32 SNAPSHOT (procede de un snapshot), 16 MBP (sintetizado a partir de niveles de precio agregados), "
             "8 BAD_TS_RECV, 4 MAYBE_BAD_BOOK (posible pérdida de paquetes), 2 PUBLISHER_SPECIFIC.",
    "depth": "Nivel de profundidad del libro afectado por este evento (0 = mejor precio).",
    "order_id": "ID de la orden (asignado por el mercado); los eventos A / M / C / F de una misma orden comparten este ID.",
    "channel_id": "ID del canal multicast del mercado.",
    "open": "Precio de apertura de la barra (punto fijo 1e-9).", "high": "Precio máximo de la barra.",
    "low": "Precio mínimo de la barra.", "close": "Precio de cierre de la barra.",
    "volume": "Volumen de la barra.",
    "ts_ref": "Hora de referencia a la que se refiere la estadística (p. ej. la sesión a la que corresponde un precio "
              "de liquidación).",
    "quantity": "Cantidad estadística (p. ej. interés abierto, volumen); el valor entero máximo indica indefinido.",
    "stat_type": "Tipo de estadística: 1 apertura, 3 liquidación, 4/5 mínimo/máximo de la sesión, 6 volumen compensado, "
                 "9 interés abierto, 11 cierre… (véase «Notas de formato»).",
    "update_action": "1 = alta, 2 = baja (retira una estadística publicada anteriormente).",
    "stat_flags": "Indicadores de estadística propios del mercado.",
    "raw_symbol": "Símbolo original del mercado, p. ej. en OPRA \"SPY   260116C00690000\" (root rellenado con espacios "
                  "hasta 6 caracteres + YYMMDD + C/P + precio de ejercicio×1000 en 8 dígitos).",
    "expiration": "Hora de vencimiento (UNIX ns).", "activation": "Hora de admisión a cotización/inicio de negociación (UNIX ns).",
    "strike_price": "Precio de ejercicio (punto fijo 1e-9).",
    "instrument_class": "Clase de instrumento: C call, P put, F futuro, K acción, S spread de futuros…",
    "underlying": "Símbolo del subyacente.", "underlying_id": "instrument_id del subyacente.",
    "min_price_increment": "Variación mínima de precio (tick size, punto fijo 1e-9).",
    "contract_multiplier": "Multiplicador del contrato (p. ej. 100 en opciones sobre acciones de EE. UU.).",
    "display_factor": "Multiplicador de los precios mostrados (punto fijo 1e-9).",
    "unit_of_measure_qty": "Cantidad de la unidad del contrato (punto fijo 1e-9).",
    "security_type": "Tipo de valor, p. ej. OOF, FUT, OPT.",
    "asset": "Código del activo.", "currency": "Divisa de cotización.", "exchange": "MIC del mercado.",
    "high_limit_price": "Precio límite superior.", "low_limit_price": "Precio límite inferior.",
    "stype_in_symbol": "Símbolo usado al suscribirse (symbology de entrada).",
    "stype_out_symbol": "Símbolo de salida correspondiente (normalmente el raw symbol).",
    "start_ts": "Inicio de vigencia de este mapping.", "end_ts": "Fin de vigencia de este mapping.",
    "msg": "Texto del mensaje del sistema (heartbeat, confirmación de suscripción…).", "err": "Texto del mensaje de error.",
    "code": "Código del mensaje.",
    "is_last": "Indica si es el último mensaje de error.",
    "is_trading": "Si se puede negociar: Y / N / ~ (desconocido).", "is_quoting": "Si se puede cotizar: Y / N / ~.",
    "is_short_sell_restricted": "Si la venta en corto está restringida: Y / N / ~.",
    "reason": "Código del motivo del cambio de estado.", "trading_event": "Código de evento de negociación adicional.",
    "ref_price": "Precio de referencia de la subasta.", "paired_qty": "Cantidad casada.",
    "total_imbalance_qty": "Desequilibrio total (cantidad).",
    "auction_type": "Tipo de subasta.",
    "_rec": "(Añadido por el viewer) Número de orden de este registro en el archivo, empezando en 0.",
    "symbol": "(Añadido por el viewer) Símbolo obtenido a partir de instrument_id mediante las metadata mappings.",
}

LEVEL = {
    "best": "en el mejor nivel (nivel 1)",
    "nth": "en el nivel {n}",
    "bid": "de compra",
    "ask": "de venta",
    "px": "Precio {side} {lvl} (punto fijo 1e-9; indefinido = INT64_MAX).",
    "sz": "Volumen total {side} {lvl}.",
    "ct": "Número de órdenes {side} {lvl}.",
    "pb": "Mercado (publisher_id) del que procede el precio {side} {lvl}. En datos consolidados sirve para ver quién "
          "proporciona el NBBO.",
}

RESERVED = "Bytes de relleno reservados o de alineación; sin datos."

SCHEMA_DOC = {
    "mbo": "Market by Order (L3): un registro por cada evento de alta/modificación/cancelación/ejecución de cada orden; "
           "permite reconstruir el libro de órdenes completo.",
    "mbp-1": "Mejor nivel (L1): un registro por cada evento que cambia la mejor compra/venta o genera una operación, con "
             "los mejores precios y cantidades de compra/venta «después» del evento.",
    "mbp-10": "Primeros 10 niveles (L2): un registro por cada cambio del libro, con precios, cantidades y número de "
              "órdenes de los 10 niveles de compra/venta después del evento.",
    "tbbo": "Operaciones + la mejor compra/venta «antes» de la operación (trades with BBO): una fila por operación.",
    "trades": "Operaciones tick a tick: una fila por operación.",
    "ohlcv-1s": "Barras de 1 segundo; solo hay registro si hubo operaciones en el intervalo; ts_event es el inicio del "
                "intervalo.",
    "ohlcv-1m": "Barras de 1 minuto; solo hay registro si hubo operaciones en el intervalo; ts_event es el inicio del "
                "intervalo.",
    "ohlcv-1h": "Barras de 1 hora.", "ohlcv-1d": "Barras diarias (límites de día UTC).",
    "ohlcv-eod": "Barras diarias delimitadas por el cierre del mercado.",
    "definition": "Definiciones de instrumentos: vencimiento, precio de ejercicio, multiplicador, tick size, "
                  "subyacente… (muy útil para extraer las especificaciones de los contratos de opciones de OPRA).",
    "statistics": "Estadísticas publicadas por el mercado: apertura/cierre, precio de liquidación, interés abierto, "
                  "volumen…; se distinguen por stat_type.",
    "status": "Cambios del estado de negociación: suspensión, reanudación, apertura, cierre, restricciones a la venta "
              "en corto, etc.",
    "imbalance": "Información sobre el desequilibrio de compra/venta en las subastas.",
    "cmbp-1": "L1 consolidado entre mercados (consolidated MBP-1): un registro cada vez que cambia la cotización de "
              "cualquier mercado, con el NBBO consolidado y los mercados que ofrecen el mejor precio "
              "(bid_pb / ask_pb). Volumen de datos muy grande.",
    "cbbo-1s": "NBBO consolidado muestreado cada segundo: solo tienen registro los instrumentos con actualización de "
               "cotización en ese segundo (requiere forward-fill). price / size / ts_event corresponden a la última "
               "operación, que puede ser muy antigua.",
    "cbbo-1m": "NBBO consolidado muestreado cada minuto: solo tienen registro los instrumentos con actualización de "
               "cotización en ese minuto (requiere forward-fill). price / size / ts_event corresponden a la última "
               "operación, que puede ser muy antigua; si nunca ha habido operaciones, son indefinidos.",
    "tcbbo": "Operaciones + el NBBO consolidado antes de la operación: una fila por operación.",
    "bbo-1s": "L1 de un solo mercado muestreado cada segundo.", "bbo-1m": "L1 de un solo mercado muestreado cada minuto.",
}

STYPE_DOC = {
    "instrument_id": "instrument_id numérico",
    "raw_symbol": "Símbolo original del mercado (p. ej. ESH4, SPY   260116C00690000)",
    "parent": "Símbolo padre: un símbolo se expande a toda una serie de contratos, p. ej. QQQ.OPT = todas las opciones "
              "de QQQ, ES.FUT = todos los futuros de ES",
    "continuous": "Contrato continuo, p. ej. ES.v.0 = el futuro de ES primero por volumen, ES.c.0 = el más próximo por "
                  "calendario",
    "nasdaq_symbol": "Símbolo Nasdaq", "cms_symbol": "Símbolo CMS", "isin": "ISIN", "us_code": "CUSIP", "figi": "FIGI",
}

ENUMS = [
    ("action", [("A", "Add: nueva orden/cotización"), ("C", "Cancel: cancelación (parcial o total)"),
                ("M", "Modify: modificación de precio o cantidad"),
                ("R", "Clear: vaciado del libro de órdenes (habitual al inicio de un snapshot)"),
                ("T", "Trade: operación (lado agresor)"), ("F", "Fill: aviso de ejecución del lado pasivo"),
                ("N", "None: sin acción (p. ej. solo se actualizan los flags)")]),
    ("side", [("B", "Bid: compra"), ("A", "Ask: venta"),
              ("N", "None (p. ej. operaciones sin lado, registros muestreados)")]),
    ("flags (bits)", [("128", "LAST: cuando un evento del mercado se divide en varios registros, solo el último lo "
                              "lleva; al reconstruir el libro, leer el estado solo después de LAST"),
                      ("64", "TOB: mensaje top-of-book (sustituye el nivel de precio completo)"),
                      ("32", "SNAPSHOT: procede de un snapshot/replay"),
                      ("16", "MBP: sintetizado a partir de datos de niveles de precio agregados"),
                      ("8", "BAD_TS_RECV: ts_recv no es fiable"),
                      ("4", "MAYBE_BAD_BOOK: posible pérdida de paquetes; el libro puede ser incorrecto"),
                      ("2", "PUBLISHER_SPECIFIC: propio del mercado")]),
    ("stat_type", [("1", "Precio de apertura"), ("2", "Precio de apertura indicativo"), ("3", "Precio de liquidación"),
                   ("4", "Mínimo de la sesión"), ("5", "Máximo de la sesión"), ("6", "Volumen compensado"),
                   ("7", "Venta más baja"), ("8", "Compra más alta"), ("9", "Interés abierto (open interest)"),
                   ("10", "Precio de fixing"), ("11", "Precio de cierre"), ("12", "Variación neta"), ("13", "VWAP"),
                   ("14", "Volatilidad"), ("15", "Delta")]),
    ("Valores indefinidos (sentinels)", [("INT64_MAX", "Precio indefinido 9223372036854775807 (se muestra como —)"),
                                         ("UINT64_MAX", "Marca de tiempo indefinida 18446744073709551615"),
                                         ("UINT32_MAX", "Cantidad indefinida 4294967295")]),
]

TIPS = [
    "Los precios son siempre entero ÷ 1e9; 9223372036854775807 significa «sin valor» y no debe usarse directamente "
    "como precio.",
    "Todas las horas están en nanosegundos UTC; el horario regular de la bolsa de EE. UU. 09:30–16:00 ET = "
    "14:30–21:00 UTC (13:30–20:00 en horario de verano). La zona horaria se puede cambiar en la barra de herramientas.",
    "ts_recv es la hora por la que se ordena el archivo; ts_event es la hora del mercado y puede estar desordenada o "
    "ser indefinida.",
    "En MBO, T/F no modifican el libro de órdenes; la reducción real de cantidad la hacen los C/M posteriores. Al "
    "reconstruir el libro, un evento solo está completo cuando flags incluye LAST.",
    "El instrument_id de OPRA puede cambiar de un día a otro; para alinear entre días use symbol, no el id.",
    "Los schemas muestreados -1s / -1m solo emiten registro cuando hay una actualización, así que hay que hacer "
    "forward-fill uno mismo; price/size son la «última operación», no las operaciones de ese intervalo.",
    "DBN v1 → v2 → v3: longitud de symbol 22 → 71; InstrumentDef 360 → 400 → 520 bytes; el quantity de StatMsg pasa "
    "de i32 a i64 en v3 (64 → 80 bytes). Este viewer cambia automáticamente según la versión de la cabecera.",
    ".zst comprime todo el flujo, por lo que no se puede saltar aleatoriamente al medio; para ver la parte final de un "
    "archivo hay que decodificar desde el principio (use el filtro de tiempo para conservar solo las filas necesarias).",
]


# --- added after the docs audit: remaining stat_type codes and the corrected statistics sentinel
def _patch():
    extra = ['Precio de cruce (subastas distintas de apertura/cierre oficial)', 'Límite de precio superior', 'Límite de precio inferior', 'Volumen de bloques', 'Precio de cierre indicativo', 'Umbral MWCB nivel 1 (7 %)', 'Umbral MWCB nivel 2 (13 %)', 'Umbral MWCB nivel 3 (20 %)', 'Precio de referencia del collar de subasta', 'Límite superior del collar de subasta', 'Límite inferior del collar de subasta', 'Volumen específico del mercado 1', 'Precio específico del mercado 1']
    for title, rows in ENUMS:
        codes = [c for c, _ in rows]
        if "15" in codes and "16" not in codes:
            rows.extend((str(c), d) for c, d in zip([16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 10001, 10002], extra))
        if "UINT32_MAX" in codes:
            i = codes.index("UINT32_MAX")
            rows[i] = ('INT32_MAX / INT64_MAX', 'quantity de statistics indefinida (INT32_MAX en v1/v2, INT64_MAX en v3)')


_patch()
