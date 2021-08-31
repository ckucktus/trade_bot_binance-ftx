import asyncio
import os

from dotenv import load_dotenv

from relationship import Rel

load_dotenv()
ftx_key = str(os.getenv('ftx_key'))
ftx_secret = str(os.getenv('ftx_secret'))
bin_key = str(os.getenv('bin_key'))
bin_secret = str(os.getenv('bin_secret'))


async def main():
    obj = Rel(ftx_key=ftx_key, ftx_secret=ftx_secret, bin_key=bin_key, bin_secret=bin_secret)
    await obj.make_conns()
    await obj.find_balances()
    await obj.init_logg()
    while True:
        await obj.get_recvs()

        if obj.iTbin and obj.iTftx: # Если получил все котировки

            if obj.iTftx['bids'][0]/obj.iTbin['asks'][0] > obj.iTbin['bids'][0] / obj.iTftx['asks'][0]:
                await obj.is_relevant_ftx_sell()
            else:
                await obj.is_relevant_bin_sell()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
