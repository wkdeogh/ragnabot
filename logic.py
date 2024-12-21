import os
import sys
import logging
import argparse
import math
import traceback
import time

import upbit
import linenotify
import datetime
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# ================================================
MINUTE_SETTING = 1
TICK = 5
SERACH_TIME = 60 #분

BUY_MODE_STOCHASTIC = 1
BUY_MODE_LOW_UP = 0
BUY_MODE_BOLBAND = 0

SELL_MODE_STOCHASTIC = 1
SELL_MODE_BOLBAND = 0
# ================================================

buy_stoc = 0
is_backtest = 0

def set_backtest():
    global is_backtest
    is_backtest = 1
    linenotify.set_no_message()


# ================================================
# 매수 로직
# ================================================
def decision_buy(target_item, tick):
    global buy_stoc

    # # 볼린저 밴드, 이평선
    bbdatas = upbit.get_bb(target_item, tick, '200', 100)
    bbp = ((bbdatas[0]['trade_price'] - bbdatas[0]['BBL']) / (bbdatas[0]['BBH'] - bbdatas[0]['BBL'])) * 100
    cur_price = bbdatas[0]['trade_price']

    bbps = []
    for i in range(0, 100):
        bbps.append(((bbdatas[i]['trade_price'] - bbdatas[i]['BBL']) / (bbdatas[i]['BBH'] - bbdatas[i]['BBL'])) * 100)

    # 거래량
    voldata, mps = upbit.get_vol(target_item, tick)

    # 매수 판단 로직
    score = 0

    if BUY_MODE_BOLBAND == 1:
        if (bbdatas[1]['low_price'] <= bbdatas[1]['BBL'] and bbdatas[0]['trade_price'] > bbdatas[0]['BBL']): # BB하한 상향돌파
            if not is_backtest: logging.info(f"[{target_item}] BB 하한 상향돌파 +10")
            score += 10
        
        if (bbdatas[0]['trade_price'] > ((bbdatas[1]['trade_price'] + bbdatas[1]['opening_price'])/2) ): # 전봉 중간 뚫고 올림
            if not is_backtest: logging.info(f"[{target_item}] 전봉 중간 뚫고 올림 +10")
            score += 10

        if(voldata[0] > voldata[1] and bbdatas[0]['trade_price'] > bbdatas[0]['opening_price']): # 거래량 상승, 양봉
            if not is_backtest: logging.info(f"[{target_item}] 거래량 상승, 양봉 +10")
            score += 10

        if((bbdatas[0]['trade_price'] + bbdatas[0]['opening_price'])/2 > (bbdatas[0]['high_price'] + bbdatas[0]['low_price'])/2 ): #몸통>가시
            if not is_backtest: logging.info(f"[{target_item}] 몸통>가시 +10")
            score += 10
        
        if (voldata[0] >= mps): # 거래량 > 평균+표준편차
            if not is_backtest: logging.info(f"[{target_item}] 거래량 > 평균+표준편차 +10")
            score += 10
    

    # 저점반등로직
    if BUY_MODE_LOW_UP == 1:
        real_low = []
        def is_real_low(data):
            return (data['low_price'] < data['BBL'])
        for bd in bbdatas[2:]:
            if is_real_low(bd):
                real_low.append(bd['low_price'])

        def is_blue_candle(data):
            return (data['trade_price'] < data['opening_price'])
        def is_red_candle(data):
            return (data['trade_price'] > data['opening_price'])
        if len(real_low) > 0:
            if (is_red_candle(bbdatas[0]) and is_blue_candle(bbdatas[1]) and is_blue_candle(bbdatas[2])): # 현재 저점 반등
                cur_low_price = bbdatas[1]['trade_price']
                if cur_low_price > real_low[0]: # 현재 저점이 최근 실저점보다 높음
                    if cur_low_price < bbdatas[0]['BBM']: # 저점이 BBP 50 미만
                        if not is_backtest: logging.info(f"[{target_item}] 저점반등")
                        score += 50

        # print(f"[DEBUG] C2:{is_blue_candle(bbdatas[2])} / C1:{is_blue_candle(bbdatas[1])} / C0:{is_red_candle(bbdatas[0])} / RL : {real_low[0]}")

    # 스토캐스틱
    if BUY_MODE_STOCHASTIC == 1:
        if is_backtest:
            print(f"{bbdatas[0]['date']}")

        stoc_data = upbit.get_stoc(target_item, tick, 10, 6)
        slowK = stoc_data['K']
        slowD = stoc_data['D']
        print(f"[5분봉] K1:{slowK[1]:.2f} / D1:{slowD[1]:.2f} / K0:{slowK[0]:.2f} / D0 : {slowD[0]:.2f}")
        if (slowK[1] < slowD[1] and slowK[0] >= slowD[0] and slowK[0] <= 80):
        # if (slowK[1] < slowD[1] and slowK[0] >= slowD[0]):
            print(f"[{target_item}] 스토캐스틱 5분봉 ok")
            buy_stoc = slowK[0]
            score += 30

        # if not is_backtest:
        #     score += ma_and_stoc('D', target_item, cur_price)
        #     score += ma_and_stoc('240', target_item, cur_price)
        score += ma_and_stoc('D', target_item, cur_price)
        score += ma_and_stoc('240', target_item, cur_price)


    if not is_backtest:
        logging.info(f"[{target_item:>12}]\t BBP: {bbp:>5.1f}\t mps: {mps:<11.2f}\t score: {score}")

    return score, bbdatas[0]['trade_price']


