# encoding: UTF-8

# AUTHOR:李来佳
# WeChat/QQ: 28888502
# 广东华富资产管理

import sys,os,csv
from datetime import datetime,timedelta
import talib as ta
import numpy as np
import math
import decimal
import copy,csv
from pykalman import KalmanFilter
import traceback

from vnpy.trader.app.ctaStrategy.ctaBase import *
from vnpy.trader.vtConstant import *
from vnpy.trader.vtConstant import DIRECTION_LONG, DIRECTION_SHORT
from vnpy.trader.app.ctaStrategy.ctaPeriod import *

DEBUGCTALOG = True

PERIOD_SECOND = 'second'  # 秒级别周期
PERIOD_MINUTE = 'minute'  # 分钟级别周期
PERIOD_HOUR = 'hour'  # 小时级别周期
PERIOD_DAY = 'day'  # 日级别周期
PERIOD_WEEK = 'week'  # 日级别周期

AREA_LONG_A = 'LONG_A'
AREA_LONG_B = 'LONG_B'
AREA_LONG_C = 'LONG_C'
AREA_LONG_D = 'LONG_D'
AREA_LONG_E = 'LONG_E'

AREA_SHORT_A = 'SHORT_A'
AREA_SHORT_B = 'SHORT_B'
AREA_SHORT_C = 'SHORT_C'
AREA_SHORT_D = 'SHORT_D'
AREA_SHORT_E = 'SHORT_E'

def getCtaBarClass(bar_type):
    assert  isinstance(bar_type,str)
    if bar_type == PERIOD_SECOND:
        return CtaLineBar
    if bar_type == PERIOD_MINUTE:
        return CtaMinuteBar
    if bar_type == PERIOD_HOUR:
        return CtaHourBar
    if bar_type == PERIOD_DAY:
        return CtaDayBar

    raise Exception('no matched CTA  bar type:{}'.format(bar_type))


