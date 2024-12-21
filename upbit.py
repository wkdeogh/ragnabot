from calendar import c
import os
import logging
import requests
import time
import smtplib
import jwt
import sys
import uuid
import hashlib
import math
import numpy
import pandas as pd
from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import urlencode
 
# Keys
#access_key = os.environ['UPBIT_OPEN_API_ACCESS_KEY']
#secret_key = os.environ['UPBIT_OPEN_API_SECRET_KEY']
#server_url = os.environ['UPBIT_OPEN_API_SERVER_URL']
server_url = 'https://api.upbit.com'
access_key = ''
secret_key = ''
def set_upbit_key():
    global access_key, secret_key
    with open('upbit_key', 'r') as f:
        keys = f.readlines()
    access_key = keys[0].strip()
    secret_key = keys[1].strip()

# -----------------------------------------------------------------------------
# - Name : set_loglevel
# - Desc : 로그레벨 설정 및 파일과 콘솔에 동시에 로그 출력
# - Input
#   1) level : 로그레벨 ('D', 'E', 기타는 'I'로 처리)
# - Output
#   2) None
# -----------------------------------------------------------------------------
def set_loglevel(level, test_mode=False, backtest=False):
    try:
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)  # 최상위 로거 레벨 설정

        # Formatter 설정
        formatter = logging.Formatter('[%(asctime)s][%(levelname)s]: %(message)s', datefmt='%Y/%m/%d %I:%M:%S %p')

        # 파일 핸들러 설정 (UTF-8 인코딩)
        if backtest:
            file_name = 'Backtest.log'
        elif test_mode:
            file_name = 'TestTradeLog.log'
        else:
            file_name = 'TradeLog.log'
        file_handler = logging.FileHandler(file_name, encoding='utf-8')
        if level.upper() == "D":
            file_handler.setLevel(logging.DEBUG)
        elif level.upper() == "E":
            file_handler.setLevel(logging.ERROR)
        else:
            file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # 콘솔 핸들러 설정
        console_handler = logging.StreamHandler(sys.stdout)
        if level.upper() == "D":
            console_handler.setLevel(logging.DEBUG)
        elif level.upper() == "E":
            console_handler.setLevel(logging.ERROR)
        else:
            console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    except Exception as e:
        raise RuntimeError(f"로그 레벨 설정 중 오류 발생: {e}")
        
 
# -----------------------------------------------------------------------------
# - Name : send_request
# - Desc : 리퀘스트 처리
# - Input
#   1) reqType : 요청 타입
#   2) reqUrl : 요청 URL
#   3) reqParam : 요청 파라메타
#   4) reqHeader : 요청 헤더
# - Output
#   4) reponse : 응답 데이터
# -----------------------------------------------------------------------------
def send_request(reqType, reqUrl, reqParam, reqHeader):
    try:
 
        # 요청 가능회수 확보를 위해 기다리는 시간(초)
        err_sleep_time = 0.3
 
        # 요청에 대한 응답을 받을 때까지 반복 수행
        while True:
 
            # 요청 처리
            response = requests.request(reqType, reqUrl, params=reqParam, headers=reqHeader)
 
            # 요청 가능회수 추출
            if 'Remaining-Req' in response.headers:
 
                hearder_info = response.headers['Remaining-Req']
                start_idx = hearder_info.find("sec=")
                end_idx = len(hearder_info)
                remain_sec = hearder_info[int(start_idx):int(end_idx)].replace('sec=', '')
            else:
                logging.error("헤더 정보 이상")
                logging.error(response.headers)
                break
 
            # 요청 가능회수가 3개 미만이면 요청 가능회수 확보를 위해 일정시간 대기
            if int(remain_sec) < 3:
                logging.debug("요청 가능회수 한도 도달! 남은횟수:" + str(remain_sec))
                time.sleep(err_sleep_time)
 
            # 정상 응답
            if response.status_code == 200 or response.status_code == 201:
                break
            # 요청 가능회수 초과인 경우
            elif response.status_code == 429:
                logging.error("요청 가능회수 초과!:" + str(response.status_code))
                time.sleep(err_sleep_time)
            # 그 외 오류
            else:
                logging.error("기타 에러:" + str(response.status_code))
                logging.error(response.status_code)
                break
 
            # 요청 가능회수 초과 에러 발생시에는 다시 요청
            logging.info("[restRequest] 요청 재처리중...")
 
        return response
 
    # ----------------------------------------
    # Exception Raise
    # ----------------------------------------
    except Exception:
        raise
        
