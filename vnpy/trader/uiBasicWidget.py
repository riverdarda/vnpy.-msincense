# encoding: UTF-8

import json
import csv
import os,sys
import platform
from collections import OrderedDict
import traceback

from vnpy.trader.vtEvent import *
from vnpy.trader.vtFunction import *
from vnpy.trader.vtGateway import *
from vnpy.trader.vtText import text as vtText
from vnpy.trader.uiQt import QtWidgets, QtGui, QtCore, BASIC_FONT
from vnpy.trader.vtConstant import EXCHANGE_BINANCE,EXCHANGE_OKEX,EXCHANGE_GATEIO,EXCHANGE_HUOBI

if str(platform.system()) == 'Windows':
    import winsound

QCOLOR_RED = QtGui.QColor('red')
QCOLOR_GREEN = QtGui.QColor('green')

########################################################################
class BasicCell(QtWidgets.QTableWidgetItem):
    """基础的单元格"""

    #----------------------------------------------------------------------
    def __init__(self, text=None, mainEngine=None):
        """Constructor"""
        super(BasicCell, self).__init__()
        self.data = None
        if text:
            self.setContent(text)

    #----------------------------------------------------------------------
    def setContent(self, text):
        """设置内容"""
        if text == '0' or text == '0.0' or type(text) == type(None):
            self.setText('')
        elif isinstance(text, float):
            f_str = str("%.8f" % text)
            self.setText(floatToStr(f_str))
        else:
            self.setText(str(text))


########################################################################
class NumCell(QtWidgets.QTableWidgetItem):
    """用来显示数字的单元格"""

    # ----------------------------------------------------------------------
    def __init__(self, text=None, mainEngine=None):
        """Constructor"""
        super(NumCell, self).__init__()
        self.data = None
        if text:
            self.setContent(text)

    # ----------------------------------------------------------------------
    def setContent(self, text):
        """设置内容"""
        # 考虑到NumCell主要用来显示OrderID和TradeID之类的整数字段，
        # 这里的数据转化方式使用int类型。但是由于部分交易接口的委托
        # 号和成交号可能不是纯数字的形式，因此补充了一个try...except
        try:
            num = int(text)
            self.setData(QtCore.Qt.DisplayRole, num)
        except ValueError:
            self.setText(text)


########################################################################
class DirectionCell(QtWidgets.QTableWidgetItem):
    """用来显示买卖方向的单元格"""

    #----------------------------------------------------------------------
    def __init__(self, text=None, mainEngine=None):
        """Constructor"""
        super(DirectionCell, self).__init__()
        self.data = None
        if text:
            self.setContent(text)

    #----------------------------------------------------------------------
    def setContent(self, text):
        """设置内容"""
        if text == DIRECTION_LONG or text == DIRECTION_NET:
            self.setForeground(QtGui.QColor('red'))
        elif text == DIRECTION_SHORT:
            self.setForeground(QtGui.QColor('green'))
        self.setText(text)

########################################################################
class NameCell(QtWidgets.QTableWidgetItem):
    """用来显示合约中文的单元格"""

    #----------------------------------------------------------------------
    def __init__(self, text=None, mainEngine=None):
        """Constructor"""
        super(NameCell, self).__init__()

        self.mainEngine = mainEngine
        self.data = None

        if text:
            self.setContent(text)

    #----------------------------------------------------------------------
    def setContent(self, text):
        """设置内容"""
        if self.mainEngine:
            # 首先尝试正常获取合约对象
            contract = self.mainEngine.getContract(text)

            # 如果能读取合约信息
            if contract:
                self.setText(contract.name)


########################################################################
class BidCell(QtWidgets.QTableWidgetItem):
    """买价单元格"""

    #----------------------------------------------------------------------
    def __init__(self, text=None, mainEngine=None):
        """Constructor"""
        super(BidCell, self).__init__()
        self.data = None

        self.setForeground(QtGui.QColor('black'))
        self.setBackground(QtGui.QColor(255,174,201))

        if text:
            self.setContent(text)

    #----------------------------------------------------------------------
    def setContent(self, text):
        """设置内容"""
        self.setText(str(text))


########################################################################
class AskCell(QtWidgets.QTableWidgetItem):
    """买价单元格"""

    #----------------------------------------------------------------------
    def __init__(self, text=None, mainEngine=None):
        """Constructor"""
        super(AskCell, self).__init__()
        self.data = None

        self.setForeground(QtGui.QColor('black'))
        self.setBackground(QtGui.QColor(160,255,160))

        if text:
            self.setContent(text)

    #----------------------------------------------------------------------
    def setContent(self, text):
        """设置内容"""
        self.setText(str(text))

########################################################################
class PnlCell(QtWidgets.QTableWidgetItem):
    """显示盈亏的单元格"""

    # ----------------------------------------------------------------------
    def __init__(self, text=None, mainEngine=None):
        """Constructor"""
        super(PnlCell, self).__init__()
        self.data = None
        self.color = ''
        if text:
            self.setContent(text)

    # ----------------------------------------------------------------------
    def setContent(self, text):
        """设置内容"""
        self.setText(text)

        try:
            value = float(text)
            if value >= 0 and self.color != 'red':
                self.color = 'red'
                self.setForeground(QCOLOR_RED)
            elif value < 0 and self.color != 'green':
                self.color = 'green'
                self.setForeground(QCOLOR_GREEN)
        except ValueError:
            pass
