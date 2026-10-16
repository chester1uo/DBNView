"""Korean documentation strings for dbnview."""

FIELD_DOC = {
    "length": "레코드 길이, 4바이트 단위(실제 바이트 수 = length × 4). 디코더는 이 값으로 다음 레코드로 건너뛴다.",
    "rtype": "레코드 유형(record type). 뒤따르는 필드의 레이아웃을 결정한다. 예: 0xA0 = MBO, 0xB1 = CMBP-1.",
    "publisher_id": "데이터 소스 번호 = dataset + 거래소(venue). 예: 30 = OPRA.PILLAR.OPRA, 1 = GLBX.MDP3.GLBX.",
    "instrument_id": "거래소/Databento가 부여한 종목 숫자 ID. symbol로 되돌리려면 metadata의 symbology mappings를 "
                     "조회해야 한다(날짜에 따라 다름).",
    "ts_event": "거래소 매칭 엔진의 이벤트 시각, UNIX epoch 나노초(UTC). cbbo/bbo 샘플링 schema에서는 '가장 최근 체결' "
                "시각이며 체결이 없으면 미정의. ohlcv에서는 봉 시작 시각.",
    "ts_recv": "Databento 수집 서버가 메시지를 수신한 시각, UNIX epoch 나노초(UTC). Databento의 기본 인덱스 시각이며 "
               "파일은 이 값으로 정렬된다. -1s / -1m 샘플링 schema에서는 초/분 단위로 맞춘 샘플링 시점.",
    "ts_in_delta": "거래소 송신 시각이 ts_recv보다 몇 나노초 앞서는지(ts_recv − 거래소 sending time).",
    "ts_out": "Databento 게이트웨이 송신 시각(live 데이터에서 ts_out을 켠 경우에만 각 레코드 마지막 8바이트에 추가됨).",
    "sequence": "거래소 메시지 일련번호(venue sequence number). 패킷 누락 확인에 쓸 수 있다.",
    "price": "가격, 고정소수점: 실제 값 = 정수 ÷ 1e9. INT64_MAX (9223372036854775807)는 미정의를 뜻한다. "
             "MBO = 주문 가격; trades/tbbo = 체결 가격; mbp = 해당 이벤트 가격; cbbo/bbo = 가장 최근 체결 가격.",
    "size": "수량(주식 수/계약 수). MBO = 해당 이벤트의 주문 수량; 취소(C)일 때는 취소된 수량.",
    "action": "이벤트 유형: A 추가, C 취소, M 정정, R 오더북 초기화, T 체결, F 체결 통보(fill), N 없음.",
    "side": "B = 매수/bid, A = 매도/ask, N = 없음. 체결(T)에서는 주도 측(aggressor)을 나타낸다: B = 매수 주도.",
    "flags": "비트 플래그: 128 LAST(같은 이벤트의 마지막 레코드), 64 TOB(top-of-book 메시지), 32 SNAPSHOT(스냅샷에서 옴), "
             "16 MBP(집계된 가격 레벨로부터 합성), 8 BAD_TS_RECV, 4 MAYBE_BAD_BOOK(패킷 누락 가능성), "
             "2 PUBLISHER_SPECIFIC.",
    "depth": "이 이벤트가 영향을 주는 오더북 깊이 레벨(0 = 최우선 가격).",
    "order_id": "주문 ID(거래소 부여). 같은 주문의 A / M / C / F는 이 ID를 공유한다.",
    "channel_id": "거래소 멀티캐스트 채널 ID.",
    "open": "봉 시가(고정소수점 1e-9).", "high": "봉 고가.", "low": "봉 저가.", "close": "봉 종가.",
    "volume": "봉 거래량.",
    "ts_ref": "통계값이 가리키는 기준 시각(예: 정산가격에 해당하는 거래일).",
    "quantity": "통계 수량(예: 미결제약정, 거래량). 정수 최댓값은 미정의를 뜻한다.",
    "stat_type": "통계 유형: 1 시가, 3 정산가격, 4/5 장중 저가/고가, 6 청산 거래량, 9 미결제약정, 11 종가…"
                 "('형식 설명' 참조).",
    "update_action": "1 = 추가, 2 = 삭제(이전에 공표한 통계 철회).",
    "stat_flags": "거래소 자체 통계 플래그.",
    "raw_symbol": "거래소 원본 심볼. 예: OPRA의 \"SPY   260116C00690000\"(root를 공백으로 6자까지 채움 + YYMMDD + C/P "
                  "+ 행사가격×1000 8자리).",
    "expiration": "만기 시각(UNIX ns).", "activation": "상장/거래 개시 시각(UNIX ns).",
    "strike_price": "행사가격(고정소수점 1e-9).",
    "instrument_class": "종목 분류: C 콜옵션, P 풋옵션, F 선물, K 주식, S 선물 스프레드…",
    "underlying": "기초자산 심볼.", "underlying_id": "기초자산의 instrument_id.",
    "min_price_increment": "최소 호가 단위(tick size, 고정소수점 1e-9).",
    "contract_multiplier": "계약 승수(예: 미국 주식옵션은 100).", "display_factor": "표시 가격의 승수(고정소수점 1e-9).",
    "unit_of_measure_qty": "계약 단위 수량(고정소수점 1e-9).", "security_type": "증권 유형. 예: OOF, FUT, OPT.",
    "asset": "자산 코드.", "currency": "표시 통화.", "exchange": "거래소 MIC.",
    "high_limit_price": "상한가.", "low_limit_price": "하한가.",
    "stype_in_symbol": "구독 시 사용한 심볼(입력 symbology).", "stype_out_symbol": "대응되는 출력 심볼(보통 raw symbol).",
    "start_ts": "이 mapping의 적용 시작 시각.", "end_ts": "이 mapping의 적용 종료 시각.",
    "msg": "시스템 메시지 텍스트(heartbeat, 구독 확인…).", "err": "오류 메시지 텍스트.", "code": "메시지 코드.",
    "is_last": "마지막 오류 메시지인지 여부.",
    "is_trading": "거래 가능 여부: Y / N / ~(알 수 없음).", "is_quoting": "호가 제출 가능 여부: Y / N / ~.",
    "is_short_sell_restricted": "공매도 제한 여부: Y / N / ~.",
    "reason": "상태 변경 사유 코드.", "trading_event": "부가 거래 이벤트 코드.",
    "ref_price": "경매 참조가격.", "paired_qty": "매칭된 수량.", "total_imbalance_qty": "총 불균형 수량.",
    "auction_type": "경매 유형.",
    "_rec": "(viewer가 추가) 파일 내 이 레코드의 순번, 0부터 시작.",
    "symbol": "(viewer가 추가) instrument_id를 metadata mappings로 조회해 얻은 심볼.",
}