def ma_and_stoc(tick, target_item, cur_price):
    score = 0
    bb = upbit.get_bb(target_item, tick,'10', 2)
    ma = bb[0]['MA20']
    print(f"[{tick}] MA20 : {ma:,.0f} , 현재가 : {cur_price:,.0f}")
    if cur_price > ma:
        print(f"[{tick}] MA20 오케이")
        score += 5
    stoc = upbit.get_stoc(target_item, tick, 10, 6)
    slowK = stoc['K'][0]
    slowD = stoc['D'][0]
    print(f"[{tick}] slowK : {slowK:.2f} , slowD : {slowD:.2f}")
    if slowK > slowD:
        print(f"[{tick}] 스토캐스틱 오케이")
        score += 5
    return score


def getROR(start, end):
    return ((end - start)/start)*100

# ================================================
# 매도 로직
# ================================================
global_sellcnt = 0
global_bbpmax = 0
def decision_sell(target_item, tick, buyPrice):
    global global_sellcnt, global_bbpmax, is_backtest
    # # 볼린저 밴드, 이평선
    bbdatas = upbit.get_bb(target_item, tick, '200', 2)
    bbp = ((bbdatas[0]['trade_price'] - bbdatas[0]['BBL']) / (bbdatas[0]['BBH'] - bbdatas[0]['BBL'])) * 100
    if (bbp > global_bbpmax):
        global_bbpmax = bbp

    cur_price = bbdatas[0]['trade_price']

    # 거래량
    voldata, mps = upbit.get_vol(target_item, tick)

    # 현재 수익률
    RORnow = round(((bbdatas[0]['trade_price'] - buyPrice) / buyPrice)*100, 2)

    # 매도 판단 로직
    score = 0
    sell_logmsg = "\n"
    if SELL_MODE_BOLBAND == 1:
        ror_cut = 10 - (0.5 * global_sellcnt)
        if ror_cut < 3: ror_cut = 3
        if (bbdatas[1]['high_price'] >= bbdatas[1]['BBH'] and bbdatas[0]['trade_price'] < bbdatas[0]['BBH']):
            sell_logmsg += "\t\t\t[selling] BBH 하향\n"
            score += 10
        # if (bbdatas[0]['trade_price'] <= bbdatas[0]['BBL'] and bbdatas[1]['trade_price'] < bbdatas[1]['BBL']):
        #     sell_logmsg += "\t\t\t[selling] BBL 하향\n"
        #     score += 10
        if (RORnow < -2):
            sell_logmsg += "\t\t\t[selling] -2% 손절\n"
            score += 10
        # if ((bbdatas[0]['trade_price'] > bbdatas[0]['opening_price']) and ((bbdatas[0]['high_price'] + bbdatas[0]['low_price'])*0.4 > bbdatas[0]['trade_price'])):
        #     sell_logmsg += f"\t\t\t[selling] 역망치양봉 (고:{bbdatas[0]['high_price']:.1f} 저:{bbdatas[0]['low_price']:.1f} 현:{bbdatas[0]['trade_price']:.1f})\n"
        #     score += 10
        if(global_bbpmax >= 90 and bbp <= 30):
            sell_logmsg += "\t\t\t[selling] bbp 약세\n"
            score += 10
        if(global_bbpmax >= 100 and bbp < 100):
            sell_logmsg += "\t\t\t[selling] bbp 조정\n"
            score += 10
        # if (RORnow >= ror_cut) :
        #     sell_logmsg += f"\t\t\t[selling] 익절라인 {ror_cut:.1f}\n"
        #     score += 10


    # 스토캐스틱
    if SELL_MODE_STOCHASTIC == 1:
        stoc_data = upbit.get_stoc(target_item, tick, 10, 6)
        slowK = stoc_data['K']
        slowD = stoc_data['D']
        if not is_backtest: logging.info(f"[5분봉] K1:{slowK[1]:.2f} / D1:{slowD[1]:.2f} / K0:{slowK[0]:.2f} / D0 : {slowD[0]:.2f}")
        # if (slowK[1] >= slowD[1] and slowK[0] < slowD[0]):
        if (slowK[0] < slowD[0]):
            if slowK[0] >= (buy_stoc + 20) or slowK[0] >= 70 or slowK[0] < (buy_stoc - 10):
                if RORnow > 0:
                    sell_logmsg += "\t\t\t[selling] 스토캐스틱 \n"
                    print("[5분봉] 스토캐스틱 꺾여버렸어 팔아버려")
                    linenotify.send_line_message("[매도] 스토캐스틱")
                    score += 10

        # if RORnow < -10:
        #     sell_logmsg += "\t\t\t[selling] 손절 \n"
        #     linenotify.send_line_message("[매도] 손절")
        #     score += 10

        # if not is_backtest:
        #     score += ma_and_stoc_sell('D', target_item, cur_price)
        #     score += ma_and_stoc_sell('240', target_item, cur_price)
        score += ma_and_stoc_sell('D', target_item, cur_price)
        score += ma_and_stoc_sell('240', target_item, cur_price)

            # if (cur_price < day_ma10):
            #     sell_logmsg += f"\t\t\t[selling] 10일 이평선 cur:{cur_price}, ma10:{day_ma10}, \n"
            #     linenotify.send_line_message("[매도] MA10")
            #     score += 10

            # 거래대금
            # vol = upbit.get_acc24(target_item)
            # if vol < 80000000000:
            #     sell_logmsg += f"\t\t\t[selling] 거래대금하락, \n"
            #     linenotify.send_line_message("[매도] 거래대금하락")
            #     score += 10
    
    
    if not is_backtest: logging.info(f"[{target_item:>12}]\t BBP: {bbp:>5.1f}\t ror: {RORnow:>5.2f}\t global_sellcnt:{global_sellcnt:<3} \t score: {score}")
    # if score >= 10:
    #     if not is_backtest: logging.info(sell_logmsg)

    global_sellcnt += 1
    return score