class CtaLineBar(object):
    """CTA K线"""
    """ 使用方法:
    1、在策略构造函数__init()中初始化
    self.lineM = None                       # 1分钟K线
    lineMSetting = {}
    lineMSetting['name'] = u'M1'
    lineMSetting['barTimeInterval'] = 60    # 1分钟对应60秒
    lineMSetting['inputEma1Len'] = 7        # EMA线1的周期
    lineMSetting['inputEma2Len'] = 21       # EMA线2的周期
    lineMSetting['inputBollLen'] = 20       # 布林特线周期
    lineMSetting['inputBollStdRate'] = 2    # 布林特线标准差
    lineMSetting['minDiff'] = self.minDiff  # 最小条
    lineMSetting['shortSymbol'] = self.shortSymbol  #商品短号
    self.lineM = CtaLineBar(self, self.onBar, lineMSetting)

    2、在onTick()中，需要导入tick数据
    self.lineM.onTick(tick)
    self.lineM5.onTick(tick) # 如果你使用2个周期

    3、在onBar事件中，按照k线结束使用；其他任何情况下bar内使用，通过对象使用即可，self.lineM.lineBar[-1].close
    
    # 创建30分钟K线（类似文华，用交易日内，累加分钟够30根1min bar）
    lineM30Setting = {}
    lineM30Setting['name'] = u'M30'
    lineM30Setting['period'] = PERIOD_MINUTE
    lineM30Setting['barTimeInterval'] = 2       
    lineM30Setting['mode'] = CtaLineBar.TICK_MODE
    lineM30Setting['minDiff'] = self.minDiff
    lineM30Setting['shortSymbol'] = self.shortSymbol
    self.lineM30 = CtaHourBar(self, self.onBarM30, lineM30Setting)
    
    # 创建2小时K线
    lineH2Setting = {}
    lineH2Setting['name'] = u'H2'
    lineH2Setting['period'] = PERIOD_HOUR
    lineH2Setting['barTimeInterval'] = 2       
    lineH2Setting['mode'] = CtaLineBar.TICK_MODE
    lineH2Setting['minDiff'] = self.minDiff
    lineH2Setting['shortSymbol'] = self.shortSymbol
    self.lineH2 = CtaHourBar(self, self.onBarH2, lineH2Setting)

    # 创建的日K线
    lineDaySetting = {}
    lineDaySetting['name'] = u'D1'
    lineDaySetting['barTimeInterval'] = 1        
    lineDaySetting['mode'] = CtaDayBar.TICK_MODE
    lineDaySetting['minDiff'] = self.minDiff
    lineDaySetting['shortSymbol'] = self.shortSymbol
    self.lineD = CtaDayBar(self, self.onBarD, lineDaySetting)
            
    """

    # 区别：
    # -使用tick模式时，当tick到达后，最新一个lineBar[-1]是当前的正在拟合的bar，不断累积tick，传统按照OnBar来计算的话，是使用LineBar[-2]。
    # -使用bar模式时，当一个bar到达时，lineBar[-1]是当前生成出来的Bar,不再更新
    TICK_MODE = 'tick'
    BAR_MODE = 'bar'

    # 参数列表，保存了参数的名称
    paramList = ['vtSymbol']
    # 参数列表

    def __init__(self, strategy, onBarFunc, setting=None):

        # OnBar事件回调函数
        self.onBarFunc = onBarFunc

        # 周期变更事件回调函数
        self.onPeriodChgFunc = None

        # K 线服务的策略
        self.strategy = strategy

        self.shortSymbol = EMPTY_STRING  # 商品的短代码
        self.minDiff = 1  # 商品的最小价格单位
        self.round_n = 4  # round() 小数点的截断数量

        self.is_7x24 = False

        # 当前的Tick
        self.curTick = None
        self.lastTick = None
        self.curTradingDay = EMPTY_STRING

        self.cur_price = EMPTY_FLOAT

        # K线保存数据
        self.bar = None  # K线数据对象
        self.lineBar = []  # K线缓存数据队列
        self.max_hold_bars = 60 * 20
        self.barFirstTick = False  # K线的第一条Tick数据

        # (实时运行时，或者addbar小于bar得周期时，不包含最后一根Bar）
        self.lineOpen = []        # 与lineBar一致得开仓价清单
        self.lineHigh = []        # 与lineBar一致得最高价清单
        self.lineLow = []         # 与lineBar一致得最低价清单
        self.lineClose = []       # 与lineBar一致得收盘价清单

        self.export_filename = None
        self.export_fields = []

        # 创建内部变量
        self.init_properties()

        # 创建初始化指标
        self.init_indicators()

        # 启动实时得函数
        self.rt_funcs = set()

        if setting:
            self.setParam(setting)

            # 修正self.barMinuteInterval
            if self.period == PERIOD_SECOND:
                self.barMinuteInterval = int(self.barTimeInterval / 60)
            elif self.period == PERIOD_MINUTE:
                self.barMinuteInterval = self.barTimeInterval
            elif self.period == PERIOD_HOUR:
                self.barMinuteInterval = 60
            elif self.period == PERIOD_DAY:
                self.barMinuteInterval = 60 * 24
            # 修正精度
            if self.minDiff < 1:

                exponent = decimal.Decimal(str(self.minDiff))
                self.round_n = abs(exponent.as_tuple().exponent)

            ## 导入卡尔曼过滤器
            if self.inputKF:
                try:
                    self.kf = KalmanFilter(transition_matrices=[1],
                                           observation_matrices=[1],
                                           initial_state_mean=0,
                                           initial_state_covariance=1,
                                           observation_covariance=1,
                                           transition_covariance=0.01)
                except:
                    self.writeCtaLog(u'导入卡尔曼过滤器失败,需先安装 pip install pykalman')
                    self.inputKF = False

    def init_properties(self):
        """
        初始化内部变量
        :return:
        """
        self.paramList.append('barTimeInterval')
        self.paramList.append('period')
        self.paramList.append('inputPreLen')
        self.paramList.append('inputEma1Len')
        self.paramList.append('inputEma2Len')
        self.paramList.append('inputEma3Len')
        self.paramList.append('inputMa1Len')
        self.paramList.append('inputMa2Len')
        self.paramList.append('inputMa3Len')
        self.paramList.append('inputDmiLen')
        self.paramList.append('inputDmiMax')
        self.paramList.append('inputAtr1Len')
        self.paramList.append('inputAtr2Len')
        self.paramList.append('inputAtr3Len')
        self.paramList.append('inputVolLen')
        self.paramList.append('inputRsi1Len')
        self.paramList.append('inputRsi2Len')
        self.paramList.append('inputCmiLen')
        self.paramList.append('inputBollLen')
        self.paramList.append('inputBollTBLen')
        self.paramList.append('inputBollStdRate')
        self.paramList.append('inputBoll2Len')
        self.paramList.append('inputBoll2TBLen')
        self.paramList.append('inputBoll2StdRate')
        self.paramList.append('inputKdjLen')
        self.paramList.append('inputKdjTBLen')
        self.paramList.append('inputKdjSlowLen')
        self.paramList.append('inputKdjSmoothLen')
        self.paramList.append('inputCciLen')
        self.paramList.append('inputMacdFastPeriodLen')
        self.paramList.append('inputMacdSlowPeriodLen')
        self.paramList.append('inputMacdSignalPeriodLen')
        self.paramList.append('inputKF')
        self.paramList.append('inputSkd')
        self.paramList.append('inputSkdLen1')
        self.paramList.append('inputSkdLen2')
        self.paramList.append('inputYb')
        self.paramList.append('inputYbLen')
        self.paramList.append('inputYbRef')
        self.paramList.append('inputSarAfStep')
        self.paramList.append('inputSarAfLimit')
        self.paramList.append('inputGoldenN')
        self.paramList.append('activate_boll_ma_area')
        self.paramList.append('inputBiasLen')
        self.paramList.append('inputBias2Len')
        self.paramList.append('inputBias3Len')

        self.paramList.append('is_7x24')

        self.paramList.append('minDiff')
        self.paramList.append('shortSymbol')

        self.paramList.append('name')

        # 输入参数
        self.name = u'LineBar'
        self.mode = self.TICK_MODE  # 缺省为tick模式
        self.period = PERIOD_SECOND  # 缺省为分钟级别周期
        self.barTimeInterval = 300  # 缺省为5分钟周期

        self.barMinuteInterval = self.barTimeInterval / 60

    def __getstate__(self):
        """移除Pickle dump()时不支持的Attribute"""
        state = self.__dict__.copy()
        # Remove the unpicklable entries.
        for key in self.__dict__.keys():
            if 'strategy' in key:
                del state[key]
            if 'Func' in key:
                del state[key]
        return state

    def __setstate__(self, state):
        """Pickle load()"""
        self.__dict__.update(state)

    def restore(self, state):
        """从Pickle中恢复数据"""
        for key in state.__dict__.keys():
            self.__dict__[key] = state.__dict__[key]

    def init_indicators(self):
        """ 定义所有的指标数据"""

        self.inputPreLen = EMPTY_INT  # 1

        self.inputMa1Len = EMPTY_INT  # 10
        self.inputMa2Len = EMPTY_INT  # 20
        self.inputMa3Len = EMPTY_INT  # 120

        self.inputEma1Len = EMPTY_INT  # 13
        self.inputEma2Len = EMPTY_INT  # 21
        self.inputEma3Len = EMPTY_INT  # 120

        self.inputDmiLen = EMPTY_INT  # 14           # DMI的计算周期
        self.inputDmiMax = EMPTY_FLOAT  # 30           # Dpi和Mdi的突破阈值

        self.inputAtr1Len = EMPTY_INT  # 10           # ATR波动率的计算周期(近端）
        self.inputAtr2Len = EMPTY_INT  # 26           # ATR波动率的计算周期（常用）
        self.inputAtr3Len = EMPTY_INT  # 50           # ATR波动率的计算周期（远端）

        self.inputVolLen = EMPTY_INT  # 14           # 平均交易量的计算周期

        self.inputRsi1Len = EMPTY_INT  # 7     # RSI 相对强弱指数（快曲线）
        self.inputRsi2Len = EMPTY_INT  # 14    # RSI 相对强弱指数（慢曲线）

        # K 线的相关计算结果数据

        self.preHigh = []  # K线的前inputPreLen的的最高
        self.preLow = []  # K线的前inputPreLen的的最低

        self.lineMa1 = []  # K线的MA1均线，周期是InputMaLen1，不包含当前bar
        self.lineMa2 = []  # K线的MA2均线，周期是InputMaLen2，不包含当前bar
        self.lineMa3 = []  # K线的MA2均线，周期是InputMaLen2，不包含当前bar
        self._rt_Ma1 = None
        self._rt_Ma2 = None
        self._rt_Ma3 = None
        self.lineMa1Atan = []
        self.lineMa2Atan = []
        self.lineMa3Atan = []
        self._rt_Ma1Atan = None
        self._rt_Ma2Atan = None
        self._rt_Ma3Atan = None


        self.lineEma1 = []  # K线的EMA1均线，周期是InputEmaLen1，不包含当前bar
        self.lineEma2 = []  # K线的EMA2均线，周期是InputEmaLen2，不包含当前bar
        self.lineEma3 = []  # K线的EMA3均线，周期是InputEmaLen3，不包含当前bar

        self.ma12_count = 0    # ma1 与 ma2 ,金叉/死叉后第几根bar
        self.ma13_count = 0    # ma1 与 ma3 ,金叉/死叉后第几根bar
        self.ma23_count = 0    # ma2 与 ma3 ,金叉/死叉后第几根bar


        # K线的DMI( Pdi，Mdi，ADX，Adxr) 计算数据
        self.barPdi = EMPTY_FLOAT  # bar内的升动向指标，即做多的比率
        self.barMdi = EMPTY_FLOAT  # bar内的下降动向指标，即做空的比率

        self.linePdi = []  # 升动向指标，即做多的比率
        self.lineMdi = []  # 下降动向指标，即做空的比率

        self.lineDx = []  # 趋向指标列表，最大长度为inputM*2
        self.barAdx = EMPTY_FLOAT  # Bar内计算的平均趋向指标
        self.lineAdx = []  # 平均趋向指标
        self.barAdxr = EMPTY_FLOAT  # 趋向平均值，为当日ADX值与M日前的ADX值的均值
        self.lineAdxr = []  # 平均趋向变化指标

        # K线的基于DMI、ADX计算的结果
        self.barAdxTrend = EMPTY_FLOAT  # ADX值持续高于前一周期时，市场行情将维持原趋势
        self.barAdxrTrend = EMPTY_FLOAT  # ADXR值持续高于前一周期时,波动率比上一周期高

        self.buyFilterCond = False  # 多过滤器条件,做多趋势的判断，ADX高于前一天，上升动向> inputMM
        self.sellFilterCond = False  # 空过滤器条件,做空趋势的判断，ADXR高于前一天，下降动向> inputMM

        # K线的ATR技术数据
        self.lineAtr1 = []  # K线的ATR1,周期为inputAtr1Len
        self.lineAtr2 = []  # K线的ATR2,周期为inputAtr2Len
        self.lineAtr3 = []  # K线的ATR3,周期为inputAtr3Len

        self.barAtr1 = EMPTY_FLOAT
        self.barAtr2 = EMPTY_FLOAT
        self.barAtr3 = EMPTY_FLOAT

        # K线的交易量平均
        self.lineAvgVol = []  # K 线的交易量平均

        # K线的RSI计算数据
        self.lineRsi1 = []  # 记录K线对应的RSI数值，只保留inputRsi1Len*8
        self.lineRsi2 = []  # 记录K线对应的RSI数值，只保留inputRsi2Len*8

        self.lowRsi = 30  # RSI的最低线
        self.highRsi = 70  # RSI的最高线

        self.lineRsiTop = []  # 记录RSI的最高峰，只保留 inputRsiLen个
        self.lineRsiButtom = []  # 记录RSI的最低谷，只保留 inputRsiLen个
        self.lastRsiTopButtom = {}  # 最近的一个波峰/波谷

        # K线的CMI计算数据
        self.inputCmiLen = EMPTY_INT
        self.lineCmi = []  # 记录K线对应的Cmi数值，只保留inputCmiLen*8

        # K线的布林特计算数据
        self.inputBollLen = EMPTY_INT  # K线周期
        self.inputBollTBLen = EMPTY_INT  # K线周期
        self.inputBollStdRate = 2  # 两倍标准差
        self.lineBollClose = []  # 用于运算的close价格列表
        self.lineUpperBand = []  # 上轨
        self.lineMiddleBand = []  # 中线
        self.lineLowerBand = []  # 下轨
        self.lineBollStd = []  # 标准差
        self.lineUpperBandAtan = []
        self.lineMiddleBandAtan = []
        self.lineLowerBandAtan = []
        self._rt_Upper = 0
        self._rt_Middle = 0
        self._rt_Lower = 0
        self._rt_UpperBandAtan = 0
        self._rt_MiddleBandAtan = 0
        self._rt_LowerBandAtan = 0

        self.lastBollUpper = EMPTY_FLOAT  # 最后一根K的Boll上轨数值（与MinDiff取整）
        self.lastBollMiddle = EMPTY_FLOAT  # 最后一根K的Boll中轨数值（与MinDiff取整）
        self.lastBollLower = EMPTY_FLOAT  # 最后一根K的Boll下轨数值（与MinDiff取整+1）

        self.inputBoll2Len = EMPTY_INT  # K线周期
        self.inputBoll2TBLen = EMPTY_INT  # K线周期
        self.inputBoll2StdRate = 2  # 两倍标准差
        self.lineUpperBand2 = []  # 上轨
        self.lineMiddleBand2 = []  # 中线
        self.lineLowerBand2 = []  # 下轨
        self.lineBoll2Std = []  # 标准差
        self.lineUpperBand2Atan = []
        self.lineMiddleBand2Atan = []
        self.lineLowerBand2Atan = []
        self._rt_Upper2 = None
        self._rt_Middle2 = None
        self._rt_Lower2 = None
        self._rt_UpperBand2Atan = None
        self._rt_MiddleBand2Atan = None
        self._rt_LowerBand2Atan = None

        self.lastBoll2Upper = EMPTY_FLOAT  # 最后一根K的Boll2上轨数值（与MinDiff取整）
        self.lastBoll2Middle = EMPTY_FLOAT  # 最后一根K的Boll2中轨数值（与MinDiff取整）
        self.lastBoll2Lower = EMPTY_FLOAT  # 最后一根K的Boll2下轨数值（与MinDiff取整+1）

        # K线的KDJ指标计算数据
        self.inputKdjLen = EMPTY_INT  # KDJ指标的长度,缺省是9
        self.inputKdjTBLen = EMPTY_INT  # KDJ指标的长度,缺省是9 ( for TB)
        self.inputKdjSlowLen = EMPTY_INT
        self.inputKdjSmoothLen = EMPTY_INT
        self.lineK = []  # K为快速指标
        self.lineD = []  # D为慢速指标
        self.lineJ = []  #
        self.lineKdjTop = []  # 记录KDJ最高峰，只保留 inputKdjLen个
        self.lineKdjButtom = []  # 记录KDJ的最低谷，只保留 inputKdjLen个
        self.lineKdjRSV = []  # RSV
        self.lastKdjTopButtom = {}  # 最近的一个波峰/波谷
        self.lastK = EMPTY_FLOAT  # bar内计算时，最后一个未关闭的bar的实时K值
        self.lastD = EMPTY_FLOAT  # bar内计算时，最后一个未关闭的bar的实时值
        self.lastJ = EMPTY_FLOAT  # bar内计算时，最后一个未关闭的bar的实时J值

        self.kd_count = 0           # > 0, 金叉， < 0 死叉
        self.kd_last_cross = 0      # 最近一次金叉/死叉的点位
        self.kd_cross_price = 0     # 最近一次发生金叉/死叉的价格

        # K线的MACD计算数据(26,12,9)
        self.inputMacdFastPeriodLen = EMPTY_INT
        self.inputMacdSlowPeriodLen = EMPTY_INT
        self.inputMacdSignalPeriodLen = EMPTY_INT

        self.lineDif = []  # DIF = EMA12 - EMA26，即为talib-MACD返回值macd
        self.lineDea = []  # DEA = （前一日DEA X 8/10 + 今日DIF X 2/10），即为talib-MACD返回值
        self.lineMacd = []  # (dif-dea)*2，但是talib中MACD的计算是bar = (dif-dea)*1,国内一般是乘以2

        self.lineMacdSegment = []  # macd 金叉/死叉的段列表，记录价格的最高/最低，Dif的最高，最低，Macd的最高/最低，Macd面接

        self._rt_Dif = None
        self._rt_Dea = None
        self._rt_Macd = None
        self.macd_count = 0
        self.macd_last_cross = 0  # 最近一次金叉/死叉的点位
        self.macd_cross_price = 0  # 最近一次发生金叉/死叉的价格

        self.macd_rt_count = 0  # 实时金叉/死叉, default = 0； -1 实时死叉； 1：实时金叉
        self.macd_rt_last_cross = 0  # 实时金叉/死叉的位置
        self.macd_rt_cross_price = 0  # 发生实时金叉死叉时的价格

        self.dif_top_divergence = False # mcad dif 与price 顶背离
        self.dif_buttom_divergence = False  # mcad dif 与price 底背离

        self.macd_top_divergence = False     # mcad 面积 与price 顶背离
        self.macd_buttom_divergence = False  # mcad 面积 与price 底背离

        # K 线的CCI计算数据
        self.inputCciLen = EMPTY_INT
        self.lineCci = []

        # 卡尔曼过滤器
        self.inputKF = False
        self.kf = None
        self.lineStateMean = []
        self.lineStateCovar = []

        # SAR
        self.inputSarAfStep = EMPTY_INT
        self.inputSarAfLimit = EMPTY_INT
        self.lineSarDirection = EMPTY_STRING
        self.lineSar = []
        self.lineSarTop = []
        self.lineSarButtom = []
        self.lineSarSrUp = []
        self.lineSarEpUp = []
        self.lineSarAfUp = []
        self.lineSarSrDown = []
        self.lineSarEpDown = []
        self.lineSarAfDown = []
        self.sar_count = 0  # SAR 上升下降变化后累加

        # 周期
        self.atan = None
        self.atan_list = []
        self.curPeriod = None  # 当前所在周期
        self.periods = []

        # 优化的多空动量线
        self.inputSkd = False
        self.inputSkdLen1 = 13  # 周期1
        self.inputSkdLen2 = 8   # 周期2
        self.lineSkdRSI = []    # 参照的RSI
        self.lineSkdSTO = []    # 根据RSI演算的STO
        self.lineSK = []        # 快线
        self.lineSD = []        # 慢线
        self.lowSkd = 30
        self.highSkd = 70
        self.skd_count = 0      # 当前金叉/死叉后累加
        self._rt_SK = None       # 实时SK值
        self._rt_SD = None       # 实时SD值

        # 多空趋势线
        self.inputYb = False
        self.lineYb = []
        self.inputYbRef = 1
        self.inputYbLen = 10
        self.yb_count = 0  # 当前黄/蓝累加
        self._rt_YB = None

        self.skd_divergence = 0     # 背离，>0,底背离， < 0 顶背离
        self.lineSkTop = []         # SK 高位
        self.lineSkButtom = []      # SK 低位
        self.skd_last_cross = 0     # 最近一次金叉/死叉的点位
        self.skd_cross_price = 0    # 最近一次发生金叉/死叉的价格
        self.skd_rt_count = 0       # 实时金叉/死叉, default = 0； -1 实时死叉； 1：实时金叉
        self.skd_rt_last_cross = 0  # 实时金叉/死叉的位置
        self.skd_rt_cross_price = 0 # 发生实时金叉死叉时的价格

        self.inputGoldenN = 0       # 黄金分割（一般设置为60）
        self.p192 = None            # HH-(HH-LL) * 0.192;
        self.p382 = None            # HH-(HH-LL) * 0.382;
        self.p500 = None            # (HH+LL)/2;
        self.p618 = None            # HH-(HH-LL) * 0.618;
        self.p809 = None            # HH-(HH-LL) * 0.809;

        self.activate_boll_ma_area = False
        self.area_list = []
        self.cur_area = None
        self.pre_area = None

        # BIAS
        self.inputBiasLen = EMPTY_INT
        self.inputBias2Len = EMPTY_INT
        self.inputBias3Len = EMPTY_INT
        self.lineBias = []   # BIAS1
        self.lineBias2 = []  # BIAS2
        self.lineBias3 = []  # BIAS3
        self.lastBias = EMPTY_FLOAT  # bar内计算时，最后一个未关闭的bar的实时BIAS1值
        self.lastBias2 = EMPTY_FLOAT  # bar内计算时，最后一个未关闭的bar的实时BIAS2值
        self.lastBias3 = EMPTY_FLOAT  # bar内计算时，最后一个未关闭的bar的实时BIAS3值
        self._rt_Bias = None
        self._rt_Bias2 = None
        self._rt_Bias3 = None

        # 存为Bar文件，For TradeBlazer   WJ
        # filename = u'../TestLogs/rb1801_{}_Min.csv'.format(datetime.now().strftime('%m%d_%H%M'))
        # self.min1File = open(filename, mode='w')
        # # For VNPY Min1
        # barMsg = u"datetime,close,date,high,instrument_id,limit_down,limit_up,low,open,open_interest,time,trading_date,total_turnover,volume,symbol\n"
        # self.min1File.write(barMsg)

    def setParam(self, setting):
        """设置参数"""
        d = self.__dict__
        for key in self.paramList:
            if key in setting:
                d[key] = setting[key]

    def setMode(self,mode):
        """Tick/Bar模式"""
        self.mode = mode

    def onTick(self, tick):
        """行情更新
        :type tick: object
        """
        # Tick 有效性检查
        #if (tick.datetime- datetime.now()).seconds > 10:
        #    self.writeCtaLog(u'无效的tick时间:{0}'.format(tick.datetime))
        #    return

        if not self.is_7x24 and (tick.datetime.hour == 8 or tick.datetime.hour == 20 ):
            self.writeCtaLog(u'竞价排名tick时间:{0}'.format(tick.datetime))
            return

        self.curTick = copy.copy(tick)
        if self.curTick.lastPrice is None or self.curTick.lastPrice == 0:
            if self.curTick.askPrice1 ==0 and  self.curTick.bidPrice1 == 0:
                return

            self.curTick.lastPrice = (self.curTick.askPrice1 + self.curTick.bidPrice1) / 2
            self.cur_price = (self.curTick.askPrice1 + self.curTick.bidPrice1) / 2
        else:
            self.cur_price = self.curTick.lastPrice

        # 3.生成x K线，若形成新Bar，则触发OnBar事件
        self.drawLineBar(tick)

        # 更新curPeriod的High，low
        if self.curPeriod is not None:
            self.curPeriod.onPrice(self.curTick.lastPrice)

        # 4.执行 bar内计算
        self.__recountKdj(countInBar=True)
        self.__recountKdj_TB(countInBar=True)

    def addBar(self, bar, bar_is_completed=False, bar_freq=1):
        """
        予以外部初始化程序增加bar
        予以外部初始化程序增加bar
        :param bar:
        :param bar_is_completed: 插入的bar，其周期与K线周期一致，就设为True

        :return:
        """
        l1 = len(self.lineBar)

        # 更新最后价格
        self.cur_price = bar.close

        if l1 == 0:
            new_bar = copy.deepcopy(bar)
            self.lineBar.append(new_bar)
            self.curTradingDay = bar.date
            self.onBar(bar)
            return

        # 与最后一个BAR的时间比对，判断是否超过K线的周期
        lastBar = self.lineBar[-1]
        self.curTradingDay = bar.tradingDay

        is_new_bar = False
        if bar_is_completed:
            is_new_bar = True

        if self.period == PERIOD_SECOND and (bar.datetime - lastBar.datetime).seconds >= self.barTimeInterval:
            is_new_bar = True

        elif self.period == PERIOD_MINUTE and (int((bar.datetime - datetime.strptime(bar.datetime.strftime('%Y-%m-%d'), '%Y-%m-%d')).total_seconds() / 60 / self.barTimeInterval) !=
                 int((lastBar.datetime - datetime.strptime(lastBar.datetime.strftime('%Y-%m-%d'), '%Y-%m-%d')).total_seconds() / 60 / self.barTimeInterval)):            # (bar.datetime - lastBar.datetime).seconds >= self.barTimeInterval*60:
            is_new_bar = True

        elif self.period == PERIOD_HOUR:
            if self.barTimeInterval == 1 and bar.datetime.hour != lastBar.datetime.hour:
                is_new_bar = True
            elif self.barTimeInterval == 2 and bar.datetime.hour != lastBar.datetime.hour \
                    and bar.datetime.hour in {1, 9, 11, 13, 15, 21, 23}:
                is_new_bar = True
            elif self.barTimeInterval == 4 and bar.datetime.hour != lastBar.datetime.hour \
                    and bar.datetime.hour in {1, 9, 13, 21}:
                is_new_bar = True
            else:
                cur_bars_in_day = int(bar.datetime.hour / self.barTimeInterval)
                last_bars_in_day = int(lastBar.datetime.hour / self.barTimeInterval)
                if cur_bars_in_day != last_bars_in_day:
                    is_new_bar = True

        # elif self.period == PERIOD_DAY and bar.datetime.date != lastBar.datetime.date :
        elif self.period == PERIOD_DAY and bar.tradingDay != lastBar.tradingDay:  # Using tradingDay instead of calanda day
            is_new_bar = True

        if is_new_bar:
            # 添加新的bar
            new_bar = copy.deepcopy(bar)
            self.lineBar.append(new_bar)
            # 将上一个Bar推送至OnBar事件
            self.onBar(lastBar)

        else:
            # 更新最后一个bar
            # 此段代码，针对一部分短周期生成长周期的k线更新，如3根5分钟k线，合并成1根15分钟k线。
            lastBar.close = bar.close
            lastBar.high = max(lastBar.high, bar.high)
            lastBar.low = min(lastBar.low, bar.low)
            lastBar.volume = lastBar.volume + bar.volume
            lastBar.dayVolume = bar.dayVolume
            lastBar.openInterest = bar.openInterest

            lastBar.mid3 = round((lastBar.close + lastBar.high + lastBar.low) / 3, self.round_n)
            lastBar.mid4 = round((2 * lastBar.close + lastBar.high + lastBar.low) / 4, self.round_n)
            lastBar.mid5 = round((2 * lastBar.close + lastBar.open + lastBar.high + lastBar.low) / 5, self.round_n)

            # 实时计算
            self.runtime_recount()

    def onBar(self, bar):
        """OnBar事件"""
        # 计算相关数据
        bar.mid3 = round((bar.close + bar.high + bar.low) / 3, self.round_n)
        bar.mid4 = round((2 * bar.close + bar.high + bar.low) / 4, self.round_n)
        bar.mid5 = round((2 * bar.close + bar.open + bar.high + bar.low) / 5, self.round_n)

        # 扩展open,close,high,low 列表
        if len(self.lineOpen) > self.max_hold_bars:
            del self.lineOpen[0]
        self.lineOpen.append(bar.open)

        if len(self.lineHigh) > self.max_hold_bars:
            del self.lineHigh[0]
        self.lineHigh.append(bar.high)

        if len(self.lineLow) > self.max_hold_bars:
            del self.lineLow[0]
        self.lineLow.append(bar.low)

        if len(self.lineClose) > self.max_hold_bars:
            del self.lineClose[0]

        self.lineClose.append(bar.close)

        self.__recountPreHighLow()
        self.__recountMa()
        self.__recountEma()
        self.__recountDmi()
        self.__recountAtr()
        self.__recoundAvgVol()
        self.__recountRsi()
        self.__recountCmi()
        self.__recountKdj()
        self.__recountKdj_TB()
        self.__recountBoll()
        self.__recountMacd()
        self.__recountCci()
        self.__recountKF()
        self.__recountPeriod(bar)
        self.__recountSKD()
        self.__recountYB()
        self.__recountSar()
        self.__recountGoldenSection()
        self.__recountArea(bar)
        self.__recountBias()
        self.export_to_csv(bar)

        # 实时计算
        self.runtime_recount()

        # 回调上层调用者
        self.onBarFunc(bar)

    def runtime_recount(self):
        """
        根据实时计算得要求，执行实时指标计算
        :return:
        """
        for func in list(self.rt_funcs):
            try:
                func()
            except Exception as ex:
                print(u'{}调用实时计算,异常:{},{}'.format(self.name, str(ex),traceback.format_exc()), file=sys.stderr)

    def export_to_csv(self, bar):
        if self.export_filename is None or len(self.export_fields) == 0:
            return
        field_names = []
        save_dict = {}
        for field in self.export_fields:
            field_name = field.get('name', None)
            attr_name = field.get('attr', None)
            source = field.get('source', None)
            type_ = field.get('type_', None)
            if field_name is None or attr_name is None or source is None or type_ is None:
                continue
            field_names.append(field_name)
            if source == 'bar':
                save_dict[field_name] = getattr(bar, str(attr_name), None)
            else:
                if type_ == 'list':
                    l = getattr(self, str(attr_name), None)
                    if l is None or len(l) == 0:
                        save_dict[field_name] = 0
                    else:
                        save_dict[field_name] = l[-1]
                else:
                    save_dict[field_name] = getattr(self, str(attr_name), 0)

        if len(save_dict) > 0:
            self.append_data(file_name=self.export_filename, dict_data=save_dict, field_names=field_names)

    def displayLastBar(self):
        """显示最后一个Bar的信息"""
        msg = u'[' + self.name + u']'

        if len(self.lineBar) < 2:
            return msg

        if self.mode == self.TICK_MODE:
            displayBar = self.lineBar[-2]
        else:
            displayBar = self.lineBar[-1]

        msg = msg + u'[td:{}] ad:{} o:{};h:{};l:{};c:{},v:{}'. \
            format(displayBar.tradingDay, displayBar.date + ' ' + displayBar.time, displayBar.open, displayBar.high,
                   displayBar.low, displayBar.close, displayBar.volume)

        if self.inputMa1Len > 0 and len(self.lineMa1) > 0:
            msg = msg + u',MA({0}):{1}'.format(self.inputMa1Len, self.lineMa1[-1])

        if self.inputMa2Len > 0 and len(self.lineMa2) > 0:
            msg = msg + u',MA({0}):{1}'.format(self.inputMa2Len, self.lineMa2[-1])
            if self.ma12_count == 1:
                msg = msg + u'MA{}金叉MA{}'.format(self.inputMa1Len, self.inputMa2Len)
            elif self.ma12_count == -1:
                msg = msg + u'MA{}死叉MA{}'.format(self.inputMa1Len, self.inputMa2Len)

        if self.inputMa3Len > 0 and len(self.lineMa3) > 0:
            msg = msg + u',MA({0}):{1}'.format(self.inputMa3Len, self.lineMa3[-1])
            if self.ma13_count == 1:
                msg = msg + u'MA{}金叉MA{}'.format(self.inputMa1Len, self.inputMa3Len)
            elif self.ma13_count == -1:
                msg = msg + u'MA{}死叉MA{}'.format(self.inputMa1Len, self.inputMa3Len)

            if self.ma23_count == 1:
                msg = msg + u'MA{}金叉MA{}'.format(self.inputMa2Len, self.inputMa3Len)
            elif self.ma23_count == -1:
                msg = msg + u'MA{}死叉MA{}'.format(self.inputMa2Len, self.inputMa3Len)

        if self.inputEma1Len > 0 and len(self.lineEma1) > 0:
            msg = msg + u',EMA({0}):{1}'.format(self.inputEma1Len, self.lineEma1[-1])

        if self.inputEma2Len > 0 and len(self.lineEma2) > 0:
            msg = msg + u',EMA({0}):{1}'.format(self.inputEma2Len, self.lineEma2[-1])

        if self.inputEma3Len > 0 and len(self.lineEma3) > 0:
            msg = msg + u',EMA({0}):{1}'.format(self.inputEma3Len, self.lineEma3[-1])

        if self.inputDmiLen > 0 and len(self.linePdi) > 0:
            msg = msg + u',Pdi:{1};Mdi:{1};Adx:{2}'.format(self.linePdi[-1], self.lineMdi[-1], self.lineAdx[-1])

        if self.inputAtr1Len > 0 and len(self.lineAtr1) > 0:
            msg = msg + u',Atr({0}):{1}'.format(self.inputAtr1Len, self.lineAtr1[-1])

        if self.inputAtr2Len > 0 and len(self.lineAtr2) > 0:
            msg = msg + u',Atr({0}):{1}'.format(self.inputAtr2Len, self.lineAtr2[-1])

        if self.inputAtr3Len > 0 and len(self.lineAtr3) > 0:
            msg = msg + u',Atr({0}):{1}'.format(self.inputAtr3Len, self.lineAtr3[-1])

        if self.inputVolLen > 0 and len(self.lineAvgVol) > 0:
            msg = msg + u',AvgVol({0}):{1}'.format(self.inputVolLen, self.lineAvgVol[-1])

        if self.inputRsi1Len > 0 and len(self.lineRsi1) > 0:
            msg = msg + u',Rsi({0}):{1}'.format(self.inputRsi1Len, self.lineRsi1[-1])

        if self.inputRsi2Len > 0 and len(self.lineRsi2) > 0:
            msg = msg + u',Rsi({0}):{1}'.format(self.inputRsi2Len, self.lineRsi2[-1])

        if self.inputKdjLen > 0 and len(self.lineK) > 0:
            msg = msg + u',KDJ({},{},{}):{},{},{}'.format(self.inputKdjLen,
                                                          self.inputKdjSlowLen,
                                                          self.inputKdjSmoothLen,
                                                          round(self.lineK[-1], self.round_n),
                                                          round(self.lineD[-1], self.round_n),
                                                          round(self.lineJ[-1], self.round_n))

        if self.inputKdjTBLen > 0 and len(self.lineK) > 0:
            msg = msg + u',KDJ_TB({},{},{}):{},K:{},D:{},J:{}'.format(self.inputKdjTBLen,
                                                                      self.inputKdjSlowLen,
                                                                      self.inputKdjSmoothLen,
                                                                      round(self.lineKdjRSV[-1], self.round_n),
                                                                      round(self.lineK[-1], self.round_n),
                                                                      round(self.lineD[-1], self.round_n),
                                                                      round(self.lineJ[-1], self.round_n))

        if self.inputCciLen > 0 and len(self.lineCci) > 0:
            msg = msg + u',Cci({0}):{1}'.format(self.inputCciLen, self.lineCci[-1])

        if (self.inputBollLen > 0 or self.inputBollTBLen > 0) and len(self.lineUpperBand) > 0:
            msg = msg + u',Boll({}):std:{},mid:{},up:{},low:{},Atan:[mid:{},up:{},low:{}]'. \
                format(self.inputBollLen, round(self.lineBollStd[-1], self.round_n),
                       round(self.lineMiddleBand[-1], self.round_n),
                       round(self.lineUpperBand[-1], self.round_n),
                       round(self.lineLowerBand[-1], self.round_n),
                       round(self.lineMiddleBandAtan[-1], 2) if len(self.lineMiddleBandAtan) > 0 else 0,
                       round(self.lineUpperBandAtan[-1], 2) if len(self.lineUpperBandAtan) > 0 else 0,
                       round(self.lineLowerBandAtan[-1], 2) if len(self.lineLowerBandAtan) > 0 else 0)

        if (self.inputBoll2Len > 0 or self.inputBoll2TBLen > 0) and len(self.lineUpperBand) > 0:
            msg = msg + u',Boll2({}):std:{},m:{},u:{},l:{}'. \
                format(self.inputBoll2Len, round(self.lineBollStd[-1], self.round_n),
                       round(self.lineMiddleBand2[-1], self.round_n),
                       round(self.lineUpperBand2[-1], self.round_n),
                       round(self.lineLowerBand2[-1], self.round_n))

        if self.inputMacdFastPeriodLen > 0 and len(self.lineDif) > 0:
            msg = msg + u',MACD({0},{1},{2}):Dif:{3},Dea{4},Macd:{5}'. \
                format(self.inputMacdFastPeriodLen, self.inputMacdSlowPeriodLen, self.inputMacdSignalPeriodLen,
                       round(self.lineDif[-1], self.round_n),
                       round(self.lineDea[-1], self.round_n),
                       round(self.lineMacd[-1], self.round_n))
            if len(self.lineMacd)>2:
                if self.lineMacd[-2] < 0 < self.lineMacd[-1]:
                    msg = msg + u'金叉 '
                elif self.lineMacd[-2] > 0 > self.lineMacd[-1]:
                    msg = msg + u'死叉 '

                if self.dif_top_divergence:
                    msg = msg + u'Dif顶背离 '
                if self.macd_top_divergence:
                    msg = msg + u'MACD顶背离 '
                if self.dif_buttom_divergence:
                    msg = msg + u'Dif底背离 '
                if self.macd_buttom_divergence:
                    msg = msg + u'MACD低背离 '

        if self.inputKF and len(self.lineStateMean) > 0:
            msg = msg + u',Kalman:{0}'.format(self.lineStateMean[-1])

        if self.inputSkd and len(self.lineSK) > 1 and len(self.lineSD) > 1:
            golden_cross = self.lineSK[-1] > self.lineSK[-2] and self.lineSK[-1] > self.lineSD[-1] and self.lineSK[-2] < \
                           self.lineSD[-2]
            dead_cross = self.lineSK[-1] < self.lineSK[-2] and self.lineSK[-1] < self.lineSD[-1] and self.lineSK[-2] > \
                         self.lineSD[-2]
            msg = msg + u',SK:{}/SD:{}{}{},count:{}' \
                .format(round(self.lineSK[-1], 2), round(self.lineSD[-1], 2), u'金叉' if golden_cross else u'',
                        u'死叉' if dead_cross else u'', self.skd_count)

            if self.skd_divergence == 1:
                msg = msg + u'底背离'
            elif self.skd_divergence == -1:
                msg = msg + u'顶背离'

        if self.inputYb and len(self.lineYb) > 1:
            c = 'Blue' if self.lineYb[-1] < self.lineYb[-2] else 'Yellow'
            msg = msg + u',YB:{},[{}({})]'.format(self.lineYb[-1], c, self.yb_count)

        if self.inputSarAfStep > 0 and self.inputSarAfLimit > 0:
            if len(self.lineSar) > 1:
                msg = msg + u',Sar:{},{}(h={},l={}),#{}'.format(self.lineSarDirection,
                                                                round(self.lineSar[-2], self.round_n),
                                                                self.lineSarTop[-1], self.lineSarButtom[-1],
                                                                self.sar_count)
        if self.activate_boll_ma_area:
            msg = msg + 'Area:{}'.format(self.cur_area)

        if self.inputBiasLen > 0 and len(self.lineBias) > 0:
            msg = msg + u',Bias({}):{}]'. \
                format(self.inputBiasLen, round(self.lineBias[-1], self.round_n))

        if self.inputBias2Len > 0 and len(self.lineBias2) > 0:
            msg = msg + u',Bias2({}):{}]'. \
                format(self.inputBias2Len, round(self.lineBias2[-1], self.round_n))

        if self.inputBias3Len > 0 and len(self.lineBias3) > 0:
            msg = msg + u',Bias3({}):{}]'. \
                format(self.inputBias3Len, round(self.lineBias3[-1], self.round_n))

        return msg

    def firstTick(self, tick):
        """ K线的第一个Tick数据"""

        self.bar = CtaBarData()  # 创建新的K线
        # 计算K线的整点分钟周期，这里周期最小是1分钟。如果你是采用非整点分钟，例如1.5分钟，请把这段注解掉
        if self.barMinuteInterval and self.period == PERIOD_SECOND:
            self.barMinuteInterval = int(self.barTimeInterval / 60)
            if self.barMinuteInterval < 1:
                self.barMinuteInterval = 1
            fixedMin = int(tick.datetime.minute / self.barMinuteInterval) * self.barMinuteInterval
            tick.datetime = tick.datetime.replace(minute=fixedMin)

        self.bar.vtSymbol = tick.vtSymbol
        self.bar.symbol = tick.symbol
        self.bar.exchange = tick.exchange
        self.bar.openInterest = tick.openInterest

        self.bar.open = tick.lastPrice  # O L H C
        self.bar.high = tick.lastPrice
        self.bar.low = tick.lastPrice
        self.bar.close = tick.lastPrice

        self.bar.mid4 = tick.lastPrice  # 4价均价
        self.bar.mid5 = tick.lastPrice  # 5价均价

        # K线的日期时间
        self.bar.tradingDay = tick.tradingDay  # K线所在的交易日期
        self.bar.date = tick.date  # K线的日期，（夜盘的话，与交易日期不同哦）
        self.bar.datetime = tick.datetime
        if (self.period  == PERIOD_SECOND and self.barTimeInterval % 60 == 0) \
                or self.period in [PERIOD_MINUTE,PERIOD_HOUR,PERIOD_DAY]:
            # K线的日期时间（去除秒）设为第一个Tick的时间
            self.bar.datetime = self.bar.datetime.replace(second=0, microsecond=0)
        self.bar.time = self.bar.datetime.strftime('%H:%M:%S')

        # K线的日总交易量，k线内交易量
        self.bar.dayVolume = tick.volume
        if self.curTradingDay != self.bar.tradingDay or not self.lineBar:
            # bar的交易日与记录的当前交易日不一致：即该bar为新的交易日,bar的交易量为当前的tick.volume
            self.bar.volume = tick.volume
            self.curTradingDay = self.bar.tradingDay
        else:
            # bar的交易日与记录的当前交易日一致, 交易量为tick的volume，减去上一根bar的日总交易量
            self.bar.volume = tick.volume - self.lineBar[-1].dayVolume

        self.barFirstTick = True  # 标识该Tick属于该Bar的第一个tick数据

        self.lineBar.append(self.bar)  # 推入到lineBar队列

    # ----------------------------------------------------------------------
    def drawLineBar(self, tick):
        """生成 line Bar  """

        l1 = len(self.lineBar)

        # 保存第一个K线数据
        if l1 == 0:
            self.firstTick(tick)
            return

        # 清除480周期前的数据，
        if l1 > self.max_hold_bars:
            del self.lineBar[0]

        # 与最后一个BAR的时间比对，判断是否超过5分钟
        lastBar = self.lineBar[-1]

        # 处理日内的间隔时段最后一个tick，如10:15分，11:30分，15:00 和 2:30分
        endtick = False
        if not self.is_7x24:
            if (tick.datetime.hour == 10 and tick.datetime.minute == 15) \
                    or (tick.datetime.hour == 11 and tick.datetime.minute == 30) \
                    or (tick.datetime.hour == 15 and tick.datetime.minute == 00) \
                    or (tick.datetime.hour == 2 and tick.datetime.minute == 30):
                endtick = True

            # 夜盘1:30收盘
            if self.shortSymbol in NIGHT_MARKET_SQ2 and tick.datetime.hour == 1 and tick.datetime.minute == 00:
                endtick = True

            # 夜盘23:00收盘
            if self.shortSymbol in [NIGHT_MARKET_SQ3,NIGHT_MARKET_DL] and tick.datetime.hour == 23 and tick.datetime.minute == 00:
                endtick = True
            # 夜盘23:30收盘
            if self.shortSymbol in NIGHT_MARKET_ZZ:
                if tick.datetime.hour == 23 and tick.datetime.minute == 30:
                    endtick = True

        # 满足时间要求
        # 1,秒周期，tick的时间，距离最后一个bar的开始时间，已经超出bar的时间周期（barTimeInterval）
        # 2，分钟周期，tick的时间属于的bar不等于最后一个bar的时间属于的bar
        # 3，小时周期，取整=0
        # 4、日周期，开盘时间
        # 5、不是最后一个结束tick
        is_new_bar = False

        if self.lastTick is None:  # Fix for Min10, 13:30 could not generate
            self.lastTick = tick

        # self.writeCtaLog('drawLineBar: datetime={}, lastPrice={}, endtick={}'.format(tick.datetime.strftime("%Y%m%d %H:%M:%S"), tick.lastPrice, endtick))
        if not endtick:
            if self.period == PERIOD_SECOND:
                if (tick.datetime - lastBar.datetime).total_seconds() >= self.barTimeInterval:
                    is_new_bar = True

            elif self.period == PERIOD_MINUTE:
                # 时间到达整点分钟数，例如5分钟的 0,5,15,20,,.与上一个tick的分钟数不是同一分钟
                cur_bars_in_day = int(((tick.datetime - datetime.strptime(tick.datetime.strftime('%Y-%m-%d'),
                                                                          '%Y-%m-%d')).total_seconds() / 60 / self.barTimeInterval))
                last_bars_in_day = int(((lastBar.datetime - datetime.strptime(lastBar.datetime.strftime('%Y-%m-%d'),
                                                                              '%Y-%m-%d')).total_seconds() / 60 / self.barTimeInterval))

                if cur_bars_in_day != last_bars_in_day:
                    is_new_bar = True

            elif self.period == PERIOD_HOUR:
                if self.barTimeInterval == 1 and tick.datetime is not None and tick.datetime.hour != self.lastTick.datetime.hour:
                    is_new_bar = True

                elif not self.is_7x24 and self.barTimeInterval == 2 and tick.datetime is not None \
                        and tick.datetime.hour != self.lastTick.datetime.hour \
                        and tick.datetime.hour in {1, 9, 11, 13, 21, 23}:
                    is_new_bar = True

                elif not self.is_7x24 and self.barTimeInterval == 4 and tick.datetime is not None \
                        and tick.datetime.hour != self.lastTick.datetime.hour \
                        and tick.datetime.hour in {1, 9, 13, 21}:
                    is_new_bar = True
                else:
                    cur_bars_in_day = int(tick.datetime.hour / self.barTimeInterval)
                    last_bars_in_day = int(lastBar.datetime.hour / self.barTimeInterval)
                    if cur_bars_in_day != last_bars_in_day:
                        is_new_bar = True

            elif self.period == PERIOD_DAY:
                if not self.is_7x24:
                    if tick.datetime is not None \
                            and (tick.datetime.hour == 21 or tick.datetime.hour == 9) \
                            and 14 <= self.lastTick.datetime.hour <= 15:
                        is_new_bar = True
                else:
                    if tick.date != lastBar.date:
                        is_new_bar = True

        if is_new_bar:
            # 创建并推入新的Bar
            self.firstTick(tick)
            # 触发OnBar事件
            self.onBar(lastBar)

            # 存为Bar文件，For TradeBlazer   WJ
            # barMsg = u"{},{},{},{},{},{},{}\n".format(lastBar.datetime.strftime('%Y/%m/%d %H:%M'), lastBar.open, lastBar.high,
            #                                           lastBar.low, lastBar.close, lastBar.volume, lastBar.openInterest)
            # self.writeCtaLog('drawLineBar: ' + barMsg)
            # self.min1File.write(barMsg)
            #
            # # 存为Bar文件，For VNPY Min1 WJ
            # # "datetime,close,date,high,instrument_id,limit_down,limit_up,low,open,open_interest,time,trading_date,total_turnover,volume,symbol\n"
            # lastBar.datetime = lastBar.datetime + timedelta(seconds=60)
            # barMsg = u"{},{},{},{},{},{},{},{},{},{},{},{},{},{},{}\n".format(lastBar.datetime.strftime('%Y%m%d%H%M%S'), lastBar.close, lastBar.datetime.strftime('%Y%m%d'),
            #                                           lastBar.high, lastBar.symbol, 0, 99999, lastBar.low, lastBar.open, lastBar.openInterest, lastBar.datetime.strftime('%H%M%S'),
            #                                           lastBar.tradingDay, 100, lastBar.volume, lastBar.vtSymbol)
            # self.min1File.write(barMsg)

        else:
            # 更新当前最后一个bar
            self.barFirstTick = False

            # 更新最高价、最低价、收盘价、成交量
            lastBar.high = max(lastBar.high, tick.lastPrice)
            lastBar.low = min(lastBar.low, tick.lastPrice)
            lastBar.close = tick.lastPrice
            lastBar.openInterest = tick.openInterest
            # 更新日内总交易量，和bar内交易量
            lastBar.dayVolume = tick.volume
            if l1 == 1:
                # 针对第一个bar的tick volume更新
                lastBar.volume = tick.volume
            else:
                # 针对新交易日的第一个bar：于上一个bar的时间在14，当前bar的时间不在14点,初始化为tick.volume
                if self.lineBar[
                    -2].datetime.hour == 14 and tick.datetime.hour != 14 and not endtick and not self.is_7x24:
                    lastBar.volume = tick.volume
                else:
                    # 其他情况，bar为同一交易日，将tick的volume，减去上一bar的dayVolume
                    lastBar.volume = tick.volume - self.lineBar[-2].dayVolume

            # 更新Bar的颜色
            if lastBar.close > lastBar.open:
                lastBar.color = COLOR_RED
            elif lastBar.close < lastBar.open:
                lastBar.color = COLOR_BLUE
            else:
                lastBar.color = COLOR_EQUAL

            # 实时计算
            self.runtime_recount()

        if not endtick:
            self.lastTick = tick

    # ----------------------------------------------------------------------
    def __recountPreHighLow(self):
        """计算 K线的前周期最高和最低"""

        if self.inputPreLen <= 0:  # 不计算
            return

        # 1、lineBar满足长度才执行计算
        if len(self.lineBar) < self.inputPreLen:
            self.writeCtaLog(u'数据未充分,当前Bar数据数量：{0}，计算High、Low需要：{1}'.
                             format(len(self.lineBar), self.inputPreLen))
            return

        # 2.计算前inputPreLen周期内(不包含当前周期）的Bar高点和低点
        preHigh = EMPTY_FLOAT
        preLow = EMPTY_FLOAT

        if self.mode == self.TICK_MODE:
            idx = 2
        else:
            idx = 1

        for i in range(len(self.lineBar) - idx, len(self.lineBar) - idx - self.inputPreLen, -1):

            if self.lineBar[i].high > preHigh or preHigh == EMPTY_FLOAT:
                preHigh = self.lineBar[i].high  # 前InputPreLen周期高点

            if self.lineBar[i].low < preLow or preLow == EMPTY_FLOAT:
                preLow = self.lineBar[i].low  # 前InputPreLen周期低点

        # 保存
        if len(self.preHigh) > self.inputPreLen * 8:
            del self.preHigh[0]
        self.preHigh.append(preHigh)

        # 保存
        if len(self.preLow) > self.inputPreLen * 8:
            del self.preLow[0]
        self.preLow.append(preLow)

    # ----------------------------------------------------------------------
    def __recountSar(self):
        """计算K线的SAR"""
        l = len(self.lineBar)
        if l < 5:
            return

        if not (self.inputSarAfStep > 0 or self.inputSarAfLimit > self.inputSarAfStep):  # 不计算
            return

        # 3、获取前InputN周期(不包含当前周期）的K线
        if self.mode == self.TICK_MODE:
            listHigh = [x.high for x in self.lineBar[0:-1]]
            listLow = [x.low for x in self.lineBar[0:-1]]
        else:
            listHigh = [x.high for x in self.lineBar]
            listLow = [x.low for x in self.lineBar]

        if len(self.lineSarSrUp) == 0 and len(self.lineSarSrDown) == 0:
            if self.lineBar[-2].close > self.lineBar[-5].close:
                # 标记为上涨趋势
                sr0 = min(listLow[0:])
                af0 = 0
                ep0 = listHigh[-1]
                self.lineSarSrUp.append(sr0)
                self.lineSarEpUp.append(ep0)
                self.lineSarAfUp.append(af0)
                self.lineSar.append(sr0)
                self.lineSarDirection = 'up'
                self.sar_count = 0
            else:
                # 标记为下跌趋势
                sr0 = max(listHigh[0:])
                af0 = 0
                ep0 = listLow[-1]
                self.lineSarSrDown.append(sr0)
                self.lineSarEpDown.append(ep0)
                self.lineSarAfDown.append(af0)
                self.lineSar.append(sr0)
                self.lineSarDirection = 'down'
                self.sar_count = 0
            self.lineSarTop.append(self.lineBar[-2].high)  # SAR的谷顶
            self.lineSarButtom.append(self.lineBar[-2].low)  # SAR的波底
        elif len(self.lineSarSrUp) > 0:
            if listLow[-1] > self.lineSarSrUp[-1]:
                sr0 = self.lineSarSrUp[-1]
                ep0 = listHigh[-1]  # 文华使用前一个K线的最高价
                af0 = min(self.inputSarAfLimit,
                          self.lineSarAfUp[-1] + self.inputSarAfStep)  # 文华的af随着K线的数目增加而递增，没有判断新高
                sr = sr0 + af0 * (ep0 - sr0)
                self.lineSarSrUp.append(sr)
                self.lineSarEpUp.append(ep0)
                self.lineSarAfUp.append(af0)
                self.lineSar.append(sr)
                self.sar_count += 1
                # self.debugCtaLog('Up: sr0={},ep0={},af0={},sr={}'.format(sr0, ep0, af0, sr))
            elif listLow[-1] <= self.lineSarSrUp[-1]:
                ep0 = max(listHigh[-len(self.lineSarSrUp):])
                sr0 = ep0
                af0 = 0
                self.lineSarSrDown.append(sr0)
                self.lineSarEpDown.append(ep0)
                self.lineSarAfDown.append(af0)
                self.lineSar.append(sr0)
                self.lineSarDirection = 'down'
                # self.debugCtaLog('Up->Down: sr0={},ep0={},af0={},sr={}'.format(sr0, ep0, af0, sr0))
                # self.debugCtaLog('lineSarTop={}, lineSarButtom={}, len={}'.format(self.lineSarTop[-1], self.lineSarButtom[-1],len(self.lineSarSrUp)))
                self.lineSarTop.append(self.lineBar[-2].high)
                self.lineSarButtom.append(self.lineBar[-2].low)
                self.lineSarSrUp = []
                self.lineSarEpUp = []
                self.lineSarAfUp = []
                sr0 = self.lineSarSrDown[-1]
                ep0 = listLow[-1]  # 文华使用前一个K线的最低价
                af0 = min(self.inputSarAfLimit,
                          self.lineSarAfDown[-1] + self.inputSarAfStep)  # 文华的af随着K线的数目增加而递增，没有判断新高
                sr = sr0 + af0 * (ep0 - sr0)
                self.lineSarSrDown.append(sr)
                self.lineSarEpDown.append(ep0)
                self.lineSarAfDown.append(af0)
                self.lineSar.append(sr)
                self.sar_count = 0
                # self.debugCtaLog('Down: sr0={},ep0={},af0={},sr={}'.format(sr0, ep0, af0, sr))
        elif len(self.lineSarSrDown) > 0:
            if listHigh[-1] < self.lineSarSrDown[-1]:
                sr0 = self.lineSarSrDown[-1]
                ep0 = listLow[-1]  # 文华使用前一个K线的最低价
                af0 = min(self.inputSarAfLimit,
                          self.lineSarAfDown[-1] + self.inputSarAfStep)  # 文华的af随着K线的数目增加而递增，没有判断新高
                sr = sr0 + af0 * (ep0 - sr0)
                self.lineSarSrDown.append(sr)
                self.lineSarEpDown.append(ep0)
                self.lineSarAfDown.append(af0)
                self.lineSar.append(sr)
                self.sar_count -= 1
                # self.debugCtaLog('Down: sr0={},ep0={},af0={},sr={}'.format(sr0, ep0, af0, sr))
            elif listHigh[-1] >= self.lineSarSrDown[-1]:
                ep0 = min(listLow[-len(self.lineSarSrDown):])
                sr0 = ep0
                af0 = 0
                self.lineSarSrUp.append(sr0)
                self.lineSarEpUp.append(ep0)
                self.lineSarAfUp.append(af0)
                self.lineSar.append(sr0)
                self.lineSarDirection = 'up'
                # self.debugCtaLog('Down->Up: sr0={},ep0={},af0={},sr={}'.format(sr0, ep0, af0, sr0))
                # self.debugCtaLog('lineSarTop={}, lineSarButtom={}, len={}'.format(self.lineSarTop[-1], self.lineSarButtom[-1],len(self.lineSarSrDown)))
                self.lineSarTop.append(self.lineBar[-2].high)
                self.lineSarButtom.append(self.lineBar[-2].low)
                self.lineSarSrDown = []
                self.lineSarEpDown = []
                self.lineSarAfDown = []
                sr0 = self.lineSarSrUp[-1]
                ep0 = listHigh[-1]  # 文华使用前一个K线的最高价
                af0 = min(self.inputSarAfLimit,
                          self.lineSarAfUp[-1] + self.inputSarAfStep)  # 文华的af随着K线的数目增加而递增，没有判断新高
                sr = sr0 + af0 * (ep0 - sr0)
                self.lineSarSrUp.append(sr)
                self.lineSarEpUp.append(ep0)
                self.lineSarAfUp.append(af0)
                self.lineSar.append(sr)
                self.sar_count = 0
                self.debugCtaLog('Up: sr0={},ep0={},af0={},sr={}'.format(sr0, ep0, af0, sr))

        if self.lineSarTop[-1] < self.lineBar[-2].high:
            self.lineSarTop[-1] = self.lineBar[-2].high
        if self.lineSarButtom[-1] > self.lineBar[-2].low:
            self.lineSarButtom[-1] = self.lineBar[-2].low

    # ----------------------------------------------------------------------
    def __recountMa(self):
        """计算K线的MA1 和MA2"""
        l = len(self.lineBar)

        if not (self.inputMa1Len > 0 or self.inputMa2Len > 0 or self.inputMa3Len > 0):  # 不计算
            return

        # 1、lineBar满足长度才执行计算
        if len(self.lineBar) < min(7, self.inputMa1Len, self.inputMa2Len, self.inputMa3Len) + 2:
            self.debugCtaLog(u'数据未充分,当前Bar数据数量：{0}，计算MA需要：{1}'.
                             format(len(self.lineBar),
                                    min(7, self.inputMa1Len, self.inputMa2Len, self.inputMa3Len) + 2))
            return

        # 计算第一条MA均线
        if self.inputMa1Len > 0:
            if self.inputMa1Len > l:
                ma1Len = l
            else:
                ma1Len = self.inputMa1Len

            # 3、获取前InputN周期(不包含当前周期）的K线
            if self.mode == self.TICK_MODE:
                listClose = [x.close for x in self.lineBar[-ma1Len - 1:-1]]
            else:
                listClose = [x.close for x in self.lineBar[-ma1Len:]]

            barMa1 = ta.MA(np.array(listClose, dtype=float), ma1Len)[-1]
            barMa1 = round(float(barMa1), self.round_n)

            if len(self.lineMa1) > self.inputMa1Len * 8:
                del self.lineMa1[0]
            self.lineMa1.append(barMa1)

            # 计算斜率
            if len(self.lineMa1)>2 and self.lineMa1[-2]!=0:
                ma1_atan = math.atan((self.lineMa1[-1] / self.lineMa1[-2] - 1) * 100) * 180 / math.pi
                ma1_atan= round(ma1_atan, 3)
                if len(self.lineMa1Atan) > self.inputMa1Len * 8:
                    del self.lineMa1Atan[0]
                self.lineMa1Atan.append(ma1_atan)

        # 计算第二条MA均线
        if self.inputMa2Len > 0:
            if self.inputMa2Len > l:
                ma2Len = l
            else:
                ma2Len = self.inputMa2Len

            # 3、获取前InputN周期(不包含当前周期）的K线
            if self.mode == self.TICK_MODE:
                listClose = [x.close for x in self.lineBar[-ma2Len - 1:-1]]
            else:
                listClose = [x.close for x in self.lineBar[-ma2Len:]]

            barMa2 = ta.MA(np.array(listClose, dtype=float), ma2Len)[-1]
            barMa2 = round(float(barMa2), self.round_n)

            if len(self.lineMa2) > self.inputMa2Len * 8:
                del self.lineMa2[0]
            self.lineMa2.append(barMa2)

            # 计算斜率
            if len(self.lineMa2) > 2 and self.lineMa2[-2] != 0:
                ma2_atan = math.atan((self.lineMa2[-1] / self.lineMa2[-2] - 1) * 100) * 180 / math.pi
                ma2_atan = round(ma2_atan, 3)
                if len(self.lineMa2Atan) > self.inputMa2Len * 8:
                    del self.lineMa2Atan[0]
                self.lineMa2Atan.append(ma2_atan)

        # 计算第三条MA均线
        if self.inputMa3Len > 0:
            if self.inputMa3Len > l:
                ma3Len = l
            else:
                ma3Len = self.inputMa3Len

            # 3、获取前InputN周期(不包含当前周期）的K线
            if self.mode == self.TICK_MODE:
                listClose = [x.close for x in self.lineBar[-ma3Len - 1:-1]]
            else:
                listClose = [x.close for x in self.lineBar[-ma3Len:]]

            barMa3 = ta.MA(np.array(listClose, dtype=float), ma3Len)[-1]
            barMa3 = round(float(barMa3), self.round_n)

            if len(self.lineMa3) > self.inputMa3Len * 8:
                del self.lineMa3[0]
            self.lineMa3.append(barMa3)

            # 计算斜率
            if len(self.lineMa3) > 2 and self.lineMa3[-2] != 0:
                ma3_atan = math.atan((self.lineMa3[-1] / self.lineMa3[-2] - 1) * 100) * 180 / math.pi
                ma3_atan = round(ma3_atan, 3)
                if len(self.lineMa3Atan) > self.inputMa3Len * 8:
                    del self.lineMa3Atan[0]
                self.lineMa3Atan.append(ma3_atan)

        # 计算MA1，MA2，MA3的金叉死叉
        if len(self.lineMa1) >= 2 and len(self.lineMa2) > 2:
            golden_cross = self.lineMa1[-1] > self.lineMa1[-2] and self.lineMa1[-1] > self.lineMa2[-1] \
                           and self.lineMa1[ -2] <= self.lineMa2[-2]
            dead_cross = self.lineMa1[-1] < self.lineMa1[-2] and self.lineMa1[-1] < self.lineMa2[-1] \
                         and self.lineMa1[-2] >= self.lineMa2[-2]
            if self.ma12_count <= 0:
                if golden_cross:
                    self.ma12_count = 1
                elif self.lineMa1[-1] < self.lineMa2[-1]:
                    self.ma12_count -= 1

            elif self.ma12_count >= 0:
                if dead_cross:
                    self.ma12_count = -1
                elif self.lineMa1[-1] > self.lineMa2[-1]:
                    self.ma12_count += 1

        if len(self.lineMa2) >= 2 and len(self.lineMa3) > 2:
            golden_cross = self.lineMa2[-1] > self.lineMa2[-2] and self.lineMa2[-1] > self.lineMa3[-1] \
                           and self.lineMa2[-2] <= self.lineMa3[-2]
            dead_cross = self.lineMa2[-1] < self.lineMa2[-2] and self.lineMa2[-1] < self.lineMa3[-1] and \
                         self.lineMa2[-2] >= self.lineMa3[-2]

            if self.ma23_count <= 0:
                if golden_cross:
                    self.ma23_count = 1
                elif self.lineMa2[-1] < self.lineMa3[-1]:
                    self.ma23_count -= 1

            elif self.ma23_count >= 0:
                if dead_cross:
                    self.ma23_count = -1
                elif self.lineMa2[-1] > self.lineMa3[-1]:
                    self.ma23_count += 1

        if len(self.lineMa1) >= 2 and len(self.lineMa3) > 2:
            golden_cross = self.lineMa1[-1] > self.lineMa1[-2] and self.lineMa1[-1] > self.lineMa3[-1] \
                           and self.lineMa1[-2] <= self.lineMa3[-2]
            dead_cross = self.lineMa1[-1] < self.lineMa1[-2] and self.lineMa1[-1] < self.lineMa3[-1] \
                         and self.lineMa1[-2] >= self.lineMa3[-2]

            if self.ma13_count <= 0:
                if golden_cross:
                    self.ma13_count = 1
                elif self.lineMa1[-1] < self.lineMa3[-1]:
                    self.ma13_count -= 1

            elif self.ma13_count >= 0:
                if dead_cross:
                    self.ma13_count = -1
                elif self.lineMa1[-1] > self.lineMa3[-1]:
                    self.ma13_count += 1

    def rt_countMa(self):
        """
        实时计算MA得值
        :param ma_num:第几条均线, 1，对应inputMa1Len,,,,
        :return:
        """
        if self.inputMa1Len > 0:
            ma_len = min(len(self.lineClose), self.inputMa1Len)
            if ma_len > 0:
                listClose = self.lineClose[-ma_len - 2:] + [self.lineBar[-1].close]
                barMa = ta.MA(np.array(listClose, dtype=float), ma_len)
                self._rt_Ma1 = round(float(barMa[-1]), self.round_n)

                # 计算斜率
                if len(barMa) > 2 and barMa[-2] != 0:
                    self._rt_Ma1Atan = round(math.atan((barMa[-1] / barMa[-2] - 1) * 100) * 180 / math.pi,3)

        if self.inputMa2Len > 0:
            ma_len = min(len(self.lineClose), self.inputMa2Len)
            if ma_len > 0:
                listClose = self.lineClose[-ma_len - 2:] + [self.lineBar[-1].close]
                barMa = ta.MA(np.array(listClose, dtype=float), ma_len)
                self._rt_Ma2 = round(float(barMa[-1]), self.round_n)

                # 计算斜率
                if len(barMa) > 2 and barMa[-2] != 0:
                    self._rt_Ma2Atan = round(math.atan((barMa[-1] / barMa[-2] - 1) * 100) * 180 / math.pi, 3)


        if self.inputMa3Len > 0:
            ma_len = min(len(self.lineClose), self.inputMa3Len)
            if ma_len > 0:
                listClose = self.lineClose[-ma_len - 2:] + [self.lineBar[-1].close]
                barMa = ta.MA(np.array(listClose, dtype=float), ma_len)
                self._rt_Ma3 = round(float(barMa[-1]), self.round_n)

                # 计算斜率
                if len(barMa) > 2 and barMa[-2] != 0:
                    self._rt_Ma3Atan = round(math.atan((barMa[-1] / barMa[-2] - 1) * 100) * 180 / math.pi, 3)

    def getRuntimeMa(self, ma_num):
        """
        获取实时MA的值
        :param ma_num:
        :return:
        """
        self.check_rt_funcs(self.rt_countMa)

        if ma_num == 1:
            return self._rt_Ma1
        elif ma_num == 2:
            return self._rt_Ma2
        elif ma_num == 3:
            return self._rt_Ma3
        else:
            return None

    @property
    def rt_Ma1(self):
        self.check_rt_funcs(self.rt_countMa)
        return self._rt_Ma1

    @property
    def rt_Ma2(self):
        self.check_rt_funcs(self.rt_countMa)
        return self._rt_Ma2

    @property
    def rt_Ma3(self):
        self.check_rt_funcs(self.rt_countMa)
        return self._rt_Ma3

    @property
    def rt_Ma1Atan(self):
        self.check_rt_funcs(self.rt_countMa)
        return self._rt_Ma1Atan

    @property
    def rt_Ma2Atan(self):
        self.check_rt_funcs(self.rt_countMa)
        return self._rt_Ma2Atan

    @property
    def rt_Ma3Atan(self):
        self.check_rt_funcs(self.rt_countMa)
        return self._rt_Ma3Atan
    # ----------------------------------------------------------------------
    def __recountEma(self):
        """计算K线的EMA1 和EMA2"""

        if not (self.inputEma1Len > 0 or self.inputEma2Len > 0 or self.inputEma3Len > 0):  # 不计算
            return

        l = len(self.lineBar)
        ema1_data_len = min(self.inputEma1Len * 4, self.inputEma1Len + 40) if self.inputEma1Len > 0 else 0
        ema2_data_len = min(self.inputEma2Len * 4, self.inputEma2Len + 40) if self.inputEma2Len > 0 else 0
        ema3_data_len = min(self.inputEma3Len * 4, self.inputEma3Len + 40) if self.inputEma3Len > 0 else 0
        max_data_len = max(ema1_data_len, ema2_data_len, ema3_data_len)
        # 1、lineBar满足长度才执行计算
        if len(self.lineBar) < max_data_len:
            self.debugCtaLog(u'数据未充分,当前Bar数据数量：{0}，计算EMA需要：{1}'.
                             format(len(self.lineBar), max_data_len))
            return

        # 计算第一条EMA均线
        if self.inputEma1Len > 0:
            if self.inputEma1Len > l:
                ema1Len = l
            else:
                ema1Len = self.inputEma1Len

            # 3、获取前InputN周期(不包含当前周期）的K线
            if self.mode == self.TICK_MODE:
                listClose = [x.close for x in self.lineBar[-ema1_data_len - 1:-1]]
            else:
                listClose = [x.close for x in self.lineBar[-ema1_data_len:]]

            barEma1 = ta.EMA(np.array(listClose, dtype=float), ema1Len)[-1]

            barEma1 = round(float(barEma1), self.round_n)

            if len(self.lineEma1) > max(self.inputEma1Len, 20):
                del self.lineEma1[0]
            self.lineEma1.append(barEma1)

        # 计算第二条EMA均线
        if self.inputEma2Len > 0:
            if self.inputEma2Len > l:
                ema2Len = l
            else:
                ema2Len = self.inputEma2Len

            # 3、获取前InputN周期(不包含当前周期）的自适应均线
            if self.mode == self.TICK_MODE:
                listClose = [x.close for x in self.lineBar[-ema2_data_len - 1:-1]]
            else:
                listClose = [x.close for x in self.lineBar[-ema2_data_len:]]

            barEma2 = ta.EMA(np.array(listClose, dtype=float), ema2Len)[-1]

            barEma2 = round(float(barEma2), self.round_n)

            if len(self.lineEma2) > max(self.inputEma2Len, 20):
                del self.lineEma2[0]
            self.lineEma2.append(barEma2)

        # 计算第三条EMA均线
        if self.inputEma3Len > 0:
            if self.inputEma3Len > l:
                ema3Len = l
            else:
                ema3Len = self.inputEma3Len

            # 3、获取前InputN周期(不包含当前周期）的自适应均线
            if self.mode == self.TICK_MODE:
                listClose = [x.close for x in self.lineBar[-ema3_data_len - 1:-1]]
            else:
                listClose = [x.close for x in self.lineBar[-ema3_data_len:]]

            barEma3 = ta.EMA(np.array(listClose, dtype=float), ema3_data_len)[-1]

            barEma3 = round(float(barEma3), self.round_n)

            if len(self.lineEma3) > max(self.inputEma3Len, 20):
                del self.lineEma3[0]
            self.lineEma3.append(barEma3)

    def getRuntimeEma(self, ema_num):
        """
        实时计算EMA得值
        :param ema_num:第几条均线, 1，对应inputEma1Len,,,,
        :return:
        """
        if ema_num not in [1, 2, 3]:
            return None

        ema_len = 1
        if ema_num == 1 and self.inputEma1Len > 0:
            ema_len = self.inputEma1Len
        elif ema_num == 2 and self.inputEma2Len > 0:
            ema_len = self.inputEma2Len
        elif ema_num == 3 and self.inputEma3Len > 0:
            ema_len = self.inputEma3Len
        else:
            return None

        ema_data_len = min(ema_len * 2, ema_len + 20)
        # 1、lineBar满足长度才执行计算
        if len(self.lineBar) < ema_data_len:
            self.debugCtaLog(u'数据未充分,当前Bar数据数量：{0}，计算实时EMA需要：{1}'.
                             format(len(self.lineBar), ema_data_len))
            return

        listClose = [x.close for x in self.lineBar[-ema_data_len - 1:]]
        rtEma = ta.EMA(np.array(listClose, dtype=float), ema_len)[-1]
        rtEma = round(float(rtEma), self.round_n)
        return rtEma

    def __recountDmi(self):
        """计算K线的DMI数据和条件"""

        if self.inputDmiLen <= 0:  # 不计算
            return

        # 1、lineMx满足长度才执行计算
        if len(self.lineBar) < self.inputDmiLen + 1:
            self.debugCtaLog(u'数据未充分,当前Bar数据数量：{0}，计算DMI需要：{1}'.format(len(self.lineBar), self.inputDmiLen + 1))
            return

        # 2、根据当前High，Low，(不包含当前周期）重新计算TR1，PDM，MDM和ATR
        barTr1 = EMPTY_FLOAT  # 获取InputP周期内的价差最大值之和
        barPdm = EMPTY_FLOAT  # InputP周期内的做多价差之和
        barMdm = EMPTY_FLOAT  # InputP周期内的做空价差之和

        if self.mode == self.TICK_MODE:
            idx = 2
        else:
            idx = 1

        for i in range(len(self.lineBar) - idx, len(self.lineBar) - idx - self.inputDmiLen, -1):  # 周期 inputDmiLen
            # 3.1、计算TR1

            # 当前周期最高与最低的价差
            high_low_spread = self.lineBar[i].high - self.lineBar[i].low
            # 当前周期最高与昨收价的价差
            high_preclose_spread = abs(self.lineBar[i].high - self.lineBar[i - 1].close)
            # 当前周期最低与昨收价的价差
            low_preclose_spread = abs(self.lineBar[i].low - self.lineBar[i - 1].close)

            # 最大价差
            max_spread = max(high_low_spread, high_preclose_spread, low_preclose_spread)
            barTr1 = barTr1 + float(max_spread)

            # 今高与昨高的价差
            high_prehigh_spread = self.lineBar[i].high - self.lineBar[i - 1].high
            # 昨低与今低的价差
            low_prelow_spread = self.lineBar[i - 1].low - self.lineBar[i].low

            # 3.2、计算周期内的做多价差之和
            if high_prehigh_spread > 0 and high_prehigh_spread > low_prelow_spread:
                barPdm = barPdm + high_prehigh_spread

            # 3.3、计算周期内的做空价差之和
            if low_prelow_spread > 0 and low_prelow_spread > high_prehigh_spread:
                barMdm = barMdm + low_prelow_spread

        # 6、计算上升动向指标，即做多的比率
        if barTr1 == 0:
            self.barPdi = 0
        else:
            self.barPdi = barPdm * 100 / barTr1

        if len(self.linePdi) > self.inputDmiLen + 1:
            del self.linePdi[0]

        self.linePdi.append(self.barPdi)

        # 7、计算下降动向指标，即做空的比率
        if barTr1 == 0:
            self.barMdi = 0
        else:
            self.barMdi = barMdm * 100 / barTr1

        # 8、计算平均趋向指标 Adx，Adxr
        if self.barMdi + self.barPdi == 0:
            dx = 0
        else:
            dx = 100 * abs(self.barMdi - self.barPdi) / (self.barMdi + self.barPdi)

        if len(self.lineMdi) > self.inputDmiLen + 1:
            del self.lineMdi[0]

        self.lineMdi.append(self.barMdi)

        if len(self.lineDx) > self.inputDmiLen + 1:
            del self.lineDx[0]

        self.lineDx.append(dx)

        # 平均趋向指标，MA计算
        if len(self.lineDx) < self.inputDmiLen + 1:
            self.barAdx = dx
        else:
            self.barAdx = ta.EMA(np.array(self.lineDx, dtype=float), self.inputDmiLen)[-1]

        # 保存Adx值
        if len(self.lineAdx) > self.inputDmiLen + 1:
            del self.lineAdx[0]

        self.lineAdx.append(self.barAdx)

        # 趋向平均值，为当日ADX值与1周期前的ADX值的均值
        if len(self.lineAdx) == 1:
            self.barAdxr = self.lineAdx[-1]
        else:
            self.barAdxr = (self.lineAdx[-1] + self.lineAdx[-2]) / 2

        # 保存Adxr值
        if len(self.lineAdxr) > self.inputDmiLen + 1:
            del self.lineAdxr[0]
        self.lineAdxr.append(self.barAdxr)

        # 7、计算A，ADX值持续高于前一周期时，市场行情将维持原趋势
        if len(self.lineAdx) < 2:
            self.barAdxTrend = False
        elif self.lineAdx[-1] > self.lineAdx[-2]:
            self.barAdxTrend = True
        else:
            self.barAdxTrend = False

        # ADXR值持续高于前一周期时,波动率比上一周期高
        if len(self.lineAdxr) < 2:
            self.barAdxrTrend = False
        elif self.lineAdxr[-1] > self.lineAdxr[-2]:
            self.barAdxrTrend = True
        else:
            self.barAdxrTrend = False

        # 多过滤器条件,做多趋势，ADX高于前一天，上升动向> inputDmiMax
        if self.barPdi > self.barMdi and self.barAdxTrend and self.barAdxrTrend and self.barPdi >= self.inputDmiMax:
            self.buyFilterCond = True

            self.writeCtaLog(u'{0}[DEBUG]Buy Signal On Bar,Pdi:{1}>Mdi:{2},adx[-1]:{3}>Adx[-2]:{4}'
                             .format(self.curTick.datetime, self.barPdi, self.barMdi, self.lineAdx[-1],
                                     self.lineAdx[-2]))
        else:
            self.buyFilterCond = False

        # 空过滤器条件 做空趋势，ADXR高于前一天，下降动向> inputMM
        if self.barPdi < self.barMdi and self.barAdxTrend and self.barAdxrTrend and self.barMdi >= self.inputDmiMax:
            self.sellFilterCond = True

            self.writeCtaLog(u'{0}[DEBUG]Short Signal On Bar,Pdi:{1}<Mdi:{2},adx[-1]:{3}>Adx[-2]:{4}'
                             .format(self.curTick.datetime, self.barPdi, self.barMdi, self.lineAdx[-1],
                                     self.lineAdx[-2]))
        else:
            self.sellFilterCond = False

    def __recountAtr(self):
        """计算Mx K线的各类数据和条件"""

        # 1、lineMx满足长度才执行计算
        maxAtrLen = max(self.inputAtr1Len, self.inputAtr2Len, self.inputAtr3Len)

        if maxAtrLen <= 0:  # 不计算
            return

        data_need_len = min(7, maxAtrLen)
        line_bar_len = len(self.lineBar)

        if line_bar_len < data_need_len:
            self.debugCtaLog(u'数据未充分,当前Bar数据数量：{0}，计算ATR需要：{1}'.
                             format(line_bar_len,data_need_len))
            return

        if self.mode == self.TICK_MODE:
            idx = 2
        else:
            idx = 1

        # 首次计算
        if (self.inputAtr1Len > 0 and len(self.lineAtr1) < 1) \
                or (self.inputAtr2Len > 0 and len(self.lineAtr2) < 1) \
                or (self.inputAtr3Len > 0 and len(self.lineAtr3) < 1):

            # 根据当前High，Low，(不包含当前周期）重新计算TR1和ATR
            barTr1 = EMPTY_FLOAT  # 获取inputAtr1Len周期内的价差最大值之和
            barTr2 = EMPTY_FLOAT  # 获取inputAtr2Len周期内的价差最大值之和
            barTr3 = EMPTY_FLOAT  # 获取inputAtr3Len周期内的价差最大值之和

            j = 0

            for i in range(len(self.lineBar) - idx, len(self.lineBar) - idx - data_need_len, -1):  # 周期 inputP
                # 3.1、计算TR

                # 当前周期最高与最低的价差
                high_low_spread = self.lineBar[i].high - self.lineBar[i].low
                # 当前周期最高与昨收价的价差
                high_preclose_spread = abs(self.lineBar[i].high - self.lineBar[i - 1].close)
                # 当前周期最低与昨收价的价差
                low_preclose_spread = abs(self.lineBar[i].low - self.lineBar[i - 1].close)

                # 最大价差
                max_spread = max(high_low_spread, high_preclose_spread, low_preclose_spread)
                if j < self.inputAtr1Len:
                    barTr1 = barTr1 + float(max_spread)
                if j < self.inputAtr2Len:
                    barTr2 = barTr2 + float(max_spread)
                if j < self.inputAtr3Len:
                    barTr3 = barTr3 + float(max_spread)

                j = j + 1

        else:  # 只计算一个

            # 当前周期最高与最低的价差
            high_low_spread = self.lineBar[0 - idx].high - self.lineBar[0 - idx].low
            # 当前周期最高与昨收价的价差
            high_preclose_spread = abs(self.lineBar[0 - idx].high - self.lineBar[-1 - idx].close)
            # 当前周期最低与昨收价的价差
            low_preclose_spread = abs(self.lineBar[0 - idx].low - self.lineBar[-1 - idx].close)

            # 最大价差
            barTr1 = max(high_low_spread, high_preclose_spread, low_preclose_spread)
            barTr2 = barTr1
            barTr3 = barTr1

        # 计算 ATR
        if self.inputAtr1Len > 0:
            data_4_atr1 = min(line_bar_len,self.inputAtr1Len)
            if len(self.lineAtr1) < 1:
                self.barAtr1 = round(barTr1 / data_4_atr1, self.round_n)
            else:
                self.barAtr1 = round((self.lineAtr1[-1] * (data_4_atr1 - 1) + barTr1) / data_4_atr1,
                                     self.round_n)

            if len(self.lineAtr1) > self.inputAtr1Len + 1:
                del self.lineAtr1[0]
            self.lineAtr1.append(self.barAtr1)

        if self.inputAtr2Len > 0:
            data_4_atr2 = min(line_bar_len, self.inputAtr2Len)
            if len(self.lineAtr2) < 1:
                self.barAtr2 = round(barTr2 / data_4_atr2, self.round_n)
            else:
                self.barAtr2 = round((self.lineAtr2[-1] * (data_4_atr2 - 1) + barTr2) / data_4_atr2,
                                     self.round_n)

            if len(self.lineAtr2) > self.inputAtr2Len + 1:
                del self.lineAtr2[0]
            self.lineAtr2.append(self.barAtr2)

        if self.inputAtr3Len > 0:
            data_4_atr3 = min(line_bar_len, self.inputAtr3Len)
            if len(self.lineAtr3) < 1:
                self.barAtr3 = round(barTr3 / data_4_atr3, self.round_n)
            else:
                self.barAtr3 = round((self.lineAtr3[-1] * (data_4_atr3 - 1) + barTr3) / data_4_atr3,
                                     self.round_n)

            if len(self.lineAtr3) > self.inputAtr3Len + 1:
                del self.lineAtr3[0]

            self.lineAtr3.append(self.barAtr3)

    # ----------------------------------------------------------------------
    def __recoundAvgVol(self):
        """计算平均成交量"""

        # 1、lineBar满足长度才执行计算
        if self.inputVolLen <= 0:  # 不计算
            return

        if len(self.lineBar) < self.inputVolLen + 1:
            self.debugCtaLog(u'数据未充分,当前Bar数据数量：{0}，计算Avg Vol需要：{1}'.
                             format(len(self.lineBar), self.inputVolLen + 1))
            return

        if self.mode == self.TICK_MODE:
            listVol = [x.volume for x in self.lineBar[-self.inputVolLen - 1: -1]]
        else:
            listVol = [x.volume for x in self.lineBar[-self.inputVolLen:]]

        sumVol = ta.SUM(np.array(listVol, dtype=float), timeperiod=self.inputVolLen)[-1]

        avgVol = round(sumVol / self.inputVolLen, 0)

        self.lineAvgVol.append(avgVol)

    # ----------------------------------------------------------------------
    def __recountRsi(self):
        """计算K线的RSI"""

        if self.inputRsi1Len <= 0 and self.inputRsi2Len <= 0:
            return

        # 1、lineBar满足长度才执行计算
        if len(self.lineBar) < self.inputRsi1Len + 2:
            self.debugCtaLog(u'数据未充分,当前Bar数据数量：{0}，计算RSI需要：{1}'.
                             format(len(self.lineBar), self.inputRsi1Len + 2))
            return

        # 计算第1根RSI曲线
        # 3、inputRsi1Len(包含当前周期）的相对强弱
        if self.mode == self.TICK_MODE:
            listClose = [x.close for x in self.lineBar[-self.inputRsi1Len - 2:-1]]
            idx = 2
        else:
            listClose = [x.close for x in self.lineBar[-self.inputRsi1Len - 1:]]
            idx = 1

        barRsi = ta.RSI(np.array(listClose, dtype=float), self.inputRsi1Len)[-1]
        barRsi = round(float(barRsi), self.round_n)

        l = len(self.lineRsi1)
        if l > self.inputRsi1Len * 8:
            del self.lineRsi1[0]

        self.lineRsi1.append(barRsi)

        if l > 3:
            # 峰
            if self.lineRsi1[-1] < self.lineRsi1[-2] and self.lineRsi1[-3] < self.lineRsi1[-2]:
                t = {}
                t["Type"] = u'T'
                t["RSI"] = self.lineRsi1[-2]
                t["Close"] = self.lineBar[-1 - idx].close

                if len(self.lineRsiTop) > self.inputRsi1Len:
                    del self.lineRsiTop[0]

                self.lineRsiTop.append(t)
                self.lastRsiTopButtom = self.lineRsiTop[-1]

            # 谷
            elif self.lineRsi1[-1] > self.lineRsi1[-2] and self.lineRsi1[-3] > self.lineRsi1[-2]:
                b = {}
                b["Type"] = u'B'
                b["RSI"] = self.lineRsi1[-2]
                b["Close"] = self.lineBar[-1 - idx].close

                if len(self.lineRsiButtom) > self.inputRsi1Len:
                    del self.lineRsiButtom[0]
                self.lineRsiButtom.append(b)
                self.lastRsiTopButtom = self.lineRsiButtom[-1]

        # 计算第二根RSI曲线
        if self.inputRsi2Len > 0:
            if len(self.lineBar) < self.inputRsi2Len + 2:
                return

            if self.mode == self.TICK_MODE:
                listClose = [x.close for x in self.lineBar[-self.inputRsi2Len - 2:-1]]
            else:
                listClose = [x.close for x in self.lineBar[-self.inputRsi2Len - 1:]]

            barRsi = ta.RSI(np.array(listClose, dtype=float), self.inputRsi2Len)[-1]
            barRsi = round(float(barRsi), self.round_n)

            l = len(self.lineRsi2)
            if l > self.inputRsi2Len * 8:
                del self.lineRsi2[0]

            self.lineRsi2.append(barRsi)

    def __recountCmi(self):
        """市场波动指数（Choppy Market Index，CMI）是一个用来判断市场走势类型的技术分析指标。
        它通过计算当前收盘价与一定周期前的收盘价的差值与这段时间内价格波动的范围的比值，来判断目前的股价走势是趋势还是盘整。
        市场波动指数CMI的计算公式：
        CMI=(Abs(Close-ref(close,(n-1)))*100/(HHV(high,n)-LLV(low,n))
        其中，Abs是绝对值。
        n是周期数，例如３０。
        市场波动指数CMI的使用方法：
        这个指标的重要用途是来区分目前的股价走势类型：盘整，趋势。当CMI指标小于２０时，市场走势是盘整；当CMI指标大于２０时，市场在趋势期。
        CMI指标还可以用于预测股价走势类型的转变。因为物极必反，当CMI长期处于０附近，此时，股价走势很可能从盘整转为趋势；当CMI长期处于１００附近，此时，股价趋势很可能变弱，形成盘整。
        """

        if self.inputCmiLen <= EMPTY_INT: return

        # 1、lineBar满足长度才执行计算
        if len(self.lineBar) < self.inputCmiLen:
            self.debugCtaLog(u'数据未充分,当前Bar数据数量：{0}，计算CMI需要：{1}'.
                             format(len(self.lineBar), self.inputCmiLen))
            return

        if self.mode == self.TICK_MODE:
            listClose = [x.close for x in self.lineBar[-self.inputCmiLen - 1:-1]]
            idx = 2
        else:
            listClose = [x.close for x in self.lineBar[-self.inputCmiLen:]]
            idx = 1

        hhv = max(listClose)
        llv = min(listClose)

        if hhv == llv:
            cmi = 100
        else:
            cmi = abs(self.lineBar[0 - idx].close - self.lineBar[-1 - idx].close) * 100 / (hhv - llv)

        cmi = round(cmi, self.round_n)

        if len(self.lineCmi) > self.inputCmiLen:
            del self.lineCmi[0]

        self.lineCmi.append(cmi)

    def __recountBoll(self):
        """布林特线"""
        if not (self.inputBollLen > EMPTY_INT or self.inputBoll2Len > EMPTY_INT or
                self.inputBollTBLen > EMPTY_INT or self.inputBoll2TBLen > EMPTY_INT):  # 不计算
            return

        l = len(self.lineBar)

        if self.inputBollLen > EMPTY_INT:
            if l < min(7, self.inputBollLen) :
                self.debugCtaLog(u'数据未充分,当前Bar数据数量：{0}，计算Boll需要：{1}'.
                                 format(len(self.lineBar), min(14, self.inputBollLen) + 1))
            else:
                if l < self.inputBollLen :
                    bollLen = l
                else:
                    bollLen = self.inputBollLen

                # 不包含当前最新的Bar
                if self.mode == self.TICK_MODE:
                    listClose = [x.close for x in self.lineBar[-bollLen - 1:-1]]
                else:
                    listClose = [x.close for x in self.lineBar[-bollLen:]]

                upper, middle, lower = ta.BBANDS(np.array(listClose, dtype=float),
                                                 timeperiod=bollLen, nbdevup=self.inputBollStdRate,
                                                 nbdevdn=self.inputBollStdRate, matype=0)
                if len(self.lineUpperBand) > self.inputBollLen * 8:
                    del self.lineUpperBand[0]
                if len(self.lineMiddleBand) > self.inputBollLen * 8:
                    del self.lineMiddleBand[0]
                if len(self.lineLowerBand) > self.inputBollLen * 8:
                    del self.lineLowerBand[0]
                if len(self.lineBollStd) > self.inputBollLen * 8:
                    del self.lineBollStd[0]

                # 1标准差
                std = (upper[-1] - lower[-1]) / (self.inputBollStdRate * 2)
                self.lineBollStd.append(std)

                u = round(upper[-1], self.round_n)
                self.lineUpperBand.append(u)  # 上轨
                self.lastBollUpper = u - u % self.minDiff  # 上轨取整

                m = round(middle[-1], self.round_n)
                self.lineMiddleBand.append(m)  # 中轨
                self.lastBollMiddle = m - m % self.minDiff  # 中轨取整

                l = round(lower[-1], self.round_n)
                self.lineLowerBand.append(l)  # 下轨
                self.lastBollLower = l - l % self.minDiff  # 下轨取整

                # 计算斜率
                if len(self.lineUpperBand) > 2 and self.lineUpperBand[-2] != 0:
                    up_atan = math.atan((self.lineUpperBand[-1] / self.lineUpperBand[-2] - 1) * 100) * 180 / math.pi
                    up_atan = round(up_atan, 3)
                    if len(self.lineUpperBandAtan) > self.inputBollLen * 8:
                        del self.lineUpperBandAtan[0]
                    self.lineUpperBandAtan.append(up_atan)
                if len(self.lineMiddleBand) > 2 and self.lineMiddleBand[-2] != 0:
                    mid_atan = math.atan((self.lineMiddleBand[-1] / self.lineMiddleBand[-2] - 1) * 100) * 180 / math.pi
                    mid_atan = round(mid_atan, 3)
                    if len(self.lineMiddleBandAtan) > self.inputBollLen * 8:
                        del self.lineMiddleBandAtan[0]
                    self.lineMiddleBandAtan.append(mid_atan)
                if len(self.lineLowerBand) > 2 and self.lineLowerBand[-2] != 0:
                    low_atan = math.atan((self.lineLowerBand[-1] / self.lineLowerBand[-2] - 1) * 100) * 180 / math.pi
                    low_atan = round(low_atan, 3)
                    if len(self.lineLowerBandAtan) > self.inputBollLen * 8:
                        del self.lineLowerBandAtan[0]
                    self.lineLowerBandAtan.append(low_atan)

        l = len(self.lineBar)
        if self.inputBoll2Len > EMPTY_INT:
            if l < min(14, self.inputBoll2Len) + 1:
                self.debugCtaLog(u'数据未充分,当前Bar数据数量：{0}，计算Boll2需要：{1}'.
                                 format(len(self.lineBar), min(14, self.inputBoll2Len) + 1))
            else:
                if l < self.inputBoll2Len + 2:
                    boll2Len = l - 1
                else:
                    boll2Len = self.inputBoll2Len

                # 不包含当前最新的Bar
                if self.mode == self.TICK_MODE:
                    listClose = [x.close for x in self.lineBar[-boll2Len - 1:-1]]
                else:
                    listClose = [x.close for x in self.lineBar[-boll2Len:]]

                upper, middle, lower = ta.BBANDS(np.array(listClose, dtype=float),
                                                 timeperiod=boll2Len, nbdevup=self.inputBoll2StdRate,
                                                 nbdevdn=self.inputBoll2StdRate, matype=0)
                if len(self.lineUpperBand2) > self.inputBoll2Len * 8:
                    del self.lineUpperBand2[0]
                if len(self.lineMiddleBand2) > self.inputBoll2Len * 8:
                    del self.lineMiddleBand2[0]
                if len(self.lineLowerBand2) > self.inputBoll2Len * 8:
                    del self.lineLowerBand2[0]
                if len(self.lineBoll2Std) > self.inputBoll2Len * 8:
                    del self.lineBoll2Std[0]

                # 1标准差
                std = (upper[-1] - lower[-1]) / (self.inputBoll2StdRate * 2)
                self.lineBoll2Std.append(std)

                u = round(upper[-1], self.round_n)
                self.lineUpperBand2.append(u)  # 上轨
                self.lastBoll2Upper = u - u % self.minDiff  # 上轨取整

                m = round(middle[-1], self.round_n)
                self.lineMiddleBand2.append(m)  # 中轨
                self.lastBoll2Middle = m - m % self.minDiff  # 中轨取整

                l = round(lower[-1], self.round_n)
                self.lineLowerBand2.append(l)  # 下轨
                self.lastBoll2Lower = l - l % self.minDiff  # 下轨取整

                # 计算斜率
                if len(self.lineUpperBand2) > 2 and self.lineUpperBand2[-2] != 0:
                    up_atan = math.atan((self.lineUpperBand2[-1] / self.lineUpperBand2[-2] - 1) * 100) * 180 / math.pi
                    up_atan = round(up_atan, 3)
                    if len(self.lineUpperBand2Atan) > self.inputBoll2Len * 8:
                        del self.lineUpperBand2Atan[0]
                    self.lineUpperBand2Atan.append(up_atan)
                if len(self.lineMiddleBand2) > 2 and self.lineMiddleBand2[-2] != 0:
                    mid_atan = math.atan((self.lineMiddleBand2[-1] / self.lineMiddleBand2[-2] - 1) * 100) * 180 / math.pi
                    mid_atan = round(mid_atan, 3)
                    if len(self.lineMiddleBand2Atan) > self.inputBoll2Len * 8:
                        del self.lineMiddleBand2Atan[0]
                    self.lineMiddleBand2Atan.append(mid_atan)
                if len(self.lineLowerBand2) > 2 and self.lineLowerBand2[-2] != 0:
                    low_atan = math.atan((self.lineLowerBand2[-1] / self.lineLowerBand2[-2] - 1) * 100) * 180 / math.pi
                    low_atan = round(low_atan, 3)
                    if len(self.lineLowerBand2Atan) > self.inputBoll2Len * 8:
                        del self.lineLowerBand2Atan[0]
                    self.lineLowerBand2Atan.append(low_atan)

        l = len(self.lineBar)
        if self.inputBollTBLen > EMPTY_INT:
            if l < min(14, self.inputBollTBLen) + 1:
                self.debugCtaLog(u'数据未充分,当前Bar数据数量：{0}，计算Boll需要：{1}'.
                                 format(len(self.lineBar), min(14, self.inputBollTBLen) + 1))
            else:
                if l < self.inputBollTBLen + 2:
                    bollLen = l - 1
                else:
                    bollLen = self.inputBollTBLen

                # 不包含当前最新的Bar
                if self.mode == self.TICK_MODE:
                    listClose = [x.close for x in self.lineBar[-bollLen - 1:-1]]
                else:
                    listClose = [x.close for x in self.lineBar[-bollLen:]]

                if len(self.lineUpperBand) > self.inputBollTBLen * 8:
                    del self.lineUpperBand[0]
                if len(self.lineMiddleBand) > self.inputBollTBLen * 8:
                    del self.lineMiddleBand[0]
                if len(self.lineLowerBand) > self.inputBollTBLen * 8:
                    del self.lineLowerBand[0]
                if len(self.lineBollStd) > self.inputBollTBLen * 8:
                    del self.lineBollStd[0]

                # 1标准差
                std = np.std(listClose, ddof=1)
                self.lineBollStd.append(std)

                m = np.mean(listClose)
                self.lineMiddleBand.append(m)  # 中轨
                self.lastBollMiddle = m - m % self.minDiff  # 中轨取整

                u = m + self.inputBollStdRate * std
                self.lineUpperBand.append(u)  # 上轨
                self.lastBollUpper = u - u % self.minDiff  # 上轨取整

                l = m - self.inputBollStdRate * std
                self.lineLowerBand.append(l)  # 下轨
                self.lastBollLower = l - l % self.minDiff  # 下轨取整

                # 计算斜率
                if len(self.lineUpperBand) > 2 and self.lineUpperBand[-2] != 0:
                    up_atan = math.atan((self.lineUpperBand[-1] / self.lineUpperBand[-2] - 1) * 100) * 180 / math.pi
                    up_atan = round(up_atan, 3)
                    if len(self.lineUpperBandAtan) > self.inputBollTBLen * 8:
                        del self.lineUpperBandAtan[0]
                    self.lineUpperBandAtan.append(up_atan)
                if len(self.lineMiddleBand) > 2 and self.lineMiddleBand[-2] != 0:
                    mid_atan = math.atan((self.lineMiddleBand[-1] / self.lineMiddleBand[-2] - 1) * 100) * 180 / math.pi
                    mid_atan = round(mid_atan, 3)
                    if len(self.lineMiddleBandAtan) > self.inputBollTBLen * 8:
                        del self.lineMiddleBandAtan[0]
                    self.lineMiddleBandAtan.append(mid_atan)
                if len(self.lineLowerBand) > 2 and self.lineLowerBand[-2] != 0:
                    low_atan = math.atan((self.lineLowerBand[-1] / self.lineLowerBand[-2] - 1) * 100) * 180 / math.pi
                    low_atan = round(low_atan, 3)
                    if len(self.lineLowerBandAtan) > self.inputBollTBLen * 8:
                        del self.lineLowerBandAtan[0]
                    self.lineLowerBandAtan.append(low_atan)

        l = len(self.lineBar)
        if self.inputBoll2TBLen > EMPTY_INT:
            if l < min(14, self.inputBoll2TBLen) + 1:
                self.debugCtaLog(u'数据未充分,当前Bar数据数量：{0}，计算Boll2需要：{1}'.
                                 format(len(self.lineBar), min(14, self.inputBoll2TBLen) + 1))
            else:
                if l < self.inputBoll2TBLen + 2:
                    boll2Len = l - 1
                else:
                    boll2Len = self.inputBoll2TBLen

                # 不包含当前最新的Bar
                if self.mode == self.TICK_MODE:
                    listClose = [x.close for x in self.lineBar[-boll2Len - 1:-1]]
                else:
                    listClose = [x.close for x in self.lineBar[-boll2Len:]]

                if len(self.lineUpperBand2) > self.inputBoll2TBLen * 8:
                    del self.lineUpperBand2[0]
                if len(self.lineMiddleBand2) > self.inputBoll2TBLen * 8:
                    del self.lineMiddleBand2[0]
                if len(self.lineLowerBand2) > self.inputBoll2TBLen * 8:
                    del self.lineLowerBand2[0]
                if len(self.lineBoll2Std) > self.inputBoll2TBLen * 8:
                    del self.lineBoll2Std[0]

                # 1标准差
                std = np.std(listClose, ddof=1)
                self.lineBoll2Std.append(std)

                m = np.mean(listClose)
                self.lineMiddleBand2.append(m)  # 中轨
                self.lastBoll2Middle = m - m % self.minDiff  # 中轨取整

                u = m + self.inputBoll2StdRate * std
                self.lineUpperBand2.append(u)  # 上轨
                self.lastBoll2Upper = u - u % self.minDiff  # 上轨取整

                l = m - self.inputBoll2StdRate * std
                self.lineLowerBand2.append(l)  # 下轨
                self.lastBoll2Lower = l - l % self.minDiff  # 下轨取整

                # 计算斜率
                if len(self.lineUpperBand2) > 2 and self.lineUpperBand2[-2] != 0:
                    up_atan = math.atan((self.lineUpperBand2[-1] / self.lineUpperBand2[-2] - 1) * 100) * 180 / math.pi
                    up_atan = round(up_atan, 3)
                    if len(self.lineUpperBand2Atan) > self.inputBoll2TBLen * 8:
                        del self.lineUpperBand2Atan[0]
                    self.lineUpperBand2Atan.append(up_atan)
                if len(self.lineMiddleBand2) > 2 and self.lineMiddleBand2[-2] != 0:
                    mid_atan = math.atan((self.lineMiddleBand2[-1] / self.lineMiddleBand2[-2] - 1) * 100) * 180 / math.pi
                    mid_atan = round(mid_atan, 3)
                    if len(self.lineMiddleBand2Atan) > self.inputBoll2TBLen * 8:
                        del self.lineMiddleBand2Atan[0]
                    self.lineMiddleBand2Atan.append(mid_atan)
                if len(self.lineLowerBand2) > 2 and self.lineLowerBand2[-2] != 0:
                    low_atan = math.atan((self.lineLowerBand2[-1] / self.lineLowerBand2[-2] - 1) * 100) * 180 / math.pi
                    low_atan = round(low_atan, 3)
                    if len(self.lineLowerBand2Atan) > self.inputBoll2TBLen * 8:
                        del self.lineLowerBand2Atan[0]
                    self.lineLowerBand2Atan.append(low_atan)

    def rt_countBoll(self):
        """实时计算布林上下轨，斜率"""
        boll_01_len = max(self.inputBollLen,self.inputBollTBLen)
        boll_02_len = max(self.inputBoll2Len, self.inputBoll2TBLen)

        if not (boll_01_len > EMPTY_INT or boll_02_len > EMPTY_INT):  # 不计算
            return

        close_len = len(self.lineClose)

        if boll_01_len > EMPTY_INT:
            if close_len < min(14, boll_01_len) + 1:
                return
            else:
                if close_len < boll_01_len + 2:
                    bollLen = close_len - 1
                else:
                    bollLen = boll_01_len

            listClose = [x.close for x in self.lineBar[-bollLen:]]
            if self.inputBollTBLen == EMPTY_INT:
                upper, middle, lower = ta.BBANDS(np.array(listClose, dtype=float),
                                                 timeperiod=bollLen, nbdevup=self.inputBollStdRate,
                                                 nbdevdn=self.inputBollStdRate, matype=0)

                # 1标准差
                std = (upper[-1] - lower[-1]) / (self.inputBollStdRate * 2)
                self._rt_Upper = round(upper[-1], self.round_n)
                self._rt_Middle = round(middle[-1], self.round_n)
                self._rt_Lower = round(lower[-1], self.round_n)
            else:
                # 1标准差
                std = np.std(listClose, ddof=1)
                m = np.mean(listClose)
                self._rt_Middle = round(m,self.round_n)
                u = m + self.inputBollStdRate * std
                self._rt_Upper = round(u,self.round_n)
                l = m - self.inputBollStdRate * std
                self._rt_Lower = round(l,self.round_n)

            # 计算斜率
            if len(self.lineUpperBand) > 2 and self.lineUpperBand[-1] != 0:
                up_atan = math.atan((self._rt_Upper / self.lineUpperBand[-1] - 1) * 100) * 180 / math.pi
                self._rt_UpperBandAtan = round(up_atan, 3)

            if len(self.lineMiddleBand) > 2 and self.lineMiddleBand[-1] != 0:
                mid_atan = math.atan((self._rt_Middle / self.lineMiddleBand[-1] - 1) * 100) * 180 / math.pi
                self._rt_MiddleBandAtan = round(mid_atan, 3)

            if len(self.lineLowerBand) > 2 and self.lineLowerBand[-1] != 0:
                low_atan = math.atan((self._rt_Lower / self.lineLowerBand[-1] - 1) * 100) * 180 / math.pi
                self._rt_LowerBandAtan = round(low_atan, 3)

        if boll_02_len > EMPTY_INT:
            if close_len < min(14, boll_02_len) + 1:
                return
            else:
                if close_len < boll_02_len + 2:
                    bollLen = close_len - 1
                else:
                    bollLen = boll_02_len

            listClose = [x.close for x in self.lineBar[-bollLen:]]
            if self.inputBoll2TBLen == EMPTY_INT:
                upper, middle, lower = ta.BBANDS(np.array(listClose, dtype=float),
                                                 timeperiod=bollLen, nbdevup=self.inputBollStdRate,
                                                 nbdevdn=self.inputBollStdRate, matype=0)

                # 1标准差
                std = (upper[-1] - lower[-1]) / (self.inputBoll2StdRate * 2)
                self._rt_Upper2 = round(upper[-1], self.round_n)
                self._rt_Middle2 = round(middle[-1], self.round_n)
                self._rt_Lower2 = round(lower[-1], self.round_n)
            else:
                # 1标准差
                std = np.std(listClose, ddof=1)
                m = np.mean(listClose)
                self._rt_Middle2 = round(m, self.round_n)
                u = m + self.inputBollStdRate * std
                self._rt_Upper2 = round(u, self.round_n)
                l = m - self.inputBollStdRate * std
                self._rt_Lower2 = round(l, self.round_n)

            # 计算斜率
            if len(self.lineUpperBand2) > 2 and self.lineUpperBand2[-1] != 0:
                up_atan = math.atan((self._rt_Upper2 / self.lineUpperBand2[-1] - 1) * 100) * 180 / math.pi
                self._rt_UpperBand2Atan = round(up_atan, 3)

            if len(self.lineMiddleBand2) > 2 and self.lineMiddleBand2[-1] != 0:
                mid_atan = math.atan((self._rt_Middle2 / self.lineMiddleBand2[-1] - 1) * 100) * 180 / math.pi
                self._rt_MiddleBand2Atan = round(mid_atan, 3)

            if len(self.lineLowerBand2) > 2 and self.lineLowerBand2[-1] != 0:
                low_atan = math.atan((self._rt_Lower2 / self.lineLowerBand2[-1] - 1) * 100) * 180 / math.pi
                self._rt_LowerBand2Atan = round(low_atan, 3)

    def check_rt_funcs(self,func):
        """检查调用函数名是否在实时计算函数清单中，如果没有，则添加并运行"""
        if func not in self.rt_funcs:
            self.writeCtaLog(u'{}添加{}到实时函数中'.format(self.name,str(func.__name__)))
            self.rt_funcs.add(func)
            func()

    @property
    def rt_Upper(self):
        self.check_rt_funcs(self.rt_countBoll)
        return self._rt_Upper
    @property
    def rt_Middle(self):
        self.check_rt_funcs(self.rt_countBoll)
        return self._rt_Middle

    @property
    def rt_Lower(self):
        self.check_rt_funcs(self.rt_countBoll)
        return self._rt_Lower

    @property
    def rt_UpperBandAtan(self):
        self.check_rt_funcs(self.rt_countBoll)
        return self._rt_UpperBandAtan

    @property
    def rt_MiddleBandAtan(self):
        self.check_rt_funcs(self.rt_countBoll)
        return self._rt_MiddleBandAtan

    @property
    def rt_LowerBandAtan(self):
        self.check_rt_funcs(self.rt_countBoll)
        return self._rt_LowerBandAtan

    @property
    def rt_Upper2(self):
        self.check_rt_funcs(self.rt_countBoll)
        return self._rt_Upper

    @property
    def rt_Middle2(self):
        self.check_rt_funcs(self.rt_countBoll)
        return self._rt_Middle

    @property
    def rt_Lower2(self):
        self.check_rt_funcs(self.rt_countBoll)
        return self._rt_Lower

    @property
    def rt_UpperBand2Atan(self):
        self.check_rt_funcs(self.rt_countBoll)
        return self._rt_UpperBand2Atan

    @property
    def rt_MiddleBand2Atan(self):
        self.check_rt_funcs(self.rt_countBoll)
        return self._rt_MiddleBand2Atan

    @property
    def rt_LowerBand2Atan(self):
        self.check_rt_funcs(self.rt_countBoll)
        return self._rt_LowerBand2Atan

    def __recountKdj(self, countInBar=False):
        """KDJ指标"""
        """
        KDJ指标的中文名称又叫随机指标，是一个超买超卖指标,最早起源于期货市场，由乔治·莱恩（George Lane）首创。
        随机指标KDJ最早是以KD指标的形式出现，而KD指标是在威廉指标的基础上发展起来的。
        不过KD指标只判断股票的超买超卖的现象，在KDJ指标中则融合了移动平均线速度上的观念，形成比较准确的买卖信号依据。在实践中，K线与D线配合J线组成KDJ指标来使用。
        KDJ指标在设计过程中主要是研究最高价、最低价和收盘价之间的关系，同时也融合了动量观念、强弱指标和移动平均线的一些优点。
        因此，能够比较迅速、快捷、直观地研判行情，被广泛用于股市的中短期趋势分析，是期货和股票市场上最常用的技术分析工具。
 
        第一步 计算RSV：即未成熟随机值（Raw Stochastic Value）。
        RSV 指标主要用来分析市场是处于“超买”还是“超卖”状态：
            - RSV高于80%时候市场即为超买状况，行情即将见顶，应当考虑出仓；
            - RSV低于20%时候，市场为超卖状况，行情即将见底，此时可以考虑加仓。
        N日RSV=(N日收盘价-N日内最低价）÷(N日内最高价-N日内最低价）×100%
        第二步 计算K值：当日K值 = 2/3前1日K值 + 1/3当日RSV ; 
        第三步 计算D值：当日D值 = 2/3前1日D值 + 1/3当日K值； 
        第四步 计算J值：当日J值 = 3当日K值 - 2当日D值. 

        """
        if self.inputKdjLen <= EMPTY_INT: return

        if len(self.lineBar) < self.inputKdjLen + 1:
            if not countInBar:
                self.debugCtaLog(u'数据未充分,当前Bar数据数量：{0}，计算KDJ需要：{1}'.format(len(self.lineBar), self.inputKdjLen + 1))
            return

        if self.inputKdjSlowLen == EMPTY_INT:
            self.inputKdjSlowLen = 3
        if self.inputKdjSmoothLen == EMPTY_INT:
            self.inputKdjSmoothLen = 3

        inputKdjLen = min(self.inputKdjLen, len(self.lineBar))
        # 数据是Tick模式，非bar内计算
        if self.mode == self.TICK_MODE and not countInBar:
            listClose = [x.close for x in self.lineBar[-self.inputKdjLen - 1:-1]]
            listHigh = [x.high for x in self.lineBar[-self.inputKdjLen - 1:-1]]
            listLow = [x.low for x in self.lineBar[-self.inputKdjLen - 1:-1]]
            idx = 2
        else:
            listClose = [x.close for x in self.lineBar[-self.inputKdjLen:]]
            listHigh = [x.high for x in self.lineBar[-self.inputKdjLen:]]
            listLow = [x.low for x in self.lineBar[-self.inputKdjLen:]]
            idx = 1

        hhv = max(listHigh)
        llv = min(listLow)

        if len(self.lineK) > 0:
            lastK = self.lineK[-1]
        else:
            lastK = 0

        if len(self.lineD) > 0:
            lastD = self.lineD[-1]
        else:
            lastD = 0

        if hhv == llv:
            rsv = 50
        else:
            rsv = (listClose[-1] - llv) / (hhv - llv) * 100

        self.lineKdjRSV.append(rsv)

        k = (self.inputKdjSlowLen - 1) * lastK / self.inputKdjSlowLen + rsv / self.inputKdjSlowLen
        if k < 0: k = 0
        if k > 100: k = 100

        d = (self.inputKdjSmoothLen - 1) * lastD / self.inputKdjSmoothLen + k / self.inputKdjSmoothLen
        if d < 0: d = 0
        if d > 100: d = 100

        j = self.inputKdjSmoothLen * k - (self.inputKdjSmoothLen - 1) * d

        if countInBar:
            self.lastD = d
            self.lastK = k
            self.lastJ = j
            return

        if len(self.lineK) > self.inputKdjLen * 8:
            del self.lineK[0]
        self.lineK.append(k)

        if len(self.lineD) > self.inputKdjLen * 8:
            del self.lineD[0]
        self.lineD.append(d)

        l = len(self.lineJ)
        if l > self.inputKdjLen * 8:
            del self.lineJ[0]
        self.lineJ.append(j)

        # 增加KDJ的J谷顶和波底
        if l > 3:
            # 峰
            if self.lineJ[-1] < self.lineJ[-2] and self.lineJ[-3] <= self.lineJ[-2]:

                t = {}
                t["Type"] = u'T'
                t["J"] = self.lineJ[-2]
                t["Close"] = self.lineBar[-1 - idx].close

                if len(self.lineKdjTop) > self.inputKdjLen:
                    del self.lineKdjTop[0]

                self.lineKdjTop.append(t)
                self.lastKdjTopButtom = self.lineKdjTop[-1]

            # 谷
            elif self.lineJ[-1] > self.lineJ[-2] and self.lineJ[-3] >= self.lineJ[-2]:

                b = {}
                b["Type"] = u'B'
                b["J"] = self.lineJ[-2]
                b["Close"] = self.lineBar[-1 - idx].close

                if len(self.lineKdjButtom) > self.inputKdjLen:
                    del self.lineKdjButtom[0]
                self.lineKdjButtom.append(b)
                self.lastKdjTopButtom = self.lineKdjButtom[-1]

        self.update_kd_cross()

    def __recountKdj_TB(self, countInBar=False):
        """KDJ指标"""
        """
        KDJ指标的中文名称又叫随机指标，是一个超买超卖指标,最早起源于期货市场，由乔治·莱恩（George Lane）首创。
        随机指标KDJ最早是以KD指标的形式出现，而KD指标是在威廉指标的基础上发展起来的。
        不过KD指标只判断股票的超买超卖的现象，在KDJ指标中则融合了移动平均线速度上的观念，形成比较准确的买卖信号依据。在实践中，K线与D线配合J线组成KDJ指标来使用。
        KDJ指标在设计过程中主要是研究最高价、最低价和收盘价之间的关系，同时也融合了动量观念、强弱指标和移动平均线的一些优点。
        因此，能够比较迅速、快捷、直观地研判行情，被广泛用于股市的中短期趋势分析，是期货和股票市场上最常用的技术分析工具。
 
        第一步 计算RSV：即未成熟随机值（Raw Stochastic Value）。
        RSV 指标主要用来分析市场是处于“超买”还是“超卖”状态：
            - RSV高于80%时候市场即为超买状况，行情即将见顶，应当考虑出仓；
            - RSV低于20%时候，市场为超卖状况，行情即将见底，此时可以考虑加仓。
        N日RSV=(N日收盘价-N日内最低价）÷(N日内最高价-N日内最低价）×100%
        第二步 计算K值：当日K值 = 2/3前1日K值 + 1/3当日RSV ; 
        第三步 计算D值：当日D值 = 2/3前1日D值 + 1/3当日K值； 
        第四步 计算J值：当日J值 = 3当日K值 - 2当日D值. 

        """
        if self.inputKdjTBLen <= EMPTY_INT: return

        if self.inputKdjTBLen + self.inputKdjSmoothLen > self.max_hold_bars:
            self.max_hold_bars = self.inputKdjTBLen + self.inputKdjSmoothLen + 1

        # if len(self.lineBar) < self.inputKdjTBLen + 1:
        #     if not countInBar:
        #         self.debugCtaLog(u'数据未充分,当前Bar数据数量：{0}，计算KDJ需要：{1}'.format(len(self.lineBar), self.inputKdjTBLen + 1))
        #     return

        if self.inputKdjSlowLen == EMPTY_INT:
            self.inputKdjSlowLen = 3
        if self.inputKdjSmoothLen == EMPTY_INT:
            self.inputKdjSmoothLen = 3

        if len(self.lineBar) < 3:
            return

        if len(self.lineBar) < self.inputKdjTBLen + 1:
            inputKdjTBLen = len(self.lineBar)
            # 数据是Tick模式，非bar内计算
            if self.mode == self.TICK_MODE and not countInBar:
                listClose = [x.close for x in self.lineBar[0:-1]]
                listHigh = [x.high for x in self.lineBar[0:-1]]
                listLow = [x.low for x in self.lineBar[0:-1]]
                idx = 2
            else:
                listClose = [x.close for x in self.lineBar]
                listHigh = [x.high for x in self.lineBar]
                listLow = [x.low for x in self.lineBar]
                idx = 1
        else:
            # 数据是Tick模式，非bar内计算
            if self.mode == self.TICK_MODE and not countInBar:
                listClose = [x.close for x in self.lineBar[-self.inputKdjTBLen - 1:-1]]
                listHigh = [x.high for x in self.lineBar[-self.inputKdjTBLen - 1:-1]]
                listLow = [x.low for x in self.lineBar[-self.inputKdjTBLen - 1:-1]]
                idx = 2
            else:
                listClose = [x.close for x in self.lineBar[-self.inputKdjTBLen:]]
                listHigh = [x.high for x in self.lineBar[-self.inputKdjTBLen:]]
                listLow = [x.low for x in self.lineBar[-self.inputKdjTBLen:]]
                idx = 1

        hhv = max(listHigh)
        llv = min(listLow)

        if len(self.lineK) > 0:
            lastK = self.lineK[-1]
        else:
            lastK = 0

        if len(self.lineD) > 0:
            lastD = self.lineD[-1]
        else:
            lastD = 0

        if hhv == llv:
            rsv = 50
        else:
            rsv = (listClose[-1] - llv) / (hhv - llv) * 100

        self.lineKdjRSV.append(rsv)

        k = (self.inputKdjSlowLen - 1) * lastK / self.inputKdjSlowLen + rsv / self.inputKdjSlowLen
        if k < 0: k = 0
        if k > 100: k = 100

        d = (self.inputKdjSmoothLen - 1) * lastD / self.inputKdjSmoothLen + k / self.inputKdjSmoothLen
        if d < 0: d = 0
        if d > 100: d = 100

        j = self.inputKdjSmoothLen * k - (self.inputKdjSmoothLen - 1) * d

        msg = 'hhv={}, llv={}, rsv={}, k={}, d={}, j={}'.format(hhv, llv, rsv, k, d, j)
        if countInBar:
            self.lastD = d
            self.lastK = k
            self.lastJ = j
            return

        if len(self.lineK) > self.inputKdjTBLen * 8:
            del self.lineK[0]
        self.lineK.append(k)

        if len(self.lineD) > self.inputKdjTBLen * 8:
            del self.lineD[0]
        self.lineD.append(d)

        l = len(self.lineJ)
        if l > self.inputKdjTBLen * 8:
            del self.lineJ[0]
        self.lineJ.append(j)

        # 增加KDJ的J谷顶和波底
        if l > 3:
            # 峰
            if self.lineJ[-1] < self.lineJ[-2] and self.lineJ[-3] <= self.lineJ[-2]:

                t = {}
                t["Type"] = u'T'
                t["J"] = self.lineJ[-2]
                t["Close"] = self.lineBar[-1 - idx].close

                if len(self.lineKdjTop) > self.inputKdjTBLen:
                    del self.lineKdjTop[0]

                self.lineKdjTop.append(t)
                self.lastKdjTopButtom = self.lineKdjTop[-1]

            # 谷
            elif self.lineJ[-1] > self.lineJ[-2] and self.lineJ[-3] >= self.lineJ[-2]:

                b = {}
                b["Type"] = u'B'
                b["J"] = self.lineJ[-2]
                b["Close"] = self.lineBar[-1 - idx].close

                if len(self.lineKdjButtom) > self.inputKdjTBLen:
                    del self.lineKdjButtom[0]
                self.lineKdjButtom.append(b)
                self.lastKdjTopButtom = self.lineKdjButtom[-1]

        self.update_kd_cross()

    def update_kd_cross(self):
        """更新KDJ金叉死叉"""
        if len(self.lineK) < 2 or len(self.lineD) < 2:
            return

        # K值大于D值
        if self.lineK[-1] > self.lineD[-1]:
            if self.lineK[-2] > self.lineD[-2]:
                # 延续金叉
                self.kd_count = max(1,self.kd_count) + 1
            else:
                # 发生金叉
                self.kd_count = 1
                self.kd_last_cross = round((self.lineK[-1] + self.lineK[-2])/2,2)
                self.kd_cross_price = self.lineBar[-1].close

        # K值小于D值
        else:
            if self.lineK[-2] < self.lineD[-2]:
                # 延续死叉
                self.kd_count = min(-1, self.kd_count) - 1
            else:
                # 发生死叉
                self.kd_count = -1
                self.kd_last_cross = round((self.lineK[-1] + self.lineK[-2]) / 2, 2)
                self.kd_cross_price = self.lineBar[-1].close

    def __recountMacd(self):
        """
        Macd计算方法：
        12日EMA的计算：EMA12 = 前一日EMA12 X 11/13 + 今日收盘 X 2/13
        26日EMA的计算：EMA26 = 前一日EMA26 X 25/27 + 今日收盘 X 2/27
        差离值（DIF）的计算： DIF = EMA12 - EMA26，即为talib-MACD返回值macd
        根据差离值计算其9日的EMA，即离差平均值，是所求的DEA值。
        今日DEA = （前一日DEA X 8/10 + 今日DIF X 2/10），即为talib-MACD返回值signal
        DIF与它自己的移动平均之间差距的大小一般BAR=（DIF-DEA)*2，即为MACD柱状图。
        但是talib中MACD的计算是bar = (dif-dea)*1
        """

        if self.inputMacdFastPeriodLen <= EMPTY_INT: return
        if self.inputMacdSlowPeriodLen <= EMPTY_INT: return
        if self.inputMacdSignalPeriodLen <= EMPTY_INT: return

        maxLen = max(self.inputMacdFastPeriodLen, self.inputMacdSlowPeriodLen) + self.inputMacdSignalPeriodLen + 1

        # maxLen = maxLen * 3             # 注：数据长度需要足够，才能准确。测试过，3倍长度才可以与国内的文华等软件一致

        if len(self.lineBar) < maxLen:
            self.debugCtaLog(u'数据未充分,当前Bar数据数量：{0}，计算MACD需要：{1}'.format(len(self.lineBar), maxLen))
            return

        dif, dea, macd = ta.MACD(np.array(self.lineClose, dtype=float), fastperiod=self.inputMacdFastPeriodLen,
                                 slowperiod=self.inputMacdSlowPeriodLen, signalperiod=self.inputMacdSignalPeriodLen)

        # dif, dea, macd = ta.MACDEXT(np.array(listClose, dtype=float),
        #                            fastperiod=self.inputMacdFastPeriodLen, fastmatype=1,
        #                            slowperiod=self.inputMacdSlowPeriodLen, slowmatype=1,
        #                            signalperiod=self.inputMacdSignalPeriodLen, signalmatype=1)

        if len(self.lineDif) > maxLen:
            del self.lineDif[0]
        self.lineDif.append(round(dif[-1],2))

        if len(self.lineDea) > maxLen:
            del self.lineDea[0]
        self.lineDea.append(round(dea[-1],2))

        if len(self.lineMacd) > maxLen:
            del self.lineMacd[0]
        self.lineMacd.append(round(macd[-1] * 2,2))  # 国内一般是2倍

        # 更新 “段”（金叉-》死叉；或 死叉-》金叉)
        segment = self.lineMacdSegment[-1] if len(self.lineMacdSegment)>0 else {}

        # 创建新的段
        if (self.lineMacd[-1] >0 and self.macd_count<=0) or \
                (self.lineMacd[-1] < 0 and self.macd_count >= 0):
            segment = {}
            # 金叉/死叉，更新位置&价格
            self.macd_count,self.macd_rt_count = (1,1) if self.lineMacd[-1] > 0 else (-1,-1)
            self.macd_last_cross = round((self.lineDif[-1] + self.lineDea[-1])/2,2)
            self.macd_cross_price = self.lineClose[-1]
            self.macd_rt_last_cross = self.macd_last_cross
            self.macd_rt_cross_price = self.macd_cross_price
            # 更新段
            segment.update({
                'macd_count':self.macd_count,
                'max_price':self.lineHigh[-1],
                'min_price':self.lineLow[-1],
                'max_dif':self.lineDif[-1],
                'min_dif':self.lineDif[-1],
                'macd_area':abs(self.lineMacd[-1]),
                'max_macd':self.lineMacd[-1],
                'min_macd':self.lineMacd[-1]
            })
            self.lineMacdSegment.append(segment)

            # 新得能量柱>0，判断是否有底背离，同时，取消原有顶背离
            if self.lineMacd[-1] > 0:
                self.dif_buttom_divergence = self.is_dif_divergence(direction=DIRECTION_SHORT)
                self.macd_buttom_divergence = self.is_macd_divergence(direction=DIRECTION_SHORT)
                self.dif_top_divergence = False
                self.macd_top_divergence = False

            # 新得能量柱<0，判断是否有顶背离，同时，取消原有底背离
            elif self.lineMacd[-1] < 0:
                self.dif_buttom_divergence = False
                self.macd_buttom_divergence = False
                self.dif_top_divergence = self.is_dif_divergence(direction=DIRECTION_LONG)
                self.macd_top_divergence = self.is_macd_divergence(direction=DIRECTION_LONG)

        else:
            # 继续金叉
            if self.lineMacd[-1] > 0 and self.macd_count > 0:
                self.macd_count += 1

                segment.update({
                    'macd_count': self.macd_count,
                    'max_price': max(segment.get('max_price',self.lineHigh[-1]),self.lineHigh[-1]),
                    'min_price': min(segment.get('min_price',self.lineLow[-1]),self.lineLow[-1]),
                    'max_dif': max(segment.get('max_dif',self.lineDif[-1]),self.lineDif[-1]),
                    'min_dif': min(segment.get('min_dif',self.lineDif[-1]),self.lineDif[-1]),
                    'macd_area': segment.get('macd_area',0)+abs(self.lineMacd[-1]),
                    'max_macd': max(segment.get('max_macd',self.lineMacd[-1]),self.lineMacd[-1])
                })
                # 取消实时得记录
                self.macd_rt_count = 0
                self.macd_rt_last_cross = 0
                self.macd_rt_cross_price = 0


            # 继续死叉
            elif self.lineMacd[-1] < 0 and self.macd_count < 0:
                self.macd_count -= 1
                segment.update({
                    'macd_count': self.macd_count,
                    'max_price': max(segment.get('max_price', self.lineHigh[-1]), self.lineHigh[-1]),
                    'min_price': min(segment.get('min_price', self.lineLow[-1]), self.lineLow[-1]),
                    'max_dif': max(segment.get('max_dif', self.lineDif[-1]), self.lineDif[-1]),
                    'min_dif': min(segment.get('min_dif', self.lineDif[-1]), self.lineDif[-1]),
                    'macd_area': segment.get('macd_area', 0) + abs(self.lineMacd[-1]),
                    'min_macd': min(segment.get('min_macd',self.lineMacd[-1]),self.lineMacd[-1])
                })

                # 取消实时得记录
                self.macd_rt_count = 0
                self.macd_rt_last_cross = 0
                self.macd_rt_cross_price = 0

        # 删除超过10个的macd段
        if len(self.lineMacdSegment)>10:
            self.lineMacdSegment.pop(0)

    def rt_countMacd(self):
        """
        (实时）Macd计算方法：
        12日EMA的计算：EMA12 = 前一日EMA12 X 11/13 + 今日收盘 X 2/13
        26日EMA的计算：EMA26 = 前一日EMA26 X 25/27 + 今日收盘 X 2/27
        差离值（DIF）的计算： DIF = EMA12 - EMA26，即为talib-MACD返回值macd
        根据差离值计算其9日的EMA，即离差平均值，是所求的DEA值。
        今日DEA = （前一日DEA X 8/10 + 今日DIF X 2/10），即为talib-MACD返回值signal
        DIF与它自己的移动平均之间差距的大小一般BAR=（DIF-DEA)*2，即为MACD柱状图。
        但是talib中MACD的计算是bar = (dif-dea)*1
        """
        if self.inputMacdFastPeriodLen <= EMPTY_INT: return
        if self.inputMacdSlowPeriodLen <= EMPTY_INT: return
        if self.inputMacdSignalPeriodLen <= EMPTY_INT: return

        maxLen = max(self.inputMacdFastPeriodLen, self.inputMacdSlowPeriodLen) + self.inputMacdSignalPeriodLen + 1
        if len(self.lineBar) < maxLen:
            return

        listClose = [x.close for x in self.lineBar[-maxLen:]]
        dif, dea, macd = ta.MACD(np.array(listClose, dtype=float), fastperiod=self.inputMacdFastPeriodLen,
                                 slowperiod=self.inputMacdSlowPeriodLen, signalperiod=self.inputMacdSignalPeriodLen)

        self._rt_Dif = round(dif[-1], 2) if len(dif) > 0 else None
        self._rt_Dea = round(dea[-1], 2) if len(dea) > 0 else None
        self._rt_Macd = round(macd[-1] * 2, 2) if len(macd) > 0 else None

        # 判断是否实时金叉/死叉
        if self._rt_Macd is not None:
            # 实时金叉
            if self._rt_Macd >=0 and self.lineMacd[-1] < 0:
                self.macd_rt_count = 1
                self.macd_rt_last_cross = round((self._rt_Dif + self._rt_Dea) / 2, 2)
                self.macd_rt_cross_price = listClose[-1]

            # 实时死叉
            elif self._rt_Macd <=0 and self.lineMacd[-1] > 0:
                self.macd_rt_count = -1
                self.macd_rt_last_cross = round((self._rt_Dif + self._rt_Dea) / 2, 2)
                self.macd_rt_cross_price = listClose[-1]

    def getRuntimeMACD(self):
        """获取实时MACD计算值"""
        if self.rt_countMacd in self.rt_funcs:
            return self._rt_Dif, self._rt_Dea, self._rt_Macd
        else:
            self.writeCtaLog(u'getRuntimeMACD(),添加rt_countMacd到实时函数中')
            self.rt_funcs.add(self.rt_countMacd)
            self.rt_countMacd()
            return self._rt_Dif, self._rt_Dea, self._rt_Macd
    @property
    def rt_Dif(self):
        self.check_rt_funcs(self.rt_countMacd)
        return self._rt_Dif

    @property
    def rt_Dea(self):
        self.check_rt_funcs(self.rt_countMacd)
        return self._rt_Dea

    @property
    def rt_Macd(self):
        self.check_rt_funcs(self.rt_countMacd)
        return self._rt_Macd

    def is_dif_divergence(self, direction):
        """
        检查MACD DIF是否与价格有背离
        :param: direction，多：检查是否有顶背离，空，检查是否有底背离
        """
        s1,s2 = None,None  # s1,倒数的一个匹配段；s2，倒数第二个匹配段
        for seg in reversed(self.lineMacdSegment):

            if direction == DIRECTION_LONG:
                if seg.get('macd_count',0) > 0:
                    if s1 is None:
                        s1 = seg
                        continue
                    elif s2 is None:
                        s2 = seg
                        break
            else:
                if seg.get('macd_count',0) < 0:
                    if s1 is None:
                        s1 = seg
                        continue
                    elif s2 is None:
                        s2 = seg
                        break

        if not all([s1,s2]):
            return False

        if direction == DIRECTION_LONG:
            s1_max_price = s1.get('max_price', None)
            s2_max_price = s2.get('max_price', None)
            s1_dif_max = s1.get('max_dif', None)
            s2_dif_max = s2.get('max_dif', None)
            if s1_max_price is None or s2_max_price is None or s1_dif_max is None and s2_dif_max is None:
                return False

            # 顶背离，只能在零轴上方才判断
            if s1_dif_max < 0 or s2_dif_max < 0:
                return False

            # 价格创新高（超过前高得0.99）；dif指标没有创新高
            if s1_max_price >= s2_max_price * 0.99 and s1_dif_max < s2_dif_max:
                return True

        if direction == DIRECTION_SHORT:
            s1_min_price = s1.get('min_price', None)
            s2_min_price = s2.get('min_price', None)
            s1_dif_min = s1.get('min_dif', None)
            s2_dif_min = s2.get('min_dif', None)
            if s1_min_price is None or s2_min_price is None or s1_dif_min is None and s2_dif_min is None:
                return False

            # 底部背离，只能在零轴下方才判断
            if s1_dif_min > 0 or s1_dif_min > 0:
                return False

            # 价格创新低，dif没有创新低
            if s1_min_price <= s2_min_price * 1.01 and s1_dif_min > s2_dif_min:
                return True

        return False

    def is_macd_divergence(self, direction):
        """
        检查MACD 能量柱是否与价格有背离
        :param: direction，多：检查是否有顶背离，空，检查是否有底背离
        """
        s1,s2 = None,None  # s1,倒数的一个匹配段；s2，倒数第二个匹配段
        for seg in reversed(self.lineMacdSegment):

            if direction == DIRECTION_LONG:
                if seg.get('macd_count',0) > 0:
                    if s1 is None:
                        s1 = seg
                        continue
                    elif s2 is None:
                        s2 = seg
                        break
            else:
                if seg.get('macd_count',0) < 0:
                    if s1 is None:
                        s1 = seg
                        continue
                    elif s2 is None:
                        s2 = seg
                        break

        if not all([s1,s2]):
            return False

        if direction == DIRECTION_LONG:
            s1_max_price = s1.get('max_price', None)
            s2_max_price = s2.get('max_price', None)
            s1_area = s1.get('macd_area', None)
            s2_area = s2.get('macd_area', None)
            if s1_max_price is None or s2_max_price is None or s1_area is None and s2_area is None:
                return False

            # 价格创新高（超过前高得0.99）；MACD能量柱没有创更大面积
            if s1_max_price >= s2_max_price * 0.99 and s1_area < s2_area:
                return True

        if direction == DIRECTION_SHORT:
            s1_min_price = s1.get('min_price', None)
            s2_min_price = s2.get('min_price', None)
            s1_area = s1.get('macd_area', None)
            s2_area = s2.get('macd_area', None)
            if s1_min_price is None or s2_min_price is None or s1_area is None and s2_area is None:
                return False

            # 价格创新低，MACD能量柱没有创更大面积
            if s1_min_price <= s2_min_price * 1.01 and s1_area < s2_area:
                return True

        return False


    def __recountCci(self):
        """CCI计算
        顺势指标又叫CCI指标，CCI指标是美国股市技术分析 家唐纳德·蓝伯特(Donald Lambert)于20世纪80年代提出的，专门测量股价、外汇或者贵金属交易
        是否已超出常态分布范围。属于超买超卖类指标中较特殊的一种。波动于正无穷大和负无穷大之间。但是，又不需要以0为中轴线，这一点也和波动于正无穷大
        和负无穷大的指标不同。
        它最早是用于期货市场的判断，后运用于股票市场的研判，并被广泛使用。与大多数单一利用股票的收盘价、开盘价、最高价或最低价而发明出的各种技术分析
        指标不同，CCI指标是根据统计学原理，引进价格与固定期间的股价平均区间的偏离程度的概念，强调股价平均绝对偏差在股市技术分析中的重要性，是一种比
        较独特的技术指标。
        它与其他超买超卖型指标又有自己比较独特之处。象KDJ、W%R等大多数超买超卖型指标都有“0-100”上下界限，因此，它们对待一般常态行情的研判比较适用
        ，而对于那些短期内暴涨暴跌的股票的价格走势时，就可能会发生指标钝化的现象。而CCI指标却是波动于正无穷大到负无穷大之间，因此不会出现指标钝化现
        象，这样就有利于投资者更好地研判行情，特别是那些短期内暴涨暴跌的非常态行情。
        http://baike.baidu.com/view/53690.htm?fromtitle=CCI%E6%8C%87%E6%A0%87&fromid=4316895&type=syn
        """

        if self.inputCciLen <= 0:
            return

        # 1、lineBar满足长度才执行计算
        if len(self.lineBar) < self.inputCciLen + 2:
            self.debugCtaLog(u'数据未充分,当前Bar数据数量：{0}，计算CCI需要：{1}'.
                             format(len(self.lineBar), self.inputCciLen + 2))
            return

        # 计算第1根RSI曲线

        # 3、inputCc1Len(包含当前周期）
        if self.mode == self.TICK_MODE:
            listClose = [x.close for x in self.lineBar[-self.inputCciLen - 2:-1]]
            listHigh = [x.high for x in self.lineBar[-self.inputCciLen - 2:-1]]
            listLow = [x.low for x in self.lineBar[-self.inputCciLen - 2:-1]]
            idx = 2
        else:
            listClose = [x.close for x in self.lineBar[-self.inputCciLen - 1:]]
            listHigh = [x.high for x in self.lineBar[-self.inputCciLen - 1:]]
            listLow = [x.low for x in self.lineBar[-self.inputCciLen - 1:]]
            idx = 1

        barCci = ta.CCI(high=np.array(listHigh, dtype=float), low=np.array(listLow, dtype=float),
                        close=np.array(listClose, dtype=float), timeperiod=self.inputCciLen)[-1]

        barCci = round(float(barCci), 3)

        l = len(self.lineCci)
        if l > self.inputCciLen * 8:
            del self.lineCci[0]
        self.lineCci.append(barCci)

    def __recountKF(self):
        """计算卡尔曼过滤器均线"""
        min_len = 20
        if not self.inputKF or self.kf is None:
            return

        if len(self.lineStateMean) == 0 or len(self.lineStateCovar) == 0:
            listClose = []
            # 3、获取前InputN周期(不包含当前周期）的K线
            if self.mode == self.TICK_MODE:
                if len(self.lineBar) < 2:
                    return
                listClose.append(self.lineBar[-2].close)
            else:
                listClose.append(self.lineBar[-1].close)

            try:
                self.kf = KalmanFilter(transition_matrices=[1],
                                       observation_matrices=[1],
                                       initial_state_mean=listClose[-1],
                                       initial_state_covariance=1,

                                       transition_covariance=0.01)
            except:
                self.writeCtaLog(u'导入卡尔曼过滤器失败,需先安装 pip install pykalman')
                self.inputKF = False

            state_means, state_covariances = self.kf.filter(np.array(listClose, dtype=float))
            m = state_means[-1].item()
            c = state_covariances[-1].item()
        else:
            m = self.lineStateMean[-1]
            c = self.lineStateCovar[-1]
            if self.mode == self.TICK_MODE:
                o = self.lineBar[-2].close
            else:
                o = self.lineBar[-1].close

            state_means, state_covariances = self.kf.filter_update(filtered_state_mean=m,
                                                                   filtered_state_covariance=c,
                                                                   observation=np.array(o, dtype=float))
            m = state_means[-1].item()
            c = state_covariances[-1].item()

        if len(self.lineStateMean) > min_len:
            del self.lineStateMean[0]
        if len(self.lineStateCovar) > min_len:
            del self.lineStateCovar[0]

        self.lineStateMean.append(m)
        self.lineStateCovar.append(c)

    def __recountPeriod(self, bar):
        """重新计算周期"""

        len_rsi = len(self.lineRsi1)

        if self.inputKF:
            if len(self.lineStateMean) < 7 or len_rsi <= 0:
                return
            listMid = self.lineStateMean[-7:-1]
            malist = ta.MA(np.array(listMid, dtype=float), 5)
            lastMid = self.lineStateMean[-1]

        else:
            len_boll = len(self.lineMiddleBand)
            if len_boll <= 6 or len_rsi <= 0:
                return
            listMid = self.lineMiddleBand[-7:-1]
            lastMid = self.lineMiddleBand[-1]
            malist = ta.MA(np.array(listMid, dtype=float), 5)

        ma5 = malist[-1]
        ma5_ref1 = malist[-2]
        if ma5 <= 0 or ma5_ref1 <= 0:
            self.writeCtaLog(u'boll中轨计算均线异常')
            return
        if self.inputKF:
            self.atan = math.atan((ma5 / ma5_ref1 - 1) * 100) * 180 / math.pi
        else:
            # 当前均值,与前5均值得价差,除以标准差
            self.atan = math.atan((ma5 - ma5_ref1)/self.lineBollStd[-1]) * 180 / math.pi

        # atan2 = math.atan((ma5 / ma5_ref1 - 1) * 100) * 180 / math.pi
        # atan3 = math.atan(ma5 / ma5_ref1 - 1)* 100
        self.atan = round(self.atan, 3)
        # self.writeCtaLog(u'{}/{}/{}'.format(self.atan, atan2, atan3))

        if self.curPeriod is None:
            self.writeCtaLog(u'初始化周期为震荡')
            self.curPeriod = CtaPeriod(mode=PERIOD_SHOCK, price=bar.close, pre_mode=PERIOD_INIT, dt=bar.datetime)
            self.periods.append(self.curPeriod)

        if len(self.atan_list) > 10:
            del self.atan_list[0]
        self.atan_list.append(self.atan)

        if len_rsi < 3:
            return

        # 当前期趋势是震荡
        if self.curPeriod.mode == PERIOD_SHOCK:
            # 初始化模式
            if self.curPeriod.pre_mode == PERIOD_INIT:
                if self.atan < -45:
                    self.curPeriod = CtaPeriod(mode=PERIOD_SHORT_EXTREME, price=bar.close, pre_mode=PERIOD_SHORT,
                                               dt=bar.datetime)
                    self.periods.append(self.curPeriod)
                    self.writeCtaLog(u'{} 角度向下,Atan:{},周期{}=》{}'.
                                     format(bar.datetime, self.atan, self.curPeriod.pre_mode, self.curPeriod.mode))
                    if self.onPeriodChgFunc is not None:
                        self.onPeriodChgFunc(self.curPeriod)

                    return
                elif self.atan > 45:
                    self.curPeriod = CtaPeriod(mode=PERIOD_LONG_EXTREME, price=bar.close, pre_mode=PERIOD_LONG,
                                               dt=bar.datetime)
                    self.periods.append(self.curPeriod)
                    self.writeCtaLog(u'{} 角度加速向上,Atan:{}，周期:{}=>{}'.
                                     format(bar.datetime, self.atan, self.curPeriod.pre_mode,
                                            self.curPeriod.mode))
                    if self.onPeriodChgFunc is not None:
                        self.onPeriodChgFunc(self.curPeriod)

                    return

            # 震荡 -》 空
            if self.atan <= -20:
                self.curPeriod = CtaPeriod(mode=PERIOD_SHORT, price=bar.close, pre_mode=PERIOD_SHOCK, dt=bar.datetime)
                self.periods.append(self.curPeriod)
                self.writeCtaLog(u'{} 角度向下,Atan:{},周期{}=》{}'.
                                 format(bar.datetime, self.atan, self.curPeriod.pre_mode, self.curPeriod.mode))
                if self.onPeriodChgFunc is not None:
                    self.onPeriodChgFunc(self.curPeriod)
            # 震荡 =》 多
            elif self.atan >= 20:
                self.curPeriod = CtaPeriod(mode=PERIOD_LONG, price=bar.close, pre_mode=PERIOD_SHOCK, dt=bar.datetime)
                self.periods.append(self.curPeriod)
                self.writeCtaLog(u'{} 角度向上,Atan:{}，周期:{}=>{}'.
                                 format(bar.datetime, self.atan, self.curPeriod.pre_mode,
                                        self.curPeriod.mode))
                if self.onPeriodChgFunc is not None:
                    self.onPeriodChgFunc(self.curPeriod)

            # 周期维持不变
            else:
                self.writeCtaLog(u'{} 角度维持，Atan:{},周期维持:{}'.
                                 format(bar.datetime, self.atan, self.curPeriod.mode))

            return

        # 当前期趋势是空
        if self.curPeriod.mode == PERIOD_SHORT:
            # 空=》空极端
            if self.atan <= -45 and self.atan_list[-1] < self.atan_list[-2]:
                self.curPeriod = CtaPeriod(mode=PERIOD_SHORT_EXTREME, price=bar.close, pre_mode=PERIOD_SHORT,
                                           dt=bar.datetime)
                self.periods.append(self.curPeriod)
                self.writeCtaLog(u'{} 角度极端向下,Atan:{}，注意反弹。周期:{}=>{}'.
                                 format(bar.datetime, self.atan, self.curPeriod.pre_mode, self.curPeriod.mode))
                if self.onPeriodChgFunc is not None:
                    self.onPeriodChgFunc(self.curPeriod)

            # 空=》震荡
            elif -20 < self.atan < 20 or (self.atan >= 20 and self.atan_list[-2] <= -20):
                self.curPeriod = CtaPeriod(mode=PERIOD_SHOCK, price=bar.close, pre_mode=PERIOD_SHORT, dt=bar.datetime)
                self.periods.append(self.curPeriod)
                self.writeCtaLog(u'{} 角度平缓，Atan:{},结束下降趋势。周期:{}=>{}'.
                                 format(bar.datetime, self.atan, self.curPeriod.pre_mode, self.curPeriod.mode))
                if self.onPeriodChgFunc is not None:
                    self.onPeriodChgFunc(self.curPeriod)

            elif self.atan > 20 and self.curPeriod.pre_mode == PERIOD_LONG_EXTREME and self.atan_list[-1] > \
                    self.atan_list[-2] and bar.close > lastMid:
                self.curPeriod = CtaPeriod(mode=PERIOD_SHOCK, price=bar.close, pre_mode=PERIOD_SHORT, dt=bar.datetime)
                self.periods.append(self.curPeriod)
                self.writeCtaLog(u'{} 角度平缓，Atan:{},结束下降趋势。周期:{}=>{}'.
                                 format(bar.datetime, self.atan, self.curPeriod.pre_mode, self.curPeriod.mode))
                if self.onPeriodChgFunc is not None:
                    self.onPeriodChgFunc(self.curPeriod)

            # 周期维持空
            else:
                self.writeCtaLog(u'{} 角度向下{},周期维持:{}'.
                                 format(bar.datetime, self.atan, self.curPeriod.mode))

            return

        # 当前期趋势是多
        if self.curPeriod.mode == PERIOD_LONG:
            # 多=》多极端
            if self.atan >= 45 and self.atan_list[-1] > self.atan_list[-2]:
                self.curPeriod = CtaPeriod(mode=PERIOD_LONG_EXTREME, price=bar.close, pre_mode=PERIOD_LONG,
                                           dt=bar.datetime)
                self.periods.append(self.curPeriod)

                self.writeCtaLog(u'{} 角度加速向上,Atan:{}，周期:{}=>{}'.
                                 format(bar.datetime, self.atan, self.curPeriod.pre_mode,
                                        self.curPeriod.mode))
                if self.onPeriodChgFunc is not None:
                    self.onPeriodChgFunc(self.curPeriod)

            # 多=》震荡
            elif -20 < self.atan < 20 or (self.atan <= -20 and self.atan_list[-2] >= 20):
                self.curPeriod = CtaPeriod(mode=PERIOD_SHOCK, price=bar.close, pre_mode=PERIOD_LONG, dt=bar.datetime)
                self.periods.append(self.curPeriod)
                self.writeCtaLog(u'{} 角度平缓,Atan:{},结束上升趋势。周期:{}=>{}'.
                                 format(bar.datetime, self.atan, self.curPeriod.pre_mode, self.curPeriod.mode))
                if self.onPeriodChgFunc is not None:
                    self.onPeriodChgFunc(self.curPeriod)

            # 多=》震荡
            elif self.atan < -20 and self.curPeriod.pre_mode == PERIOD_SHORT_EXTREME and self.atan_list[-1] < \
                    self.atan_list[-2] and bar.close < lastMid:
                self.curPeriod = CtaPeriod(mode=PERIOD_SHOCK, price=bar.close, pre_mode=PERIOD_LONG, dt=bar.datetime)
                self.periods.append(self.curPeriod)
                self.writeCtaLog(u'{} 角度平缓,Atan:{},结束上升趋势。周期:{}=>{}'.
                                 format(bar.datetime, self.atan, self.curPeriod.pre_mode, self.curPeriod.mode))

                if self.onPeriodChgFunc is not None:
                    self.onPeriodChgFunc(self.curPeriod)
            # 周期保持多
            else:
                self.writeCtaLog(u'{} 角度向上,Atan:{},周期维持:{}'.
                                 format(bar.datetime, self.atan, self.curPeriod.mode))
            return

        # 当前周期为多极端
        if self.curPeriod.mode == PERIOD_LONG_EXTREME:
            # 多极端 =》 空
            if self.lineRsi1[-1] < self.lineRsi1[-2] \
                    and max(self.lineRsi1[-5:-2]) >= 50 \
                    and bar.close < lastMid:

                self.curPeriod = CtaPeriod(mode=PERIOD_SHORT, price=bar.close, pre_mode=PERIOD_LONG_EXTREME,
                                           dt=bar.datetime)
                self.periods.append(self.curPeriod)

                self.writeCtaLog(u'{} 角度高位反弹向下，Atan:{} , RSI {}=》{},{}下穿中轨{},周期：{}=》{}'.
                                 format(bar.datetime, self.atan, self.lineRsi1[-2], self.lineRsi1[-1],
                                        bar.close, lastMid,
                                        self.curPeriod.pre_mode, self.curPeriod.mode))
                if self.onPeriodChgFunc is not None:
                    self.onPeriodChgFunc(self.curPeriod)

            # 多极端 =》多
            elif self.lineRsi1[-1] < self.lineRsi1[-2] \
                    and bar.close > lastMid:
                self.curPeriod = CtaPeriod(mode=PERIOD_LONG, price=bar.close, pre_mode=PERIOD_LONG_EXTREME,
                                           dt=bar.datetime)
                self.periods.append(self.curPeriod)
                self.writeCtaLog(u'{} 角度上加速放缓，Atan:{}, & RSI{}=>{}，周期：{}=》{}'.
                                 format(bar.datetime, self.atan, self.lineRsi1[-2], self.lineRsi1[-1],
                                        self.curPeriod.pre_mode, self.curPeriod.mode))
                if self.onPeriodChgFunc is not None:
                    self.onPeriodChgFunc(self.curPeriod)

            # 当前趋势保持多极端
            else:
                self.writeCtaLog(u'{} 角度向上加速{},周期维持:{}'.
                                 format(bar.datetime, self.atan, self.curPeriod.mode))

            return

        # 当前周期为空极端
        if self.curPeriod.mode == PERIOD_SHORT_EXTREME:
            # 空极端 =》多
            if self.lineRsi1[-1] > self.lineRsi1[-2] and min(self.lineRsi1[-5:-2]) <= 50 \
                    and bar.close > lastMid:

                self.curPeriod = CtaPeriod(mode=PERIOD_LONG, price=bar.close, pre_mode=PERIOD_SHORT_EXTREME,
                                           dt=bar.datetime)
                self.periods.append(self.curPeriod)

                self.writeCtaLog(u'{} 角度下极限低位反弹转折,Atan:{}, RSI:{}=>{},周期:{}=>{}'.
                                 format(bar.datetime, self.atan, self.lineRsi1[-2], self.lineRsi1[-1],
                                        self.curPeriod.pre_mode, self.curPeriod.mode))
                if self.onPeriodChgFunc is not None:
                    self.onPeriodChgFunc(self.curPeriod)

            # 空极端=》空
            elif self.lineRsi1[-1] > self.lineRsi1[-2] and bar.close < lastMid:
                self.curPeriod = CtaPeriod(mode=PERIOD_SHORT, price=bar.close, pre_mode=PERIOD_SHORT_EXTREME,
                                           dt=bar.datetime)
                self.periods.append(self.curPeriod)
                self.writeCtaLog(u'{} 角度下加速放缓，Atan:{},RSI:{}=>{}, ,周期：{}=>{}'.
                                 format(bar.datetime, self.atan, self.lineRsi1[-2], self.lineRsi1[-1],
                                        self.curPeriod.pre_mode, self.curPeriod.mode))
                if self.onPeriodChgFunc is not None:
                    self.onPeriodChgFunc(self.curPeriod)

            # 保持空极端趋势
            else:
                self.writeCtaLog(u'{} 角度向下加速,Atan:{},周期维持:{}'.
                                 format(bar.datetime, self.atan, self.curPeriod.mode))

            return

    def __recountSKD(self):
        """
        改良得多空线(类似KDJ，RSI）
        :param bar:
        :return:
        """
        if not self.inputSkd:
            return

        data_len = max(self.inputSkdLen1 * 2, self.inputSkdLen1 + 20)
        if len(self.lineBar) < data_len:
            return

        # 取得Len1*2 长度的Close
        if self.mode == self.TICK_MODE:
            close_list = [x.close for x in self.lineBar[-data_len:-1]]
        else:
            close_list = [x.close for x in self.lineBar[-data_len:]]

        # 计算最后一根Bar的RSI指标
        last_rsi = ta.RSI(np.array(close_list, dtype=float), self.inputSkdLen1)[-1]
        # 添加到lineSkdRSI队列
        if len(self.lineSkdRSI) > data_len:
            del self.lineSkdRSI[0]
        self.lineSkdRSI.append(last_rsi)

        if len(self.lineSkdRSI) < self.inputSkdLen2:
            return

        # 计算最后根的最高价/最低价
        rsi_HHV = max(self.lineSkdRSI[-self.inputSkdLen2:])
        rsi_LLV = min(self.lineSkdRSI[-self.inputSkdLen2:])

        # 计算STO
        if rsi_HHV == rsi_LLV:
            sto = 0
        else:
            sto = 100 * (last_rsi - rsi_LLV) / (rsi_HHV - rsi_LLV)
        sto_len = len(self.lineSkdSTO)
        if sto_len > data_len * 2:
            del self.lineSkdSTO[0]
        self.lineSkdSTO.append(sto)

        # 根据STO，计算SK = EMA(STO,5)
        if sto_len < 5:
            return
        sk = ta.EMA(np.array(self.lineSkdSTO, dtype=float), 5)[-1]
        if len(self.lineSK) > data_len * 2:
            del self.lineSK[0]
        self.lineSK.append(sk)

        if len(self.lineSK) < 3:
            return

        sd = ta.EMA(np.array(self.lineSK, dtype=float), 3)[-1]
        if len(self.lineSD) > data_len * 2:
            del self.lineSD[0]
        self.lineSD.append(sd)

        if len(self.lineSD) < 2:
            return

        for t in self.lineSkTop[-1:]:
            t['bars'] += 1

        for b in self.lineSkButtom[-1:]:
            b['bars'] += 1

        #  记录所有SK的顶部和底部
        # 峰(顶部)
        if self.lineSK[-1] < self.lineSK[-2] and self.lineSK[-3] < self.lineSK[-2]:
            t = {}
            t['type'] = u'T'
            t['sk'] = self.lineSK[-2]
            t['price'] = max([bar.high for bar in self.lineBar[-4:]])
            t['time'] = self.lineBar[-1].datetime
            t['bars'] = 0
            if len(self.lineSkTop) > self.inputSkdLen2:
                del self.lineSkTop[0]
            self.lineSkTop.append(t)
            if self.skd_count > 0:
                # 检查是否有顶背离
                if self.is_sk_divergence(direction=DIRECTION_LONG):
                    self.skd_divergence = -1

        # 谷(底部)
        elif self.lineSK[-1] > self.lineSK[-2] and self.lineSK[-3] > self.lineSK[-2]:
            b = {}
            b['type'] = u'B'
            b['sk'] = self.lineSK[-2]
            b['price'] = min([bar.low for bar in self.lineBar[-4:]])
            b['time'] = self.lineBar[-1].datetime
            b['bars'] = 0
            if len(self.lineSkButtom) > self.inputSkdLen2:
                del self.lineSkButtom[0]
            self.lineSkButtom.append(b)
            if self.skd_count < 0:
                # 检查是否有底背离
                if self.is_sk_divergence(direction=DIRECTION_SHORT):
                    self.skd_divergence = 1

        # 判断是否金叉和死叉
        golden_cross = self.lineSK[-1] > self.lineSK[-2] and self.lineSK[-2] < self.lineSD[-2] \
                       and self.lineSK[-1] > self.lineSD[-1]

        dead_cross = self.lineSK[-1] < self.lineSK[-2] and self.lineSK[-2] > self.lineSD[-2] \
                     and self.lineSK[-1] < self.lineSD[-1]

        if self.skd_count <= 0:
            if golden_cross:
                # 金叉
                self.skd_count = 1
                self.skd_last_cross = (self.lineSK[-1] + self.lineSK[-2] + self.lineSD[-1] + self.lineSD[-2]) / 4
                self.skd_rt_count = self.skd_count
                self.skd_rt_last_cross = self.skd_last_cross
                if self.skd_rt_cross_price == 0 or self.cur_price < self.skd_rt_cross_price:
                    self.skd_rt_cross_price = self.cur_price
                self.skd_cross_price = self.cur_price
                if self.skd_divergence < 0:
                    # 若原来是顶背离，消失
                    self.skd_divergence = 0
                #self.writeCtaLog(u'{} Gold Cross:{} at {}'.format(self.name, self.skd_last_cross, self.skd_cross_price))
            else:  # if self.lineSK[-1] < self.lineSK[-2]:
                # 延续死叉
                self.skd_count -= 1
                # 取消实时的数据
                self.skd_rt_count = 0
                self.skd_rt_last_cross = 0
                self.skd_rt_cross_price = 0

                # 延续顶背离
                if self.skd_divergence < 0:
                    self.skd_divergence -= 1
            return

        elif self.skd_count >= 0:
            if dead_cross:
                self.skd_count = -1
                self.skd_last_cross = (self.lineSK[-1] + self.lineSK[-2] + self.lineSD[-1] + self.lineSD[-2]) / 4
                self.skd_rt_count = self.skd_count
                self.skd_rt_last_cross = self.skd_last_cross
                if self.skd_rt_cross_price == 0 or self.cur_price > self.skd_rt_cross_price:
                    self.skd_rt_cross_price = self.cur_price
                self.skd_cross_price = self.cur_price

                # 若原来是底背离，消失
                if self.skd_divergence > 0:
                    self.skd_divergence = 0

                #self.writeCtaLog(u'{} Dead Cross:{} at {}'.format(self.name, self.skd_last_cross, self.skd_cross_price))

            else:  # if self.lineSK[-1] > self.lineSK[-2]:
                # 延续金叉
                self.skd_count += 1

                # 取消实时的数据
                self.skd_rt_count = 0
                self.skd_rt_last_cross = 0
                self.skd_rt_cross_price = 0

                # 延续底背离
                if self.skd_divergence > 0:
                    self.skd_divergence += 1

    def get_2nd_item(self, line):
        """
        获取第二个合适的选项
        :param line:
        :return:
        """
        bars = 0
        for item in reversed(line):
            bars += item['bars']
            if bars > 5:
                return item

        return line[0]

    def is_sk_divergence(self, direction, runtime=False):
        """
        检查是否有背离
        :param:direction，多：检查是否有顶背离，空，检查是否有底背离
        :return:
        """
        if len(self.lineSkTop) < 2 or len(self.lineSkButtom) < 2 or self._rt_SK is None or self._rt_SD is None:
            return False

        t1 = self.lineSkTop[-1]
        t2 = self.get_2nd_item(self.lineSkTop[:-1])
        b1 = self.lineSkButtom[-1]
        b2 = self.get_2nd_item(self.lineSkButtom[:-1])

        if runtime:
            # 峰(顶部)
            if self._rt_SK < self.lineSK[-1] and self.lineSK[-2] < self.lineSK[-1]:
                t1 = {}
                t1['type'] = u'T'
                t1['sk'] = self.lineSK[-1]
                t1['price'] = max([bar.high for bar in self.lineBar[-4:]])
                t1['time'] = self.lineBar[-1].datetime
                t1['bars'] = 0
                t2 = self.get_2nd_item(self.lineSkTop)
            # 谷(底部)
            elif self._rt_SK > self.lineSK[-1] and self.lineSK[-2] > self.lineSK[-1]:
                b1 = {}
                b1['type'] = u'B'
                b1['sk'] = self.lineSK[-1]
                b1['price'] = min([bar.low for bar in self.lineBar[-4:]])
                b1['time'] = self.lineBar[-1].datetime
                b1['bars'] = 0
                b2 = self.get_2nd_item(self.lineSkButtom)

        # 检查顶背离
        if direction == DIRECTION_LONG:
            t1_price = t1.get('price', 0)
            t2_price = t2.get('price', 0)
            t1_sk = t1.get('sk', 0)
            t2_sk = t2.get('sk', 0)
            b1_sk = b1.get('sk', 0)

            t2_t1_price_rate = ((t1_price - t2_price) / t2_price) if t2_price != 0 else 0
            t2_t1_sk_rate = ((t1_sk - t2_sk) / t2_sk) if t2_sk != 0 else 0
            # 背离：价格创新高，SK指标没有创新高
            if t2_t1_price_rate > 0 and t2_t1_sk_rate < 0 and b1_sk > self.highSkd:
                return True

        elif direction == DIRECTION_SHORT:
            b1_price = b1.get('price', 0)
            b2_price = b2.get('price', 0)
            b1_sk = b1.get('sk', 0)
            b2_sk = b2.get('sk', 0)
            t1_sk = t1.get('sk', 0)
            b2_b1_price_rate = ((b1_price - b2_price) / b2_price) if b2_price != 0 else 0
            b2_b1_sk_rate = ((b1_sk - b2_sk) / b2_sk) if b2_sk != 0 else 0
            # 背离：价格创新低，指标没有创新低
            if b2_b1_price_rate < 0 and b2_b1_sk_rate > 0 and t1_sk < self.lowSkd:
                return True

        return False

    def getRuntimeSKD(self):
        if self.rt_countSkd in self.rt_funcs or self.rt_count_SK_SD in self.rt_funcs:
            return self._rt_SK, self._rt_SD
        else:
            self.writeCtaLog(u'getRuntimeSKD(),添加rt_countSkd到实时函数中')
            self.rt_funcs.add(self.rt_countSkd)
            self.rt_count_SK_SD()
            return self._rt_SK, self._rt_SD

    def rt_count_SK_SD(self):
        """
        计算实时SKD
        :return:
        """
        if not self.inputSkd:
            return

        # 准备得数据长度
        data_len = max(self.inputSkdLen1 * 2, self.inputSkdLen1 + 20)
        if len(self.lineBar) < data_len:
            return

        # 收盘价 = 结算bar + 最后一个未结束得close
        close_list = self.lineClose[-data_len:]
        close_list.append(self.lineBar[-1].close)
        # close_list = [x.close for x in self.lineBar[-data_len:]]

        # 计算最后得动态RSI值
        last_rsi = ta.RSI(np.array(close_list, dtype=float), self.inputSkdLen1)[-1]

        # 所有RSI值长度不足计算标准
        if len(self.lineSkdRSI) < self.inputSkdLen2:
            return

        # 拼接RSI list
        rsi_list = self.lineSkdRSI[1 - self.inputSkdLen2:]
        rsi_list.append(last_rsi)

        # 获取 RSI得最高/最低值
        rsi_HHV = max(rsi_list)
        rsi_LLV = min(rsi_list)

        # 计算动态STO
        if rsi_HHV == rsi_LLV:
            sto = 0
        else:
            sto = 100 * (last_rsi - rsi_LLV) / (rsi_HHV - rsi_LLV)

        sto_len = len(self.lineSkdSTO)
        if sto_len < 5:
            self._rt_SK = self.lineSK[-1] if len(self.lineSK) > 0 else 0
            self._rt_SD = self.lineSD[-1] if len(self.lineSD) > 0 else 0
            return

        # 历史STO
        sto_list = self.lineSkdSTO[:]
        sto_list.append(sto)

        self._rt_SK = ta.EMA(np.array(sto_list, dtype=float), 5)[-1]

        sk_list = self.lineSK[:]
        sk_list.append(self._rt_SK)
        if len(sk_list) < 5:
            self._rt_SD = self.lineSD[-1] if len(self.lineSD) > 0 else 0
        else:
            self._rt_SD = ta.EMA(np.array(sk_list, dtype=float), 3)[-1]

    def skd_is_risk(self, direction, dist=15, runtime=False):
        """
        检查SDK的方向风险
        :return:
        """
        if not self.inputSkd or len(self.lineSK) < 2 or self._rt_SK is None:
            return False

        if runtime:
            sk = self._rt_SK
        else:
            sk = self.lineSK[-1]
        if direction == DIRECTION_LONG and sk >= 100 - dist:
            return True

        if direction == DIRECTION_SHORT and sk <= dist:
            return True

        return False

    def skd_is_high_dead_cross(self, runtime=False, high_skd=None):
        """
        检查是否高位死叉
        :return:
        """
        if not self.inputSkd or len(self.lineSK) < self.inputSkdLen2:
            return False

        if high_skd is None:
            high_skd = self.highSkd

        if runtime:
            # 兼容写法，如果老策略没有配置实时运行，又用到实时数据，就添加
            if self.rt_countSkd not in self.rt_funcs:
                self.writeCtaLog(u'skd_is_high_dead_cross(),添加rt_countSkd到实时函数中')
                self.rt_funcs.add(self.rt_countSkd)
                self.rt_count_SK_SD()
            if self._rt_SK is None or self._rt_SD is None:
                return False

            # 判断是否实时死叉
            dead_cross = self._rt_SK < self.lineSK[-1] and self.lineSK[-1] > self.lineSD[-1] and self._rt_SK < self._rt_SD

            # 实时死叉
            if self.skd_count >= 0 and dead_cross:
                skd_last_cross = (self._rt_SK + self.lineSK[-1] + self._rt_SD + self.lineSD[-1]) / 4
                # 记录bar内首次死叉后的值:交叉值，价格
                if self.skd_rt_count >= 0:
                    self.skd_rt_count = -1
                    self.skd_rt_last_cross = skd_last_cross
                    self.skd_rt_cross_price = self.cur_price
                    #self.writeCtaLog(u'{} rt Dead Cross at:{} ,price:{}'
                    #                 .format(self.name, self.skd_rt_last_cross, self.skd_rt_cross_price))

                if skd_last_cross > high_skd:
                    return True

        # 非实时，高位死叉
        if self.skd_count < 0 and self.skd_last_cross > high_skd:
            return True

        return False

    def skd_is_low_golden_cross(self, runtime=False, low_skd=None):
        """
        检查是否低位金叉
        :return:
        """
        if not self.inputSkd or len(self.lineSK) < self.inputSkdLen2:
            return False
        if low_skd is None:
            low_skd = self.lowSkd

        if runtime:
            # 兼容写法，如果老策略没有配置实时运行，又用到实时数据，就添加
            if self.rt_countSkd not in self.rt_funcs:
                self.writeCtaLog(u'skd_is_low_golden_cross添加rt_countSkd到实时函数中')
                self.rt_funcs.add(self.rt_countSkd)
                self.rt_count_SK_SD()

            if self._rt_SK is None or self._rt_SD is None:
                return False
            # 判断是否金叉和死叉
            golden_cross = self._rt_SK > self.lineSK[-1] and self.lineSK[-1] < self.lineSD[
                -1] and self._rt_SK > self._rt_SD

            if self.skd_count <= 0 and golden_cross:
                # 实时金叉
                skd_last_cross = (self._rt_SK + self.lineSK[-1] + self._rt_SD + self.lineSD[-1]) / 4

                if self.skd_rt_count <= 0:
                    self.skd_rt_count = 1
                    self.skd_rt_last_cross = skd_last_cross
                    self.skd_rt_cross_price = self.cur_price
                    #self.writeCtaLog(u'{} rt Gold Cross at:{} ,price:{}'
                    #                 .format(self.name, self.skd_rt_last_cross, self.skd_rt_cross_price))
                if skd_last_cross < low_skd:
                    return True

        # 非实时低位金叉
        if self.skd_count > 0 and self.skd_last_cross < low_skd:
            return True

        return False

    def rt_countSkd(self):
        """
        实时计算 SK,SD值，并且判断计算是否实时金叉/死叉
        :return:
        """
        if self.inputSkd:
            # 计算实时指标 rt_SK, rt_SD
            self.rt_count_SK_SD()

            # 计算 实时金叉/死叉
            self.skd_is_high_dead_cross(runtime=True, high_skd=0)
            self.skd_is_low_golden_cross(runtime=True, low_skd=100)

    @property
    def rt_SK(self):
        self.check_rt_funcs(self.rt_countSkd)
        return self._rt_SK

    @property
    def rt_SD(self):
        self.check_rt_funcs(self.rt_countSkd)
        return self._rt_SD

    def __recountYB(self):
        """某种趋势线"""

        if not self.inputYb:
            return

        if self.inputYbLen < 1:
            return

        if self.inputYbRef < 1:
            self.debugCtaLog(u'参数 self.inputYbRef:{}不能低于1'.format(self.inputYbRef))
            return

        # 1、lineBar满足长度才执行计算
        #if len(self.lineBar) < 4 * self.inputYbLen:
        #    self.debugCtaLog(u'数据未充分,当前Bar数据数量：{0}，计算YB 需要：{1}'.
        #                     format(len(self.lineBar), 4 * self.inputYbLen))
        #    return

        emaLen = min(len(self.lineBar),self.inputYbLen)
        if emaLen < 3:
            self.debugCtaLog(u'数据未充分,当前Bar数据数量：{0}'.
                                                 format(len(self.lineBar)))
            return
        # 3、获取前InputN周期(不包含当前周期）的K线
        if self.mode == self.TICK_MODE:
            list_mid3 = [x.mid3 for x in self.lineBar[-emaLen * 4 - 1:-1]]
        else:
            list_mid3 = [x.mid3 for x in self.lineBar[-emaLen * 4:]]
        bar_mid3_ema10 = ta.EMA(np.array(list_mid3, dtype=float), emaLen)[-1]
        bar_mid3_ema10 = round(float(bar_mid3_ema10), self.round_n)

        if len(self.lineYb) > self.inputYbLen * 4:
            del self.lineYb[0]

        self.lineYb.append(bar_mid3_ema10)

        if len(self.lineYb) < self.inputYbRef + 1:
            return

        if self.lineYb[-1] > self.lineYb[-1 - self.inputYbRef]:
            self.yb_count = self.yb_count + 1 if self.yb_count >= 0 else 1
        else:
            self.yb_count = self.yb_count - 1 if self.yb_count <= 0 else -1

    def rt_countYb(self):
        """
        实时计算黄蓝
        :return:
        """
        if not self.inputYb:
            return
        if self.inputYbLen < 1:
            return
        if self.inputYbRef < 1:
            self.debugCtaLog(u'参数 self.inputYbRef:{}不能低于1'.format(self.inputYbRef))
            return

        # 1、lineBar满足长度才执行计算
        #if len(self.lineBar) < 4 * self.inputYbLen:
        #    self.debugCtaLog(u'数据未充分,当前Bar数据数量：{0}，计算实时YB 需要：{1}'.
        #                     format(len(self.lineBar), 4 * self.inputYbLen))
        #    return

        emaLen = min(len(self.lineBar),self.inputYbLen)
        if emaLen < 3:
            self.debugCtaLog(u'数据未充分,当前Bar数据数量：{0}'.
                                                 format(len(self.lineBar)))
            return
        # 3、获取前InputN周期(包含当前周期）的K线
        list_mid3 = [x.mid3 for x in self.lineBar[-emaLen * 4:-1]]
        last_bar_mid3 = (self.lineBar[-1].close + self.lineBar[-1].high + self.lineBar[-1].low) / 3
        list_mid3.append(last_bar_mid3)
        bar_mid3_ema10 = ta.EMA(np.array(list_mid3, dtype=float), emaLen)[-1]
        self._rt_YB = round(float(bar_mid3_ema10), self.round_n)

    def getRuningYb(self):
        """
        获取未完结的bar计算出来的YB值
        :return: None，空值；float,计算值
        """
        if self.rt_countYb not in self.rt_funcs:
            self.writeCtaLog(u'{}添加rt_countYb到实时函数中'.format(self.name))
            self.rt_funcs.add(self.rt_countYb)
            self.rt_countYb()
        return self._rt_YB

    @property
    def rt_YB(self):
        self.check_rt_funcs(self.rt_countYb)
        return self._rt_YB

    def __recountGoldenSection(self):
        """
        重新计算黄金分割线
        :return:
        """
        if self.inputGoldenN < 0:
            return

        bar_len = self.inputGoldenN

        if self.mode == self.TICK_MODE:
            if bar_len > len(self.lineBar) - 1:
                bar_len = len(self.lineBar) - 1

            if bar_len < 2:
                return
            hhv = max([bar.high for bar in self.lineBar[-bar_len - 1:-1]])
            llv = min([bar.low for bar in self.lineBar[-bar_len - 1:-1]])
        else:
            if bar_len > len(self.lineBar):
                bar_len = len(self.lineBar)

            if bar_len < 2:
                return

            hhv = max([bar.high for bar in self.lineBar[-bar_len:]])
            llv = min([bar.low for bar in self.lineBar[-bar_len:]])

        if hhv == llv:
            return

        self.p192 = hhv - (hhv - llv) * 0.192
        self.p382 = hhv - (hhv - llv) * 0.382
        self.p500 = (hhv + llv) / 2
        self.p618 = hhv - (hhv - llv) * 0.618
        self.p809 = hhv - (hhv - llv) * 0.809

        # 根据最小跳动取整
        self.p192 = self.p192 - self.p192 % self.minDiff
        self.p382 = self.p382 - self.p382 % self.minDiff
        self.p500 = self.p500 - self.p500 % self.minDiff
        self.p618 = self.p618 - self.p618 % self.minDiff
        self.p809 = self.p809 - self.p809 % self.minDiff

    def __recountArea(self, bar):
        """计算布林和MA的区域"""
        if not self.activate_boll_ma_area:
            return

        if len(self.lineMa1) < 2 or len(self.lineMiddleBand) < 2:
            return

        last_area = self.area_list[-1] if len(self.area_list) > 0 else None
        new_area = None
        # 判断做多/做空，判断在那个区域
        # 做多：均线（169）向上，且中轨在均线上方(不包含金叉死叉点集)
        # 做空：均线（169）向下，且中轨在均线下方（不包含金叉死叉点集）

        if self.lineMiddleBand[-1] > self.lineMa1[-1] > self.lineMa1[-2] :
            # 做多
            if self.lineMiddleBand[-1] >= bar.close >= max(self.lineMa1[-1],self.lineLowerBand[-1]):
                # 判断 A 的区域 ( ma169或下轨 ~ 中轨)
                new_area = AREA_LONG_A
            elif self.lineUpperBand[-1] >= bar.close > self.lineMiddleBand[-1]:
                # 判断 B 的区域( 中轨 ~ 上轨)
                new_area = AREA_LONG_B
            elif self.lineUpperBand[-1] < bar.close:
                # 判断 C 的区域( 上轨~ )
                new_area = AREA_LONG_C
            elif max(self.lineMa1[-1],self.lineLowerBand[-1]) > bar.close >= min(self.lineMa1[-1],self.lineLowerBand[-1]):
                # 判断 D 的区域( 下轨~均线~ )
                new_area = AREA_LONG_D
            elif min(self.lineLowerBand[-1],self.lineMa1[-1]) > bar.close:
                # 判断 E 的区域( ~下轨或均线下方 )
                new_area = AREA_LONG_E
        elif self.lineMa1[-2] > self.lineMa1[-1] > self.lineMiddleBand[-1]:
            # 做空
            if self.lineMiddleBand[-1] <= bar.close <= min(self.lineMa1[-1],self.lineUpperBand[-1]):
                # 判断 A 的区域 ( ma169或上轨 ~ 中轨)
                new_area = AREA_SHORT_A
            elif self.lineLowerBand[-1] <= bar.close < self.lineMiddleBand[-1]:
                # 判断 B 的区域( 下轨~中轨 )
                new_area = AREA_SHORT_B
            elif self.lineLowerBand[-1] > bar.close:
                # 判断 C 的区域( ~下轨 )
                new_area = AREA_SHORT_C
            elif min(self.lineMa1[-1],self.lineUpperBand[-1]) < bar.close <= max(self.lineMa1[-1],self.lineUpperBand[-1]):
                # 判断 D 的区域(均线~上轨 )
                new_area = AREA_SHORT_D
            elif max(self.lineMa1[-1],self.lineUpperBand[-1]) < bar.close:
                # 判断 E 的区域( 上轨~ )
                new_area = AREA_SHORT_E

        if last_area != new_area:
            self.area_list.append(new_area)
            self.cur_area = new_area
            self.pre_area = last_area

    def __recountBias(self):
        """乖离率"""
        # BIAS1 : (CLOSE-MA(CLOSE,L1))/MA(CLOSE,L1)*100;
        if not (self.inputBiasLen > EMPTY_INT or self.inputBias2Len > EMPTY_INT or
                self.inputBias3Len > EMPTY_INT):  # 不计算
            return

        l = len(self.lineBar)
        if self.inputBiasLen > EMPTY_INT:
            if l < min(6, self.inputBiasLen) + 1:
                self.debugCtaLog(u'数据未充分,当前Bar数据数量：{0}，计算Bias需要：{1}'.
                                 format(len(self.lineBar), min(14, self.inputBiasLen) + 1))
            else:
                if l < self.inputBiasLen + 2:
                    BiasLen = l - 1
                else:
                    BiasLen = self.inputBiasLen

                # 不包含当前最新的Bar
                if self.mode == self.TICK_MODE:
                    listClose = [x.close for x in self.lineBar[-BiasLen-1:-1]]
                else:
                    listClose = [x.close for x in self.lineBar[-BiasLen:]]

                if len(self.lineBias) > self.inputBiasLen * 8:
                    del self.lineBias[0]

                # 计算BIAS
                m = np.mean(listClose)
                bias = (listClose[-1] - m) / m * 100
                self.lineBias.append(bias)  # 中轨
                self.lastBias = bias

        l = len(self.lineBar)
        if self.inputBias2Len > EMPTY_INT:
            if l < min(6, self.inputBias2Len) + 1:
                self.debugCtaLog(u'数据未充分,当前Bar数据数量：{0}，计算Bias2需要：{1}'.
                                 format(len(self.lineBar), min(14, self.inputBias2Len) + 1))
            else:
                if l < self.inputBias2Len + 2:
                    Bias2Len = l - 1
                else:
                    Bias2Len = self.inputBias2Len

                # 不包含当前最新的Bar
                if self.mode == self.TICK_MODE:
                    listClose = [x.close for x in self.lineBar[-Bias2Len-1:-1]]
                else:
                    listClose = [x.close for x in self.lineBar[-Bias2Len:]]

                if len(self.lineBias2) > self.inputBias2Len * 8:
                    del self.lineBias2[0]

                # 计算BIAS2
                m = np.mean(listClose)
                bias2 = (listClose[-1] - m) / m * 100
                self.lineBias2.append(bias2)  # 中轨
                self.lastBias2 = bias2

        l = len(self.lineBar)
        if self.inputBias3Len > EMPTY_INT:
            if l < min(6, self.inputBias3Len) + 1:
                self.debugCtaLog(u'数据未充分,当前Bar数据数量：{0}，计算Bias3需要：{1}'.
                                 format(len(self.lineBar), min(14, self.inputBias3Len) + 1))
            else:
                if l < self.inputBias3Len + 2:
                    Bias3Len = l - 1
                else:
                    Bias3Len = self.inputBias3Len

                # 不包含当前最新的Bar
                if self.mode == self.TICK_MODE:
                    listClose = [x.close for x in self.lineBar[-Bias3Len-1:-1]]
                else:
                    listClose = [x.close for x in self.lineBar[-Bias3Len:]]

                if len(self.lineBias3) > self.inputBias3Len * 8:
                    del self.lineBias3[0]

                # 计算BIAS3
                m = np.mean(listClose)
                bias3 = (listClose[-1] - m) / m * 100
                self.lineBias3.append(bias3)  # 中轨
                self.lastBias3 = bias3

    def rt_countBias(self):
        """实时计算乖离率"""
        if not (self.inputBiasLen > EMPTY_INT or self.inputBias2Len or self.inputBias3Len > EMPTY_INT):  # 不计算
            return

        close_len = len(self.lineClose)

        if self.inputBiasLen > EMPTY_INT:
            if close_len < min(6, self.inputBiasLen) + 1:
                return
            else:
                if close_len < self.inputBiasLen + 2:
                    biasLen = close_len - 1
                else:
                    biasLen = self.inputBiasLen

            listClose = [x.close for x in self.lineBar[-biasLen:]]

            # 计算BIAS
            m = np.mean(listClose)
            self._rt_Bias = (listClose[-1] - m) / m * 100

        if self.inputBias2Len > EMPTY_INT:
            if close_len < min(6, self.inputBias2Len) + 1:
                return
            else:
                if close_len < self.inputBias2Len + 2:
                    biasLen = close_len - 1
                else:
                    biasLen = self.inputBias2Len

            listClose = [x.close for x in self.lineBar[-biasLen:]]

            # 计算BIAS
            m = np.mean(listClose)
            self._rt_Bias2 = (listClose[-1] - m) / m * 100

        if self.inputBias3Len > EMPTY_INT:
            if close_len < min(6, self.inputBias3Len) + 1:
                return
            else:
                if close_len < self.inputBias3Len + 2:
                    biasLen = close_len - 1
                else:
                    biasLen = self.inputBias3Len

            listClose = [x.close for x in self.lineBar[-biasLen:]]

            # 计算BIAS
            m = np.mean(listClose)
            self._rt_Bias3 = (listClose[-1] - m) / m * 100

    def getRuntimeBias(self):
        """获取实时BIAS计算值"""
        if self.rt_countBias in self.rt_funcs:
            return self._rt_Bias, self._rt_Bias2, self._rt_Bias3
        else:
            self.writeCtaLog(u'getRuntimeBias(),添加rt_countBias到实时函数中')
            self.rt_funcs.add(self.rt_countBias)
            self.rt_countBias()
            return self._rt_Bias, self._rt_Bias2, self._rt_Bias3

    @property
    def rt_Bias(self):
        self.check_rt_funcs(self.rt_countBias)
        return self._rt_Bias

    @property
    def rt_Bias2(self):
        self.check_rt_funcs(self.rt_countBias)
        return self._rt_Bias2

    @property
    def rt_Bias3(self):
        self.check_rt_funcs(self.rt_countBias)
        return self._rt_Bias3

    # ----------------------------------------------------------------------
    def writeCtaLog(self, content):
        """记录CTA日志"""
        self.strategy.writeCtaLog(u'[' + self.name + u']' + content)

    def debugCtaLog(self, content):
        """记录CTA日志"""
        if DEBUGCTALOG:
            self.strategy.writeCtaLog(u'[' + self.name + u'-DEBUG]' + content)

    def getTradingDate(self, dt=None):
        """
        根据输入的时间，返回交易日的日期
        :param dt:
        :return:
        """
        tradingDay = ''
        if dt is None:
            dt = datetime.now()

        if dt.hour >= 21:
            if dt.isoweekday() == 5:
                # 星期五=》星期一
                return (dt + timedelta(days=3)).strftime('%Y-%m-%d')
            else:
                # 第二天
                return (dt + timedelta(days=1)).strftime('%Y-%m-%d')
        elif dt.hour < 8 and dt.isoweekday() == 6:
            # 星期六=>星期一
            return (dt + timedelta(days=2)).strftime('%Y-%m-%d')
        else:
            return dt.strftime('%Y-%m-%d')

    def append_data(self, file_name, dict_data, field_names=None):
        """
        添加数据到csv文件中
        :param file_name:  csv的文件全路径
        :param dict_data:  OrderedDict
        :return:
        """
        if not isinstance(dict_data, dict):
            print(u'{}.append_data，输入数据不是dict'.format(self.name), file=sys.stderr)
            return

        dict_fieldnames = list(dict_data.keys()) if field_names is None else field_names

        if not isinstance(dict_fieldnames, list):
            print(u'{}append_data，输入字段不是list'.format(self.name), file=sys.stderr)
            return
        try:
            if not os.path.exists(file_name):
                self.writeCtaLog(u'create csv file:{}'.format(file_name))
                with open(file_name, 'a', encoding='utf8', newline='') as csvWriteFile:
                    writer = csv.DictWriter(f=csvWriteFile, fieldnames=dict_fieldnames, dialect='excel')
                    self.writeCtaLog(u'write csv header:{}'.format(dict_fieldnames))
                    writer.writeheader()
                    writer.writerow(dict_data)
            else:
                dt = dict_data.get('datetime', None)
                if dt is not None:
                    dt_index = dict_fieldnames.index('datetime')
                    last_dt = self.get_csv_last_dt(file_name=file_name, dt_index=dt_index,
                                                   line_length=sys.getsizeof(dict_data) / 8 + 1)
                    if last_dt is not None and dt < last_dt:
                        print(u'新增数据时间{}比最后一条记录时间{}早，不插入'.format(dt, last_dt))

                        return

                with open(file_name, 'a', encoding='utf8', newline='') as csvWriteFile:
                    writer = csv.DictWriter(f=csvWriteFile, fieldnames=dict_fieldnames, dialect='excel',extrasaction='ignore')
                    writer.writerow(dict_data)
        except Exception as ex:
            print(u'{}.append_data exception:{}/{}'.format(self.name, str(ex), traceback.format_exc()))

    def get_csv_last_dt(self, file_name, dt_index=0, line_length=1000):
        """
        获取csv文件最后一行的日期数据(第dt_index个字段必须是 '%Y-%m-%d %H:%M:%S'格式
        :param file_name:文件名
        :param line_length: 行数据的长度
        :return: None，文件不存在，或者时间格式不正确
        """
        with open(file_name, 'r') as f:
            f_size = os.path.getsize(file_name)
            if f_size < line_length:
                line_length = f_size
            f.seek(f_size - line_length)  # 移动到最后1000个字节
            for row in f.readlines()[-1:]:

                datas = row.split(',')
                if len(datas) > dt_index + 1:
                    try:
                        last_dt = datetime.strptime(datas[dt_index], '%Y-%m-%d %H:%M:%S')
                        return last_dt
                    except:
                        return None
            return None

    def is_shadow_line(self, open, high, low, close, direction, shadow_rate, wave_rate):
        """
        是否上影线/下影线
        :param open: 开仓价
        :param high: 最高价
        :param low: 最低价
        :param close: 收盘价
        :param direction: 方向（多/空）
        :param shadown_rate: 上影线比例（百分比）
        :param wave_rate:振幅（百分比）
        :return:
        """
        if close <= 0 or high <= low or shadow_rate <= 0 or wave_rate <= 0:
            self.writeCtaLog(u'是否上下影线,参数出错.close={}, high={},low={},shadow_rate={},wave_rate={}'
                             .format(close, high, low, shadow_rate, wave_rate))
            return False

        # 振幅 = 高-低 / 收盘价 百分比
        cur_wave_rate = round(100 * float((high - low) / close), 2)

        # 上涨时，判断上影线
        if direction == DIRECTION_LONG:
            # 上影线比例 = 上影线（高- max（开盘，收盘））/ 当日振幅=（高-低）
            cur_shadow_rate = round(100 * float((high - max(open, close)) / (high - low)), 2)
            if cur_wave_rate >= wave_rate and cur_shadow_rate >= shadow_rate:
                return True

        # 下跌时，判断下影线
        elif direction == DIRECTION_SHORT:
            cur_shadow_rate = round(100 * float((min(open, close) - low) / (high - low)), 2)
            if cur_wave_rate >= wave_rate and cur_shadow_rate >= shadow_rate:
                return True

        return False

    def is_end_tick(self, tick_dt):
        """
        根据短合约和时间，判断是否为最后一个tick
        :param tick_dt:
        :return:
        """
        if self.is_7x24:
            return False

        # 中金所，只有11：30 和15：15，才有最后一个tick
        if self.shortSymbol in MARKET_ZJ:
            if (tick_dt.hour == 11 and tick_dt.minute == 30) or (tick_dt.hour == 15 and tick_dt.minute == 15):
                return True
            else:
                return False

        # 其他合约(上期所/郑商所/大连）
        if 2 <= tick_dt.hour < 23:
            if (tick_dt.hour == 10 and tick_dt.minute == 15) \
                    or (tick_dt.hour == 11 and tick_dt.minute == 30) \
                    or (tick_dt.hour == 15 and tick_dt.minute == 00) \
                    or (tick_dt.hour == 2 and tick_dt.minute == 30):
                return True
            else:
                return False

        # 夜盘1:30收盘
        if self.shortSymbol in NIGHT_MARKET_SQ2 and tick_dt.hour == 1 and tick_dt.minute == 00:
            return True

        # 夜盘23:00收盘
        if self.shortSymbol in [NIGHT_MARKET_SQ3,NIGHT_MARKET_DL] and tick_dt.hour == 23 and tick_dt.minute == 00:
            return True

        # 夜盘23:30收盘
        if self.shortSymbol in NIGHT_MARKET_ZZ :
            if tick_dt.hour == 23 and tick_dt.minute == 30:
                return True

        return False


