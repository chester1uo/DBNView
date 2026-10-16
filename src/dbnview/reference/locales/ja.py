"""Japanese documentation strings for dbnview."""

FIELD_DOC = {
    "length": "レコード長（4 バイト単位、実際のバイト数 = length × 4）。デコーダはこれを使って次のレコードへスキップする。",
    "rtype": "レコード種別 (record type)。後続フィールドのレイアウトを決める。例：0xA0 = MBO、0xB1 = CMBP-1。",
    "publisher_id": "データソース番号 = dataset + 取引所 (venue)。例：30 = OPRA.PILLAR.OPRA、1 = GLBX.MDP3.GLBX。",
    "instrument_id": "取引所／Databento が割り当てた銘柄の数値 ID。symbol に戻すには metadata の symbology mappings を"
                     "参照する必要がある（日付によって異なる）。",
    "ts_event": "取引所マッチングエンジンでのイベント時刻、UNIX epoch ナノ秒 (UTC)。cbbo/bbo サンプリング schema では"
                "「直近の約定」の時刻で、約定がなければ未定義。ohlcv では足の開始時刻。",
    "ts_recv": "Databento のキャプチャサーバがメッセージを受信した時刻、UNIX epoch ナノ秒 (UTC)。Databento の主インデックス"
               "時刻で、ファイルはこれでソートされている。-1s / -1m サンプリング schema では秒／分に揃えたサンプリング時点。",
    "ts_in_delta": "取引所の送信時刻が ts_recv より何ナノ秒早いか（ts_recv − 取引所 sending time）。",
    "ts_out": "Databento ゲートウェイの送信時刻（live データで ts_out を有効にした場合のみ、各レコード末尾の 8 バイトに付加される）。",
    "sequence": "取引所メッセージのシーケンス番号 (venue sequence number)。パケット欠落の確認に使える。",
    "price": "価格、固定小数点：実際の値 = 整数 ÷ 1e9。INT64_MAX (9223372036854775807) は未定義を表す。MBO = 注文価格；"
             "trades/tbbo = 約定価格；mbp = そのイベントの価格；cbbo/bbo = 直近の約定価格。",
    "size": "数量（株数／枚数）。MBO = そのイベントの注文数量；取消 (C) の場合は取り消された数量。",
    "action": "イベント種別：A 追加、C 取消、M 訂正、R 板のクリア、T 約定、F 約定通知 (fill)、N なし。",
    "side": "B = 買い／bid、A = 売り／ask、N = なし。約定 (T) ではアグレッサー側 (aggressor) を表す：B = 買いが能動側。",
    "flags": "ビットフラグ：128 LAST（同一イベントの最後のレコード）、64 TOB（top-of-book メッセージ）、32 SNAPSHOT"
             "（スナップショット由来）、16 MBP（集約された価格レベルから合成）、8 BAD_TS_RECV、4 MAYBE_BAD_BOOK"
             "（パケット欠落の可能性）、2 PUBLISHER_SPECIFIC。",
    "depth": "このイベントが影響する板の深さレベル（0 = 最良気配）。",
    "order_id": "注文 ID（取引所が割り当て）。同一注文の A / M / C / F はこの ID を共有する。",
    "channel_id": "取引所のマルチキャストチャネル ID。",
    "open": "足の始値（固定小数点 1e-9）。", "high": "足の高値。", "low": "足の安値。", "close": "足の終値。",
    "volume": "足の出来高。",
    "ts_ref": "統計値が参照する基準時刻（例：清算値に対応する取引日）。",
    "quantity": "統計数量（例：建玉、出来高）。整数の最大値は未定義を表す。",
    "stat_type": "統計種別：1 始値、3 清算値、4/5 日中安値/高値、6 清算出来高、9 建玉、11 終値…（「フォーマット説明」を参照）。",
    "update_action": "1 = 追加、2 = 削除（以前に公表した統計の撤回）。",
    "stat_flags": "取引所独自の統計フラグ。",
    "raw_symbol": "取引所の元のシンボル。例：OPRA の \"SPY   260116C00690000\"（root を空白で 6 文字に埋める + YYMMDD "
                  "+ C/P + 行使価格×1000 の 8 桁）。",
    "expiration": "満期時刻 (UNIX ns)。", "activation": "上場／取引開始時刻 (UNIX ns)。",
    "strike_price": "行使価格（固定小数点 1e-9）。",
    "instrument_class": "銘柄クラス：C コール、P プット、F 先物、K 株式、S 先物スプレッド…",
    "underlying": "原資産のシンボル。", "underlying_id": "原資産の instrument_id。",
    "min_price_increment": "呼値の単位 (tick size、固定小数点 1e-9)。",
    "contract_multiplier": "契約乗数（例：米国株式オプションは 100）。", "display_factor": "表示価格の乗数（固定小数点 1e-9）。",
    "unit_of_measure_qty": "契約単位の数量（固定小数点 1e-9）。", "security_type": "証券種別。例：OOF、FUT、OPT。",
    "asset": "資産コード。", "currency": "建値通貨。", "exchange": "取引所 MIC。",
    "high_limit_price": "値幅制限の上限価格。", "low_limit_price": "値幅制限の下限価格。",
    "stype_in_symbol": "購読時に使用したシンボル（入力 symbology）。",
    "stype_out_symbol": "対応する出力シンボル（通常は raw symbol）。",
    "start_ts": "この mapping の有効開始時刻。", "end_ts": "この mapping の有効終了時刻。",
    "msg": "システムメッセージ本文（heartbeat、購読確認…）。", "err": "エラーメッセージ本文。", "code": "メッセージコード。",
    "is_last": "最後のエラーメッセージかどうか。",
    "is_trading": "取引可能か：Y / N / ~（不明）。", "is_quoting": "気配提示が可能か：Y / N / ~。",
    "is_short_sell_restricted": "空売り規制の有無：Y / N / ~。",
    "reason": "ステータス変更の理由コード。", "trading_event": "付随する取引イベントのコード。",
    "ref_price": "オークションの参照価格。", "paired_qty": "マッチ済み数量。", "total_imbalance_qty": "総インバランス数量。",
    "auction_type": "オークション種別。",
    "_rec": "（viewer が付加）ファイル内でのこのレコードの通し番号、0 起点。",
    "symbol": "（viewer が付加）instrument_id から metadata mappings で引いたシンボル。",
}

