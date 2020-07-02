from typing import List, Dict, Union,Tuple
from vnpy.trader.constant import Interval
from vnpy.app.portfolio_strategy import StrategyTemplate, StrategyEngine
from vnpy.trader.utility import BarGenerator, ArrayManager
from vnpy.trader.object import TickData, BarData
from vnpy.app.cta_strategy import (
    StopOrder,
    TickData,
    BarData,
    TradeData,
    OrderData,
    BarGenerator,
    ArrayManager,
    SpreadArrayManager,
    CtaSignal,
    TargetPosTemplate
)
import numpy as np
import talib

class ResidualModelStrategy(StrategyTemplate):
    """"""

    author = "yiran"

    x_symbol: str = None
    y_symbol: str = None



    x_multiplier: float = 0
    y_multiplier: float = 1
    intercept: float = 0

    short_entry_multiplier: float = 3
    short_exit_multiplier: float = 0

    long_entry_multiplier: float = -3
    long_exit_multiplier: float = 0

    std_window = 20
    mean_window = 10
    fixed_size = 1

    spread_volume_threshold = 50

    x_fixed_size: float = None
    y_fixed_size: float = None

    spread_value: float = 0
    # 用来过滤交易量低的情况
    spread_volume: float = 0
    spread_long_entry: float = 0
    spread_long_exit: float = 0
    spread_short_entry: float = 0
    spread_volume_filter: bool = False

    open_direction_dict: Dict[str, float] = {}
    close_direction_dict: Dict[str, float] = {}
    intra_trade_low = 0



    parameters = [
        "x_multiplier",
        "y_multiplier",
        'short_entry_multiplier',
        "short_exit_multiplier",
        "long_entry_multiplier",
        "long_exit_multiplier",
        "fixed_size",
        "std_window",
        "mean_window"
    ]
    variables = ["spread_value","spread_long_entry","spread_short_entry","spread_volume_filter"]

    def __init__(
        self,
        strategy_engine: StrategyEngine,
        strategy_name: str,
        vt_symbols: List[str],
        setting: dict
    ):
        """"""
        super().__init__(strategy_engine, strategy_name, vt_symbols, setting)

        # self.y_symbol = (self.vt_symbols[0].split('.'))[0]
        # self.x_symbol = (self.vt_symbols[1].split('.'))[1]
        self.y_symbol = self.vt_symbols[0]
        self.x_symbol = self.vt_symbols[1]


        self.x_fixed_size = int(np.abs(self.fixed_size * self.x_multiplier))
        self.y_fixed_size = int(np.abs(self.fixed_size * self.y_multiplier))

        self.open_direction_dict['x_symbol'] = 0
        self.open_direction_dict['y_symbol'] = 0

        self.close_direction_dict['x_symbol'] = 0
        self.close_direction_dict['y_symbol'] = 0




        self.sam = SpreadArrayManager()



    def on_init(self):
        """
        Callback when strategy is inited.
        """
        self.write_log("策略初始化")

        self.load_bars(10)

    def on_start(self):
        """
        Callback when strategy is started.
        """
        self.write_log("策略启动")

    def on_stop(self):
        """
        Callback when strategy is stopped.
        """
        self.write_log("策略停止")


    def on_bars(self, bars: Dict[str, BarData]):
        """"""
        self.cancel_all()


        # 计算价差
        # 将价差放入sam 进行后续技术指标计算
        self.spread_value = self.y_multiplier*(bars[self.y_symbol].close_price) - self.x_multiplier*(bars[self.x_symbol].close_price) - self.intercept
        self.spread_volume = min(bars[self.y_symbol].volume, bars[self.x_symbol].volume)
        self.sam.update_spread(self.spread_value, self.spread_volume)

        # 成交量过滤，成交量低于指定阈值将不会进行操作
        if self.spread_volume < self.spread_volume_threshold:
            self.spread_volume_filter = False
        else:
            self.spread_volume_filter = True

        if not self.sam.inited:
            return

        # 计算技术指标
        sam = self.sam
        std = sam.std(self.std_window)
        mean = sam.sma(self.mean_window)


        # 计算入场和出场价位
        self.spread_long_entry = mean + self.long_entry_multiplier * std
        self.spread_long_exit = mean + self.long_exit_multiplier * std

        self.spread_short_entry = mean + self.short_entry_multiplier * std
        self.spread_short_exit = mean + self.short_exit_multiplier * std

        # 获取每个品种持仓
        x_pos = self.get_pos(self.x_symbol)
        y_pos = self.get_pos(self.y_symbol)


        # 平仓逻辑判断(平仓之后,在当前bar中不会再开仓),通过判断open_direction的方向来判断是做多还是做空价差
        if self.open_direction_dict['y_symbol'] == 1 and self.open_direction_dict['x_symbol'] == -1:
            # 做多价差平仓,不进行成交量过滤;
            if self.spread_value >= self.spread_long_exit:
                self.sell(self.y_symbol, bars[self.y_symbol].close_price*0.95, np.abs(y_pos))
                self.cover(self.x_symbol,bars[self.x_symbol].close_price*1.05, np.abs(x_pos))

                self.open_direction_dict['y_symbol'] = 0
                self.open_direction_dict['x_symbol'] = 0

                self.close_direction_dict['y_symbol'] = -1
                self.close_direction_dict['x_symbol'] = 1
                print(f'时间{bars[self.y_symbol].datetime}','做多价差平仓',f'平多{self.y_symbol} {self.y_fixed_size} 手 平空{self.x_symbol} {self.x_fixed_size} 手')
                return

        elif self.open_direction_dict['y_symbol'] == -1 and self.open_direction_dict['x_symbol'] == 1:
            # 做空价差平仓,不进行成交量过滤;
            if self.spread_value <= self.spread_long_exit:
                self.cover(self.y_symbol, bars[self.y_symbol].close_price*1.05, np.abs(y_pos))
                self.sell(self.x_symbol,bars[self.x_symbol].close_price*0.95, np.abs(x_pos))

                self.open_direction_dict['y_symbol'] = 0
                self.open_direction_dict['x_symbol'] = 0

                self.close_direction_dict['y_symbol'] = 1
                self.close_direction_dict['x_symbol'] = -1
                print(f'时间{bars[self.y_symbol].datetime}','做空价差平仓',f'平空{self.y_symbol} {self.y_fixed_size} 手 平多{self.x_symbol} {self.x_fixed_size} 手')
                return


        # 针对两种情况1.可能出现某一个leg没有买满的情况 2. 可能出现某一个leg仓位没有平掉的情况
        # 没有考虑： 多买的情况；似乎不可能出现
        # 这种情况下，如果有其它买入信号，不会去执行相应买入动作
        if (x_pos != 0 or y_pos != 0):
            symbols = ['y_symbol', 'x_symbol']
            vt_symbol_dict = {'y_symbol':self.y_symbol, 'x_symbol':self.x_symbol}
            pos_dict = {'y_symbol':y_pos,'x_symbol':x_pos}
            fixed_size_dict = {'y_symbol':self.y_fixed_size, 'x_symbol':self.x_fixed_size}
            bar_dict = {'y_symbol': bars[self.y_symbol].close_price,'x_symbol': bars[self.x_symbol].close_price}
            for symbol in symbols:
                # direction = self.open_direction_dict[symbol]
                diff = int(np.abs(pos_dict[symbol]-fixed_size_dict[symbol]))
                # 如果处于平仓状态：对没有平掉的仓位，进行平仓
                if self.open_direction_dict[symbol] == 0:
                    if self.close_direction_dict[symbol] == -1:
                        self.sell(vt_symbol_dict[symbol], bar_dict[symbol]*0.95, np.abs(pos_dict[symbol]))
                    elif self.close_direction_dict[symbol] == -1:
                        self.cover(vt_symbol_dict[symbol], bar_dict[symbol]*1.05, np.abs(pos_dict[symbol]))

                # 如果是处于持仓状态，对没有买到指定数量的品种，进行补仓
                if self.open_direction_dict[symbol] != 0 and diff >= 1:

                    if self.open_direction_dict[symbol] == 1:
                        self.buy(vt_symbol_dict[symbol], bar_dict[symbol]*1.01, diff)

                    elif self.open_direction_dict[symbol] == -1:
                        self.short(vt_symbol_dict[symbol], bar_dict[symbol]*0.99, diff)


        # 开仓逻辑判断，只有两个品种都是空仓的时候才会进行开仓
        if x_pos == 0 and y_pos == 0:
            # 做多价差开仓，加入对成交量过滤；
            if self.spread_value <= self.spread_long_entry and self.spread_volume_filter:
                self.buy(self.y_symbol, bars[self.y_symbol].close_price*1.01, self.y_fixed_size)
                self.short(self.x_symbol,bars[self.x_symbol].close_price*0.99, self.x_fixed_size)

                self.open_direction_dict['y_symbol'] = 1
                self.open_direction_dict['x_symbol'] = -1

                self.close_direction_dict['y_symbol'] = 0
                self.close_direction_dict['x_symbol'] = 0
                print(f'时间{bars[self.y_symbol].datetime}','做多价差开仓',f'做多{self.y_symbol} {self.y_fixed_size} 手 做空{self.x_symbol} {self.x_fixed_size} 手')

            # 做空价差开仓，加入对成交量过滤；
            elif self.spread_value >= self.spread_short_entry and self.spread_volume_filter:
                self.short(self.y_symbol, bars[self.y_symbol].close_price*0.99, self.y_fixed_size)
                self.buy(self.x_symbol,bars[self.x_symbol].close_price*1.01, self.x_fixed_size)

                self.open_direction_dict['y_symbol'] = -1
                self.open_direction_dict['x_symbol'] = 1

                self.close_direction_dict['y_symbol'] = 0
                self.close_direction_dict['x_symbol'] = 0
                print(f'时间{bars[self.y_symbol].datetime}','做空价差开仓',f'做空{self.y_symbol} {self.y_fixed_size} 手 做多{self.x_symbol} {self.x_fixed_size} 手')