class CtaMinuteBar(CtaLineBar):
    """
    分钟级别K线
    对比基类CtaLineBar
    """

    def __init__(self, strategy, onBarFunc, setting=None):

        if 'period' in setting:
            del setting['period']

        super(CtaMinuteBar, self).__init__(strategy, onBarFunc, setting)

        # 一天内bar的数量累计
        self.bars_count = 0
        self.minutes_adjust = -15
        self.m1_bars_count = 0
        self.lastMinuteBar = CtaBarData()

    def init_properties(self):
        """
        初始化内部变量
        :return:
        """
        self.paramList.append('barTimeInterval')
        self.paramList.append('period')
        self.paramList.append('inputPreLen')
        self.paramList.append('inputEma1Len')
        self.paramList.append('inputEma2Len')
        self.paramList.append('inputEma3Len')
        self.paramList.append('inputMa1Len')
        self.paramList.append('inputMa2Len')
        self.paramList.append('inputMa3Len')
        self.paramList.append('inputDmiLen')
        self.paramList.append('inputDmiMax')
        self.paramList.append('inputAtr1Len')
        self.paramList.append('inputAtr2Len')
        self.paramList.append('inputAtr3Len')
        self.paramList.append('inputVolLen')
        self.paramList.append('inputRsi1Len')
        self.paramList.append('inputRsi2Len')
        self.paramList.append('inputCmiLen')
        self.paramList.append('inputBollLen')
        self.paramList.append('inputBollTBLen')
        self.paramList.append('inputBollStdRate')
        self.paramList.append('inputBoll2Len')
        self.paramList.append('inputBoll2TBLen')
        self.paramList.append('inputBoll2StdRate')
        self.paramList.append('inputKdjLen')
        self.paramList.append('inputKdjTBLen')
        self.paramList.append('inputKdjSlowLen')
        self.paramList.append('inputKdjSmoothLen')
        self.paramList.append('inputCciLen')
        self.paramList.append('inputMacdFastPeriodLen')
        self.paramList.append('inputMacdSlowPeriodLen')
        self.paramList.append('inputMacdSignalPeriodLen')
        self.paramList.append('inputKF')
        self.paramList.append('inputSkd')
        self.paramList.append('inputSkdLen1')
        self.paramList.append('inputSkdLen2')
        self.paramList.append('inputYb')
        self.paramList.append('inputYbLen')
        self.paramList.append('inputYbRef')
        self.paramList.append('inputYellowBlueLen')
        self.paramList.append('inputTangentLen')
        self.paramList.append('inputSarAfStep')
        self.paramList.append('inputSarAfLimit')
        self.paramList.append('inputGoldenN')
        self.paramList.append('activate_boll_ma_area')
        self.paramList.append('is_7x24')

        self.paramList.append('minDiff')
        self.paramList.append('shortSymbol')

        self.paramList.append('name')

        # 输入参数
        self.name = u'MinuteBar'
        self.mode = self.TICK_MODE  # 缺省为tick模式
        self.period = PERIOD_MINUTE  # 分钟级别周期
        self.barTimeInterval = 5  # 缺省为5分钟周期

        self.barMinuteInterval = 60  # 1分钟

    def addBar(self, bar, bar_is_completed=False, bar_freq=1):
        """
        予以外部初始化程序增加bar
        :param bar:
        :param bar_is_completed: 插入的bar，其周期与K线周期一致，就设为True
         :param bar_freq, bar对象得frequency
        :return:
        """
        # self.writeCtaLog("addBar(): {}, o={}, h={}, l={}, c={}, v={}".format(bar.datetime.strftime("%Y%m%d %H:%M:%S"),
        #     bar.open, bar.high, bar.low, bar.close, bar.volume
        # ))
        if bar.tradingDay is None:
            if self.is_7x24:
                bar.tradingDay = bar.date
            else:
                bar.tradingDay = self.getTradingDate(bar.datetime)

        # 更新最后价格
        self.cur_price = bar.close

        l1 = len(self.lineBar)

        if l1 == 0:
            self.lineBar.append(bar)
            self.curTradingDay = bar.tradingDay
            # self.m1_bars_count += bar_freq
            if bar_is_completed:
                # self.m1_bars_count = 0
                self.onBar(bar)
            # 计算当前加入的 bar的1分钟，属于当日的第几个1分钟
            minutes_passed = (bar.datetime - datetime.strptime(bar.datetime.strftime('%Y-%m-%d'),
                                                               '%Y-%m-%d')).total_seconds() / 60
            # 计算，当前的bar，属于当日的第几个bar
            self.bars_count = int(minutes_passed / self.barTimeInterval)
            return

        # 与最后一个BAR的时间比对，判断是否超过K线的周期
        lastBar = self.lineBar[-1]

        is_new_bar = False
        if bar_is_completed:
            is_new_bar = True

        minutes_passed = (bar.datetime - datetime.strptime(bar.datetime.strftime('%Y-%m-%d'), '%Y-%m-%d')).total_seconds()/ 60
        if self.shortSymbol in MARKET_ZJ:
            if int(bar.datetime.strftime('%H%M')) > 1130 and int(bar.datetime.strftime('%H%M')) < 1600:
                # 扣除11:30到13:00的中场休息的90分钟
                minutes_passed = minutes_passed - 90
        else:
            if int(bar.datetime.strftime('%H%M')) > 1015 and int(bar.datetime.strftime('%H%M')) <= 1130:
                # 扣除10:15到10:30的中场休息的15分钟
                minutes_passed = minutes_passed - 15
            elif int(bar.datetime.strftime('%H%M')) > 1130 and int(bar.datetime.strftime('%H%M')) < 1600:
                # 扣除(10:15到10:30的中场休息的15分钟)&(11:30到13:30的中场休息的120分钟)
                minutes_passed = minutes_passed - 135
        bars_passed = int(minutes_passed / self.barTimeInterval)

        # 不在同一交易日，推入新bar
        if self.curTradingDay != bar.tradingDay:
            is_new_bar = True
            self.curTradingDay = bar.tradingDay
            self.bars_count = bars_passed
            # self.writeCtaLog("drawLineBar(): {}, m1_bars_count={}".format(bar.datetime.strftime("%Y%m%d %H:%M:%S"),
            #                                                              self.m1_bars_count))
        else:
            if bars_passed != self.bars_count:
                is_new_bar = True
                self.bars_count = bars_passed

                # self.writeCtaLog("addBar(): {}, bars_count={}".format(bar.datetime.strftime("%Y%m%d %H:%M:%S"),
                #                                                      self.bars_count))

        # 数字货币，如果bar的前后距离，超过周期，重新开启一个新的bar
        if self.is_7x24 and (bar.datetime - lastBar.datetime).total_seconds() >= 60 * self.barTimeInterval:
            is_new_bar = True

        if is_new_bar:
            new_bar = copy.deepcopy(bar)
            # 添加新的bar
            self.lineBar.append(new_bar)
            # 将上一个Bar推送至OnBar事件
            self.onBar(lastBar)
        else:
            # 更新最后一个bar
            # 此段代码，针对一部分短周期生成长周期的k线更新，如3根5分钟k线，合并成1根15分钟k线。
            lastBar.close = bar.close
            lastBar.high = max(lastBar.high, bar.high)
            lastBar.low = min(lastBar.low, bar.low)
            lastBar.volume = lastBar.volume + bar.volume
            lastBar.dayVolume = bar.dayVolume
            lastBar.openInterest = bar.openInterest

            lastBar.mid3 = round((lastBar.close + lastBar.high + lastBar.low) / 4, self.round_n)
            lastBar.mid4 = round((2 * lastBar.close + lastBar.high + lastBar.low) / 4, self.round_n)
            lastBar.mid5 = round((2 * lastBar.close + lastBar.open + lastBar.high + lastBar.low) / 5, self.round_n)
            # 实时计算
            self.runtime_recount()

    # ----------------------------------------------------------------------
    def drawLineBar(self, tick):
        """
        生成 line Bar
        :param tick:
        :return:
        """

        l1 = len(self.lineBar)

        minutes_passed = (tick.datetime - datetime.strptime(tick.datetime.strftime('%Y-%m-%d'),'%Y-%m-%d')).total_seconds() / 60
        if self.shortSymbol in MARKET_ZJ:
            if int(tick.datetime.strftime('%H%M')) > 1130 and int(tick.datetime.strftime('%H%M')) < 1600:
                # 扣除11:30到13:00的中场休息的90分钟
                minutes_passed = minutes_passed - 90
        else:
            if int(tick.datetime.strftime('%H%M')) > 1015 and int(tick.datetime.strftime('%H%M')) <= 1130:
                # 扣除10:15到10:30的中场休息的15分钟
                minutes_passed = minutes_passed - 15
            elif int(tick.datetime.strftime('%H%M')) > 1130 and int(tick.datetime.strftime('%H%M')) < 1600:
                # 扣除(10:15到10:30的中场休息的15分钟)&(11:30到13:30的中场休息的120分钟)
                minutes_passed = minutes_passed - 135
        bars_passed = int(minutes_passed / self.barTimeInterval)

        # 保存第一个K线数据
        if l1 == 0:
            self.firstTick(tick)
            self.bars_count = bars_passed
            return

        # 清除480周期前的数据，
        if l1 > self.max_hold_bars:
            del self.lineBar[0]

        # 与最后一个BAR的时间比对，判断是否超过K线周期
        lastBar = self.lineBar[-1]
        is_new_bar = False

        endtick = False
        if not self.is_7x24:
            # 处理日内的间隔时段最后一个tick，如10:15分，11:30分，15:00 和 2:30分
            if (tick.datetime.hour == 10 and tick.datetime.minute == 15) \
                    or (tick.datetime.hour == 11 and tick.datetime.minute == 30) \
                    or (tick.datetime.hour == 15 and tick.datetime.minute == 00) \
                    or (tick.datetime.hour == 2 and tick.datetime.minute == 30):
                endtick = True

            # 夜盘1:30收盘
            if self.shortSymbol in NIGHT_MARKET_SQ2 and tick.datetime.hour == 1 and tick.datetime.minute == 00:
                endtick = True

            # 夜盘23:00收盘
            if self.shortSymbol in [NIGHT_MARKET_SQ3,NIGHT_MARKET_DL] and tick.datetime.hour == 23 and tick.datetime.minute == 00:
                endtick = True
            # 夜盘23:30收盘
            if self.shortSymbol in NIGHT_MARKET_ZZ :
                if tick.datetime.hour == 23 and tick.datetime.minute == 30:
                    endtick = True

            if endtick is True:
                return

        is_new_bar = False

        # 不在同一交易日，推入新bar
        if self.curTradingDay != tick.tradingDay:
            #self.writeCtaLog('{} drawLineBar() new_bar,{} curTradingDay:{},tick.tradingDay:{} bars_count={}'
            #                 .format(self.name, tick.datetime.strftime("%Y-%m-%d %H:%M:%S"), self.curTradingDay,
            #                         tick.tradingDay, self.bars_count))

            is_new_bar = True
            self.curTradingDay = tick.tradingDay
            self.bars_count = bars_passed

        else:
            # 同一交易日，看过去了多少个周期的Bar
            if bars_passed != self.bars_count:
                is_new_bar = True
                self.bars_count = bars_passed
                #self.writeCtaLog('{} drawLineBar() new_bar,{} bars_count={}'
                #                 .format(self.name, tick.datetime, self.bars_count))

        self.last_minute = tick.datetime.minute

        # 数字货币市场，分钟是连续的，所以只判断是否取整，或者与上一根bar的距离
        if self.is_7x24:
            if (
                    tick.datetime.minute % self.barTimeInterval == 0 and tick.datetime.minute != lastBar.datetime.minute) or (
                    tick.datetime - lastBar.datetime).total_seconds() > self.barTimeInterval * 60:
                # self.writeCtaLog('{} drawLineBar() new_bar,{} lastbar:{}, bars_count={}'
                #                 .format(self.name, tick.datetime, lastBar.datetime,
                #                         self.bars_count))
                is_new_bar = True

        if is_new_bar:
            # 创建并推入新的Bar
            self.firstTick(tick)
            # 触发OnBar事件
            self.onBar(lastBar)
        else:
            # 更新当前最后一个bar
            self.barFirstTick = False

            # 更新最高价、最低价、收盘价、成交量
            lastBar.high = max(lastBar.high, tick.lastPrice)
            lastBar.low = min(lastBar.low, tick.lastPrice)
            lastBar.close = tick.lastPrice
            lastBar.openInterest = tick.openInterest
            # 更新日内总交易量，和bar内交易量
            lastBar.dayVolume = tick.volume
            if l1 == 1:
                # 针对第一个bar的tick volume更新
                lastBar.volume = tick.volume
            else:
                lastBar.volume = tick.volume - self.lineBar[-2].dayVolume

            # 更新Bar的颜色
            if lastBar.close > lastBar.open:
                lastBar.color = COLOR_RED
            elif lastBar.close < lastBar.open:
                lastBar.color = COLOR_BLUE
            else:
                lastBar.color = COLOR_EQUAL

            lastBar.mid3 = round((lastBar.close + lastBar.high + lastBar.low) / 4, self.round_n)
            lastBar.mid4 = round((2 * lastBar.close + lastBar.high + lastBar.low) / 4, self.round_n)
            lastBar.mid5 = round((2 * lastBar.close + lastBar.open + lastBar.high + lastBar.low) / 5, self.round_n)
            # 实时计算
            self.runtime_recount()

