# encoding: UTF-8

import sys,os
from time import sleep

#from qtpy import QtGui

vnpy_root = os.path.abspath(os.path.join(os.path.dirname(__file__),'..','..','..','..','..'))
if vnpy_root not in sys.path:
    print(u'append {}'.format(vnpy_root))
    sys.path.append(vnpy_root)

from vnpy.api.ctp.vnctpmd import MdApi
from threading import Thread


#----------------------------------------------------------------------
def print_dict(d):
    """按照键值打印一个字典"""
    for key,value in d.items():
        print( key + ':' + str(value))


#----------------------------------------------------------------------
def simple_log(func):
    """简单装饰器用于输出函数名"""
    def wrapper(*args, **kw):
        print( "")
        print( str(func.__name__))
        return func(*args, **kw)
    return wrapper


########################################################################
class TestMdApi(MdApi):
    """测试用实例"""

    #----------------------------------------------------------------------
    def __init__(self):
        """Constructor"""
        super(TestMdApi, self).__init__()
        self.is_connected = False
    #----------------------------------------------------------------------
    @simple_log
    def onFrontConnected(self):
        """服务器连接"""
        print('tdtest.py: onFrontConnected')
        self.is_connected = True

    #----------------------------------------------------------------------
    @simple_log
    def onFrontDisconnected(self, n):
        """服务器断开"""
        print (n)
        self.is_connected = False
    #----------------------------------------------------------------------
    @simple_log
    def onHeartBeatWarning(self, n):
        """心跳报警"""
        print (n)

    #----------------------------------------------------------------------
    @simple_log
    def onRspError(self, error, n, last):
        """错误"""
        print_dict(error)

    @simple_log
    #----------------------------------------------------------------------
    def onRspUserLogin(self, data, error, n, last):
        """登陆回报"""
        print_dict(data)
        print_dict(error)
        print('onRspUserLogin')
    #----------------------------------------------------------------------
    @simple_log
    def onRspUserLogout(self, data, error, n, last):
        """登出回报"""
        print_dict(data)
        print_dict(error)

    #----------------------------------------------------------------------
    @simple_log
    def onRspSubMarketData(self, data, error, n, last):
        """订阅合约回报"""
        print_dict(data)
        print_dict(error)

    #----------------------------------------------------------------------
    @simple_log
    def onRspUnSubMarketData(self, data, error, n, last):
        """退订合约回报"""
        print_dict(data)
        print_dict(error)

    #----------------------------------------------------------------------
    @simple_log
    def onRtnDepthMarketData(self, data):
        """行情推送"""
        print_dict(data)

    #----------------------------------------------------------------------
    @simple_log
    def onRspSubForQuoteRsp(self, data, error, n, last):
        """订阅合约回报"""
        print_dict(data)
        print_dict(error)

    #----------------------------------------------------------------------
    @simple_log
    def onRspUnSubForQuoteRsp(self, data, error, n, last):
        """退订合约回报"""
        print_dict(data)
        print_dict(error)

    #----------------------------------------------------------------------
    @simple_log
    def onRtnForQuoteRsp(self, data):
        """行情推送"""
        print_dict(data)

# 长江
md_addr = "tcp://124.74.10.62:47213"
td_addr = "tcp://124.74.10.62:43205"
# 银河联通:
#md_addr = "tcp://114.255.82.175:31213"
#td_addr = "tcp://114.255.82.175:31205"
# 银河电信
#md_addr = "tcp://106.39.36.72:31213"
#td_addr = "tcp://106.39.36.72:31205"

user_id = "70000989"
user_pass = "cjqh@123"
app_id = "client_huafu_2.0.0"
auth_code = "T14ZHEJ5X7EH6VAM"
broker_id = '4300'

#----------------------------------------------------------------------
def main():
    """主测试函数，出现堵塞时可以考虑使用sleep"""
    reqid = 0

    # 创建Qt应用对象，用于事件循环
    #app = QtGui.QApplication(sys.argv)

    # 创建API对象
    api = TestMdApi()

    # 在C++环境中创建MdApi对象，传入参数是希望用来保存.con文件的地址
    print('create mdapi')
    api.createFtdcMdApi('')

    # 注册前置机地址
    print('mdtest:registerFront:{}'.format(md_addr))

    api.registerFront(md_addr)

    # 初始化api，连接前置机
    api.init()
    sleep(0.5)

    print('mdtest: login')
    # 登陆
    loginReq = {}                           # 创建一个空字典
    loginReq['UserID'] = user_id                 # 参数作为字典键值的方式传入
    loginReq['Password'] = user_pass               # 键名和C++中的结构体成员名对应
    loginReq['BrokerID'] = broker_id
    reqid = reqid + 1                       # 请求数必须保持唯一性
    i = api.reqUserLogin(loginReq, 1)
    counter = 0
    while (True):

        if api.is_connected:
            break

        sleep(1)
        counter += 1
        print('waiting {}'.format(counter))
        if counter > 10:
            print('time expired, connect fail, auth fail')
            exit(0)

    ## 登出，测试出错（无此功能）
    #reqid = reqid + 1
    #i = api.reqUserLogout({}, 1)
    #sleep(0.5)

    ## 安全退出，测试通过
    #i = api.exit()

    ## 获取交易日，目前输出为空
    #day = api.getTradingDay()
    #print 'Trading Day is:' + str(day)
    #sleep(0.5)

    ## 订阅合约，测试通过
    print('subscribe')
    i = api.subscribeMarketData('sc1906')

    ## 退订合约，测试通过
    #i = api.unSubscribeMarketData('IF1505')

    # 订阅询价，测试通过
    #i = api.subscribeForQuoteRsp('IO1504-C-3900')

    # 退订询价，测试通过
    #i = api.unSubscribeForQuoteRsp('IO1504-C-3900')




if __name__ == '__main__':
    # 主程序
    thread = Thread(target=main, args=())
    thread.start()