def ma_and_stoc_sell(tick, target_item, cur_price):
    score = 0
    bb = upbit.get_bb(target_item, tick,'2', 1)
    ma = bb[0]['MA20']
    if cur_price < ma:
        print(f"[{tick}] 20일 이평선 아래로 내려가벼렸어 팔아버려")
        score += 10
    stoc = upbit.get_stoc(target_item, tick, 10, 6)
    slowK = stoc['K']
    slowD = stoc['D']
    if slowK < slowD:
        print(f"[{tick}] 스토캐스틱 내려갔어 팔아버려")
        score += 10
    return score



# ================================================
# 메인
# ================================================
virtual_KRW = None
virtual_Item = None

def main(test_mode=False):
    global virtual_KRW, virtual_Item, global_bbpmax, global_sellcnt
    try:
        print("===================================================")
        print(" - RagnaBotO (24/12/15)")
        print(" - 라그나봇 Original")
        print("===================================================\n")
        upbit.set_loglevel('I', test_mode)
        upbit.set_upbit_key()

        # local
        cur_item = 'KRW-BTC'
        errcnt = 0
        ntick = str(TICK)
        wait_time = TICK * 60
        search_interval = SERACH_TIME // TICK 
        sellmoney = 0
        loop_count = -1
        # ItemList = []
        ItemList = ['KRW-BTC']

        if test_mode:
            logging.info("TestMode Activate")
            linenotify.set_no_message()
            virtual_KRW = 10000000
        else:
            krwbal = upbit.get_krwbal()['available_krw']
            holdings = upbit.get_accounts("Y", "KRW")
            # 매도 후 시작
            if len(holdings) > 0:
                cur_item = holdings[0]['market']
                cur_balance = upbit.get_balance(cur_item)
                upbit.sellcoin_mp(cur_item, cur_balance)
        
        # #테스트
        # testitem = 'KRW-XRP'
        # deci, buyPrice = decision_buy(testitem, ntick)
        # deci = decision_sell(testitem, ntick, buyPrice)
        BTC_start_price = 0

        # loop start
        cur_state = "buying"
        logging.info("======= START TRADING =========")
        linenotify.send_line_message("START TRADING")
        while True:
            print("")
            loop_start_time = int(time.time())
            loop_count += 1
            logging.info("  ")
            logging.info(f"LOOP COUNT : {loop_count}")
            if test_mode:
                krwbal = virtual_KRW
            else:
                krwbal = upbit.get_krwbal()['available_krw']

            candle = upbit.get_candle(cur_item, ntick, 1)
            price = candle[0]['trade_price']
            if BTC_start_price == 0 : BTC_start_price = price
            else:
                cur_BTC_ror = getROR(BTC_start_price, price)
                logging.info(f" cur BTC ror : {cur_BTC_ror:.0f} %  (BTC start : {BTC_start_price:,.0f} / BTC cur : {price:,.0f})")
            if cur_state == "selling":
                if test_mode:
                    total_holdings_value = virtual_Item['balance']
                else:
                    total_holdings = float(upbit.get_balance(cur_item))
                    total_holdings_value = total_holdings * price
            else:
                total_holdings_value = 0

            total_assets = krwbal + total_holdings_value
            if cur_state == "selling":
                coin = virtual_Item['item'] if test_mode else cur_item
                logging.info(f">> 총자산 : {total_assets:,.0f} / KRW : {krwbal:,.0f} / {coin} : {total_holdings_value:,.0f}")
            else:
                logging.info(f">> 총자산 : {total_assets:,.0f} / KRW : {krwbal:,.0f}")

            # # 타겟 재검색
            # if (cur_state == 'buying'): 
            #     if len(ItemList) == 0 or (loop_count % search_interval == 0):
            #         ItemList = upbit.search_target()
            #         if (len(ItemList) == 0):
            #             logging.info("NO TARGET FOUND ..")
            #             continue

            # minute setting
            if MINUTE_SETTING == 1:
                logging.info(" minute setting..")
                t_now = datetime.datetime.now()
                while(not ((t_now.minute % TICK == (TICK-1)) and t_now.second >= 54)):
                    time.sleep(1)
                    t_now = datetime.datetime.now() 
                logging.info(" minute setting done")

            # error check
            if (cur_state == 'buying' and krwbal == 0):
                logging.info("ERROR(NO KRW) / state: %s / KRW: %d"%(cur_state, krwbal))
                errcnt += 1
                if errcnt == 10:
                    linenotify.send_line_message("[ERROR](NO KRW)\nstate: %s\nKRW: %d"%(cur_state, krwbal))
                    break
                time.sleep(10)
                continue

            if cur_state == 'buying':
                for Item in ItemList:     
                    deci, buyPrice = decision_buy(Item, ntick)
                    if (deci >= 50):
                        cur_state = 'selling'
                        buymoney = krwbal
                        if test_mode:
                            testmode_buy(Item, krwbal, ntick)
                        else:
                            upbit.buycoin_mp(Item, krwbal)
                        cur_item = Item
                        # ---------------------- make buy log --------------
                        linenotify.send_line_message(Item + " 매수")
                        logmsg = "[%s]"%(str(datetime.datetime.now())[:-10])
                        logmsg += " %s\tbuy_price: %d\n"%(cur_item, buymoney)
                        logging.info(logmsg)
                        # ---------------------------------------------------
                        break

            elif (cur_state == 'selling'):
                cur_balance = upbit.get_balance(cur_item)
                if cur_balance == 0:
                    linenotify.send_line_message("수동매도가 감지되었습니다. state->buying")
                    logging.info("수동 매도 감지")
                    cur_state = 'buying'
                    continue
                deci = decision_sell(cur_item, ntick, buyPrice)
                if (deci >= 10):
                    cur_state = 'buying'
                    global_bbpmax = 0
                    global_sellcnt = 0
                    if test_mode:
                        testmode_sell(cur_item, ntick)
                    else:
                        upbit.sellcoin_mp(cur_item, cur_balance)
                    # ---------------- make sell log ------------------------
                    time.sleep(1)
                    if test_mode:
                        sellmoney = virtual_KRW
                    else:
                        sellmoney = upbit.get_krwbal()['available_krw']
                    suik = sellmoney - buymoney
                    if buymoney > 0:
                        suikyul = round((suik / buymoney)*100,2)
                    else:
                        suikyul = 0
                    logging.info("수익률 : %0.2f"%(suikyul))
                    linenotify.send_line_message("\n매도수익 : %d\n수익률 : %0.2f"%(suik,suikyul))
                    logmsg = "[%s]"%(str(datetime.datetime.now())[:-10])
                    logmsg += " %s\tsell_price: %d\treturn: %d\tror: %0.2f\n"%(cur_item, sellmoney, suik, suikyul)
                    logging.info(logmsg)
                    time.sleep(3)
                    continue
                    # -----------------------------------------------------
   
            # time control
            one_loop_time = int(time.time()) - loop_start_time
            total_time = wait_time - 1 # 1초 마진
            if (total_time > one_loop_time):
                time.sleep(total_time - one_loop_time)
            