class CtaHourBar(CtaLineBar):
    """
    小时级别K线
    对比基类CtaLineBar
    """

    def __init__(self, strategy, onBarFunc, setting=None):

        if 'period' in setting:
            del setting['period']

        super(CtaHourBar, self).__init__(strategy, onBarFunc, setting)

        # bar内得分钟数量累计
        self.m1_bars_count = 0
        self.last_minute = None

    def init_properties(self):
        """
        初始化内部变量
        :return:
        """
        self.paramList.append('barTimeInterval')
        self.paramList.append('period')
        self.paramList.append('inputPreLen')
        self.paramList.append('inputEma1Len')
        self.paramList.append('inputEma2Len')
        self.paramList.append('inputEma3Len')
        self.paramList.append('inputMa1Len')
        self.paramList.append('inputMa2Len')
        self.paramList.append('inputMa3Len')
        self.paramList.append('inputDmiLen')
        self.paramList.append('inputDmiMax')
        self.paramList.append('inputAtr1Len')
        self.paramList.append('inputAtr2Len')
        self.paramList.append('inputAtr3Len')
        self.paramList.append('inputVolLen')
        self.paramList.append('inputRsi1Len')
        self.paramList.append('inputRsi2Len')
        self.paramList.append('inputCmiLen')
        self.paramList.append('inputBollLen')
        self.paramList.append('inputBollTBLen')
        self.paramList.append('inputBollStdRate')
        self.paramList.append('inputBoll2Len')
        self.paramList.append('inputBoll2TBLen')
        self.paramList.append('inputBoll2StdRate')
        self.paramList.append('inputKdjLen')
        self.paramList.append('inputKdjTBLen')
        self.paramList.append('inputKdjSlowLen')
        self.paramList.append('inputKdjSmoothLen')
        self.paramList.append('inputCciLen')
        self.paramList.append('inputMacdFastPeriodLen')
        self.paramList.append('inputMacdSlowPeriodLen')
        self.paramList.append('inputMacdSignalPeriodLen')
        self.paramList.append('inputKF')
        self.paramList.append('inputSkd')
        self.paramList.append('inputSkdLen1')
        self.paramList.append('inputSkdLen2')
        self.paramList.append('inputYb')
        self.paramList.append('inputYbLen')
        self.paramList.append('inputYbRef')
        self.paramList.append('inputGoldenN')
        self.paramList.append('activate_boll_ma_area')
        self.paramList.append('is_7x24')

        self.paramList.append('minDiff')
        self.paramList.append('shortSymbol')
        self.paramList.append('name')

        # 输入参数
        self.name = u'HourBar'
        self.mode = self.TICK_MODE  # 缺省为tick模式
        self.period = PERIOD_HOUR  # 小时级别周期
        self.barTimeInterval = 1  # 缺省为小时周期

        self.barMinuteInterval = 60  #

    def addBar(self, bar, bar_is_completed=False, bar_freq=1):
        """
        予以外部初始化程序增加bar
        :param bar:
        :param bar_is_completed: 插入的bar，其周期与K线周期一致，就设为True
         :param bar_freq, bar对象得frequency
        :return:
        """
        if bar.tradingDay is None:
            if self.is_7x24:
                bar.tradingDay = bar.date
            else:
                bar.tradingDay = self.getTradingDate(bar.datetime)

        # 更新最后价格
        self.cur_price = bar.close

        l1 = len(self.lineBar)

        if l1 == 0:
            self.lineBar.append(bar)
            self.curTradingDay = bar.tradingDay
            self.m1_bars_count += bar_freq
            if bar_is_completed:
                self.m1_bars_count = 0
                self.onBar(bar)
            return

        # 与最后一个BAR的时间比对，判断是否超过K线的周期
        lastBar = self.lineBar[-1]

        is_new_bar = False
        if bar_is_completed:
            is_new_bar = True

        if self.curTradingDay is None:
            self.curTradingDay = bar.tradingDay

        if self.curTradingDay != bar.tradingDay:
            is_new_bar = True
            self.curTradingDay = bar.tradingDay

        if self.is_7x24:
            if (bar.datetime - lastBar.datetime).total_seconds() >= 3600 * self.barTimeInterval:
                is_new_bar = True
                self.curTradingDay = bar.tradingDay

        if self.m1_bars_count + bar_freq > 60 * self.barTimeInterval:
            is_new_bar = True

        if is_new_bar:
            # 添加新的bar
            self.lineBar.append(bar)
            self.m1_bars_count = bar_freq
            # 将上一个Bar推送至OnBar事件
            self.onBar(lastBar)

        else:
            # 更新最后一个bar
            # 此段代码，针对一部分短周期生成长周期的k线更新，如3根5分钟k线，合并成1根15分钟k线。
            lastBar.close = bar.close
            lastBar.high = max(lastBar.high, bar.high)
            lastBar.low = min(lastBar.low, bar.low)
            lastBar.volume = lastBar.volume + bar.volume
            lastBar.dayVolume = bar.dayVolume
            lastBar.openInterest = bar.openInterest

            lastBar.mid3 = round((lastBar.close + lastBar.high + lastBar.low) / 4, self.round_n)
            lastBar.mid4 = round((2 * lastBar.close + lastBar.high + lastBar.low) / 4, self.round_n)
            lastBar.mid5 = round((2 * lastBar.close + lastBar.open + lastBar.high + lastBar.low) / 5, self.round_n)

            self.m1_bars_count += bar_freq

            # 实时计算
            self.runtime_recount()

        # ----------------------------------------------------------------------

    def drawLineBar(self, tick):
        """
        生成 line Bar
        :param tick:
        :return:
        """

        l1 = len(self.lineBar)

        # 保存第一个K线数据
        if l1 == 0:
            self.firstTick(tick)
            return

        # 清除480周期前的数据，
        if l1 > self.max_hold_bars:
            del self.lineBar[0]
        endtick = False
        if not self.is_7x24:
            # 处理日内的间隔时段最后一个tick，如10:15分，11:30分，15:00 和 2:30分
            if (tick.datetime.hour == 10 and tick.datetime.minute == 15) \
                    or (tick.datetime.hour == 11 and tick.datetime.minute == 30) \
                    or (tick.datetime.hour == 15 and tick.datetime.minute == 00) \
                    or (tick.datetime.hour == 2 and tick.datetime.minute == 30):
                endtick = True

            # 夜盘1:30收盘
            if self.shortSymbol in NIGHT_MARKET_SQ2 and tick.datetime.hour == 1 and tick.datetime.minute == 00:
                endtick = True

            # 夜盘23:00收盘
            if self.shortSymbol in [NIGHT_MARKET_SQ3,NIGHT_MARKET_DL] and tick.datetime.hour == 23 and tick.datetime.minute == 00:
                endtick = True
            # 夜盘23:30收盘
            if self.shortSymbol in NIGHT_MARKET_ZZ :
                if tick.datetime.hour == 23 and tick.datetime.minute == 30:
                    endtick = True

        # 与最后一个BAR的时间比对，判断是否超过K线周期
        lastBar = self.lineBar[-1]
        is_new_bar = False

        if self.last_minute is None:
            if tick.datetime.second == 0:
                self.m1_bars_count += 1
            self.last_minute = tick.datetime.minute

        # 不在同一交易日，推入新bar
        if self.curTradingDay != tick.tradingDay:
            is_new_bar = True
            # 去除分钟和秒数
            tick.datetime = datetime.strptime(tick.datetime.strftime('%Y-%m-%d %H:00:00'), '%Y-%m-%d %H:%M:%S')
            tick.time = tick.datetime.strftime('%H:%M:%S')
            self.last_minute = tick.datetime.minute
            self.curTradingDay = tick.tradingDay
            #self.writeCtaLog('{} drawLineBar() new_bar,{} curTradingDay:{},tick.tradingDay:{}'
            #                 .format(self.name, tick.datetime.strftime("%Y-%m-%d %H:%M:%S"), self.curTradingDay,
            #                         tick.tradingDay))

        else:
            # 同一交易日，看分钟是否一致
            if tick.datetime.minute != self.last_minute and not endtick:
                self.m1_bars_count += 1
                self.last_minute = tick.datetime.minute

        if self.is_7x24:
            # 数字货币，用前后时间间隔
            if (tick.datetime - lastBar.datetime).total_seconds() >= 3600 * self.barTimeInterval:
                #self.writeCtaLog('{} drawLineBar() new_bar,{} - {} > 3600 * {} '
                #                 .format(self.name, tick.datetime.strftime("%Y-%m-%d %H:%M:%S"),
                #                         lastBar.datetime.strftime("%Y-%m-%d %H:%M:%S"),
                #                         self.barTimeInterval))
                is_new_bar = True
                # 去除分钟和秒数
                tick.datetime = datetime.strptime(tick.datetime.strftime('%Y-%m-%d %H:00:00'), '%Y-%m-%d %H:%M:%S')
                tick.time = tick.datetime.strftime('%H:%M:%S')
                if len(tick.tradingDay) > 0:
                    self.curTradingDay = tick.tradingDay
                else:
                    self.curTradingDay = tick.date
        else:
            # 国内期货,用bar累加
            if self.m1_bars_count > 60 * self.barTimeInterval:
                #self.writeCtaLog('{} drawLineBar() new_bar,{} {} > 60 * {} '
                #                 .format(self.name, tick.datetime.strftime("%Y-%m-%d %H:%M:%S"),
                #                         self.m1_bars_count,
                #                         self.barTimeInterval))
                is_new_bar = True
                # 去除秒数
                tick.datetime = datetime.strptime(tick.datetime.strftime('%Y-%m-%d %H:%M:00'), '%Y-%m-%d %H:%M:%S')
                tick.time = tick.datetime.strftime('%H:%M:%S')

        if is_new_bar:
            # 创建并推入新的Bar
            self.firstTick(tick)
            self.m1_bars_count = 1
            # 触发OnBar事件
            self.onBar(lastBar)

        else:
            # 更新当前最后一个bar
            self.barFirstTick = False

            # 更新最高价、最低价、收盘价、成交量
            lastBar.high = max(lastBar.high, tick.lastPrice)
            lastBar.low = min(lastBar.low, tick.lastPrice)
            lastBar.close = tick.lastPrice
            lastBar.openInterest = tick.openInterest
            # 更新日内总交易量，和bar内交易量
            lastBar.dayVolume = tick.volume
            if l1 == 1:
                # 针对第一个bar的tick volume更新
                lastBar.volume = tick.volume
            else:
                lastBar.volume = tick.volume - self.lineBar[-2].dayVolume

            # 更新Bar的颜色
            if lastBar.close > lastBar.open:
                lastBar.color = COLOR_RED
            elif lastBar.close < lastBar.open:
                lastBar.color = COLOR_BLUE
            else:
                lastBar.color = COLOR_EQUAL

            lastBar.mid3 = round((lastBar.close + lastBar.high + lastBar.low) / 4, self.round_n)
            lastBar.mid4 = round((2 * lastBar.close + lastBar.high + lastBar.low) / 4, self.round_n)
            lastBar.mid5 = round((2 * lastBar.close + lastBar.open + lastBar.high + lastBar.low) / 5, self.round_n)

            # 实时计算
            self.runtime_recount()

        if not endtick:
            self.lastTick = tick