########################################################################
class BasicMonitor(QtWidgets.QTableWidget):
    """
    基础监控

    headerDict中的值对应的字典格式如下
    {'chinese': u'中文名', 'cellType': BasicCell}

    """
    signal = QtCore.Signal(type(Event()))

    #----------------------------------------------------------------------
    def __init__(self, mainEngine=None, eventEngine=None, parent=None):
        """Constructor"""
        super(BasicMonitor, self).__init__(parent)

        self.mainEngine = mainEngine
        self.eventEngine = eventEngine

        # 保存表头标签用
        self.headerDict = OrderedDict()  # 有序字典，key是英文名，value是对应的配置字典
        self.headerList = []             # 对应self.headerDict.keys()

        # 保存相关数据用
        self.dataDict = {}  # 字典，key是字段对应的数据，value是保存相关单元格的字典
        self.dataKey = ''   # 字典键对应的数据字段

        # 监控的事件类型
        self.eventType = ''

        # 字体
        self.font = None

        # 保存数据对象到单元格
        self.saveData = False

        # 默认不允许根据表头进行排序，需要的组件可以开启
        self.sorting = False

        # 初始化右键菜单
        self.initMenu()

    #----------------------------------------------------------------------
    def setHeaderDict(self, headerDict):
        """设置表头有序字典"""
        self.headerDict = headerDict
        self.headerList = headerDict.keys()

    #----------------------------------------------------------------------
    def setDataKey(self, dataKey):
        """设置数据字典的键"""
        self.dataKey = dataKey

    #----------------------------------------------------------------------
    def setEventType(self, eventType):
        """设置监控的事件类型"""
        self.eventType = eventType

    #----------------------------------------------------------------------
    def setFont(self, font):
        """设置字体"""
        self.font = font

    #----------------------------------------------------------------------
    def setSaveData(self, saveData):
        """设置是否要保存数据到单元格"""
        self.saveData = saveData

    #----------------------------------------------------------------------
    def initTable(self):
        """初始化表格"""
        # 设置表格的列数
        col = len(self.headerDict)
        self.setColumnCount(col)

        # 设置列表头
        labels = [d['chinese'] for d in list(self.headerDict.values())]
        self.setHorizontalHeaderLabels(labels)

        # 关闭左边的垂直表头
        self.verticalHeader().setVisible(False)

        # 设为不可编辑
        self.setEditTriggers(self.NoEditTriggers)

        # 设为行交替颜色
        self.setAlternatingRowColors(True)

        # 设置允许排序
        self.setSortingEnabled(self.sorting)

    #----------------------------------------------------------------------
    def registerEvent(self):
        """注册GUI更新相关的事件监听"""
        self.signal.connect(self.updateEvent)
        self.eventEngine.register(self.eventType, self.signal.emit)

    #----------------------------------------------------------------------
    def updateEvent(self, event):
        """收到事件更新"""
        try:
            data = event.dict_['data']
            self.updateData(data)
        except Exception as ex:
            print(ex)
            traceback.print_exc()

    # ----------------------------------------------------------------------
    def updateData(self, data):
        try:
            """将数据更新到表格中"""
            # 如果允许了排序功能，则插入数据前必须关闭，否则插入新的数据会变乱
            if self.sorting:
                self.setSortingEnabled(False)

            # 如果设置了dataKey，则采用存量更新模式
            if self.dataKey:
                if isinstance(self.dataKey, list):
                    # 多个key，逐一组合
                    key = '_'.join([str(getattr(data, item, '')) for item in self.dataKey])
                else:
                    # 单个key
                    key = getattr(data, self.dataKey, None)
                    if key is None:
                        print('uiBaseWidget.updateData() error: data had not attribute {} '.format(self.dataKey))
                        return
                # 如果键在数据字典中不存在，则先插入新的一行，并创建对应单元格
                if key not in self.dataDict:
                    self.insertRow(0)
                    d = {}
                    for n, header in enumerate(self.headerList):
                        content = safeUnicode(data.__getattribute__(header))
                        cellType = self.headerDict[header]['cellType']
                        cell = cellType(content, self.mainEngine)

                        if self.font:
                            cell.setFont(self.font)  # 如果设置了特殊字体，则进行单元格设置

                        if self.saveData:            # 如果设置了保存数据对象，则进行对象保存
                            cell.data = data

                        self.setItem(0, n, cell)
                        d[header] = cell
                    self.dataDict[key] = d
                # 否则如果已经存在，则直接更新相关单元格
                else:
                    d = self.dataDict[key]
                    for header in self.headerList:
                        content = safeUnicode(data.__getattribute__(header))
                        cell = d[header]
                        cell.setContent(content)

                        if self.saveData:            # 如果设置了保存数据对象，则进行对象保存
                            cell.data = data
            # 否则采用增量更新模式
            else:
                self.insertRow(0)
                for n, header in enumerate(self.headerList):
                    content = safeUnicode(data.__getattribute__(header))
                    cellType = self.headerDict[header]['cellType']
                    cell = cellType(content, self.mainEngine)

                    if self.font:
                        cell.setFont(self.font)

                    if self.saveData:
                        cell.data = data

                    self.setItem(0, n, cell)

            # 调整列宽
            #self.resizeColumns()

            # 重新打开排序
            if self.sorting:
                self.setSortingEnabled(True)
        except Exception as ex:
            print('update data exception:{},{}'.format(str(ex),traceback.format_exc()),file=sys.stderr)

    #----------------------------------------------------------------------
    def resizeColumns(self):
        """调整各列的大小"""
        self.horizontalHeader().resizeSections(QtWidgets.QHeaderView.ResizeToContents)

    #----------------------------------------------------------------------
    def setSorting(self, sorting):
        """设置是否允许根据表头排序"""
        self.sorting = sorting

    #----------------------------------------------------------------------
    def saveToCsv(self, path=EMPTY_STRING):
        """保存表格内容到CSV文件"""

        # 获取想要保存的文件名
        if not path:
            # 先隐藏右键菜单
            self.menu.close()

            # 获取想要保存的文件名
            path = QtWidgets.QFileDialog.getSaveFileName(self, vtText.SAVE_DATA, '', 'CSV(*.csv)')
            if len(path)<1:
                return
            path = path[0]
        log = VtLogData()
        log.gatewayName = u'-'

        try:
            if not os.path.exists(path):
                with open(path, 'w',encoding='utf8') as f:
                    writer = csv.writer(f)

                    # 保存标签
                    headers = [header for header in self.headerList]
                    writer.writerow(headers)

                    # 保存每行内容
                    for row in range(self.rowCount()):
                        rowdata = []
                        for column in range(self.columnCount()):
                            item = self.item(row, column)
                            if item is not None:
                                rowdata.append(item.text())
                            else:
                                rowdata.append('')
                        writer.writerow(rowdata)

                log.logContent = u'数据保存至:{0}'.format(path)

        except IOError:
            log.logContent = u'文件IO失败:{0}'.format(path)

            event1 = Event(type_=EVENT_LOG)
            event1.dict_['data'] = log
            self.eventEngine.put(event1)

    #----------------------------------------------------------------------
    def initMenu(self):
        """初始化右键菜单"""
        self.menu = QtWidgets.QMenu(self)

        saveAction = QtWidgets.QAction(vtText.SAVE_DATA, self)
        saveAction.triggered.connect(self.saveToCsv)

        self.menu.addAction(saveAction)

    #----------------------------------------------------------------------
    def contextMenuEvent(self, event):
        """右键点击事件"""
        self.menu.popup(QtGui.QCursor.pos())

    def clearData(self):
        """清空数据"""
        self.dataDict = {}
        self.setRowCount(0)

########################################################################
class MarketMonitor(BasicMonitor):
    """市场监控组件"""

    #----------------------------------------------------------------------
    def __init__(self, mainEngine, eventEngine, parent=None):
        """Constructor"""
        super(MarketMonitor, self).__init__(mainEngine, eventEngine, parent)

        # 设置表头有序字典
        d = OrderedDict()
        d['symbol'] = {'chinese':vtText.CONTRACT_SYMBOL, 'cellType':BasicCell}
        d['vtSymbol'] = {'chinese':vtText.CONTRACT_NAME, 'cellType':NameCell}
        d['lastPrice'] = {'chinese':vtText.LAST_PRICE, 'cellType':BasicCell}
        d['preClosePrice'] = {'chinese':vtText.PRE_CLOSE_PRICE, 'cellType':BasicCell}
        d['volume'] = {'chinese':vtText.VOLUME, 'cellType':BasicCell}
        d['openInterest'] = {'chinese':vtText.OPEN_INTEREST, 'cellType':BasicCell}
        d['openPrice'] = {'chinese':vtText.OPEN_PRICE, 'cellType':BasicCell}
        d['highPrice'] = {'chinese':vtText.HIGH_PRICE, 'cellType':BasicCell}
        d['lowPrice'] = {'chinese':vtText.LOW_PRICE, 'cellType':BasicCell}
        d['bidPrice1'] = {'chinese':vtText.BID_PRICE_1, 'cellType':BidCell}
        d['bidVolume1'] = {'chinese':vtText.BID_VOLUME_1, 'cellType':BidCell}
        d['askPrice1'] = {'chinese':vtText.ASK_PRICE_1, 'cellType':AskCell}
        d['askVolume1'] = {'chinese':vtText.ASK_VOLUME_1, 'cellType':AskCell}
        d['time'] = {'chinese':vtText.TIME, 'cellType':BasicCell}
        d['gatewayName'] = {'chinese':vtText.GATEWAY, 'cellType':BasicCell}
        self.setHeaderDict(d)

        # 设置数据键
        self.setDataKey(['vtSymbol', 'gatewayName'])

        # 设置监控事件类型
        self.setEventType(EVENT_TICK)

        # 设置字体
        self.setFont(BASIC_FONT)

        # 保存cell绑定数据
        self.setSaveData(True)

        # 设置允许排序
        self.setSorting(True)

        # 初始化表格
        self.initTable()

        # 注册事件监听
        self.registerEvent()


