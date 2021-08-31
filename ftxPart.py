from websockets import connect
import time
import hmac
import zlib
from json import dumps, loads
from decimal import Decimal as Dl
from itertools import zip_longest
import asyncio
from collections import defaultdict
from typing import DefaultDict, Dict


class FTX:
    ftx_url = 'https://ftx.com'
    _subscriptions = False
    orderbook_ftx = None
    _ftx_secret = None
    _ftx_key = None

    def __init__(self):
        self._orderbooks: Dict[str, DefaultDict[float, float]] = {side: defaultdict(float) for side in {'bids', 'asks'}}

    async def _make_conn_ftx(self):
        self._connFTX = await connect('wss://ftx.com/ws/', ping_interval=None)
        ts, sign = self._make_sign_webSock(secret=self._ftx_secret)
        message = {'op': 'login', 'args': {'key': self._ftx_key, 'sign': sign, 'time': ts}}
        await self._connFTX.send(dumps(message))
        if not self._subscriptions:
            await self._subscribe()

    async def _subscribe(self):
        await self._connFTX.send(dumps({'op': 'subscribe', 'channel': 'orderbook', 'market': '1INCH/USD'}))
        self._subscriptions = True

    async def _unsubscribe(self) -> None:
        await self._connFTX.send(dumps({'op': 'unsubscribe', 'channel': 'orderbook', 'market': '1INCH/USD'}))
        self._subscriptions = False

    def _make_sign_webSock(self, secret):
        ts = int(time.time() * 1000)
        sign = hmac.new(secret.encode(), f'{ts}websocket_login'.encode(), 'sha256').hexdigest()
        return ts, sign

    async def _get_recv_ftx(self):
        self.t_ftx = time.time()
        resp = loads(await self._connFTX.recv())
        self.t_resp_ftx = time.time()

        self._disributor_ftx(resp)
        if resp.get('data', {'time': time.time()})['time'] - self.t_ftx >= 15.0:
            await self._connFTX.send(dumps({'op': 'ping'}))
            self.t_ftx = resp['data']['time']

    def _disributor_ftx(self, resp):
        avg_bid = 0
        avg_ask = 0
        self._handle_orderbook_message(resp)
        if self.orderbook_ftx:
            print(self.orderbook_ftx['bids'][0])
            for i in self.orderbook_ftx['bids'][:3]:
                avg_bid += i[0]
            else:
                avg_bid /= 3
            for i in self.orderbook_ftx['asks'][:3]:
                avg_ask += i[0]
            else:
                avg_ask /= 3

            self.iTftx = {'bids': [Dl(avg_bid), Dl(self.orderbook_ftx['bids'][0][1])],
                          'asks': [Dl(avg_ask), Dl(self.orderbook_ftx['asks'][0][1])]}

    def _reset_orderbook(self) -> None:
        if self._orderbooks.get('bids'):
            del self._orderbooks['bids']
        if self._orderbooks.get('asks'):
            del self._orderbooks['asks']

    def _get_orderbook(self):
        return {
            side: sorted(
                [(price, quantity) for price, quantity in list(self._orderbooks[side].items())
                 if quantity],
                key=lambda order: order[0] * (-1 if side == 'bids' else 1)
            )
            for side in {'bids', 'asks'}
        }

    def _handle_orderbook_message(self, message: Dict) -> None:
        data = message.get('data')
        if data:
            if data['action'] == 'partial':
                self._reset_orderbook()

            for side in {'bids', 'asks'}:
                book = self._orderbooks[side]
                for price, size in data[side]:
                    if size:
                        book[price] = size
                    else:
                        del book[price]
            checksum = data['checksum']
            self.orderbook_ftx = self._get_orderbook()
            checksum_data = [
                ':'.join([f'{float(order[0])}:{float(order[1])}' for order in (bid, offer) if order])
                for (bid, offer) in zip_longest(self.orderbook_ftx['bids'][:100], self.orderbook_ftx['asks'][:100])
            ]

            computed_result = int(zlib.crc32(':'.join(checksum_data).encode()))
            if computed_result != checksum:
                print('несовпадение сумм')
                del self.orderbook_ftx
                self._reset_orderbook()
                self._unsubscribe()
                self._subscribe()

    async def sign_req_ftx(self, method, endpoint, SS=None):
        global params
        if SS:
            side, size = SS
            params = {
                'market': '1INCH/USD',
                'side': side,
                'price': None,
                'size': size,
                "type": "market",
                'reduceOnly': False,
                'ioc': False,
                'postOnly': False,
                'clientId': None

            }
            ts, sign = self._make_sign_rest(method, endpoint, params)

        else:
            ts, sign = self._make_sign_rest(method, endpoint)

        headers = {
            'FTX-KEY': self._ftx_key,
            'FTX-SIGN': sign,
            'FTX-TS': str(ts)
        }
        request = self._dispatch_req_ftx(method)
        if SS:
            headers['Content-Type'] = 'application/json'
            r = await request(FTX.ftx_url + endpoint, headers=headers, data=dumps(params))
        else:
            r = await request(FTX.ftx_url + endpoint, headers=headers)

        r = await r.json()
        if r.get('success') != True and method == 'POST':
            print(r)
        return r

    def _make_sign_rest(self, method, endpoint, params = None):
        ts = int(time.time() * 1000)
        if method == 'GET':
            signature_payload = f'{ts}{method}{endpoint}'.encode()
            sign = hmac.new(self._ftx_secret.encode(), signature_payload, 'sha256').hexdigest()
            return ts, sign
        if method == 'POST':
            signature_payload = f'{ts}{method}{endpoint}{dumps(params)}'.encode()
            sign = hmac.new(self._ftx_secret.encode(), signature_payload, 'sha256').hexdigest()
            return ts, sign

    def _dispatch_req_ftx(self, method):
        session = self.session
        return {
            'GET': session.get,
            'POST': session.post
        }.get(method)

    async def _get_balances_ftx(self):
        r = await self.sign_req_ftx('GET', '/api/wallet/balances')
        self.ftx_balance = {}
        for i in r['result']:
            if i['coin'] == '1INCH':
                self.ftx_balance['1INCH'] = Dl(i['free'])
            if i['coin'] == 'USD':
                self.ftx_balance['USD'] = Dl(i['free'])



class test(FTX):
    async def make_conn(self):
        await self._make_conn_ftx()

    async def get_rec(self):
        await self._get_recv_ftx()


async def sestdef():
    a = test()
    await a.make_conn()
    while True:
        await a.get_rec()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(sestdef())
