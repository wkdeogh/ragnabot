import sys
import time
import argparse
import datetime
import logging
import json
import threading
import pickle

import upbit
import logic

paused = False
should_pause = False

def input_listener():
    global paused, should_pause
    for line in sys.stdin:
        line = line.strip()
        if line == 'a':
            # 일시정지 요청 -> 현재 루프 끝난 뒤에 일시정지할 거라서 should_pause 사용
            should_pause = True
        elif line == 's':
            # 재개
            paused = False

def get_multiple_candles(market, tick_kind, total_count):
    all_candles = []
    count_per_req = 200

    # 처음 요청 시에는 to 파라미터 없이 가장 최근 캔들 받기
    candles = upbit.get_candle(market, tick_kind, count_per_req)
    all_candles.extend(candles)

    # 이미 받은 갯수
    received_count = len(candles)

    # 추가로 받을 횟수 계산
    req_times = (total_count - received_count) // count_per_req
    if (total_count - received_count) % count_per_req > 0:
        req_times += 1

    # candles는 최신순으로 정렬되어 있으니, 가장 오래된 캔들의 시간정보를 이용해 더 과거데이터 요청
    for _ in range(req_times):
        if len(all_candles) == 0:
            break
        oldest_candle = all_candles[-1]  # all_candles는 계속 뒤에 쌓이므로 마지막이 가장 오래된 봉
        oldest_time_str = oldest_candle['candle_date_time_utc']  # 'YYYY-MM-DDTHH:MM:SS'
        # oldest_time_str을 datetime으로 변환
        oldest_time = datetime.datetime.strptime(oldest_time_str, "%Y-%m-%dT%H:%M:%S")
        # 1초 더 이전으로 이동해서 to 파라미터로 이용 (이 시간 이전 데이터 가져오기)
        to_time = oldest_time - datetime.timedelta(seconds=1)
        to_str = to_time.strftime("%Y-%m-%dT%H:%M:%S+00:00")

        # to 파라미터로 이전 데이터 요청
        candles = upbit.send_request("GET",
                                     upbit.server_url + f"/v1/candles/minutes/{tick_kind}",
                                     {"market": market, "count": count_per_req, "to": to_str},
                                     "")
        if candles.status_code == 200:
            cdata = candles.json()
            # cdata도 최신->과거 순
            all_candles.extend(cdata)
        else:
            # 에러 처리
            break

        # 만약 이미 원하는 개수 이상 받았으면 중단
        if len(all_candles) >= total_count:
            break

        # 요청 사이에 잠깐 쉬어주기(요청제한 방지)
        time.sleep(0.1)

    # 필요한 개수만큼 잘라내어 리턴
    return all_candles[:total_count]

def getROR(start, end):
    return ((end - start)/start)*100

