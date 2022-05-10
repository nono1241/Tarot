from web3 import Web3
from web3.middleware import geth_poa_middleware
from uniswap import uniswap
from config import *
import requests
import json

w3 = Web3(Web3.HTTPProvider(Rpc.FTM.value))
w3.middleware_onion.inject(geth_poa_middleware, layer=0)

def getW3Object(address, ABI):
    adr = w3.toChecksumAddress(address)
    return w3.eth.contract(address=adr, abi=ABI)

def getTokenPrice_old(token1, token2):
    adr1 = w3.toChecksumAddress(token1)
    adr2 = w3.toChecksumAddress(token2)

    router = getW3Object(Contract.spooky_uniswapv2_router.value, Abi.spooky_uniswapv2_router.value)
    factory = getW3Object(Contract.spooky_uniswapv2_factory.value, Abi.spooky_uniswapv2_factory.value)

    exchange_rate = 0
    lp_adr = factory.functions.getPair(adr1, adr2).call()
    if lp_adr:
        lp = w3.eth.contract(address=lp_adr, abi=Abi.spooky_uniswapv2_lp.value)
        reserve = lp.functions.getReserves().call()
        w3_token1 = getW3Object(lp.functions.token0().call(), Abi.token_usdc.value)
        w3_token2 = getW3Object(lp.functions.token1().call(), Abi.token_usdc.value)
        exchange_rate = (reserve[0] / (10 ** w3_token1.functions.decimals().call())) / (reserve[1] / (10 ** w3_token2.functions.decimals().call()))
    return exchange_rate


def getTokenPrice(from_adr, to_adr, quantity=1000):
    # Get the number of decimal of from_adr to compute WEI
    from_adr_w3 = getW3Object(from_adr, Abi.token_usdc.value)
    from_decimal = from_adr_w3.functions.decimals().call()
    # Firebird API to get the price
    url = f'https://router.firebird.finance/aggregator/v1/route?chainId=250&from={from_adr}&to={to_adr}&amount={str((10 ** from_decimal) * quantity)}&source=tarot_testing_bot'
    response = requests.get(url)
    token_price = json.loads(response.text)
    token_w3 = getW3Object(to_adr, Abi.token_usdc.value)
    token_decimal = token_w3.functions.decimals().call()

    price = int(token_price['maxReturn']['totalTo']) / quantity / (10 ** token_decimal)
    return price

if __name__ == "__main__":
    try:
        vault_adr = Contract.spooky_btc_eth_vault.value
        # Vault token
        vault_token = getW3Object(vault_adr, Abi.tarot_vault.value)
        #token0_adr = vault_token.functions.token0().call()
        #token1_adr = vault_token.functions.token1().call()
        lp_adr = vault_token.functions.underlying().call()

        # Get the borrowable tokens from the bTarot factory using the vault address
        borrowable_factory = getW3Object(Contract.tarot_factory.value, Abi.tarot_factory.value)
        borrowable_instrument = borrowable_factory.functions.getLendingPool(w3.toChecksumAddress(vault_adr)).call()
        borrowable_token0 = borrowable_instrument[3]
        borrowable_token1 = borrowable_instrument[4]

        current_token = borrowable_token0

        # borrowableTarot
        b_tarot = getW3Object(current_token, Abi.borrowable.value)
        current_underlying_adr = b_tarot.functions.underlying().call()
        current_underlying = getW3Object(current_underlying_adr, Abi.token_usdc.value)
        current_underlying_decimal = current_underlying.functions.decimals().call()
        total_borrow = b_tarot.functions.totalBorrows().call() / (10 ** current_underlying_decimal)
        total_supply = b_tarot.functions.totalSupply().call() / (10 ** current_underlying_decimal)
        exchange_rate = b_tarot.functions.exchangeRateLast().call() / (10 ** 18)
        kink_utilization_rate = b_tarot.functions.kinkUtilizationRate().call() / (10 ** 18)
        kink_borrow_Rate = b_tarot.functions.kinkBorrowRate().call() / (10 ** 18)
        borrow_rate = b_tarot.functions.borrowRate().call() / (10 ** 18)

        # farming pool
        farming_pool_adr = b_tarot.functions.borrowTracker().call()
        farming_pool = getW3Object(farming_pool_adr, Abi.farming_pool.value)
        epoch_amount = farming_pool.functions.epochAmount().call() / (10 ** 18)
        segment_length = farming_pool.functions.segmentLength().call()  # 2 weeks in seconds
        tarot_price = getTokenPrice(Token.TAROT.value, Token.USDC.value)

        token_price = getTokenPrice(current_underlying_adr, Token.USDC.value, 1)
        utilization_rate = (total_borrow / (total_supply * exchange_rate))
        borrow_apr = borrow_rate * 365 * 24 * 3600 * 100
        supply_rate = borrow_rate * utilization_rate * (1 - b_tarot.functions.reserveFactor().call() / (10 ** 18))
        supply_apr = supply_rate * 365 * 24 * 3600 * 100
        farming_apr = ((365 * 24 * 3600) * (tarot_price * epoch_amount) / segment_length) / (total_borrow * token_price) * 100

        print(f'Token: {current_underlying.functions.name().call()}, price: {str(token_price)}')
        print(f'Total supply (USDC): {round(total_supply * token_price * exchange_rate, 2):,}')
        print(f'Total borrow (USDC): {round(total_borrow * token_price, 2):,}')
        print(f'Utilisation rate: {round(utilization_rate * 100, 2)}%')
        print(f'Supply APR: {round(supply_apr, 2)}%')
        print(f'Borrow APR: {round(borrow_apr, 2)}%')
        print(f'Farming APR: {round(farming_apr, 2):,}')
    except Exception as e:
        print(str(e))