LEVEL = {
    "best": "最良（第 1 レベル）",
    "nth": "第 {n} レベル",
    "bid": "買い",
    "ask": "売り",
    "px": "{lvl}の{side}気配値（固定小数点 1e-9；未定義 = INT64_MAX）。",
    "sz": "{lvl}の{side}数量の合計。",
    "ct": "{lvl}の{side}注文件数。",
    "pb": "{lvl}の{side}気配値を提示している取引所（publisher_id）。統合データで NBBO を誰が提供しているかの確認に使う。",
}

RESERVED = "予約／アライメント用のパディングバイト。データなし。"

SCHEMA_DOC = {
    "mbo": "注文単位 (Market by Order, L3)：各注文の追加／訂正／取消／約定イベントごとに 1 レコード。板を完全に再構築できる。",
    "mbp-1": "最良気配 (L1)：最良売買気配を変えるか約定を生むイベントごとに 1 レコード。イベント「後」の最良売買気配の"
             "価格と数量が付く。",
    "mbp-10": "上位 10 レベル (L2)：板が変化するイベントごとに 1 レコード。イベント後の 10 レベル分の売買気配の価格・数量・"
              "注文件数が付く。",
    "tbbo": "約定 + 約定「前」の最良売買気配 (trades with BBO)：約定 1 件につき 1 行。",
    "trades": "約定ティック：約定 1 件につき 1 行。",
    "ohlcv-1s": "1 秒足。その区間に約定があった場合のみレコードがあり、ts_event は区間の開始時刻。",
    "ohlcv-1m": "1 分足。その区間に約定があった場合のみレコードがあり、ts_event は区間の開始時刻。",
    "ohlcv-1h": "1 時間足。", "ohlcv-1d": "日足（UTC の日境界）。", "ohlcv-eod": "取引所の終了時刻で区切った日足。",
    "definition": "銘柄定義：満期日、行使価格、乗数、tick size、原資産…（OPRA オプションの契約仕様の解析に便利）。",
    "statistics": "取引所が公表する統計：始値／終値、清算値、建玉、出来高…。stat_type で区別する。",
    "status": "取引ステータスの変化：売買停止、再開、取引開始、取引終了、空売り規制など。",
    "imbalance": "オークションの売買インバランス情報。",
    "cmbp-1": "取引所横断の統合 L1 (consolidated MBP-1)：いずれかの取引所の気配が変わるたびに 1 レコード。統合後の NBBO と、"
              "最良気配を提示している取引所 (bid_pb / ask_pb) が付く。データ量が非常に大きい。",
    "cbbo-1s": "1 秒ごとにサンプリングした統合 NBBO：その秒に気配更新があった銘柄のみレコードがある（forward-fill が必要）。"
               "price / size / ts_event は直近の約定で、かなり前のものの場合もある。",
    "cbbo-1m": "1 分ごとにサンプリングした統合 NBBO：その分に気配更新があった銘柄のみレコードがある（forward-fill が必要）。"
               "price / size / ts_event は直近の約定で、かなり前のものの場合もあり、一度も約定がなければ未定義。",
    "tcbbo": "約定 + 約定前の統合 NBBO：約定 1 件につき 1 行。",
    "bbo-1s": "単一取引所の L1 を 1 秒ごとにサンプリング。", "bbo-1m": "単一取引所の L1 を 1 分ごとにサンプリング。",
}

STYPE_DOC = {
    "instrument_id": "数値の instrument_id",
    "raw_symbol": "取引所の元のシンボル（例：ESH4、SPY   260116C00690000）",
    "parent": "親シンボル：1 つのシンボルが一連の契約に展開される。例：QQQ.OPT = QQQ の全オプション、ES.FUT = ES の全先物",
    "continuous": "つなぎ足（連続限月）。例：ES.v.0 = 出来高 1 位の ES 先物、ES.c.0 = 暦で直近の限月",
    "nasdaq_symbol": "Nasdaq シンボル", "cms_symbol": "CMS シンボル", "isin": "ISIN", "us_code": "CUSIP", "figi": "FIGI",
}