def backtest(ticker, slow_mode=False, store_load='default', file_path='candle_data.pkl'):
    global paused, should_pause
    # 백테스트 파라미터
    tick_kind = "5"        # 5분봉
    candle_count = 2000    # 2000개 캔들 조회 (1년 105120)
    warmup = 200           # 앞부분 200개는 지표 계산 용도로만 사용

    # 입력 스레드 시작
    t = threading.Thread(target=input_listener, daemon=True)
    t.start()

    # 초기 가상 자산
    START_KRW = 10_000_000
    logic.virtual_KRW = START_KRW
    logic.virtual_Item = None
    logic.global_bbpmax = 0
    logic.global_sellcnt = 0

    # 로그레벨 설정
    upbit.set_loglevel('I', test_mode=True, backtest=True)
    upbit.set_upbit_key() # 실제 키를 사용안하지만 호출만 진행

    if store_load == 'load':
        print(f"[ load candle datas ] {file_path}")
        with open(file_path, 'rb') as file:  # 'rb'는 읽기 모드 + 바이너리 모드
            candles = pickle.load(file)
    else:
        # 캔들 데이터 가져오기 (과거 -> 최신)
        candles = get_multiple_candles(ticker, tick_kind, candle_count)
        # candles[0]이 가장 최근봉, candles[-1]이 가장 과거봉이라면 뒤집어서 처리
        # upbit.get_candle에서 반환되는 데이터는 최신순으로 정렬되어 있음
        # 백테스트 편의를 위해 오래된 데이터부터 순회하기 위해 reverse
        candles = list(reversed(candles))

    # store data
    if store_load == 'store':
        print(f"[ store candle datas start ] {file_path}")
        with open(file_path, 'wb') as file:  # 'wb'는 쓰기 모드 + 바이너리 모드
            pickle.dump(candles, file)
        print(f"[ store candle datas done ] {file_path}")
        return

    # warm-up 구간 이후부터 백테스트 시작
    start_index = warmup
    end_index = len(candles)

    # 로직에서 사용하는 상태 변수 세팅
    cur_state = "buying"   # 매수 대기 상태
    cur_item = ticker
    buy_price = 0
    buy_amount = 0
    buy_krw = 0

    prev_bal = 0

    # logic.py 내 함수들은 실시간 데이터를 get_candle로 가져가는데,
    # 여기서는 각 루프마다 현재 시간을 특정 candle로 가정하고
    # logic의 decision 함수를 호출하기 전에 testmode_buy, testmode_sell 할 때 해당 시점의 가격을 가져가도록 한다.
    #
    # 따라서 매 루프에서 현재 인덱스의 candle 기준으로 의사결정을 내린다고 가정한다.
    # decision_buy, decision_sell 함수는 logic.main에서 krwbal등을 가져다 쓰는데,
    # 여기서는 virtual_KRW와 virtual_Item로 대신한다.

    # 5분봉 당 5분을 실제로 대기하는 대신,
    # slow_mode=False일 경우 0.5초 정도 sleep을 줘서 실제 대기감을 주는 식으로 처리
    # slow_mode=True일 경우 sleep 없이 즉시 루프 진행(방법2)
    # 실제 5분 대기는 너무 길기 때문에 여기서는 간소화하여 0.5초 vs 0초 로 비교

    logging.basicConfig(level=print, format="[%(asctime)s][%(levelname)s]: %(message)s")

    print("==========================================")
    print(f"Backtest Start - Ticker: {ticker}, Slow: {slow_mode}")
    print("==========================================")

    monthly_logs = []
    mon_flag = False
    max_asset = 0
    min_asset = 9999999999

    for i in range(start_index, end_index):
        while paused:
            time.sleep(0.1)

        current_candle = candles[i]
        # print(f"Current Candle Data:\n{json.dumps(current_candle, indent=4, ensure_ascii=False)}")
        # 현재 시점 캔들 정보를 upbit.get_candle 호출 없이 logic 함수들이 참고할 수 있도록
        # testmode_buy/sell 함수에서 가격을 가져갈 때 upbit.get_candle(...) 1개를 호출하기 때문에
        # 이때 반환할 데이터에 영향을 주기 위해 mocking 비슷한 과정을 할 수도 있지만,
        # 여기서는 실제로 logic의 testmode_buy/sell은 upbit.get_candle을 통해 현재가를 얻는다.
        # 단, 매번 get_candle(1) 하면 항상 최신 최근봉을 가져오므로 지금 인덱스의 캔들을 현재봉으로 가정하기 어렵다.
        #
        # 해결 방법:
        # - logic.py를 수정할 수 없으므로, get_candle을 호출할 때마다 반환되는 데이터를 우리가 원하는 시점 데이터로 맞춰줄 필요가 있다.
        #   이를 위해 backtest.py에서 upbit.get_candle 함수를 monkey patching해서 원하는 시점의 캔들을 반환하도록 한다.
        #
        # monkey patch
        if not hasattr(upbit, '_original_get_candle'):
            upbit._original_get_candle = upbit.get_candle
        def mock_get_candle(target_item, tk, rng):
            rng = int(rng)  # 문자열로 들어온 rng를 정수로 변환
            end_slice = i+1
            start_slice = max(0, end_slice - rng)
            sliced = candles[start_slice:end_slice]
            # get_candle 원래 결과 포맷에 맞추기 위해 역순정렬(업비트API 결과가 최신->과거)
            return list(reversed(sliced))
        upbit.get_candle = mock_get_candle

        # 현재 가상 잔고
        krwbal = logic.virtual_KRW
        holding_amount = logic.virtual_Item['amount'] if logic.virtual_Item else 0
        holding_item = logic.virtual_Item['item'] if logic.virtual_Item else None
        holding_balance = logic.virtual_Item['balance'] if logic.virtual_Item else 0

        cur_asset = krwbal + holding_balance
        if cur_asset > max_asset:
            max_asset = cur_asset
        if cur_asset < min_asset:
            min_asset = cur_asset

        # 상태 출력
        date_str = current_candle['candle_date_time_kst']
        cur_year = int(date_str.split('T')[0].split('-')[0])
        cur_month = int(date_str.split('T')[0].split('-')[1])
        cur_day = int(date_str.split('T')[0].split('-')[2])
        trade_price = current_candle['trade_price']
        # print(f"[{date_str}] State: {cur_state}, KRW: {krwbal:,.0f}, Holding: {holding_item} {holding_amount:.6f}ea @ {trade_price}")

        # 월별 기록
        if cur_day == 1 and mon_flag == False:
            ror_acc = getROR(START_KRW, cur_asset)
            if prev_bal != 0:
                ror_mon = getROR(prev_bal, cur_asset)
            else:
                ror_mon = 0
                
            prev_bal = cur_asset
            mon_flag = True
            mon_log_data = {
                'asset' : cur_asset,
                'ror_acc' : ror_acc,
                'ror_mon' : ror_mon,
                'year' : cur_year,
                'month' : cur_month,
                'day' : cur_day,
            }
            monthly_logs.append(mon_log_data)
        if cur_day == 2:
            mon_flag = False

        logic.set_backtest()
        if cur_state == "buying":
            # ticker 하나만 백테스트 하므로 ItemList 개념은 없음.
            # decision_buy(ticker, tick_kind) 호출
            # decision_buy 반환값: score, 현재가격
            score, _ = logic.decision_buy(ticker, tick_kind)
            # score >= 40일 때 매수진행
            if score >= 30 and krwbal > 0:
                # 매수
                logic.testmode_buy(ticker, krwbal, tick_kind)
                buy_krw = krwbal
                # 매수 완료 후 상태 전환
                cur_state = "selling"
                # 매수가
                buy_price = logic.virtual_Item['buy_price']

                # krwbal = logic.virtual_KRW
                # holding_balance = logic.virtual_Item['balance'] if logic.virtual_Item else 0
                # cur_asset = krwbal + holding_balance
                # print("\n")
                # print(f"[{date_str}]")
                # print(f"State: {cur_state}")
                # print(f"Asset: {cur_asset:,.0f} ")
                # print(f"[BUY] ")

        elif cur_state == "selling":
            # decision_sell(ticker, tick_kind, buyPrice)
            score = logic.decision_sell(ticker, tick_kind, buy_price)
            # score >= 10이면 매도
            if score >= 10 and logic.virtual_Item:
                logic.testmode_sell(ticker, tick_kind)
                sell_krw = logic.virtual_KRW
                profit = sell_krw - buy_krw
                logic.global_bbpmax = 0
                logic.global_sellcnt = 0
                if buy_krw > 0:
                    ror = (profit / buy_krw) * 100
                else:
                    ror = 0.0
                # 다시 매수상태로 전환
                cur_state = "buying"

                krwbal = logic.virtual_KRW
                holding_balance = logic.virtual_Item['balance'] if logic.virtual_Item else 0
                cur_asset = krwbal + holding_balance
                print("\n")
                print(f"[{date_str}]")
                print(f"State: {cur_state}")
                print(f"Asset: {cur_asset:,.0f} ")
                print(f"[SELL] Profit: {profit:.0f} ROR: {ror:.2f}%")

        # 루프 종료 시점에서 should_pause 확인
        if should_pause:
            # 현재 루프는 이미 완료되었으니 이제 일시정지에 들어감
            should_pause = False
            paused = True

        # 루프간 대기
        if slow_mode:
            time.sleep(0.5)

    # 백테스트 종료 후 최종 자산 출력
    print("")
    for mon_logs in monthly_logs:
        print("==========================================")
        print(f" [{mon_logs['year']}-{mon_logs['month']}] ")
        print(f" Asset : {mon_logs['asset']}")
        print(f" Mon_ROR : {mon_logs['ror_mon']:.2f} %")
        print(f" Acc_ROR : {mon_logs['ror_acc']:.2f} %")
        
    final_krw = logic.virtual_KRW
    final_asset = final_krw
    if logic.virtual_Item:
        # 마지막에 청산(강제 매도) 가정
        # 마지막봉 가격으로 청산
        final_trade_price = candles[-1]['trade_price']
        final_asset += logic.virtual_Item['amount'] * final_trade_price
    start_price = candles[0]['trade_price']
    final_price = candles[-1]['trade_price']
    print("==========================================")
    print(f"Backtest start : {candles[0]['candle_date_time_kst']} / {start_price:,.0f}")
    print(f"Backtest end : {candles[-1]['candle_date_time_kst']} / {final_price:,.0f} / {getROR(start_price, final_price):.0f} %")
    print(f"Backtest End - Ticker: {ticker}")
    print(f"Max asset : {max_asset:,.0f} ")
    print(f"Min asset : {min_asset:,.0f} ")
    print(f"Final Asset: {final_asset:,.0f} KRW")
    print(f"profit ror: {getROR(START_KRW, final_asset):.0f} %")
    print("==========================================")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backtest for logic.py using upbit.py data")
    parser.add_argument('ticker', nargs='?', default='KRW-BTC', help='Ticker to test (default: KRW-BTC)')
    parser.add_argument('--slow', action='store_true', help='Run backtest slowly with sleep')
    parser.add_argument('--store', type=str, help='Path to store the backtest results')
    parser.add_argument('--load', type=str, help='Path to load previous backtest results')

    args = parser.parse_args()

    if args.store:
        sl = 'store'
        fp = args.store
    elif args.load:
        sl = 'load'
        fp = args.load
    else:
        sl = 'default'
        fp = None
    backtest(args.ticker, slow_mode=args.slow, store_load=sl, file_path=fp)