LEVEL = {
    "best": "최우선(1단계)",
    "nth": "{n}단계",
    "bid": "매수",
    "ask": "매도",
    "px": "{lvl} {side} 호가(고정소수점 1e-9; 미정의 = INT64_MAX).",
    "sz": "{lvl} {side} 총수량.",
    "ct": "{lvl} {side} 주문 건수.",
    "pb": "{lvl} {side} 호가를 제공한 거래소(publisher_id). 통합 데이터에서 NBBO를 누가 제공하는지 확인하는 데 쓴다.",
}

RESERVED = "예약/정렬용 패딩 바이트. 데이터 없음."

SCHEMA_DOC = {
    "mbo": "주문별 시세(Market by Order, L3): 각 주문의 추가/정정/취소/체결 이벤트마다 한 건씩. 오더북을 완전히 "
           "재구성할 수 있다.",
    "mbp-1": "최우선 호가(L1): 최우선 매수·매도 호가를 바꾸거나 체결을 일으킨 이벤트마다 한 건씩, 이벤트 '이후'의 최우선 "
             "매수·매도 가격과 수량이 붙는다.",
    "mbp-10": "상위 10단계(L2): 오더북이 변하는 이벤트마다 한 건씩, 이벤트 이후 10단계 매수·매도 가격·수량과 주문 건수가 붙는다.",
    "tbbo": "체결 + 체결 '이전'의 최우선 매수·매도 호가(trades with BBO): 체결 한 건당 한 행.",
    "trades": "틱 단위 체결: 체결 한 건당 한 행.",
    "ohlcv-1s": "1초봉. 해당 구간에 체결이 있어야만 레코드가 있으며, ts_event는 구간 시작 시각.",
    "ohlcv-1m": "1분봉. 해당 구간에 체결이 있어야만 레코드가 있으며, ts_event는 구간 시작 시각.",
    "ohlcv-1h": "1시간봉.", "ohlcv-1d": "일봉(UTC 날짜 경계).", "ohlcv-eod": "거래소 장 마감을 경계로 한 일봉.",
    "definition": "종목 정의: 만기일, 행사가격, 승수, tick size, 기초자산…(OPRA 옵션의 계약 명세를 파싱하는 데 유용).",
    "statistics": "거래소가 공표하는 통계: 시가/종가, 정산가격, 미결제약정, 거래량…. stat_type으로 구분한다.",
    "status": "거래 상태 변화: 거래 정지, 재개, 개장, 마감, 공매도 제한 등.", "imbalance": "경매의 매수·매도 불균형 정보.",
    "cmbp-1": "거래소 통합 L1(consolidated MBP-1): 어느 거래소든 호가가 바뀔 때마다 한 건씩, 통합된 NBBO와 최우선 가격을 "
              "제공한 거래소(bid_pb / ask_pb)가 붙는다. 데이터 양이 매우 크다.",
    "cbbo-1s": "1초마다 샘플링한 통합 NBBO: 그 1초 동안 호가 갱신이 있었던 종목만 레코드가 있다(forward-fill 필요). "
               "price / size / ts_event는 가장 최근 체결이며, 아주 오래전 것일 수 있다.",
    "cbbo-1m": "1분마다 샘플링한 통합 NBBO: 그 1분 동안 호가 갱신이 있었던 종목만 레코드가 있다(forward-fill 필요). "
               "price / size / ts_event는 가장 최근 체결이며, 아주 오래전 것일 수 있고, 체결된 적이 없으면 미정의.",
    "tcbbo": "체결 + 체결 이전의 통합 NBBO: 체결 한 건당 한 행.",
    "bbo-1s": "단일 거래소 L1을 1초마다 샘플링.", "bbo-1m": "단일 거래소 L1을 1분마다 샘플링.",
}

