import asyncio  # import get_event_loop
import time
from decimal import Decimal as Dl
from math import floor

import aiohttp
from aiofile import AIOFile

from binancePart import Bin
from ftxPart import FTX

'''окей сейчас логику приложения я вижу такой каждый заход я сравниваю что больше продажа на одной бирже 
или на другой в зависимости от результата вызываю функцию  проверки рентабельности она уже смотрит 
на соответствие всем требованиям сделки (наличие баланса, минимальной стоимости сделки, доступности на рынке)
и если все ок и сделка рентабельна то вызывается функция с хардкодными аргументами'''


class Rel(FTX, Bin):
    _connFTX = None
    _conn_bin = None

    def __init__(self, ftx_key, ftx_secret, bin_key, bin_secret):
        self.session = aiohttp.ClientSession()
        self.rest_bin_t = [time.time(), time.time()]
        self.ftx_balance = None  # {'1INCH': dec(1.22)}
        self.bin_balance = None  # {'1INCH': dec(1.22)}}
        self.iTbin = None  # {'bids': [b, B], 'asks': [a, A]} price/amount
        self.iTftx = None  # {'bids': [b, B], 'asks':[a, A]}
        self._ftx_key = ftx_key
        self._ftx_secret = ftx_secret
        self._bin_key = bin_key
        self._bin_secret = bin_secret

        FTX.__init__(self)

    async def find_balances(self):
        await self._get_balances_ftx()
        await self._get_balances_bin()

    async def make_conns(self):
        await self._make_conn_bin()
        await self._make_conn_ftx()

    async def get_recvs(self):

        t1 = asyncio.create_task(self._get_recv_bin())
        t2 = asyncio.create_task(self._get_recv_ftx())
        await asyncio.gather(t1, t2)

    def _eq_resp_time(self):
        diff = self.t_resp_bin - self.t_resp_ftx
        if abs(diff) < 0.1:
            return True

    async def is_relevant_bin_sell(self):
        sell_price, amount_2_sell = self.iTbin['bids']
        buy_price, amount_2_buy = self.iTftx['asks']

        percent_dif = sell_price / buy_price - 1

        if percent_dif > 0.002:  # ок
            our_amount = self._determ_amount(amount_2_buy, amount_2_sell, 'bin')  # ok
            if our_amount and self.check_weight() and self._eq_resp_time():
                await self._sell_and_buy(
                    ('POST', '/api/v3/order', 'SELL', our_amount),
                    ('POST', '/api/orders', 'buy', our_amount)
                )
                await self.find_balances()
                await self._write_log(our_amount, 'Binance')
                print(f'Вот сейчас продам {our_amount} на бинансе {time.ctime()}')
                await self._write_log(our_amount, 'Binance')

    async def is_relevant_ftx_sell(self):
        sell_price, amount_2_sell = self.iTftx['bids']
        buy_price, amount_2_buy = self.iTbin['asks']

        if sell_price / buy_price - 1 > 0.002:
            our_amount = self._determ_amount(amount_2_buy, amount_2_sell, 'ftx')
            if our_amount and self.check_weight() and self._eq_resp_time():
                await self._sell_and_buy(
                    ('POST', '/api/v3/order', 'BUY', our_amount),
                    ('POST', '/api/orders', 'sell', our_amount)
                )
                await self.find_balances()
                await self._write_log(our_amount, 'FTX')
                print(f'Вот сейчас продам {our_amount} на FTX {time.ctime()}')
                await self._write_log(our_amount, 'FTX')

    async def _sell_and_buy(self, binn, ftx):
        method_b, path_b, side_b, size_b = binn
        method_f, path_f, side_f, size_f = ftx
        t1 = asyncio.create_task(self.sign_req_bin(method_b, path_b, (side_b, size_b)))
        t2 = asyncio.create_task(self.sign_req_ftx(method_f, path_f, (side_f, size_f)))
        await asyncio.gather(t1, t2)

    def _determ_amount(self, amount_2_buy, amount_2_sell, market):

        how_much_i_sell = Dl(min(amount_2_buy, amount_2_sell))

        if market == 'bin':
            if self.bin_balance['1INCH'] < amount_2_sell:  # хватает ли вообще у меня столько инчей на балансе
                how_much_i_sell = Dl(self._precision(self.bin_balance['1INCH'], '1INCH'))
            if how_much_i_sell * self.iTftx['asks'][0] > self.ftx_balance['USD']:  # хватит ли на фтх долларов
                how_much_i_sell = self._precision(self.ftx_balance['USD'] / self.iTftx['asks'][0] * Dl('0.9'), '1INCH')
        if market == 'ftx':
            if self.ftx_balance['1INCH'] < amount_2_sell:  # хватает ли вообще у меня столько инчей на балансе
                how_much_i_sell = Dl(self._precision(self.ftx_balance['1INCH'], '1INCH'))
            if how_much_i_sell * self.iTbin['asks'][0] > self.bin_balance['BUSD']:
                how_much_i_sell = self._precision(self.bin_balance['BUSD'] / self.iTbin['asks'][0] * Dl('0.9'), '1INCH')
        if how_much_i_sell > 5:  # просто ограничитель размера
            how_much_i_sell = Dl('5')

        if Dl(how_much_i_sell) * min(self.iTbin['bids'][0], self.iTftx['bids'][0]) < 10:
            '''проверка на минимальную сделку'''
            how_much_i_sell = None

        return self._precision(how_much_i_sell, '1INCH')

    def _precision(self, n: Dl, symbol: str) -> float:
        try:
            if symbol == '1INCH':
                return floor(n * 100) / 100
        except:
            return None

    async def init_logg(self):
        self.file = await AIOFile('logg.txt', 'a')
        await self.file.write(f'Баланс\n {self.ftx_balance} - FTX\n{self.bin_balance} - Biance\n')

    async def _write_log(self, our_amount, mrkt):  # mrkt - это где продаем

        '''вызывается из функций релевантности'''

        await self.file.write(f'------------\nПродаем {our_amount} на {mrkt} {time.ctime()}\n')
        if mrkt == 'Binance':
            await self.file.write(
                f"Выручка до комиссии составляет {self.iTbin['bids'][0] / self.iTftx['asks'][0] * Dl(our_amount)} 1INCH \
после комисси: {self.iTbin['bids'][0] / self.iTftx['asks'][0]}\n")
        else:
            await self.file.write(
                f"Выручка до комиссии составляет {self.iTftx['bids'][0] / self.iTbin['asks'][0] * Dl(our_amount)} 1INCH {self.iTftx['bids'][0] / self.iTbin['asks'][0]}\n")
        await self.file.write(f'Котировки:\n {self.iTbin} - Binance \n{self.iTftx} - FTX\n')
        await self.file.write(f'Баланс после сделки:\n {self.ftx_balance} - FTX\n{self.bin_balance} - Biance\n')
        await self.file.write('------------------------')



if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