# ============================================================================
 
    except KeyboardInterrupt:
        logging.error("KeyboardInterrupt Exception 발생!")
        logging.error(traceback.format_exc())
        sys.exit(1)
 
    except Exception:
        linenotify.send_line_message("Exception 발생")
        logging.error("Exception 발생!")
        if not test_mode and cur_state == "selling":
            cur_balance = upbit.get_balance(cur_item)
            upbit.sellcoin_mp(cur_item, cur_balance)
        logging.error(traceback.format_exc())
        sys.exit(1)

# ================================================
# 테스트 모드
# ================================================
def testmode_buy(Item, krw, ntick):
    global virtual_KRW, virtual_Item
    buy_price = float(upbit.get_candle(Item, ntick, 1)[0]['trade_price'])
    quantity = krw / buy_price
    virtual_Item = {
        'item' : Item,
        'buy_price' : buy_price,
        'amount' : quantity,
        'balance' : krw
    }
    virtual_KRW -= krw
    # print("----------------------------------------------")
    # print("[테스트] 시장가 매수 완료")
    # print(f"[{Item}] {krw:,.0f}")
    # print("----------------------------------------------")

def testmode_sell(Item, ntick):
    global virtual_KRW, virtual_Item
    cur_price = float(upbit.get_candle(Item, ntick, 1)[0]['trade_price'])
    sell_val = (virtual_Item['amount'] * cur_price)
    virtual_KRW += sell_val
    virtual_Item = None
    # print("----------------------------------------------")
    # print("[테스트] 시장가 매도 완료")
    # print(f"{sell_val:,.0f}")
    # print("----------------------------------------------")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upbit Trading Bot")
    parser.add_argument('-test', action='store_true', help="테스트 모드 활성화")
    args = parser.parse_args()

    main(test_mode=args.test)