# -----------------------------------------------------------------------------
# - Name : get_candle
# - Desc : 캔들 조회
# - Input
#   1) target_item : 대상 종목
#   2) tick_kind : 캔들 종류 (1, 3, 5, 10, 15, 30, 60, 240 - 분, D-일, W-주, M-월)
#   3) inq_range : 조회 범위
# - Output
#   1) 캔들 정보 배열
#{'market': 'KRW-SAND', 
# 'candle_date_time_utc': '2022-01-13T10:50:00', 
# 'candle_date_time_kst': '2022-01-13T19:50:00', 
# 'opening_price': 6160.0, 'high_price': 6160.0, 
# 'low_price': 6150.0, 
# 'trade_price': 6150.0,  <-- 종가
# 'timestamp': 1642071082151, 
# 'candle_acc_trade_price': 59622312.32010475, 
# 'candle_acc_trade_volume': 9686.96537909, 
# 'unit': 5}
# -----------------------------------------------------------------------------
def get_candle(target_item, tick_kind, inq_range):
    try:
 
        # ----------------------------------------
        # Tick 별 호출 URL 설정
        # ----------------------------------------
        if tick_kind in ["1","3","5","10","15","30","60","240"]:
            target_url = "minutes/" + tick_kind
        elif tick_kind == "D":
            target_url = "days"
        elif tick_kind == "W":
            target_url = "weeks"
        elif tick_kind == "M":
            target_url = "months"
        else:
            raise ValueError(f"잘못된 틱 종류: {tick_kind}")
 
        # ----------------------------------------
        # Tick 조회
        # ----------------------------------------
        querystring = {"market": target_item, "count": inq_range}
        res = send_request("GET", server_url + "/v1/candles/" + target_url, querystring, "")
        candle_data = res.json()
 
        return candle_data
 
    # ----------------------------------------
    # Exception Raise
    # ----------------------------------------
    except Exception:
        raise
        
        