STYPE_DOC = {
    "instrument_id": "숫자 instrument_id",
    "raw_symbol": "거래소 원본 심볼(예: ESH4, SPY   260116C00690000)",
    "parent": "상위 심볼: 하나의 심볼이 일련의 계약 전체로 펼쳐진다. 예: QQQ.OPT = QQQ 전체 옵션, ES.FUT = ES 전체 선물",
    "continuous": "연속 계약. 예: ES.v.0 = 거래량 1위 ES 선물, ES.c.0 = 달력상 최근월",
    "nasdaq_symbol": "Nasdaq 심볼", "cms_symbol": "CMS 심볼", "isin": "ISIN", "us_code": "CUSIP", "figi": "FIGI",
}

ENUMS = [
    ("action", [("A", "Add 신규 주문/호가 추가"), ("C", "Cancel 취소(일부 또는 전부)"), ("M", "Modify 가격 또는 수량 정정"),
                ("R", "Clear 오더북 초기화(스냅샷 시작 부분에서 흔함)"), ("T", "Trade 체결(주도 측)"),
                ("F", "Fill 수동 측 체결 통보"), ("N", "None 동작 없음(예: flags만 갱신)")]),
    ("side", [("B", "Bid 매수"), ("A", "Ask 매도"), ("N", "None(예: 방향이 없는 체결, 샘플링 레코드)")]),
    ("flags(비트)", [("128", "LAST: 하나의 거래소 이벤트가 여러 레코드로 나뉠 때 마지막 레코드에만 설정됨. "
                             "오더북 재구성 시 LAST 이후에 상태를 읽어야 한다"),
                    ("64", "TOB: top-of-book 메시지(해당 가격 레벨 전체를 대체)"), ("32", "SNAPSHOT: 스냅샷/리플레이에서 옴"),
                    ("16", "MBP: 집계된 가격 레벨 데이터로부터 합성"), ("8", "BAD_TS_RECV: ts_recv가 부정확"),
                    ("4", "MAYBE_BAD_BOOK: 패킷 누락 가능성, 오더북이 틀릴 수 있음"),
                    ("2", "PUBLISHER_SPECIFIC: 거래소 자체 정의")]),
    ("stat_type", [("1", "시가"), ("2", "예상 시가"), ("3", "정산가격"), ("4", "장중 최저가"), ("5", "장중 최고가"),
                   ("6", "청산 거래량"), ("7", "최저 매도호가"), ("8", "최고 매수호가"), ("9", "미결제약정 (open interest)"),
                   ("10", "기준가격 (fixing)"), ("11", "종가"), ("12", "등락"), ("13", "VWAP"), ("14", "변동성"),
                   ("15", "Delta")]),
    ("미정의 값 (sentinel)", [("INT64_MAX", "가격 미정의 9223372036854775807(— 로 표시)"),
                          ("UINT64_MAX", "타임스탬프 미정의 18446744073709551615"),
                          ("UINT32_MAX", "수량 미정의 4294967295")]),
]