########################################################################
class LogMonitor(BasicMonitor):
    """日志监控"""

    #----------------------------------------------------------------------
    def __init__(self, mainEngine, eventEngine, parent=None):
        """Constructor"""
        super(LogMonitor, self).__init__(mainEngine, eventEngine, parent)

        d = OrderedDict()
        d['logTime'] = {'chinese':vtText.TIME, 'cellType':BasicCell}
        d['logContent'] = {'chinese':vtText.CONTENT, 'cellType':BasicCell}
        d['gatewayName'] = {'chinese':vtText.GATEWAY, 'cellType':BasicCell}
        self.setHeaderDict(d)

        self.setEventType(EVENT_LOG)
        self.setFont(BASIC_FONT)
        self.initTable()
        self.registerEvent()


########################################################################
class ErrorMonitor(BasicMonitor):
    """错误监控"""

    #----------------------------------------------------------------------
    def __init__(self, mainEngine, eventEngine, parent=None):
        """Constructor"""
        super(ErrorMonitor, self).__init__(mainEngine, eventEngine, parent)

        d = OrderedDict()
        d['errorTime']  = {'chinese':vtText.TIME, 'cellType':BasicCell}
        d['errorID'] = {'chinese':vtText.ERROR_CODE, 'cellType':BasicCell}
        d['errorMsg'] = {'chinese':vtText.ERROR_MESSAGE, 'cellType':BasicCell}
        d['gatewayName'] = {'chinese':vtText.GATEWAY, 'cellType':BasicCell}
        d['additionalInfo'] = {'chinese': u'补充信息', 'cellType': BasicCell}

        self.setHeaderDict(d)

        self.setEventType(EVENT_ERROR)
        self.setFont(BASIC_FONT)
        self.initTable()
        self.registerEvent()

        self.eventEngine.register(EVENT_TRADE, self.play_trade)

    def play_trade(self, event):
        """播放交易声音"""

        # 1.获取事件的Trade数据
        trade = event.dict_['data']
        winsound.PlaySound('warn.wav', winsound.SND_ASYNC)

########################################################################
class TradeMonitor(BasicMonitor):
    """成交监控"""

    #----------------------------------------------------------------------
    def __init__(self, mainEngine, eventEngine, parent=None):
        """Constructor"""
        super(TradeMonitor, self).__init__(mainEngine, eventEngine, parent)

        d = OrderedDict()
        d['tradeID'] = {'chinese':vtText.TRADE_ID, 'cellType':NumCell}
        d['orderID'] = {'chinese':vtText.ORDER_ID, 'cellType':NumCell}
        d['symbol'] = {'chinese':vtText.CONTRACT_SYMBOL, 'cellType':BasicCell}
        d['vtSymbol'] = {'chinese':vtText.CONTRACT_NAME, 'cellType':NameCell}
        d['direction'] = {'chinese':vtText.DIRECTION, 'cellType':DirectionCell}
        d['offset'] = {'chinese':vtText.OFFSET, 'cellType':BasicCell}
        d['price'] = {'chinese':vtText.PRICE, 'cellType':BasicCell}
        d['volume'] = {'chinese':vtText.VOLUME, 'cellType':BasicCell}
        d['tradeTime'] = {'chinese':vtText.TRADE_TIME, 'cellType':BasicCell}
        d['gatewayName'] = {'chinese':vtText.GATEWAY, 'cellType':BasicCell}
        self.setHeaderDict(d)

        self.setDataKey(['vtTradeID','gatewayName'])
        self.setEventType(EVENT_TRADE)
        self.setFont(BASIC_FONT)
        self.setSorting(True)

        self.initTable()
        self.registerEvent()

        self.eventEngine.register( EVENT_TRADE, self.play_trade)


    def play_trade(self, event):
        """播放交易声音"""

        # 1.获取事件的Trade数据
        trade = event.dict_['data']
        winsound.PlaySound('match.wav', winsound.SND_ASYNC)


########################################################################
class OrderMonitor(BasicMonitor):
    """委托监控"""

    #----------------------------------------------------------------------
    def __init__(self, mainEngine, eventEngine, parent=None):
        """Constructor"""
        super(OrderMonitor, self).__init__(mainEngine, eventEngine, parent)

        self.mainEngine = mainEngine

        d = OrderedDict()
        d['orderID'] = {'chinese':vtText.ORDER_ID, 'cellType':NumCell}
        d['symbol'] = {'chinese':vtText.CONTRACT_SYMBOL, 'cellType':BasicCell}
        d['vtSymbol'] = {'chinese':vtText.CONTRACT_NAME, 'cellType':NameCell}
        d['direction'] = {'chinese':vtText.DIRECTION, 'cellType':DirectionCell}
        d['offset'] = {'chinese':vtText.OFFSET, 'cellType':BasicCell}
        d['price'] = {'chinese':vtText.PRICE, 'cellType':BasicCell}
        d['totalVolume'] = {'chinese':vtText.ORDER_VOLUME, 'cellType':BasicCell}
        d['tradedVolume'] = {'chinese':vtText.TRADED_VOLUME, 'cellType':BasicCell}
        d['status'] = {'chinese':vtText.ORDER_STATUS, 'cellType':BasicCell}
        d['orderTime'] = {'chinese':vtText.ORDER_TIME, 'cellType':BasicCell}
        d['cancelTime'] = {'chinese':vtText.CANCEL_TIME, 'cellType':BasicCell}
        #d['frontID'] = {'chinese':vtText.FRONT_ID, 'cellType':BasicCell}         # 考虑到在vn.trader中，ctpGateway的报单号应该是始终递增的，因此这里可以忽略
        #d['sessionID'] = {'chinese':vtText.SESSION_ID, 'cellType':BasicCell}
        d['gatewayName'] = {'chinese':vtText.GATEWAY, 'cellType':BasicCell}
        self.setHeaderDict(d)

        # vtOrderId已经包含了gatewayName和本地orderId，已经足够作为主键
        self.setDataKey('vtOrderID')
        self.setEventType(EVENT_ORDER)
        self.setFont(BASIC_FONT)
        self.setSaveData(True)

        # add by Incense 20160728
        self.setSorting(True)

        self.initTable()
        self.registerEvent()

        self.connectSignal()


    #----------------------------------------------------------------------
    def connectSignal(self):
        """连接信号"""
        # 双击单元格撤单
        self.itemDoubleClicked.connect(self.cancelOrder)

    #----------------------------------------------------------------------
    def cancelOrder(self, cell):
        """根据单元格的数据撤单"""
        order = cell.data

        req = VtCancelOrderReq()
        req.symbol = order.symbol
        req.vtSymbol = order.symbol
        req.exchange = order.exchange
        req.frontID = order.frontID
        req.sessionID = order.sessionID
        req.orderID = order.orderID
        self.mainEngine.cancelOrder(req, order.gatewayName)

    def updateData(self, data):
        """更新数据"""
        super(OrderMonitor, self).updateData(data)

        # 为了跟踪调试