# -----------------------------------------------------------------------------
# - Name : get_bb
# - Desc : 볼린저밴드 조회
# - Input
#   1) target_item : 대상 종목
#   2) tick_kind : 캔들 종류 (1, 3, 5, 10, 15, 30, 60, 240 - 분, D-일, W-주, M-월)
#   3) inq_range : 캔들 조회 범위
#   4) loop_cnt : 지표 반복계산 횟수
# - Output
#   1) 볼린저 밴드 값
# -----------------------------------------------------------------------------
def get_bb(target_item, tick_kind, inq_range, loop_cnt):
    try:
 
        # 캔들 데이터 조회용
        candle_datas = []
 
        # 볼린저밴드 데이터 리턴용
        bb_list = []
 
        # 캔들 추출
        candle_data = get_candle(target_item, tick_kind, inq_range)
        
        # 조회 횟수별 candle 데이터 조합
        for i in range(0, int(loop_cnt)):
            candle_datas.append(candle_data[i:int(len(candle_data))])

        # 캔들 데이터만큼 수행
        for candle_data_for in candle_datas:
            df = pd.DataFrame(candle_data_for)
            dfDt = df['candle_date_time_kst'].iloc[::-1]
            df = df['trade_price'].iloc[::-1]
 
            # 표준편차(곱)
            unit = 2
 
            band1 = unit * numpy.std(df[len(df) - 20:len(df)])
            bb_center = numpy.mean(df[len(df) - 20:len(df)])
            ma_list = get_ma(candle_datas, 1)[0]
            ma_5 = ma_list['MA5']
            ma_10 = ma_list['MA10']
            ma_20 = ma_list['MA20']
            ma_30 = ma_list['MA30']
            ma_40 = ma_list['MA40']
            ma_60 = ma_list['MA60']
            ma_80 = ma_list['MA80']
            ma_120 = ma_list['MA120']
            band_high = bb_center + band1
            band_low = bb_center - band1
 
            bb_list.append({"type": "BB", "DT": dfDt[0], 
                            "BBH": round(band_high, 4), 
                            "BBM": round(bb_center, 4),
                            "BBL": round(band_low, 4), 
                            "MA5": round(ma_5, 8), 
                            "MA10": round(ma_10, 8),
                            "MA20": round(ma_20, 8),
                            "MA30": round(ma_30, 8), 
                            "MA40": round(ma_40, 8), 
                            "MA60": round(ma_60, 8), 
                            "MA80": round(ma_80, 8), 
                            "MA120": round(ma_120, 8),
                            "trade_price": candle_data_for[0]['trade_price'],
                            "opening_price": candle_data_for[0]['opening_price'],
                            "low_price": candle_data_for[0]['low_price'],
                            "high_price": candle_data_for[0]['high_price'],
                            "date" : candle_data_for[0]['candle_date_time_kst']
                            })
 
        return bb_list
 
 
    # ----------------------------------------
    # 모든 함수의 공통 부분(Exception 처리)
    # ----------------------------------------
    except Exception:
        raise



# -----------------------------------------------------------------------------
# - Name : get_ma
# - Desc : MA 조회
# - Input
#   1) candle_datas : 캔들 정보
#   2) loop_cnt : 반복 횟수
# - Output
#   1) MA 값
# -----------------------------------------------------------------------------
def get_ma(candle_datas, loop_cnt):
    try:
        # MA 데이터 리턴용
        ma_list = []
 
        df = pd.DataFrame(candle_datas[0])
        df = df.iloc[::-1]
        df = df['trade_price']
 
        # MA 계산
 
        ma5 = df.rolling(window=5).mean()
        ma10 = df.rolling(window=10).mean()
        ma20 = df.rolling(window=20).mean()
        ma30 = df.rolling(window=30).mean()
        ma40 = df.rolling(window=40).mean()
        ma60 = df.rolling(window=60).mean()
        ma80 = df.rolling(window=80).mean()
        ma120 = df.rolling(window=120).mean()
 
        for i in range(0, int(loop_cnt)):
            ma_list.append(
                {"type": "MA", "DT": candle_datas[0][i]['candle_date_time_kst'], "MA5": ma5[i], "MA10": ma10[i], "MA20": ma20[i],
                 "MA30": ma30[i],"MA40": ma40[i], "MA60": ma60[i],"MA80": ma80[i], "MA120": ma120[i]
                    , "MA_5_10": str(Decimal(str(ma5[i])) - Decimal(str(ma10[i])))
                    , "MA_10_30": str(Decimal(str(ma10[i])) - Decimal(str(ma30[i])))
                    , "MA_30_60": str(Decimal(str(ma30[i])) - Decimal(str(ma60[i])))
                    , "MA_60_120": str(Decimal(str(ma60[i])) - Decimal(str(ma120[i])))})
 
        return ma_list
 
    # ----------------------------------------
    # 모든 함수의 공통 부분(Exception 처리)
    # ----------------------------------------
    except Exception:
        raise