class CtaDayBar(CtaLineBar):
    """
    日线级别K线
    """

    def __init__(self, strategy, onBarFunc, setting=None):
        self.had_night_market = False  # 是否有夜市

        if 'period' in setting:
            del setting['period']

        if 'barTimeInterval' in setting:
            del setting['barTimeInterval']

        super(CtaDayBar, self).__init__(strategy, onBarFunc, setting)

    def init_properties(self):
        """
        初始化内部变量
        :return:
        """
        self.paramList.append('barTimeInterval')
        self.paramList.append('period')
        self.paramList.append('inputPreLen')
        self.paramList.append('inputEma1Len')
        self.paramList.append('inputEma2Len')
        self.paramList.append('inputEma3Len')
        self.paramList.append('inputMa1Len')
        self.paramList.append('inputMa2Len')
        self.paramList.append('inputMa3Len')
        self.paramList.append('inputDmiLen')
        self.paramList.append('inputDmiMax')
        self.paramList.append('inputAtr1Len')
        self.paramList.append('inputAtr2Len')
        self.paramList.append('inputAtr3Len')
        self.paramList.append('inputVolLen')
        self.paramList.append('inputRsi1Len')
        self.paramList.append('inputRsi2Len')
        self.paramList.append('inputCmiLen')
        self.paramList.append('inputBollLen')
        self.paramList.append('inputBollTBLen')
        self.paramList.append('inputBollStdRate')
        self.paramList.append('inputBoll2Len')
        self.paramList.append('inputBoll2TBLen')
        self.paramList.append('inputBoll2StdRate')
        self.paramList.append('inputKdjLen')
        self.paramList.append('inputKdjTBLen')
        self.paramList.append('inputKdjSlowLen')
        self.paramList.append('inputKdjSmoothLen')
        self.paramList.append('inputCciLen')
        self.paramList.append('inputMacdFastPeriodLen')
        self.paramList.append('inputMacdSlowPeriodLen')
        self.paramList.append('inputMacdSignalPeriodLen')
        self.paramList.append('inputKF')
        self.paramList.append('inputSkd')
        self.paramList.append('inputSkdLen1')
        self.paramList.append('inputSkdLen2')
        self.paramList.append('inputYb')
        self.paramList.append('inputYbLen')
        self.paramList.append('inputYbRef')
        self.paramList.append('inputGoldenN')
        self.paramList.append('activate_boll_ma_area')
        self.paramList.append('is_7x24')

        self.paramList.append('minDiff')
        self.paramList.append('shortSymbol')

        self.paramList.append('name')

        # 输入参数
        self.name = u'DayBar'
        self.mode = self.TICK_MODE  # 缺省为tick模式
        self.period = PERIOD_DAY  # 日线级别周期
        self.barTimeInterval = 1  # 缺省为1天

        self.barMinuteInterval = 60 * 24

    def addBar(self, bar, bar_is_completed=False, bar_freq=1):
        """
        予以外部初始化程序增加bar
        :param bar:
        :param bar_is_completed: 插入的bar，其周期与K线周期一致，就设为True
        :param bar_freq, bar对象得frequency
        :return:
        """
        # 更新最后价格
        self.cur_price = bar.close

        l1 = len(self.lineBar)

        if l1 == 0:
            new_bar = copy.deepcopy(bar)
            self.lineBar.append(new_bar)
            self.curTradingDay = bar.tradingDay if bar.tradingDay is not None else bar.date
            if bar_is_completed:
                self.onBar(bar)
            return

        # 与最后一个BAR的时间比对，判断是否超过K线的周期
        lastBar = self.lineBar[-1]
        self.curTradingDay = bar.tradingDay if bar.tradingDay is not None else bar.date

        is_new_bar = False
        if bar_is_completed:
            is_new_bar = True

        # 夜盘时间判断（当前的bar时间在21点后，上一根Bar的时间在21点前
        if not self.is_7x24 and bar.datetime.hour >= 21 and lastBar.datetime.hour < 21:
            is_new_bar = True
            self.curTradingDay = bar.tradingDay if bar.tradingDay is not None else bar.date

        # 日期判断
        if not is_new_bar and lastBar.tradingDay != self.curTradingDay:
            is_new_bar = True
            self.curTradingDay = bar.tradingDay if bar.tradingDay is not None else bar.date

        if is_new_bar:
            # 添加新的bar
            new_bar = copy.deepcopy(bar)
            self.lineBar.append(new_bar)
            # 将上一个Bar推送至OnBar事件
            self.onBar(lastBar)
        else:
            # 更新最后一个bar
            # 此段代码，针对一部分短周期生成长周期的k线更新，如3根5分钟k线，合并成1根15分钟k线。
            lastBar.close = bar.close
            lastBar.high = max(lastBar.high, bar.high)
            lastBar.low = min(lastBar.low, bar.low)
            lastBar.volume = lastBar.volume + bar.volume
            lastBar.dayVolume = lastBar.volume
            lastBar.openInterest = bar.openInterest
            lastBar.mid3 = round((lastBar.close + lastBar.high + lastBar.low) / 3, self.round_n)
            lastBar.mid4 = round((2 * lastBar.close + lastBar.high + lastBar.low) / 4, self.round_n)
            lastBar.mid5 = round((2 * lastBar.close + lastBar.open + lastBar.high + lastBar.low) / 5, self.round_n)

            # 实时计算
            self.runtime_recount()

    # ----------------------------------------------------------------------
    def drawLineBar(self, tick):
        """
        生成 line Bar
        :param tick:
        :return:
        """

        l1 = len(self.lineBar)

        # 保存第一个K线数据
        if l1 == 0:
            self.firstTick(tick)
            return

        # 清除480周期前的数据，
        if l1 > self.max_hold_bars:
            del self.lineBar[0]

        # 与最后一个BAR的时间比对，判断是否超过K线周期
        lastBar = self.lineBar[-1]

        is_new_bar = False

        # 交易日期不一致，新的交易日
        if len(tick.tradingDay) > 0 and tick.tradingDay != lastBar.tradingDay:
            is_new_bar = True

        # 数字货币方面，如果当前tick 日期与bar的日期不一致.(取消，按照上面的统一处理，因为币安是按照UTC时间算的每天开始，ok是按照北京时间开始)
        # if self.is_7x24 and tick.date != lastBar.date:
        #    is_new_bar = True

        if is_new_bar:
            # 创建并推入新的Bar
            self.firstTick(tick)
            # 触发OnBar事件
            self.onBar(lastBar)

        else:
            # 更新当前最后一个bar
            self.barFirstTick = False

            # 更新最高价、最低价、收盘价、成交量
            lastBar.high = max(lastBar.high, tick.lastPrice)
            lastBar.low = min(lastBar.low, tick.lastPrice)
            lastBar.close = tick.lastPrice
            lastBar.openInterest = tick.openInterest
            # 更新日内总交易量，和bar内交易量
            lastBar.dayVolume = tick.volume
            if l1 == 1:
                # 针对第一个bar的tick volume更新
                lastBar.volume = tick.volume
            else:
                lastBar.volume = tick.volume - self.lineBar[-2].dayVolume

            # 更新Bar的颜色
            if lastBar.close > lastBar.open:
                lastBar.color = COLOR_RED
            elif lastBar.close < lastBar.open:
                lastBar.color = COLOR_BLUE
            else:
                lastBar.color = COLOR_EQUAL

            # 实时计算
            self.runtime_recount()

        self.lastTick = tick