########################################################################
class PositionMonitor(BasicMonitor):
    """持仓监控"""
    #----------------------------------------------------------------------
    def __init__(self, mainEngine, eventEngine, parent=None):
        """Constructor"""
        super(PositionMonitor, self).__init__(mainEngine, eventEngine, parent)

        d = OrderedDict()
        d['symbol'] = {'chinese':vtText.CONTRACT_SYMBOL, 'cellType':BasicCell}
        d['vtSymbol'] = {'chinese':vtText.CONTRACT_NAME, 'cellType':NameCell}
        d['direction'] = {'chinese':vtText.DIRECTION, 'cellType':DirectionCell}
        d['position'] = {'chinese':vtText.POSITION, 'cellType':BasicCell}
        d['ydPosition'] = {'chinese':vtText.YD_POSITION, 'cellType':BasicCell}
        d['frozen'] = {'chinese':vtText.FROZEN, 'cellType':BasicCell}
        d['price'] = {'chinese':vtText.PRICE, 'cellType':BasicCell}
        d['positionProfit'] = {'chinese':vtText.POSITION_PROFIT, 'cellType':BasicCell}
        d['gatewayName'] = {'chinese':vtText.GATEWAY, 'cellType':BasicCell}
        self.setHeaderDict(d)

        # 设置合约/多空/接口为联合索引
        self.setDataKey(['vtSymbol', 'direction', 'gatewayName'])

        self.setEventType(EVENT_POSITION)
        self.setFont(BASIC_FONT)
        self.setSaveData(True)

        # add by Incense 20160728
        self.setSorting(True)

        self.initTable()
        self.registerEvent()

########################################################################
class AccountMonitor(BasicMonitor):
    """账户监控"""

    #----------------------------------------------------------------------
    def __init__(self, mainEngine, eventEngine, parent=None):
        """Constructor"""
        super(AccountMonitor, self).__init__(mainEngine, eventEngine, parent)

        d = OrderedDict()
        d['accountID'] = {'chinese':vtText.ACCOUNT_ID, 'cellType':BasicCell}
        d['preBalance'] = {'chinese':vtText.PRE_BALANCE, 'cellType':BasicCell}
        d['balance'] = {'chinese':vtText.BALANCE, 'cellType':BasicCell}
        d['available'] = {'chinese':vtText.AVAILABLE, 'cellType':BasicCell}
        d['commission'] = {'chinese':vtText.COMMISSION, 'cellType':BasicCell}
        d['margin'] = {'chinese':vtText.MARGIN, 'cellType':BasicCell}
        d['closeProfit'] = {'chinese':vtText.CLOSE_PROFIT, 'cellType':BasicCell}
        d['positionProfit'] = {'chinese':vtText.POSITION_PROFIT, 'cellType':BasicCell}
        d['gatewayName'] = {'chinese':vtText.GATEWAY, 'cellType':BasicCell}
        d['currency'] = {'chinese': vtText.CURRENCY, 'cellType': BasicCell}
        self.setHeaderDict(d)

        self.setDataKey(['vtAccountID','gatewayName','currency'])
        self.setEventType(EVENT_ACCOUNT)
        self.setFont(BASIC_FONT)
        self.initTable()
        self.registerEvent()