# -----------------------------------------------------------------------------
# - author : 장대호
# - Name : get_stoc
# - Desc : 스토캐스틱 조회 10,5,5
# - Input
# - 1) target_item : 종목
# - 2) 캔들(10분봉) 
# - 3) 캔들뽑는범위
# - 4) 캔들 몇번뽑을지
# - Output
#   1) stocastic %K, %D
# -----------------------------------------------------------------------------
def get_stoc(target_item, tick_kind, inq_range, loop_cnt):
    try:
        # inq_range = %K Length (ex: 10)
        # %K Smoothing = 5
        # %D Smoothing = 5
        k_length = inq_range
        k_smooth = 5
        d_smooth = 5

        # 캔들 데이터 가져오기: 충분히 많은 캔들 확보
        # loop_cnt개의 최종 데이터 얻기 위해 최소: inq_range + loop_cnt + (k_smooth - 1) + (d_smooth -1) 이상 필요
        # 넉넉히 inq_range + loop_cnt + 20 정도 가져간다.
        need_count = inq_range + loop_cnt + k_smooth + d_smooth
        candle_data = get_candle(target_item, tick_kind, need_count)
        # candle_data는 최신이 0번 인덱스, 과거로 갈수록 인덱스 증가
        # 계산 편의를 위해 역순정렬: oldest first
        candle_data = list(reversed(candle_data))

        closes = [c['trade_price'] for c in candle_data]
        highs = [c['high_price'] for c in candle_data]
        lows = [c['low_price'] for c in candle_data]

        # Fast %K 계산
        # %K = (Current Close - Lowest Low(k_length)) / (Highest High(k_length)-Lowest Low(k_length)) * 100
        fastK = []
        for i in range(len(candle_data)):
            if i < k_length - 1:
                # 초기 k_length 이전에는 계산 불가능
                fastK.append(None)
            else:
                recent_closes = closes[i-(k_length-1):i+1]
                recent_highs = highs[i-(k_length-1):i+1]
                recent_lows = lows[i-(k_length-1):i+1]

                lowest_low = min(recent_lows)
                highest_high = max(recent_highs)
                current_close = closes[i]

                if highest_high == lowest_low:
                    k_val = 100.0
                else:
                    k_val = ((current_close - lowest_low) / (highest_high - lowest_low)) * 100.0
                fastK.append(k_val)

        # fastK 중 None이 아닌 부분부터 슬로우K 적용
        # slowK = fastK의 5개 이동평균
        def moving_avg(arr, length):
            result = []
            for i in range(len(arr)):
                if i < length-1 or arr[i] is None:
                    result.append(None)
                else:
                    window = [x for x in arr[i-(length-1):i+1] if x is not None]
                    if len(window) < length:
                        result.append(None)
                    else:
                        result.append(sum(window)/length)
            return result

        slowK = moving_avg(fastK, k_smooth)
        slowD = moving_avg(slowK, d_smooth)

        # slowD까지 계산된 상태에서 slowK, slowD 중 None이 아닌 마지막 부분(가장 최근 지표들) 중 loop_cnt개 추출
        # slowD와 slowK는 oldest first. 가장 마지막 값이 최신.
        # 하지만 최종 return은 가장 최근값이 index 0번
        # 즉, slowK[-1]이 가장 최신, slowK[-2]는 한 캔들 전 ...

        # None이 아닌 값들만 필터링
        valid_indices = [i for i, v in enumerate(slowD) if v is not None]

        if len(valid_indices) < loop_cnt:
            # 유효한 데이터가 loop_cnt개보다 적다면 나머지는 일단 버림
            # 혹은 예외 처리
            loop_cnt = len(valid_indices)

        # 가장 최근 loop_cnt개 인덱스 추출
        end_idx = valid_indices[-1]  # 마지막 유효 인덱스 (가장 최근)
        start_idx = valid_indices[-loop_cnt]  # 최근 loop_cnt개 중 첫 시작 인덱스

        recent_slowK = slowK[start_idx:end_idx+1]
        recent_slowD = slowD[start_idx:end_idx+1]

        # 현재 최신값을 0번 인덱스로 하고 싶으니 reverse
        recent_slowK.reverse()
        recent_slowD.reverse()

        stoc_data = {
            'K': recent_slowK,
            'D': recent_slowD
        }

        return stoc_data
    except Exception as e:
        raise e