ENUMS = [
    ("action", [("A", "Add 新規注文／気配の追加"), ("C", "Cancel 取消（一部または全部）"), ("M", "Modify 価格または数量の訂正"),
                ("R", "Clear 板のクリア（スナップショットの先頭によく出る）"), ("T", "Trade 約定（能動側）"),
                ("F", "Fill 受動側の約定通知"), ("N", "None 動作なし（例：flags のみ更新）")]),
    ("side", [("B", "Bid 買い"), ("A", "Ask 売り"), ("N", "None（例：方向のない約定、サンプリングレコード）")]),
    ("flags（ビット）", [("128", "LAST：1 つの取引所イベントが複数レコードに分かれる場合、最後のレコードにのみ立つ。"
                               "板を再構築する際は LAST の後で状態を読むこと"),
                      ("64", "TOB：top-of-book メッセージ（その価格レベル全体を置き換える）"),
                      ("32", "SNAPSHOT：スナップショット／リプレイ由来"),
                      ("16", "MBP：集約された価格レベルデータから合成"), ("8", "BAD_TS_RECV：ts_recv が不正確"),
                      ("4", "MAYBE_BAD_BOOK：パケット欠落の可能性があり、板が誤っているかもしれない"),
                      ("2", "PUBLISHER_SPECIFIC：取引所独自")]),
    ("stat_type", [("1", "始値"), ("2", "参考始値"), ("3", "清算値"), ("4", "日中安値"), ("5", "日中高値"),
                   ("6", "清算出来高"), ("7", "最低売り気配"), ("8", "最高買い気配"), ("9", "建玉 (open interest)"),
                   ("10", "フィキシング価格 (fixing)"), ("11", "終値"), ("12", "前日比"), ("13", "VWAP"),
                   ("14", "ボラティリティ"), ("15", "Delta")]),
    ("未定義値 (sentinel)", [("INT64_MAX", "価格未定義 9223372036854775807（— と表示）"),
                          ("UINT64_MAX", "タイムスタンプ未定義 18446744073709551615"),
                          ("UINT32_MAX", "数量未定義 4294967295")]),
]

TIPS = [
    "価格は常に整数 ÷ 1e9。9223372036854775807 は「値なし」を意味し、そのまま価格として計算してはいけない。",
    "時刻はすべて UTC ナノ秒。米国株の立会時間 09:30–16:00 ET = 14:30–21:00 UTC（夏時間は 13:30–20:00）。"
    "ツールバーでタイムゾーンを切り替えられる。",
    "ts_recv はファイルのソートに使われる時刻。ts_event は取引所時刻で、順序が乱れていたり未定義だったりする。",
    "MBO の T／F は板を変えず、実際に数量を減らすのは後続の C／M。板の再構築では flags に LAST が含まれて"
    "初めて 1 つの完結したイベントとなる。",
    "OPRA の instrument_id は日によって変わることがあるので、日をまたぐ照合には id ではなく symbol を使う。",
    "-1s / -1m サンプリング schema は更新があったときだけレコードが出るので、自分で forward-fill する必要がある。"
    "price/size は「直近の約定」であり、その区間内の約定ではない。",
    "DBN v1 → v2 → v3：symbol 長 22 → 71；InstrumentDef 360 → 400 → 520 bytes；StatMsg の quantity は v3 で i32 "
    "から i64 に変更（64 → 80 bytes）。この viewer はファイルヘッダのバージョンで自動的に切り替える。",
    ".zst はストリーム全体を圧縮しているため、途中へランダムにジャンプできない。ファイル後半を見るには先頭から"
    "デコードする必要がある（時間フィルタを使えば必要な行だけを残せる）。",
]


# --- added after the docs audit: remaining stat_type codes and the corrected statistics sentinel
def _patch():
    extra = ['板寄せ約定価格（公式始値・終値以外）', '値幅上限', '値幅下限', 'ブロック取引出来高', '参考終値', 'サーキットブレーカー レベル1 (7%)', 'サーキットブレーカー レベル2 (13%)', 'サーキットブレーカー レベル3 (20%)', 'オークション価格帯 基準値', 'オークション価格帯 上限', 'オークション価格帯 下限', '取引所固有の出来高 1', '取引所固有の価格 1']
    for title, rows in ENUMS:
        codes = [c for c, _ in rows]
        if "15" in codes and "16" not in codes:
            rows.extend((str(c), d) for c, d in zip([16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 10001, 10002], extra))
        if "UINT32_MAX" in codes:
            i = codes.index("UINT32_MAX")
            rows[i] = ('INT32_MAX / INT64_MAX', 'statistics の quantity が未定義（v1/v2 は INT32_MAX、v3 は INT64_MAX）')


_patch()