########################################################################
class TradingWidget(QtWidgets.QFrame):
    """简单交易组件"""
    signal = QtCore.Signal(type(Event()))

    directionList = [DIRECTION_LONG,
                     DIRECTION_SHORT]

    offsetList = [OFFSET_OPEN,
                  OFFSET_CLOSE,
                  OFFSET_CLOSEYESTERDAY,
                  OFFSET_CLOSETODAY]

    priceTypeList = [PRICETYPE_LIMITPRICE,
                     PRICETYPE_MARKETPRICE,
                     PRICETYPE_FAK,
                     PRICETYPE_FOK]

    exchangeList = [EXCHANGE_NONE,
                    EXCHANGE_CFFEX,
                    EXCHANGE_SHFE,
                    EXCHANGE_DCE,
                    EXCHANGE_CZCE,
                    EXCHANGE_SSE,
                    EXCHANGE_SZSE,
                    EXCHANGE_XSHG,
                    EXCHANGE_XSHE,
                    EXCHANGE_INE,
                    EXCHANGE_SGE,
                    EXCHANGE_HKEX,
                    EXCHANGE_HKFE,
                    EXCHANGE_SMART,
                    EXCHANGE_ICE,
                    EXCHANGE_CME,
                    EXCHANGE_NYMEX,
                    EXCHANGE_GLOBEX,
                    EXCHANGE_IDEALPRO,
                    EXCHANGE_OKEX,
                    EXCHANGE_BINANCE,
                    EXCHANGE_HUOBI,
                    EXCHANGE_GATEIO,
                    EXCHANGE_FCOIN]

    currencyList = [CURRENCY_NONE,
                    CURRENCY_CNY,
                    CURRENCY_HKD,
                    CURRENCY_USD,
                    CURRENCY_UNKNOWN]

    productClassList = [PRODUCT_NONE,
                        PRODUCT_EQUITY,
                        PRODUCT_FUTURES,
                        PRODUCT_OPTION,
                        PRODUCT_FOREX,
                        PRODUCT_SPOT]

    gatewayList = ['']

    #----------------------------------------------------------------------
    def __init__(self, mainEngine, eventEngine, parent=None):
        """Constructor"""
        super(TradingWidget, self).__init__(parent)
        self.mainEngine = mainEngine
        self.eventEngine = eventEngine

        self.symbol = ''

        # 添加交易接口
        self.gatewayList.extend(mainEngine.getAllGatewayNames())

        self.initUi()
        self.connectSignal()

    #----------------------------------------------------------------------
    def initUi(self):
        """初始化界面"""
        self.setWindowTitle(vtText.TRADING)
        self.setMaximumWidth(400)
        self.setFrameShape(self.Box)    # 设置边框
        self.setLineWidth(1)

        # 左边部分
        labelSymbol = QtWidgets.QLabel(vtText.CONTRACT_SYMBOL)
        labelName =  QtWidgets.QLabel(vtText.CONTRACT_NAME)
        labelDirection = QtWidgets.QLabel(vtText.DIRECTION)
        labelOffset = QtWidgets.QLabel(vtText.OFFSET)
        labelPrice = QtWidgets.QLabel(vtText.PRICE)
        self.checkFixed = QtWidgets.QCheckBox(u'')  # 价格固定选择框
        labelVolume = QtWidgets.QLabel(vtText.VOLUME)
        labelPriceType = QtWidgets.QLabel(vtText.PRICE_TYPE)
        labelExchange = QtWidgets.QLabel(vtText.EXCHANGE)
        labelCurrency = QtWidgets.QLabel(vtText.CURRENCY)
        labelProductClass = QtWidgets.QLabel(vtText.PRODUCT_CLASS)
        labelGateway = QtWidgets.QLabel(vtText.GATEWAY)

        self.lineSymbol = QtWidgets.QLineEdit()
        self.lineName = QtWidgets.QLineEdit()

        self.comboDirection = QtWidgets.QComboBox()
        self.comboDirection.addItems(self.directionList)

        self.comboOffset = QtWidgets.QComboBox()
        self.comboOffset.addItems(self.offsetList)

        self.spinPrice = QtWidgets.QDoubleSpinBox()
        self.spinPrice.setDecimals(4)
        self.spinPrice.setMinimum(-10000)    # 原来是0，为支持套利，改为-10000
        self.spinPrice.setMaximum(sys.maxsize)

        self.spinVolume = QtWidgets.QDoubleSpinBox()
        self.spinVolume.setMinimum(0)
        #self.spinVolume.setDecimals(8)
        self.spinVolume.setMaximum(sys.maxsize)

        self.comboPriceType = QtWidgets.QComboBox()
        self.comboPriceType.addItems(self.priceTypeList)

        self.comboExchange = QtWidgets.QComboBox()
        self.comboExchange.addItems(self.exchangeList)

        self.comboCurrency = QtWidgets.QComboBox()
        self.comboCurrency.addItems(self.currencyList)

        self.comboProductClass = QtWidgets.QComboBox()
        self.comboProductClass.addItems(self.productClassList)

        self.comboGateway = QtWidgets.QComboBox()
        self.comboGateway.addItems(self.gatewayList)

        gridleft = QtWidgets.QGridLayout()
        gridleft.addWidget(labelSymbol, 0, 0)
        gridleft.addWidget(labelName, 1, 0)
        gridleft.addWidget(labelDirection, 2, 0)
        gridleft.addWidget(labelOffset, 3, 0)
        gridleft.addWidget(labelPrice, 4, 0)
        gridleft.addWidget(labelVolume, 5, 0)
        gridleft.addWidget(labelPriceType, 6, 0)
        gridleft.addWidget(labelExchange, 7, 0)

        gridleft.addWidget(labelCurrency, 8, 0)
        gridleft.addWidget(labelProductClass, 9, 0)
        gridleft.addWidget(labelGateway, 10, 0)

        gridleft.addWidget(self.lineSymbol, 0, 1, 1, -1)
        gridleft.addWidget(self.lineName, 1, 1, 1, -1)
        gridleft.addWidget(self.comboDirection, 2, 1, 1, -1)
        gridleft.addWidget(self.comboOffset, 3, 1, 1, -1)
        gridleft.addWidget(self.checkFixed, 4, 1)
        gridleft.addWidget(self.spinPrice, 4, 2)
        gridleft.addWidget(self.spinVolume, 5, 1, 1, -1)
        gridleft.addWidget(self.comboPriceType, 6, 1, 1, -1)
        gridleft.addWidget(self.comboExchange, 7, 1, 1, -1)
        gridleft.addWidget(self.comboCurrency, 8, 1, 1, -1)
        gridleft.addWidget(self.comboProductClass, 9, 1, 1, -1)
        gridleft.addWidget(self.comboGateway, 10, 1, 1, -1)

        # 右边部分
        labelBid1 = QtWidgets.QLabel(vtText.BID_1)
        labelBid2 = QtWidgets.QLabel(vtText.BID_2)
        labelBid3 = QtWidgets.QLabel(vtText.BID_3)
        labelBid4 = QtWidgets.QLabel(vtText.BID_4)
        labelBid5 = QtWidgets.QLabel(vtText.BID_5)

        labelAsk1 = QtWidgets.QLabel(vtText.ASK_1)
        labelAsk2 = QtWidgets.QLabel(vtText.ASK_2)
        labelAsk3 = QtWidgets.QLabel(vtText.ASK_3)
        labelAsk4 = QtWidgets.QLabel(vtText.ASK_4)
        labelAsk5 = QtWidgets.QLabel(vtText.ASK_5)

        self.labelBidPrice1 = QtWidgets.QLabel()
        self.labelBidPrice2 = QtWidgets.QLabel()
        self.labelBidPrice3 = QtWidgets.QLabel()
        self.labelBidPrice4 = QtWidgets.QLabel()
        self.labelBidPrice5 = QtWidgets.QLabel()
        self.labelBidVolume1 = QtWidgets.QLabel()
        self.labelBidVolume2 = QtWidgets.QLabel()
        self.labelBidVolume3 = QtWidgets.QLabel()
        self.labelBidVolume4 = QtWidgets.QLabel()
        self.labelBidVolume5 = QtWidgets.QLabel()

        self.labelAskPrice1 = QtWidgets.QLabel()
        self.labelAskPrice2 = QtWidgets.QLabel()
        self.labelAskPrice3 = QtWidgets.QLabel()
        self.labelAskPrice4 = QtWidgets.QLabel()
        self.labelAskPrice5 = QtWidgets.QLabel()
        self.labelAskVolume1 = QtWidgets.QLabel()
        self.labelAskVolume2 = QtWidgets.QLabel()
        self.labelAskVolume3 = QtWidgets.QLabel()
        self.labelAskVolume4 = QtWidgets.QLabel()
        self.labelAskVolume5 = QtWidgets.QLabel()

        labelLast = QtWidgets.QLabel(vtText.LAST)
        self.labelLastPrice = QtWidgets.QLabel()
        self.labelReturn = QtWidgets.QLabel()

        self.labelLastPrice.setMinimumWidth(60)
        self.labelReturn.setMinimumWidth(60)

        gridRight = QtWidgets.QGridLayout()
        gridRight.addWidget(labelAsk5, 0, 0)
        gridRight.addWidget(labelAsk4, 1, 0)
        gridRight.addWidget(labelAsk3, 2, 0)
        gridRight.addWidget(labelAsk2, 3, 0)
        gridRight.addWidget(labelAsk1, 4, 0)
        gridRight.addWidget(labelLast, 5, 0)
        gridRight.addWidget(labelBid1, 6, 0)
        gridRight.addWidget(labelBid2, 7, 0)
        gridRight.addWidget(labelBid3, 8, 0)
        gridRight.addWidget(labelBid4, 9, 0)
        gridRight.addWidget(labelBid5, 10, 0)

        gridRight.addWidget(self.labelAskPrice5, 0, 1)
        gridRight.addWidget(self.labelAskPrice4, 1, 1)
        gridRight.addWidget(self.labelAskPrice3, 2, 1)
        gridRight.addWidget(self.labelAskPrice2, 3, 1)
        gridRight.addWidget(self.labelAskPrice1, 4, 1)
        gridRight.addWidget(self.labelLastPrice, 5, 1)
        gridRight.addWidget(self.labelBidPrice1, 6, 1)
        gridRight.addWidget(self.labelBidPrice2, 7, 1)
        gridRight.addWidget(self.labelBidPrice3, 8, 1)
        gridRight.addWidget(self.labelBidPrice4, 9, 1)
        gridRight.addWidget(self.labelBidPrice5, 10, 1)

        gridRight.addWidget(self.labelAskVolume5, 0, 2)
        gridRight.addWidget(self.labelAskVolume4, 1, 2)
        gridRight.addWidget(self.labelAskVolume3, 2, 2)
        gridRight.addWidget(self.labelAskVolume2, 3, 2)
        gridRight.addWidget(self.labelAskVolume1, 4, 2)
        gridRight.addWidget(self.labelReturn, 5, 2)
        gridRight.addWidget(self.labelBidVolume1, 6, 2)
        gridRight.addWidget(self.labelBidVolume2, 7, 2)
        gridRight.addWidget(self.labelBidVolume3, 8, 2)
        gridRight.addWidget(self.labelBidVolume4, 9, 2)
        gridRight.addWidget(self.labelBidVolume5, 10, 2)

        # 发单按钮
        buttonSendOrder = QtWidgets.QPushButton(vtText.SEND_ORDER)
        buttonCancelAll = QtWidgets.QPushButton(vtText.CANCEL_ALL)

        size = buttonSendOrder.sizeHint()
        buttonSendOrder.setMinimumHeight(size.height()*2)   # 把按钮高度设为默认两倍
        buttonCancelAll.setMinimumHeight(size.height()*2)

        # 整合布局
        hbox = QtWidgets.QHBoxLayout()
        hbox.addLayout(gridleft)
        hbox.addLayout(gridRight)

        vbox = QtWidgets.QVBoxLayout()
        vbox.addLayout(hbox)
        vbox.addWidget(buttonSendOrder)
        vbox.addWidget(buttonCancelAll)
        vbox.addStretch()

        self.setLayout(vbox)

        # 关联更新
        buttonSendOrder.clicked.connect(self.sendOrder)
        buttonCancelAll.clicked.connect(self.cancelAll)
        self.lineSymbol.returnPressed.connect(self.updateSymbol)

    #----------------------------------------------------------------------
    def updateSymbol(self):
        """合约变化"""
        # 读取组件数据
        symbol = str(self.lineSymbol.text())
        exchange = self.comboExchange.currentText()
        currency = self.comboCurrency.currentText()
        productClass = self.comboProductClass.currentText()
        gatewayName = self.comboGateway.currentText()

        try:
            # 查询合约
            if exchange:
                vtSymbol = '.'.join([symbol, exchange])
                contract = self.mainEngine.getContract(vtSymbol)
            else:
                vtSymbol = symbol
                contract = self.mainEngine.getContract(symbol)

            if contract:
                vtSymbol = contract.vtSymbol
                if len(gatewayName)==0 and contract.gatewayName is not None and len(contract.gatewayName) > 0:
                    gatewayName = contract.gatewayName
                self.lineName.setText(contract.name)
                exchange = contract.exchange    # 保证有交易所代码

        except Exception as ex:
            print(u'获取合约{}异常:{},{}'.format(symbol,str(ex),traceback.format_exc()),file=sys.stderr)
            return

        # 清空价格数量
        self.spinPrice.setValue(0)
        #self.spinVolume.setValue(0)

        # 清空行情显示
        self.labelBidPrice1.setText('')
        self.labelBidPrice2.setText('')
        self.labelBidPrice3.setText('')
        self.labelBidPrice4.setText('')
        self.labelBidPrice5.setText('')
        self.labelBidVolume1.setText('')
        self.labelBidVolume2.setText('')
        self.labelBidVolume3.setText('')
        self.labelBidVolume4.setText('')
        self.labelBidVolume5.setText('')
        self.labelAskPrice1.setText('')
        self.labelAskPrice2.setText('')
        self.labelAskPrice3.setText('')
        self.labelAskPrice4.setText('')
        self.labelAskPrice5.setText('')
        self.labelAskVolume1.setText('')
        self.labelAskVolume2.setText('')
        self.labelAskVolume3.setText('')
        self.labelAskVolume4.setText('')
        self.labelAskVolume5.setText('')
        self.labelLastPrice.setText('')
        self.labelReturn.setText('')

        # 重新注册事件监听
        if len(self.symbol) > 0:
            self.eventEngine.unregister(EVENT_TICK + self.symbol, self.signal.emit)
        if vtSymbol != self.symbol:
            self.eventEngine.register(EVENT_TICK + vtSymbol, self.signal.emit)

        # 订阅合约
        req = VtSubscribeReq()
        req.symbol = symbol
        req.exchange = exchange
        req.currency = currency
        req.productClass = productClass

        # 默认跟随价
        self.checkFixed.setChecked(False)

        self.mainEngine.subscribe(req, gatewayName)

        # 更新组件当前交易的合约
        self.symbol = vtSymbol

    #----------------------------------------------------------------------
    def updateTick(self, event):
        """更新行情"""
        tick = event.dict_['data']

        if tick.vtSymbol == self.symbol:
            if not self.checkFixed.isChecked():
                if isinstance(tick.lastPrice, float):
                    p = decimal.Decimal(str(tick.lastPrice))
                    decimal_len = abs(p.as_tuple().exponent)
                    if decimal_len != self.spinPrice.decimals():
                        self.spinPrice.setDecimals(decimal_len)
                self.spinPrice.setValue(tick.lastPrice)

                if isinstance(tick.askVolume1,float):
                    p = decimal.Decimal(str(tick.askVolume1))
                    decimal_len = abs(p.as_tuple().exponent)
                    if decimal_len > self.spinVolume.decimals():
                        self.spinVolume.setDecimals(decimal_len)

            self.labelBidPrice1.setText('{}'.format(tick.bidPrice1))
            self.labelAskPrice1.setText('{}'.format(tick.askPrice1))
            self.labelBidVolume1.setText('{}'.format(tick.bidVolume1))
            self.labelAskVolume1.setText('{}'.format(tick.askVolume1))

            if tick.bidPrice2:
                self.labelBidPrice2.setText('{}'.format(tick.bidPrice2))
                self.labelBidPrice3.setText('{}'.format(tick.bidPrice3))
                self.labelBidPrice4.setText('{}'.format(tick.bidPrice4))
                self.labelBidPrice5.setText('{}'.format(tick.bidPrice5))

                self.labelAskPrice2.setText('{}'.format(tick.askPrice2))
                self.labelAskPrice3.setText('{}'.format(tick.askPrice3))
                self.labelAskPrice4.setText('{}'.format(tick.askPrice4))
                self.labelAskPrice5.setText('{}'.format(tick.askPrice5))

                self.labelBidVolume2.setText('{}'.format(tick.bidVolume2))
                self.labelBidVolume3.setText('{}'.format(tick.bidVolume3))
                self.labelBidVolume4.setText('{}'.format(tick.bidVolume4))
                self.labelBidVolume5.setText('{}'.format(tick.bidVolume5))

                self.labelAskVolume2.setText('{}'.format(tick.askVolume2))
                self.labelAskVolume3.setText('{}'.format(tick.askVolume3))
                self.labelAskVolume4.setText('{}'.format(tick.askVolume4))
                self.labelAskVolume5.setText('{}'.format(tick.askVolume5))

            self.labelLastPrice.setText('{}'.format(tick.lastPrice))

            if tick.preClosePrice:
                rt = (tick.lastPrice/tick.preClosePrice)-1
                self.labelReturn.setText(('%.2f' %(rt*100))+'%')
            else:
                self.labelReturn.setText('')

            self.comboExchange.setCurrentText(tick.exchange)

    #----------------------------------------------------------------------
    def connectSignal(self):
        """连接Signal"""
        self.signal.connect(self.updateTick)

    #----------------------------------------------------------------------
    def sendOrder(self):
        """发单"""
        try:
            symbol = str(self.lineSymbol.text())
            vtSymbol = symbol
            exchange = self.comboExchange.currentText()
            currency = self.comboCurrency.currentText()
            productClass = self.comboProductClass.currentText()
            gatewayName = self.comboGateway.currentText()

            # 查询合约
            if exchange:
                vtSymbol = '.'.join([symbol, exchange])
                contract = self.mainEngine.getContract(vtSymbol)
            else:
                vtSymbol = symbol
                contract = self.mainEngine.getContract(symbol)

            if contract:
                if not gatewayName:
                    gatewayName = contract.gatewayName
                exchange = contract.exchange    # 保证有交易所代码

            if gatewayName not in self.mainEngine.connected_gw_names:
                if len(self.mainEngine.connected_gw_names) == 1:
                    gatewayName = self.mainEngine.connected_gw_names[0]
                else:
                    self.mainEngine.writeError(u'没有连接网关:{}'.format(gatewayName))
                    return

            req = VtOrderReq()
            req.symbol = symbol
            req.vtSymbol = vtSymbol
            req.exchange = exchange
            req.price = self.spinPrice.value()
            req.volume = self.spinVolume.value()
            req.direction = self.comboDirection.currentText()
            req.priceType = self.comboPriceType.currentText()
            req.offset = self.comboOffset.currentText()
            req.currency = currency
            req.productClass = productClass

            self.mainEngine.sendOrder(req, gatewayName)
        except Exception as ex:
            self.mainEngine.writeError(
                u'tradingWg.sendOrder exception:{},{}'.format(str(ex), traceback.format_exc()))

    def canelOrder(self):
        """撤单"""
        orderRef = str(self.lineOrder.text())

        l = self.mainEngine.getAllWorkingOrders()
        for order in l:
            if order.orderID == orderRef:
                req = VtCancelOrderReq()
                req.symbol = order.symbol
                req.exchange = order.exchange
                req.frontID = order.frontID
                req.sessionID = order.sessionID
                req.orderID = order.orderID
                self.mainEngine.cancelOrder(req, order.gatewayName)


    # ----------------------------------------------------------------------
    def cancelAll(self):
        """一键撤销所有委托"""
        l = self.mainEngine.getAllWorkingOrders()
        for order in l:
            req = VtCancelOrderReq()
            req.symbol = order.symbol
            req.exchange = order.exchange
            req.frontID = order.frontID
            req.sessionID = order.sessionID
            req.orderID = order.orderID
            self.mainEngine.cancelOrder(req, order.gatewayName)

    #----------------------------------------------------------------------
    def closePosition(self, cell):
        """根据持仓信息自动填写交易组件"""
        try:
            # 读取持仓数据，cell是一个表格中的单元格对象
            pos = cell.data
            symbol = pos.symbol

            # 拆分 合约.交易所接口
            symbol_split_list = symbol.split('.')

            if len(symbol_split_list)==2:
                # 交易所
                exchange_name = symbol_split_list[-1]

                # 数字货币类交易所
                if exchange_name in [EXCHANGE_OKEX,EXCHANGE_BINANCE,EXCHANGE_HUOBI,EXCHANGE_GATEIO]:
                    symbol_pair_list = symbol.split('_')
                    if len(symbol_pair_list) ==1:
                        # 获取合约
                        if symbol.lower() == 'usdt':
                            return
                        symbol = symbol_pair_list[0] + '_' + 'usdt'+'.'+symbol_split_list[-1]
            # 更新交易组件的显示合约
            self.lineSymbol.setText(symbol)
            self.updateSymbol()

            # 自动填写信息
            self.comboPriceType.setCurrentIndex(self.priceTypeList.index(PRICETYPE_LIMITPRICE))
            self.comboOffset.setCurrentIndex(self.offsetList.index(OFFSET_CLOSE))
            if isinstance(pos.position, float):
                p = decimal.Decimal(str(pos.position))
                decimal_len = abs(p.as_tuple().exponent)
                if decimal_len > self.spinVolume.decimals():
                    self.spinVolume.setDecimals(decimal_len)
            elif isinstance(pos.position, int):
                self.spinVolume.setDecimals(0)

            self.spinVolume.setValue(pos.position)

            if pos.direction == DIRECTION_LONG or pos.direction == DIRECTION_NET:
                self.comboDirection.setCurrentIndex(self.directionList.index(DIRECTION_SHORT))
            else:
                self.comboDirection.setCurrentIndex(self.directionList.index(DIRECTION_LONG))
        except Exception as ex:
            self.mainEngine.writeError(u'tradingWg.closePosition exception:{},{}'.format(str(ex),traceback.format_exc()))
        # 价格留待更新后由用户输入，防止有误操作

    # ----------------------------------------------------------------------

    def autoFillSymbol(self, cell):
        """根据行情信息自动填写交易组件"""
        try:
            # 读取行情数据，cell是一个表格中的单元格对象
            tick = cell.data
            if tick is None:
                return

            if tick.vtSymbol:

                # 更新交易组件的显示合约
                if '.' in tick.vtSymbol:
                    symbol_pairs = tick.vtSymbol.split('.')
                    if symbol_pairs[-1] != 'SPD':
                        self.lineSymbol.setText(symbol_pairs[0])
                        self.comboExchange.setCurrentText(symbol_pairs[-1])
                else:
                    self.lineSymbol.setText(tick.vtSymbol)
                self.updateSymbol()

            # 自动填写信息
            if tick.gatewayName:
                self.comboGateway.setCurrentIndex(self.gatewayList.index(tick.gatewayName))

            self.spinVolume.setValue(1)

        except Exception as ex:
            self.mainEngine.writeError(u'tradingWg.autoFillSymbol exception:{}'.format(str(ex)))