# -----------------------------------------------------------------------------
# - author : 장대호
# - Name : get_vol
# - Desc : 거래량뽑기
# - Input
# - 1) target_item : 종목
# - 2) 틱 종류
# - Output
#   1) 2틱 거래량
# -----------------------------------------------------------------------------
def get_vol(target_item, tick_kind): 
    try:
        volume_data = []

        candle_data = get_candle(target_item, tick_kind, 20)

        # volume_data.append(candle_data[0]['candle_acc_trade_volume'])
        # volume_data.append(candle_data[1]['candle_acc_trade_volume'])
        for i in range(20):
            volume_data.append(candle_data[i]['candle_acc_trade_volume'])

        meanpstd = numpy.mean(volume_data) + numpy.std(volume_data)

        return volume_data, meanpstd

    except Exception:
        raise


# =============================================================================
#                                                                      매매 로직
# =============================================================================

# -----------------------------------------------------------------------------
# - Name : buycoin_mp
# - Desc : 시장가 매수
# - Input
#   1) target_item : 대상종목
#   2) buy_amount : 매수금액
# - Output
#   1) rtn_data : 매수결과
# -----------------------------------------------------------------------------
def buycoin_mp(target_item, buy_amount):
    try:
 
        query = {
            'market': target_item,
            'side': 'bid',
            'price': buy_amount,
            'ord_type': 'price',
        }
 
        query_string = urlencode(query).encode()
 
        m = hashlib.sha512()
        m.update(query_string)
        query_hash = m.hexdigest()
 
        payload = {
            'access_key': access_key,
            'nonce': str(uuid.uuid4()),
            'query_hash': query_hash,
            'query_hash_alg': 'SHA512',
        }
 
        jwt_token = jwt.encode(payload, secret_key)
        authorize_token = 'Bearer {}'.format(jwt_token)
        headers = {"Authorization": authorize_token}
 
        res = send_request("POST", server_url + "/v1/orders", query, headers)
        rtn_data = res.json()
 
        logging.info("----------------------------------------------")
        logging.info("시장가 매수 완료")
        logging.info("[%s] %s"%(rtn_data['market'],rtn_data['price']))
        logging.info("----------------------------------------------")
 
        return rtn_data
 
    # ----------------------------------------
    # Exception Raise
    # ----------------------------------------
    except Exception:
        raise


# -----------------------------------------------------------------------------
# - Name : get_balance
# - Desc : 주문가능 잔고 조회
# - Input
#   1) target_item : 대상 종목
# - Output
#   2) rtn_balance : 주문가능 잔고
# -----------------------------------------------------------------------------
def get_balance(target_item):
    try:
 
        # 주문가능 잔고 리턴용
        rtn_balance = 0
 
        # 최대 재시도 횟수
        max_cnt = 0
 
        payload = {
            'access_key': access_key,
            'nonce': str(uuid.uuid4()),
        }
 
        jwt_token = jwt.encode(payload, secret_key)
        authorize_token = 'Bearer {}'.format(jwt_token)
        headers = {"Authorization": authorize_token}
 
        # 잔고가 조회 될 때까지 반복
        while True:
 
            # 조회 회수 증가
            max_cnt = max_cnt + 1
 
            res = send_request("GET", server_url + "/v1/accounts", "", headers)
            my_asset = res.json()
 
            # 해당 종목에 대한 잔고 조회
            # 잔고는 마켓에 상관없이 전체 잔고가 조회됨
            for myasset_for in my_asset:
                if myasset_for['currency'] == target_item.split('-')[1]:
                    rtn_balance = myasset_for['balance']
 
            # 잔고가 0 이상일때까지 반복
            if Decimal(str(rtn_balance)) >= Decimal(str(0)):
                break
 
            # 최대 100회 수행
            if max_cnt > 100:
                break
 
            logging.info("[주문가능 잔고 리턴용] 요청 재처리중...")
 
        return rtn_balance
 
    # ----------------------------------------
    # Exception Raise
    # ----------------------------------------
    except Exception:
        raise