class CtaWeekBar(CtaLineBar):
    """
    周线级别K线
    """

    def __init__(self, strategy, onBarFunc, setting=None):
        self.had_night_market = False  # 是否有夜市

        if 'period' in setting:
            del setting['period']

        if 'barTimeInterval' in setting:
            del setting['barTimeInterval']

        super(CtaWeekBar, self).__init__(strategy, onBarFunc, setting)

        # 使用周一作为周线时间
        self.use_monday = False
        # 开始的小时/分钟/秒
        self.bar_start_hour_dt = '21:00:00'

        if self.is_7x24:
            # 数字货币，使用周一的开始时间
            self.use_monday = True
            self.bar_start_hour_dt = '00:00:00'
        else:
            # 判断是否期货
            if self.shortSymbol is not None:
                if len(self.shortSymbol)<=4:
                    from vnpy.trader.vtFunction import getShortSymbol
                    # 是期货
                    if getShortSymbol(self.shortSymbol) in MARKET_DAY_ONLY:
                        # 日盘期货
                        self.use_monday = True
                        if getShortSymbol(self.shortSymbol) in MARKET_ZJ:
                            # 中金所
                            self.bar_start_hour_dt = '09:15:00'
                        else:
                            # 其他日盘期货
                            self.bar_start_hour_dt = '09:00:00'
                    else:
                        # 夜盘期货
                        self.use_monday = False
                        self.bar_start_hour_dt = '21:00:00'
                else:
                    # 可能是股票
                    self.use_monday = True
                    self.bar_start_hour_dt = '09:30:00'
            else:
                # 可能是股票
                self.use_monday = True
                self.bar_start_hour_dt = '09:30:00'

    def init_properties(self):
        """
        初始化内部变量
        :return:
        """

        #self.paramList.append('barTimeInterval')
        #self.paramList.append('period')

        self.paramList.append('inputPreLen')
        self.paramList.append('inputEma1Len')
        self.paramList.append('inputEma2Len')
        self.paramList.append('inputEma3Len')
        self.paramList.append('inputMa1Len')
        self.paramList.append('inputMa2Len')
        self.paramList.append('inputMa3Len')
        self.paramList.append('inputDmiLen')
        self.paramList.append('inputDmiMax')
        self.paramList.append('inputAtr1Len')
        self.paramList.append('inputAtr2Len')
        self.paramList.append('inputAtr3Len')
        self.paramList.append('inputVolLen')
        self.paramList.append('inputRsi1Len')
        self.paramList.append('inputRsi2Len')
        self.paramList.append('inputCmiLen')
        self.paramList.append('inputBollLen')
        self.paramList.append('inputBollTBLen')
        self.paramList.append('inputBollStdRate')
        self.paramList.append('inputBoll2Len')
        self.paramList.append('inputBoll2TBLen')
        self.paramList.append('inputBoll2StdRate')
        self.paramList.append('inputKdjLen')
        self.paramList.append('inputKdjTBLen')
        self.paramList.append('inputKdjSlowLen')
        self.paramList.append('inputKdjSmoothLen')
        self.paramList.append('inputCciLen')
        self.paramList.append('inputMacdFastPeriodLen')
        self.paramList.append('inputMacdSlowPeriodLen')
        self.paramList.append('inputMacdSignalPeriodLen')
        self.paramList.append('inputKF')
        self.paramList.append('inputSkd')
        self.paramList.append('inputSkdLen1')
        self.paramList.append('inputSkdLen2')
        self.paramList.append('inputYb')
        self.paramList.append('inputYbLen')
        self.paramList.append('inputYbRef')
        self.paramList.append('inputGoldenN')
        self.paramList.append('activate_boll_ma_area')
        self.paramList.append('is_7x24')

        self.paramList.append('minDiff')
        self.paramList.append('shortSymbol')

        self.paramList.append('name')

        # 输入参数
        self.name = u'WeekBar'
        self.mode = self.TICK_MODE  # 缺省为tick模式
        self.period = PERIOD_WEEK   # 周线级别周期
        self.barTimeInterval = 1    # 为1周

        self.barMinuteInterval = 60 * 24 * 7

    def addBar(self, bar, bar_is_completed=False, bar_freq=1):
        """
        予以外部初始化程序增加bar
        :param bar:
        :param bar_is_completed: 插入的bar，其周期与K线周期一致，就设为True
        :param bar_freq, bar对象得frequency
        :return:

        # 国内期货,周线时间开始为周五晚上21点
        # 股票，周线开始时间为周一
        # 数字货币，周线的开始时间为周一

        """
        # 更新最后价格
        self.cur_price = bar.close

        l1 = len(self.lineBar)

        if l1 == 0:
            new_bar = copy.deepcopy(bar)
            new_bar.datetime = self.get_bar_start_dt(bar.datetime)
            self.writeCtaLog(u'周线开始时间:{}=>{}'.format(bar.datetime,new_bar.datetime))
            self.lineBar.append(new_bar)
            self.curTradingDay = bar.tradingDay if bar.tradingDay is not None else bar.date
            if bar_is_completed:
                self.onBar(bar)
            return

        # 与最后一个BAR的时间比对，判断是否超过K线的周期
        lastBar = self.lineBar[-1]
        self.curTradingDay = bar.tradingDay if bar.tradingDay is not None else bar.date

        is_new_bar = False
        if bar_is_completed:
            is_new_bar = True

        # 时间判断,与上一根Bar的时间，超过7天
        if (bar.datetime - lastBar.datetime).total_seconds()>= 60*60*24*7:
            is_new_bar = True
            self.curTradingDay = bar.tradingDay if bar.tradingDay is not None else bar.date

        if is_new_bar:
            # 添加新的bar
            new_bar = copy.deepcopy(bar)
            new_bar.datetime = self.get_bar_start_dt(bar.datetime)
            self.writeCtaLog(u'新周线开始时间:{}=>{}'.format(bar.datetime, new_bar.datetime))
            self.lineBar.append(new_bar)
            # 将上一个Bar推送至OnBar事件
            self.onBar(lastBar)
        else:
            # 更新最后一个bar
            # 此段代码，针对一部分短周期生成长周期的k线更新，如3根5分钟k线，合并成1根15分钟k线。
            lastBar.close = bar.close
            lastBar.high = max(lastBar.high, bar.high)
            lastBar.low = min(lastBar.low, bar.low)
            lastBar.volume = lastBar.volume + bar.volume
            lastBar.dayVolume = lastBar.volume
            lastBar.openInterest = bar.openInterest

            lastBar.mid3 = round((lastBar.close + lastBar.high + lastBar.low) / 3, self.round_n)
            lastBar.mid4 = round((2 * lastBar.close + lastBar.high + lastBar.low) / 4, self.round_n)
            lastBar.mid5 = round((2 * lastBar.close + lastBar.open + lastBar.high + lastBar.low) / 5, self.round_n)

            # 实时计算
            self.runtime_recount()

    def get_bar_start_dt(self,cur_dt):
        """获取当前时间计算的周线Bar开始时间"""

        if self.use_monday:
            # 使用周一. 例如当前是周二，weekday=1,相当于减去一天
            monday_dt = cur_dt.replace(hour=0,minute=0,second=0,microsecond=0) - timedelta(days=cur_dt.weekday())
            start_dt = datetime.strptime(monday_dt.strftime('%Y-%m-%d')+' '+self.bar_start_hour_dt,'%Y-%m-%d %H:%M:%S')
            return start_dt

        else:
            # 使用周五
            week_day = cur_dt.weekday()

            if week_day >= 5 or (week_day == 4 and cur_dt.hour > 20):
                # 周六或周天; 或者周五晚上21:00以后
                friday_dt = cur_dt.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=cur_dt.weekday()-4)
            else:
                # 周一~周五白天
                friday_dt = cur_dt.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=cur_dt.weekday()+2)

            friday_night_dt = datetime.strptime(friday_dt.strftime('%Y-%m-%d') + ' ' + self.bar_start_hour_dt,
                                                '%Y-%m-%d %H:%M:%S')
            return friday_night_dt


    # ----------------------------------------------------------------------
    def drawLineBar(self, tick):
        """
        生成 line Bar
        :param tick:
        :return:
        """

        l1 = len(self.lineBar)

        # 保存第一个K线数据
        if l1 == 0:
            self.firstTick(tick)
            return

        # 清除480周期前的数据，
        if l1 > self.max_hold_bars:
            del self.lineBar[0]

        # 与最后一个BAR的时间比对，判断是否超过K线周期
        lastBar = self.lineBar[-1]

        is_new_bar = False

        # 交易日期不一致，新的交易日
        if (tick.datetime - lastBar.datetime).total_seconds() >= 60 * 60 * 24 * 7:
            is_new_bar = True

        if is_new_bar:
            # 创建并推入新的Bar
            self.firstTick(tick)
            # 触发OnBar事件
            self.onBar(lastBar)

        else:
            # 更新当前最后一个bar
            self.barFirstTick = False

            # 更新最高价、最低价、收盘价、成交量
            lastBar.high = max(lastBar.high, tick.lastPrice)
            lastBar.low = min(lastBar.low, tick.lastPrice)
            lastBar.close = tick.lastPrice
            lastBar.openInterest = tick.openInterest
            # 更新日内总交易量，和bar内交易量
            lastBar.dayVolume = tick.volume
            if l1 == 1:
                # 针对第一个bar的tick volume更新
                lastBar.volume = tick.volume
            else:
                lastBar.volume = tick.volume - self.lineBar[-2].dayVolume

            # 更新Bar的颜色
            if lastBar.close > lastBar.open:
                lastBar.color = COLOR_RED
            elif lastBar.close < lastBar.open:
                lastBar.color = COLOR_BLUE
            else:
                lastBar.color = COLOR_EQUAL

            # 实时计算
            self.runtime_recount()

        self.lastTick = tick