########################################################################
class ContractMonitor(BasicMonitor):
    """合约查询"""

    #----------------------------------------------------------------------
    def __init__(self, mainEngine, parent=None):
        """Constructor"""
        super(ContractMonitor, self).__init__(parent=parent)

        self.mainEngine = mainEngine

        d = OrderedDict()
        d['symbol'] = {'chinese':vtText.CONTRACT_SYMBOL, 'cellType':BasicCell}
        d['exchange'] = {'chinese':vtText.EXCHANGE, 'cellType':BasicCell}
        d['vtSymbol'] = {'chinese':vtText.VT_SYMBOL, 'cellType':BasicCell}
        d['name'] = {'chinese':vtText.CONTRACT_NAME, 'cellType':BasicCell}
        d['productClass'] = {'chinese':vtText.PRODUCT_CLASS, 'cellType':BasicCell}
        d['size'] = {'chinese':vtText.CONTRACT_SIZE, 'cellType':BasicCell}
        d['priceTick'] = {'chinese':vtText.PRICE_TICK, 'cellType':BasicCell}
        d['strikePrice'] = {'chinese':vtText.STRIKE_PRICE, 'cellType':BasicCell}
        d['underlyingSymbol'] = {'chinese':vtText.UNDERLYING_SYMBOL, 'cellType':BasicCell}
        d['optionType'] = {'chinese':vtText.OPTION_TYPE, 'cellType':BasicCell}
        self.setHeaderDict(d)

        # 过滤显示用的字符串
        self.filterContent = EMPTY_STRING

        self.initUi()

    #----------------------------------------------------------------------
    def initUi(self):
        """初始化界面"""
        self.setWindowTitle(u'合约查询')
        self.setMinimumSize(800, 800)
        self.setFont(BASIC_FONT)
        self.initTable()
        self.addMenuAction()

    #----------------------------------------------------------------------
    def showAllContracts(self):
        """显示所有合约数据"""
        l = self.mainEngine.getAllContracts()
        d = {'.'.join([contract.exchange, contract.symbol]):contract for contract in l}
        l2 = d.keys()
        #l2.sort(reverse=True)
        l2 = sorted(l2,reverse=True)
        self.setRowCount(len(l2))
        row = 0

        for key in l2:
            # 如果设置了过滤信息且合约代码中不含过滤信息，则不显示
            if self.filterContent and self.filterContent not in key:
                continue

            contract = d[key]

            for n, header in enumerate(self.headerList):
                content = safeUnicode(contract.__getattribute__(header))
                cellType = self.headerDict[header]['cellType']
                cell = cellType(content)

                if self.font:
                    cell.setFont(self.font)  # 如果设置了特殊字体，则进行单元格设置

                self.setItem(row, n, cell)

            row = row + 1

    #----------------------------------------------------------------------
    def refresh(self):
        """刷新"""
        self.menu.close()   # 关闭菜单
        self.clearContents()
        self.setRowCount(0)
        self.showAllContracts()

    #----------------------------------------------------------------------
    def addMenuAction(self):
        """增加右键菜单内容"""
        refreshAction = QtWidgets.QAction(vtText.REFRESH, self)
        refreshAction.triggered.connect(self.refresh)

        self.menu.addAction(refreshAction)

    #----------------------------------------------------------------------
    def show(self):
        """显示"""
        super(ContractMonitor, self).show()
        self.refresh()

    #----------------------------------------------------------------------
    def setFilterContent(self, content):
        """设置过滤字符串"""
        self.filterContent = content


