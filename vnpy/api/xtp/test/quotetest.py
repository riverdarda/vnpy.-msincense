# encoding: UTF-8

from __future__ import print_function
import os
from time import sleep
import sys
XTP_API_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(XTP_API_PATH)

from vnxtpquote import *

#----------------------------------------------------------------------
def printDict(d):
    """"""
    print('-' * 50)
    l = d.keys()
    l = sorted(l)
    for k in l:
        print(k, d[k])


########################################################################
class TestApi(QuoteApi):
    """"""

    #----------------------------------------------------------------------
    def __init__(self):
        """Constructor"""
        super(TestApi, self).__init__()

    #----------------------------------------------------------------------
    def onDisconnected(self, reason):
        """"""
        print('disconnect', reason)

    #----------------------------------------------------------------------
    def onError(self, data):
        """"""
        print('error')
        printDict(data)

    #----------------------------------------------------------------------
    def onSubMarketData(self, data, error, last):
        """"""
        print('sub market data')
        printDict(data)
        printDict(error)

    #----------------------------------------------------------------------
    def onUnSubMarketData(self, data, error, last):
        """"""
        print('unsub market data')
        printDict(data)
        printDict(error)

    #----------------------------------------------------------------------
    def onMarketData(self, data):
        """"""
        print('new market data')
        printDict(data)

    #----------------------------------------------------------------------
    def onQueryAllTickers(self):
        """"""
        pass


if __name__ == '__main__':
    ip = '120.27.164.138'
    port = 6002
    user = 'xxx'
    password = 'xxx'

    # 创建API并初始化
    api = TestApi()

    api.createQuoteApi(1, os.getcwd())

    # 登录
    n = api.login(ip, port, user, password, 1)
    print('login result', n)

    # 订阅行情
    api.subscribeMarketData([{'ticker':'000001'}],1,1)

    # 取消订阅
    sleep(5)
    api.unSubscribeMarketData([{'ticker':'000001'}], 1,1)

    # 阻塞
    _input = input('press any key')