# -----------------------------------------------------------------------------
# - Name : sellcoin_mp
# - Desc : 시장가 매도
# - Input
#   1) target_item : 대상종목
# - Output
#   1) rtn_data : 매도결과
# -----------------------------------------------------------------------------
# 시장가 매도
def sellcoin_mp(target_item, balance):
    try:
 
        # 잔고 조회
        cur_balance = get_balance(target_item)
        if (float(balance) > float(cur_balance)):
           logging.info("매도 잔고 부족")
           return -1

        query = {
            'market': target_item,
            'side': 'ask',
            'volume': str(balance),
            'ord_type': 'market',
        }
 
        query_string = urlencode(query).encode()
 
        m = hashlib.sha512()
        m.update(query_string)
        query_hash = m.hexdigest()
 
        payload = {
            'access_key': access_key,
            'nonce': str(uuid.uuid4()),
            'query_hash': query_hash,
            'query_hash_alg': 'SHA512',
        }
 
        jwt_token = jwt.encode(payload, secret_key)
        authorize_token = 'Bearer {}'.format(jwt_token)
        headers = {"Authorization": authorize_token}
 
        res = send_request("POST", server_url + "/v1/orders", query, headers)
        rtn_data = res.json()
 
        logging.info("----------------------------------------------")
        logging.info("시장가 매도 완료")
        logging.info(rtn_data)
        logging.info("----------------------------------------------")
 
        return rtn_data
 
    # ----------------------------------------
    # Exception Raise
    # ----------------------------------------
    except Exception:
        raise





# -----------------------------------------------------------------------------
# - Name : get_accounts
# - Desc : 잔고정보 조회
# - Input
#   1) except_yn : KRW 및 소액 제외
#   2) market_code : 마켓코드 추가(매도시 필요)
# - Output
#   1) 잔고 정보
# -----------------------------------------------------------------------------
# 계좌 조회
def get_accounts(except_yn, market_code):
    try:
 
        rtn_data = []
 
        # 소액 제외 기준
        min_price = 5000
 
        payload = {
            'access_key': access_key,
            'nonce': str(uuid.uuid4()),
        }
 
        jwt_token = jwt.encode(payload, secret_key)
        authorize_token = 'Bearer {}'.format(jwt_token)
        headers = {"Authorization": authorize_token}
 
        res = send_request("GET", server_url + "/v1/accounts", "", headers)
        account_data = res.json()
 
        for account_data_for in account_data:
 
            # KRW 및 소액 제외
            if except_yn == "Y" or except_yn == "y":
                if account_data_for['currency'] != "KRW" and Decimal(str(account_data_for['avg_buy_price'])) * (Decimal(str(account_data_for['balance'])) + Decimal(str(account_data_for['locked']))) >= Decimal(str(min_price)):
                    rtn_data.append(
                        {'market': market_code + '-' + account_data_for['currency'], 'balance': account_data_for['balance'],
                         'locked': account_data_for['locked'],
                         'avg_buy_price': account_data_for['avg_buy_price'],
                         'avg_buy_price_modified': account_data_for['avg_buy_price_modified']})
            else:
                rtn_data.append(
                    {'market': market_code + '-' + account_data_for['currency'], 'balance': account_data_for['balance'],
                     'locked': account_data_for['locked'],
                     'avg_buy_price': account_data_for['avg_buy_price'],
                     'avg_buy_price_modified': account_data_for['avg_buy_price_modified']})
 
        return rtn_data
 
    # ----------------------------------------
    # Exception Raise
    # ----------------------------------------
    except Exception:
        raise