########################################################################
class ContractManager(QtWidgets.QWidget):
    """合约管理组件"""

    #----------------------------------------------------------------------
    def __init__(self, mainEngine, parent=None):
        """Constructor"""
        super(ContractManager, self).__init__(parent=parent)

        self.mainEngine = mainEngine

        self.initUi()

    #----------------------------------------------------------------------
    def initUi(self):
        """初始化界面"""
        self.setWindowTitle(vtText.CONTRACT_SEARCH)

        self.lineFilter = QtWidgets.QLineEdit()
        self.buttonFilter = QtWidgets.QPushButton(vtText.SEARCH)
        self.buttonFilter.clicked.connect(self.filterContract)
        self.monitor = ContractMonitor(self.mainEngine)
        self.monitor.refresh()

        hbox = QtWidgets.QHBoxLayout()
        hbox.addWidget(self.lineFilter)
        hbox.addWidget(self.buttonFilter)
        hbox.addStretch()

        vbox = QtWidgets.QVBoxLayout()
        vbox.addLayout(hbox)
        vbox.addWidget(self.monitor)

        self.setLayout(vbox)

    #----------------------------------------------------------------------
    def filterContract(self):
        """显示过滤后的合约"""
        content = str(self.lineFilter.text())
        self.monitor.setFilterContent(content)
        self.monitor.refresh()