class test_strategy(object):

    def __init__(self):

        self.minDiff = 1
        self.shortSymbol = 'I'
        self.vtSymbol = 'I99'

        self.lineM5 = None
        self.lineM30 = None
        self.lineH1 = None
        self.lineH2 = None
        self.lineD = None
        self.lineW = None

        self.TMinuteInterval = 1

        self.save_m30_bars = []
        self.save_h1_bars = []
        self.save_h2_bars = []
        self.save_d_bars = []

        self.save_w_bars = []
    def createM5(self):
        lineM5Setting = {}
        lineM5Setting['name'] = u'M5'
        lineM5Setting['period'] = PERIOD_MINUTE
        lineM5Setting['barTimeInterval'] =5
        lineM5Setting['mode'] = CtaLineBar.TICK_MODE
        lineM5Setting['minDiff'] = self.minDiff
        lineM5Setting['shortSymbol'] = self.shortSymbol
        self.lineM5 = CtaMinuteBar(self, self.onBarM5, lineM5Setting)

    def onBarM5(self,bar):
        self.writeCtaLog(self.lineM5.displayLastBar())

    def createlineM30_with_macd(self):
        # 创建M30 K线
        lineM30Setting = {}
        lineM30Setting['name'] = u'M30'
        lineM30Setting['period'] = PERIOD_MINUTE
        lineM30Setting['barTimeInterval'] = 30
        lineM30Setting['inputMacdFastPeriodLen'] = 26
        lineM30Setting['inputMacdSlowPeriodLen'] = 12
        lineM30Setting['inputMacdSignalPeriodLen'] = 9
        lineM30Setting['mode'] = CtaLineBar.TICK_MODE
        lineM30Setting['minDiff'] = self.minDiff
        lineM30Setting['shortSymbol'] = self.shortSymbol
        self.lineM30 = CtaLineBar(self, self.onBarM30MACD, lineM30Setting)

    def onBarM30MACD(self, bar):
        self.writeCtaLog(self.lineM30.displayLastBar())

    def createLineM30(self):
        # 创建M30 K线
        lineM30Setting = {}
        lineM30Setting['name'] = u'M30'
        lineM30Setting['period'] = PERIOD_MINUTE
        lineM30Setting['barTimeInterval'] = 30
        lineM30Setting['inputPreLen'] = 5
        lineM30Setting['inputMa1Len'] = 5
        lineM30Setting['inputMa2Len'] = 10
        lineM30Setting['inputMa3Len'] = 18
        lineM30Setting['inputYb'] = True
        lineM30Setting['inputSkd'] = True
        lineM30Setting['mode'] = CtaLineBar.TICK_MODE
        lineM30Setting['minDiff'] = self.minDiff
        lineM30Setting['shortSymbol'] = self.shortSymbol
        self.lineM30 = CtaLineBar(self, self.onBarM30, lineM30Setting)

        return
        # 写入文件
        self.lineM30.export_filename = os.path.abspath(
            os.path.join(os.getcwd(),
                         u'export_{}_{}.csv'.format(self.vtSymbol, self.lineM30.name)))

        self.lineM30.export_fields = [
            {'name': 'datetime', 'source': 'bar', 'attr': 'datetime', 'type_': 'datetime'},
            {'name': 'open', 'source': 'bar', 'attr': 'open', 'type_': 'float'},
            {'name': 'high', 'source': 'bar', 'attr': 'high', 'type_': 'float'},
            {'name': 'low', 'source': 'bar', 'attr': 'low', 'type_': 'float'},
            {'name': 'close', 'source': 'bar', 'attr': 'close', 'type_': 'float'},
            {'name': 'turnover', 'source': 'bar', 'attr': 'turnover', 'type_': 'float'},
            {'name': 'volume', 'source': 'bar', 'attr': 'volume', 'type_': 'float'},
            {'name': 'openInterest', 'source': 'bar', 'attr': 'openInterest', 'type_': 'float'},
            {'name': 'kf', 'source': 'lineBar', 'attr': 'lineStateMean', 'type_': 'list'}
        ]

    def createLineH1(self):
        # 创建2小时K线
        lineH2Setting = {}
        lineH2Setting['name'] = u'H1'
        lineH2Setting['period'] = PERIOD_HOUR
        lineH2Setting['barTimeInterval'] = 1
        lineH2Setting['inputPreLen'] = 5
        lineH2Setting['inputMa1Len'] = 5
        lineH2Setting['inputMa2Len'] = 10
        lineH2Setting['inputMa3Len'] = 18
        lineH2Setting['inputYb'] = True
        lineH2Setting['inputSkd'] = True
        lineH2Setting['mode'] = CtaLineBar.TICK_MODE
        lineH2Setting['minDiff'] = self.minDiff
        lineH2Setting['shortSymbol'] = self.shortSymbol
        self.lineH1 = CtaHourBar(self, self.onBarH1, lineH2Setting)

    def createLineH2(self):
        # 创建2小时K线
        lineH2Setting = {}
        lineH2Setting['name'] = u'H2'
        lineH2Setting['period'] = PERIOD_HOUR
        lineH2Setting['barTimeInterval'] = 2
        lineH2Setting['inputPreLen'] = 5
        lineH2Setting['inputMa1Len'] = 5
        lineH2Setting['inputMa2Len'] = 10
        lineH2Setting['inputMa3Len'] = 18
        lineH2Setting['inputYb'] = True
        lineH2Setting['inputSkd'] = True
        lineH2Setting['mode'] = CtaLineBar.TICK_MODE
        lineH2Setting['minDiff'] = self.minDiff
        lineH2Setting['shortSymbol'] = self.shortSymbol
        self.lineH2 = CtaHourBar(self, self.onBarH2, lineH2Setting)

    def createLineD(self):
        # 创建的日K线
        lineDaySetting = {}
        lineDaySetting['name'] = u'D1'
        lineDaySetting['barTimeInterval'] = 1
        lineDaySetting['inputPreLen'] = 5
        lineDaySetting['inputAtr1Len'] = 26
        lineDaySetting['inputMa1Len'] = 5
        lineDaySetting['inputMa2Len'] = 10
        lineDaySetting['inputMa3Len'] = 18
        lineDaySetting['inputYb'] = True
        lineDaySetting['inputSkd'] = True
        lineDaySetting['mode'] = CtaDayBar.TICK_MODE
        lineDaySetting['minDiff'] = self.minDiff
        lineDaySetting['shortSymbol'] = self.shortSymbol
        self.lineD = CtaDayBar(self, self.onBarD, lineDaySetting)

    def createLineW(self):
        """创建周线"""
        lineWeekSetting = {}
        lineWeekSetting['name'] = u'W1'
        lineWeekSetting['inputPreLen'] = 5
        lineWeekSetting['inputAtr1Len'] = 26
        lineWeekSetting['inputMa1Len'] = 5
        lineWeekSetting['inputMa2Len'] = 10
        lineWeekSetting['inputMa3Len'] = 18
        lineWeekSetting['inputYb'] = True
        lineWeekSetting['inputSkd'] = True
        lineWeekSetting['mode'] = CtaDayBar.TICK_MODE
        lineWeekSetting['minDiff'] = self.minDiff
        lineWeekSetting['shortSymbol'] = self.shortSymbol
        self.lineW = CtaWeekBar(self, self.onBarW, lineWeekSetting)

    def onBar(self, bar):
        # print(u'tradingDay:{},dt:{},o:{},h:{},l:{},c:{},v:{}'.format(bar.tradingDay,bar.datetime, bar.open, bar.high, bar.low, bar.close, bar.volume))
        if self.lineW:
            self.lineW.addBar(bar, bar_freq=self.TMinuteInterval)
        if self.lineD:
            self.lineD.addBar(bar, bar_freq=self.TMinuteInterval)
        if self.lineH2:
            self.lineH2.addBar(bar, bar_freq=self.TMinuteInterval)

        if self.lineH1:
            self.lineH1.addBar(bar, bar_freq=self.TMinuteInterval)

        if self.lineM30:
            self.lineM30.addBar(bar, bar_freq=self.TMinuteInterval)

        if self.lineM5:
            self.lineM5.addBar(bar,bar_freq=self.TMinuteInterval)

        # if self.lineH2:
        #    self.lineH2.skd_is_high_dead_cross(runtime=True, high_skd=30)
        #    self.lineH2.skd_is_low_golden_cross(runtime=True, low_skd=70)

    def onBarM30(self, bar):
        self.writeCtaLog(self.lineM30.displayLastBar())

        self.save_m30_bars.append({
            'datetime': bar.datetime,
            'open': bar.open,
            'high': bar.high,
            'low': bar.low,
            'close': bar.close,
            'turnover': 0,
            'volume': bar.volume,
            'openInterest': 0,
            'ma5': self.lineM30.lineMa1[-1] if len(self.lineM30.lineMa1) > 0 else bar.close,
            'ma10': self.lineM30.lineMa2[-1] if len(self.lineM30.lineMa2) > 0 else bar.close,
            'ma18': self.lineM30.lineMa3[-1] if len(self.lineM30.lineMa3) > 0 else bar.close,
            'sk': self.lineM30.lineSK[-1] if len(self.lineM30.lineSK) > 0 else 0,
            'sd': self.lineM30.lineSD[-1] if len(self.lineM30.lineSD) > 0 else 0
        })

    def onBarH1(self, bar):
        self.writeCtaLog(self.lineH1.displayLastBar())

        self.save_h1_bars.append({
            'datetime': bar.datetime,
            'open': bar.open,
            'high': bar.high,
            'low': bar.low,
            'close': bar.close,
            'turnover': 0,
            'volume': bar.volume,
            'openInterest': 0,
            'ma5': self.lineH1.lineMa1[-1] if len(self.lineH1.lineMa1) > 0 else bar.close,
            'ma10': self.lineH1.lineMa2[-1] if len(self.lineH1.lineMa2) > 0 else bar.close,
            'ma18': self.lineH1.lineMa3[-1] if len(self.lineH1.lineMa3) > 0 else bar.close,
            'sk': self.lineH1.lineSK[-1] if len(self.lineH1.lineSK) > 0 else 0,
            'sd': self.lineH1.lineSD[-1] if len(self.lineH1.lineSD) > 0 else 0
        })

    def onBarH2(self, bar):
        self.writeCtaLog(self.lineH2.displayLastBar())

        self.save_h2_bars.append({
            'datetime': bar.datetime,
            'open': bar.open,
            'high': bar.high,
            'low': bar.low,
            'close': bar.close,
            'turnover': 0,
            'volume': bar.volume,
            'openInterest': 0,
            'ma5': self.lineH2.lineMa1[-1] if len(self.lineH2.lineMa1) > 0 else bar.close,
            'ma10': self.lineH2.lineMa2[-1] if len(self.lineH2.lineMa2) > 0 else bar.close,
            'ma18': self.lineH2.lineMa3[-1] if len(self.lineH2.lineMa3) > 0 else bar.close,
            'sk': self.lineH2.lineSK[-1] if len(self.lineH2.lineSK) > 0 else 0,
            'sd': self.lineH2.lineSD[-1] if len(self.lineH2.lineSD) > 0 else 0
        })

    def onBarD(self, bar):
        self.writeCtaLog(self.lineD.displayLastBar())
        self.save_d_bars.append({
            'datetime': bar.datetime,
            'open': bar.open,
            'high': bar.high,
            'low': bar.low,
            'close': bar.close,
            'turnover': 0,
            'volume': bar.volume,
            'openInterest': 0,
            'ma5': self.lineD.lineMa1[-1] if len(self.lineD.lineMa1) > 0 else bar.close,
            'ma10': self.lineD.lineMa2[-1] if len(self.lineD.lineMa2) > 0 else bar.close,
            'ma18': self.lineD.lineMa3[-1] if len(self.lineD.lineMa3) > 0 else bar.close,
            'sk': self.lineD.lineSK[-1] if len(self.lineD.lineSK) > 0 else 0,
            'sd': self.lineD.lineSD[-1] if len(self.lineD.lineSD) > 0 else 0
        })

    def onBarW(self, bar):
        self.writeCtaLog(self.lineW.displayLastBar())
        self.save_w_bars.append({
            'datetime': bar.datetime,
            'open': bar.open,
            'high': bar.high,
            'low': bar.low,
            'close': bar.close,
            'turnover': 0,
            'volume': bar.volume,
            'openInterest': 0,
            'ma5': self.lineW.lineMa1[-1] if len(self.lineW.lineMa1) > 0 else bar.close,
            'ma10': self.lineW.lineMa2[-1] if len(self.lineW.lineMa2) > 0 else bar.close,
            'ma18': self.lineW.lineMa3[-1] if len(self.lineW.lineMa3) > 0 else bar.close,
            'sk': self.lineW.lineSK[-1] if len(self.lineW.lineSK) > 0 else 0,
            'sd': self.lineW.lineSD[-1] if len(self.lineW.lineSD) > 0 else 0
        })


    def onTick(self, tick):
        print(u'{0},{1},ap:{2},av:{3},bp:{4},bv:{5}'.format(tick.datetime, tick.lastPrice, tick.askPrice1,
                                                            tick.askVolume1, tick.bidPrice1, tick.bidVolume1))

    def writeCtaLog(self, content):
        print(content)

    def saveData(self):

        if len(self.save_m30_bars) > 0:
            outputFile = '{}_m30.csv'.format(self.vtSymbol)
            with open(outputFile, 'w', encoding='utf8', newline='') as f:
                fieldnames = ['datetime', 'open',  'high', 'low', 'close', 'turnover', 'volume', 'openInterest',
                              'ma5', 'ma10', 'ma18', 'sk', 'sd']
                writer = csv.DictWriter(f=f, fieldnames=fieldnames, dialect='excel')
                writer.writeheader()
                for row in self.save_m30_bars:
                    writer.writerow(row)

        if len(self.save_h1_bars) > 0:
            outputFile = '{}_h1.csv'.format(self.vtSymbol)
            with open(outputFile, 'w', encoding='utf8', newline='') as f:
                fieldnames = ['datetime', 'open',  'high', 'low', 'close', 'turnover', 'volume', 'openInterest',
                              'ma5', 'ma10', 'ma18', 'sk', 'sd']
                writer = csv.DictWriter(f=f, fieldnames=fieldnames, dialect='excel')
                writer.writeheader()
                for row in self.save_h1_bars:
                    writer.writerow(row)

        if len(self.save_h2_bars) > 0:
            outputFile = '{}_h2.csv'.format(self.vtSymbol)
            with open(outputFile, 'w', encoding='utf8', newline='') as f:
                fieldnames = ['datetime', 'open', 'high', 'low', 'close', 'turnover', 'volume', 'openInterest',
                              'ma5', 'ma10', 'ma18', 'sk', 'sd']
                writer = csv.DictWriter(f=f, fieldnames=fieldnames, dialect='excel')
                writer.writeheader()
                for row in self.save_h2_bars:
                    writer.writerow(row)

        if len(self.save_d_bars) > 0:
            outputFile = '{}_d.csv'.format(self.vtSymbol)
            with open(outputFile, 'w', encoding='utf8', newline='') as f:
                fieldnames = ['datetime', 'open',  'high', 'low', 'close', 'turnover', 'volume', 'openInterest',
                              'ma5', 'ma10', 'ma18', 'sk', 'sd']
                writer = csv.DictWriter(f=f, fieldnames=fieldnames, dialect='excel')
                writer.writeheader()
                for row in self.save_d_bars:
                    writer.writerow(row)

        if len(self.save_w_bars) > 0:
            outputFile = '{}_w.csv'.format(self.vtSymbol)
            with open(outputFile, 'w', encoding='utf8', newline='') as f:
                fieldnames = ['datetime', 'open', 'high', 'low', 'close', 'turnover', 'volume', 'openInterest',
                              'ma5', 'ma10', 'ma18', 'sk', 'sd']
                writer = csv.DictWriter(f=f, fieldnames=fieldnames, dialect='excel')
                writer.writeheader()
                for row in self.save_w_bars:
                    writer.writerow(row)

