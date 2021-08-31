import asyncio
import hashlib
import hmac
import time
from decimal import Decimal as Dl
from json import dumps, loads
from urllib.parse import urlencode

from websockets import connect


class Bin:
    __Base_url = 'https://api.binance.com'
    headers = {
        'Content-Type': 'application/json;charset=utf-8',
        'X-MBX-APIKEY': 'vYEVlyheb7k7lq5etPqAX9dNFuopeVHcMuhG2AtSu2olK6jCDsf9v09ireNdMXak'}
    lastUpdateId = 0
    rest_bin_t = []

    async def _make_conn_bin(self):
        url = 'wss://stream.binance.com:9443/ws'
        self._conn_bin = await connect(url, ping_interval=None)
        data = {
            "method": "SUBSCRIBE",
            "params":
                [
                    "1inchbusd@depth5@100ms",
                ],
            "id": 1}
        await self._conn_bin.send(dumps(data))

    async def _get_recv_bin(self):
        self._t_bin = time.time()
        resp = loads(await self._conn_bin.recv())
        self.t_resp_bin = time.time()

        self._distributor_bin(resp)

        if time.time() - self._t_bin >= 180.0:
            self._t_bin = time.time()
            await self._conn_bin.pong()

    def _distributor_bin(self, resp):
        if resp.get('lastUpdateId'):
            if resp.get('lastUpdateId') > self.lastUpdateId:
                self.lastUpdateId = resp['lastUpdateId']

                B = Dl(resp['bids'][0][1])
                A = Dl(resp['asks'][0][1])
                summ3 = 0
                summ_amount = 0
                for i in resp['bids'][:3]:
                    summ3 += (Dl(i[0]) * Dl(i[1]))
                    summ_amount += Dl(i[1])
                else:
                    b = summ3 / summ_amount
                    summ3 = 0
                    summ_amount = 0
                for i in resp['asks'][:3]:
                    summ3 += (Dl(i[0]) * Dl(i[1]))
                    summ_amount += Dl(i[1])
                else:
                    a = summ3 / summ_amount

                self.iTbin = {'bids': [b, B], 'asks': [a, A]}  # price/amount

    @staticmethod
    def __get_timestamp():
        return int(time.time() * 1000)

    def __dispatch_request(self, http_method):
        session = self.session
        return {
            'GET': session.get,
            'DELETE': session.delete,
            'PUT': session.put,
            'POST': session.post,
        }.get(http_method, 'GET')

    def __hashing(self, query_string):
        return hmac.new(self._bin_secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()

    async def sign_req_bin(self, method, endpoint, SS=None):  # side - uppercase/size decimal
        url_path = self._make_signed_path(SS)
        req = Bin.__dispatch_request(self, method)
        r = await req(Bin.__Base_url + endpoint + url_path, headers=Bin.headers)
        self.rest_bin_t[self.rest_bin_t.index(min(self.rest_bin_t))] = time.time()
        r = await r.json()
        if r.get('status') != 'FILLED' and method == 'POST':
            print(r)
        return r

    def _make_signed_path(self, SS):
        ts = Bin.__get_timestamp()
        if SS:
            side, size = SS
            params = {'symbol': '1INCHBUSD', 'side': side, 'type': 'MARKET', 'quantity': size}
            raw_url = f'{urlencode(params, True)}&timestamp={ts}'
            url_path = f'?{raw_url}&signature={self.__hashing(raw_url)}'
        else:
            raw_url = f'timestamp={ts}'
            url_path = f'?{raw_url}&signature={self.__hashing(raw_url)}'
        return url_path

    async def _get_balances_bin(self):
        r = await self.sign_req_bin('GET', '/api/v3/account')
        self.bin_balance = {}
        for k in r['balances']:
            if k['asset'] == 'BUSD':
                self.bin_balance['BUSD'] = Dl(k['free'])
            if k['asset'] == '1INCH':
                self.bin_balance['1INCH'] = Dl(k['free'])

    def check_weight(self):
        if time.time() - min(self.rest_bin_t) > 60:
            return True
        else:
            return False


class test(Bin):
    async def make_conn(self):
        await self._make_conn_bin()

    async def get_rec(self):
        await self._get_recv_bin()


async def sestdef():
    a = test()
    await a.make_conn()
    while True:
        await a.get_rec()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(sestdef())