TIPS = [
    "가격은 항상 정수 ÷ 1e9이다. 9223372036854775807은 '값 없음'을 뜻하므로 그대로 가격으로 계산하면 안 된다.",
    "시간은 모두 UTC 나노초다. 미국 주식 정규장 09:30–16:00 ET = 14:30–21:00 UTC(서머타임 13:30–20:00). "
    "도구 모음에서 시간대를 전환할 수 있다.",
    "ts_recv는 파일 정렬에 쓰이는 시각이고, ts_event는 거래소 시각으로 순서가 뒤섞이거나 미정의일 수 있다.",
    "MBO의 T/F는 오더북을 바꾸지 않으며, 실제로 수량을 줄이는 것은 뒤따르는 C/M이다. 오더북을 재구성할 때는 flags에 "
    "LAST가 포함되어야 하나의 완전한 이벤트가 된다.",
    "OPRA의 instrument_id는 날마다 다를 수 있으므로, 여러 날에 걸쳐 맞출 때는 id가 아니라 symbol을 사용해야 한다.",
    "-1s / -1m 샘플링 schema는 갱신이 있을 때만 레코드가 나오므로 직접 forward-fill해야 한다. price/size는 '가장 "
    "최근 체결'이지 해당 구간의 체결이 아니다.",
    "DBN v1 → v2 → v3: symbol 길이 22 → 71; InstrumentDef 360 → 400 → 520 bytes; StatMsg의 quantity는 v3에서 "
    "i32에서 i64로 변경(64 → 80 bytes). 이 viewer는 파일 헤더의 버전에 따라 자동으로 전환한다.",
    ".zst는 스트림 전체를 압축하므로 중간으로 임의 이동할 수 없다. 파일 뒷부분을 보려면 처음부터 디코딩해야 한다"
    "(시간 필터를 쓰면 필요한 행만 남길 수 있다).",
]


# --- added after the docs audit: remaining stat_type codes and the corrected statistics sentinel
def _patch():
    extra = ['단일가 체결가격(공식 시가/종가 제외)', '가격 상한', '가격 하한', '블록 거래량', '예상 종가', '서킷브레이커 1단계 (7%)', '서킷브레이커 2단계 (13%)', '서킷브레이커 3단계 (20%)', '경매 가격대 기준가', '경매 가격대 상한', '경매 가격대 하한', '거래소 고유 거래량 1', '거래소 고유 가격 1']
    for title, rows in ENUMS:
        codes = [c for c, _ in rows]
        if "15" in codes and "16" not in codes:
            rows.extend((str(c), d) for c, d in zip([16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 10001, 10002], extra))
        if "UINT32_MAX" in codes:
            i = codes.index("UINT32_MAX")
            rows[i] = ('INT32_MAX / INT64_MAX', 'statistics quantity 미정의 (v1/v2는 INT32_MAX, v3는 INT64_MAX)')


_patch()