# -----------------------------------------------------------------------------
# - Name : get_krwbal
# - Desc : KRW 잔고 조회
# - Input
# - Output
#   1) KRW 잔고 Dictionary
#     1. krw_balance : KRW 잔고
#     2. fee : 수수료
#     3. available_krw : 매수가능 KRW잔고(수수료를 고려한 금액)
# -----------------------------------------------------------------------------
def get_krwbal():
    try:
 
        # 잔고 리턴용
        rtn_balance = {}
 
        # 수수료 0.05%(업비트 기준)
        fee_rate = 0.05
 
        payload = {
            'access_key': access_key,
            'nonce': str(uuid.uuid4()),
        }
 
        jwt_token = jwt.encode(payload, secret_key)
        authorize_token = 'Bearer {}'.format(jwt_token)
        headers = {"Authorization": authorize_token}
 
        res = send_request("GET", server_url + "/v1/accounts", "", headers)
        data = res.json()
        for dataFor in data:
            if (dataFor['currency']) == "KRW":
                krw_balance = math.floor(Decimal(str(dataFor['balance'])))
 
        # 잔고가 있는 경우만
        if Decimal(str(krw_balance)) > Decimal(str(0)):
            # 수수료
            fee = math.ceil(Decimal(str(krw_balance)) * (Decimal(str(fee_rate)) / Decimal(str(100))))
 
            # 매수가능금액
            available_krw = math.floor(Decimal(str(krw_balance)) - Decimal(str(fee)))
 
        else:
            # 수수료
            fee = 0
 
            # 매수가능금액
            available_krw = 0
 
        # 결과 조립
        rtn_balance['krw_balance'] = krw_balance
        rtn_balance['fee'] = fee
        rtn_balance['available_krw'] = available_krw
 
        return rtn_balance
 
    # ----------------------------------------
    # Exception Raise
    # ----------------------------------------
    except Exception:
        raise


# def get_ma(df, n):
#     return df['close'].rolling(window=n).mean()


def get_acc24(target_item):
    headers = {"Accept": "application/json"}
    url = "https://api.upbit.com/v1/ticker?markets=" + target_item
    response = requests.request("GET", url, headers=headers)
    atp = response.json()[0]['acc_trade_price_24h']
    return atp


def get_rising_items():
    try:
        logging.info(" - SEARCHING TARGETS ")

        url = "https://api.upbit.com/v1/market/all?isDetails=false"
        headers = {"Accept": "application/json"}
        response = requests.request("GET", url, headers=headers)
        tickers = response.json()

        arr = []

        # print("┌──────────────────────────────────────────────────────────────────────────────────────────────────────────┐")
        for r in tickers:
            markets = r['market']
            if not markets.startswith("KRW"):
                continue
            if markets in ["KRW-USDT"]:
                continue
            if markets not in ["KRW-BTC", "KRW-XRP"]: ## 지정
                continue
            cd = get_candle(markets, 'D', 100)
            if (len(cd) < 100):
                continue

            url = "https://api.upbit.com/v1/ticker?markets=" + markets
            response = requests.request("GET", url, headers=headers)
            atp = response.json()[0]['acc_trade_price_24h']

            bb = get_bb(markets, 'D', '10', 1)
            ma = bb[0]['MA10']
            tp = bb[0]['trade_price']
            if (atp > 90000000000 and tp > ma): #100,000 백만
                arr.append((atp, markets))
            print(":", end='', flush=True)
            time.sleep(0.1)

        print(">", flush=True)

        toptick = sorted(arr)
        return reversed(toptick)

    except Exception:
        raise

    #195526008645
    #100000000000 100,000백만


def search_target():
    targetitems = get_rising_items()
    logstr = "[NEW TARGETS] : "
    ItemList = []
    for tg in targetitems:
        logstr += f"{str(tg[1])} "
        ItemList.append(tg[1])
    logging.info(logstr)
    return ItemList
