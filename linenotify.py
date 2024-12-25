import time
import logging
import requests
import jwt
import uuid
import hashlib
import math
import os
import pandas as pd
import numpy
 
from urllib.parse import urlencode
from decimal import Decimal
 
# Keys
line_target_url = 'https://notify-api.line.me/api/notify'
line_token = 'rZQAywLZC640aKnGvrWedHFxnpnlvowYdIR0DdJLKXu'
 
 
# -----------------------------------------------------------------------------
# - Name : set_loglevel
# - Desc : 로그레벨 설정
# - Input
#   1) level : 로그레벨
#     1. D(d) : DEBUG
#     2. E(e) : ERROR
#     3. 그외(기본) : INFO
# - Output
# -----------------------------------------------------------------------------
def set_loglevel(level):
    try:
 
        # ---------------------------------------------------------------------
        # 로그레벨 : DEBUG
        # ---------------------------------------------------------------------
        if level.upper() == "D":
            logging.basicConfig(
                format='[%(asctime)s][%(levelname)s][%(filename)s:%(lineno)d]:%(message)s',
                datefmt='%Y/%m/%d %I:%M:%S %p',
                level=logging.DEBUG
            )
        # ---------------------------------------------------------------------
        # 로그레벨 : ERROR
        # ---------------------------------------------------------------------
        elif level.upper() == "E":
            logging.basicConfig(
                format='[%(asctime)s][%(levelname)s][%(filename)s:%(lineno)d]:%(message)s',
                datefmt='%Y/%m/%d %I:%M:%S %p',
                level=logging.ERROR
            )
        # ---------------------------------------------------------------------
        # 로그레벨 : INFO
        # ---------------------------------------------------------------------
        else:
            # -----------------------------------------------------------------------------
            # 로깅 설정
            # 로그레벨(DEBUG, INFO, WARNING, ERROR, CRITICAL)
            # -----------------------------------------------------------------------------
            logging.basicConfig(
                format='[%(asctime)s][%(levelname)s][%(filename)s:%(lineno)d]:%(message)s',
                datefmt='%Y/%m/%d %I:%M:%S %p',
                level=logging.INFO
            )
 
    # ----------------------------------------
    # Exception Raise
    # ----------------------------------------
    except Exception:
        raise
        
no_message = False
def set_no_message():
    global no_message
    no_message = True
 
# -----------------------------------------------------------------------------
# - Name : send_line_msg
# - Desc : 라인 메세지 전송
# - Input
#   1) message : 메세지
# - Output
#   1) response : 발송결과(200:정상)
# -----------------------------------------------------------------------------
def send_line_message(message):
    global no_message
    if no_message:
        return
    try:
        headers = {'Authorization': 'Bearer ' + line_token}
        data = {'message': message}
 
        response = requests.post(line_target_url, headers=headers, data=data)        
 
        return response
 
    # ----------------------------------------
    # 모든 함수의 공통 부분(Exception 처리)
    # ----------------------------------------
    except Exception:
        raise