if __name__ == '__main__':
    t = test_strategy()
    t.minDiff = 0.5
    t.shortSymbol = 'J'
    t.vtSymbol = 'J99'

    t.createM5()
    #t.createLineW()

    #t.createlineM30_with_macd()

    # 创建M30线
    #t.createLineM30()

    # 回测1小时线
    # t.createLineH1()

    # 回测2小时线
    # t.createLineH2()

    # 回测日线
    # t.createLineD()

    filename = 'cache/{}_20141201_20171231_1m.csv'.format(t.vtSymbol)

    barTimeInterval = 60  # 60秒
    minDiff = 1  # 回测数据的最小跳动


    def pickPrice(price, minDiff):
        return int(price / minDiff) * minDiff


    import csv

    csvfile = open(filename, 'r', encoding='utf8')
    reader = csv.DictReader((line.replace('\0', '') for line in csvfile), delimiter=",")
    last_tradingDay = None
    for row in reader:
        try:
            bar = CtaBarData()
            bar.symbol = t.vtSymbol
            bar.vtSymbol = t.vtSymbol

            # 从tb导出的csv文件
            # bar.open = float(row['Open'])
            # bar.high = float(row['High'])
            # bar.low = float(row['Low'])
            # bar.close = float(row['Close'])
            # bar.volume = float(row['TotalVolume'])#
            # barEndTime = datetime.strptime(row['Date']+' ' + row['Time'], '%Y/%m/%d %H:%M:%S')

            # 从ricequant导出的csv文件

            bar.open = pickPrice(float(row['open']), minDiff)
            bar.high = pickPrice(float(row['high']), minDiff)
            bar.low = pickPrice(float(row['low']), minDiff)
            bar.close = pickPrice(float(row['close']), minDiff)

            bar.volume = float(row['volume'])
            barEndTime = datetime.strptime(row['index'], '%Y-%m-%d %H:%M:%S')

            # 使用Bar的开始时间作为datetime
            bar.datetime = barEndTime - timedelta(seconds=barTimeInterval)

            bar.date = bar.datetime.strftime('%Y-%m-%d')
            bar.time = bar.datetime.strftime('%H:%M:%S')
            if 'trading_date' in row:
                bar.tradingDay = row['trading_date']
            else:
                if bar.datetime.hour >= 21:
                    if bar.datetime.isoweekday() == 5:
                        # 星期五=》星期一
                        bar.tradingDay = (barEndTime + timedelta(days=3)).strftime('%Y-%m-%d')
                    else:
                        # 第二天
                        bar.tradingDay = (barEndTime + timedelta(days=1)).strftime('%Y-%m-%d')
                elif bar.datetime.hour < 8 and bar.datetime.isoweekday() == 6:
                    # 星期六=>星期一
                    bar.tradingDay = (barEndTime + timedelta(days=2)).strftime('%Y-%m-%d')
                else:
                    bar.tradingDay = bar.date

            t.onBar(bar)
            # 测试 实时计算值
            #sk, sd = t.lineM30.getRuntimeSKD()

            # 测试实时计算值
            #if bar.datetime.minute==1:
            #    print('rt_Dif:{}'.format(t.lineM30.rt_Dif))
        except Exception as ex:
            t.writeCtaLog(u'{0}:{1}'.format(Exception, ex))
            traceback.print_exc()
            break

    t.saveData()