########################################################################
class WorkingOrderMonitor(OrderMonitor):
    """活动委托监控"""
    STATUS_COMPLETED = [STATUS_ALLTRADED, STATUS_CANCELLED, STATUS_REJECTED]

    # ----------------------------------------------------------------------
    def __init__(self, mainEngine, eventEngine, parent=None):
        """Constructor"""
        super(WorkingOrderMonitor, self).__init__(mainEngine, eventEngine, parent)

    # ----------------------------------------------------------------------
    def updateData(self, data):
        """更新数据"""
        super(WorkingOrderMonitor, self).updateData(data)

        # 如果该委托已完成，则隐藏该行
        if data.status in self.STATUS_COMPLETED:
            if isinstance(self.dataKey, list):
                # 多个key，逐一组合
                key = '_'.join([getattr(data, item, '') for item in self.dataKey])
            else:
                # 单个key
                key = getattr(data, self.dataKey, None)
            if key is not None:
                cellDict = self.dataDict.get(key)
                if cellDict is not None:
                    cell = cellDict['status']
                    row = self.row(cell)
                    self.hideRow(row)


########################################################################
class SettingEditor(QtWidgets.QWidget):
    """配置编辑器"""

    # ----------------------------------------------------------------------
    def __init__(self, mainEngine, parent=None):
        """Constructor"""
        super(SettingEditor, self).__init__(parent)

        self.mainEngine = mainEngine
        self.currentFileName = ''

        self.initUi()

    # ----------------------------------------------------------------------
    def initUi(self):
        """初始化界面"""
        self.setWindowTitle(vtText.EDIT_SETTING)

        self.comboFileName = QtWidgets.QComboBox()
        self.comboFileName.addItems(jsonPathDict.keys())

        buttonLoad = QtWidgets.QPushButton(vtText.LOAD)
        buttonSave = QtWidgets.QPushButton(vtText.SAVE)
        buttonLoad.clicked.connect(self.loadSetting)
        buttonSave.clicked.connect(self.saveSetting)

        self.editSetting = QtWidgets.QTextEdit()
        self.labelPath = QtWidgets.QLabel()

        hbox = QtWidgets.QHBoxLayout()
        hbox.addWidget(self.comboFileName)
        hbox.addWidget(buttonLoad)
        hbox.addWidget(buttonSave)
        hbox.addStretch()

        vbox = QtWidgets.QVBoxLayout()
        vbox.addLayout(hbox)
        vbox.addWidget(self.editSetting)
        vbox.addWidget(self.labelPath)

        self.setLayout(vbox)

    # ----------------------------------------------------------------------
    def loadSetting(self):
        """加载配置"""
        self.currentFileName = str(self.comboFileName.currentText())
        filePath = jsonPathDict[self.currentFileName]
        self.labelPath.setText(filePath)

        with open(filePath,'r',encoding='utf8') as f:
            self.editSetting.clear()

            for line in f:
                line = line.replace('\n', '')  # 移除换行符号
                #line = line.decode('UTF-8')
                self.editSetting.append(line)

    # ----------------------------------------------------------------------
    def saveSetting(self):
        """保存配置"""
        if not self.currentFileName:
            return

        filePath = jsonPathDict[self.currentFileName]

        with open(filePath, 'w', encoding='utf8') as f:
            content = self.editSetting.toPlainText()
            #content = content.encode('UTF-8')
            f.write(content)

    # ----------------------------------------------------------------------
    def show(self):
        """显示"""
        # 更新配置文件下拉框
        self.comboFileName.clear()
        self.comboFileName.addItems(jsonPathDict.keys())

        # 显示界面
        super(SettingEditor, self).show()



