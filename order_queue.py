from networking import *
import time
from file_logger import FileLogger
import numpy as np
import statistics

MAX_LONG_EXPOSURE = 300_000
MAX_SHORT_EXPOSURE = 200_000
SELL = "SELL"
BUY = "BUY"
ALPHA = 2

class OrderQueue:
    logger = FileLogger("order_queue.log")

    def __init__(self):
        """Initialize order queue and inventory tracking."""
        self.queue = dict()  # Stores buy trades
        self.trade_log = []


        

    def check_gross_limit(self, trade_size):
        positions = get_market_positions()
        gross_exposure = sum(abs(v) for v in positions.values())
        return gross_exposure + trade_size > MAX_LONG_EXPOSURE
    
    # returns true if over limit with order
    def check_net_limit(self, trade_size, action):
        positions = get_market_positions()
        net_exposure = sum(positions.values())

        # make sure net limit checks the correct inequality based on the action
        # we are about to perform
        if action == SELL:
            return net_exposure - trade_size < -MAX_SHORT_EXPOSURE
        else:
            return net_exposure + trade_size > MAX_SHORT_EXPOSURE
    
    def offload_etf(self, ticker, action_performed, quantity):
        if action_performed == BUY:
            while quantity > 0:
                trade_size = min(10_000, quantity)
                place_market_order(SELL, ticker, trade_size)
                quantity -= trade_size
        if action_performed == SELL:
            while quantity > 0:
                trade_size = min(10_000, quantity)
                place_market_order(BUY, ticker, trade_size)
                quantity -= trade_size

    def return_order_id(self, order_id):
        while True:
            order_status = get_order(order_id, False)
            
            start_time = time.time()
            if order_status is None:
                if not order_id:
                    print(f"What")
                print(f"⚠ Order not found yet ({order_id}), retrying...")
                time.sleep(0.1)  # Wait half a second before retrying
            else:
                end_time = time.time()
                delay = end_time - start_time
                self.print(f"✅ Order {order_id} recognized after {delay:.2f} seconds.")
                return order_status
            

    def add_trade(self, ticker, price, action, id, z_mean, z):
        order = self.return_order_id(id)
        assert(order["action"] == action)
        assert(order["ticker"] == ticker)

        if not order:
            print("❌ AHH why is order not available")
            import sys
            sys.exit(0)
            return
        
        order["stop/loss"] = self.calculate_stop_loss(ticker, action, z, z_mean, price)

        self.queue[id] = order

    def calculate_stop_loss(self, ticker, action, z, z_mean, price):
        if ticker in ETF_TICKERS:
            # simple stop loss
            # stop loss is 2 * sigma of the difference between equilibrium and mid price of ETF
            diff = abs(z_mean - z)
            print(diff)

            if action == SELL:
                return price + diff * ALPHA
            else:
                return price - diff * ALPHA
        else:
            # now I am dealing with stocks
            percentage = self.rolling_prices[ticker][-1] / self.rolling_prices["eq_joy_c"][-1] 
            diff = abs(z_mean - z)
            adjusted_diff = percentage * diff

            if action == SELL:
                return price + adjusted_diff * ALPHA
            else:
                return price - adjusted_diff * ALPHA
                
    def place_all_market_orders(self, action, trade_size):
        for ticker in ["SAD", "ANGER", "FEAR", "CRY"]:
            place_market_order(action, ticker, trade_size // 4)

    def place_all_limit_orders(self, action, trade_size, z_mean, z):
        for ticker in ["SAD", "ANGER", "FEAR", "CRY"]:
            price = self.rolling_prices[ticker][-1]
            order_id = place_limit_order(action, ticker, price, trade_size // 4)
            self.add_trade(ticker, price, action, order_id, z_mean, z)

    # i want to BUY/SELL joy_c and do the reverse for the stocks
    # this is the break even point, I offload my shares here
    def joy_c_arb(self, action_for_joy, eq_joy_c, quantity, z_mean, sigma, z_sd, z):

        if action_for_joy == SELL:
            price_etf_sold, price_etf_bought = None, None
            price_stocks_sold = {
                ticker: None
                for ticker in STOCK_TICKERS
            }
            price_stocks_bought = {
                ticker: None
                for ticker in STOCK_TICKERS
            }

            # sell ETF at current price (minus a bit)
            price_etf_sold = self.rolling_prices["JOY_C"][-1]
            id_etf = place_limit_order(SELL, "JOY_C", price_etf_sold, quantity)
            assert(id_etf is not None)

            # buy stocks at current price (plus a bit)
            id_1 = {
                ticker: None
                for ticker in STOCK_TICKERS
            }
            for ticker in ["SAD", "ANGER", "FEAR", "CRY"]:
                price = self.rolling_prices[ticker][-1]
                price_stocks_bought[ticker] = price
                id_1[ticker] = place_limit_order(BUY, ticker, price_stocks_bought[ticker], quantity // 4)
                assert(id_1[ticker] is not None)
                self.add_trade(ticker, price_stocks_bought[ticker], BUY, id_1[ticker], z_mean, z)

            # add trades to queue
            self.add_trade("JOY_C", price_etf_sold, SELL, id_etf, z_mean, z)


            # buy back ETF at equilibrium price
            price_etf_bought = eq_joy_c + z_mean
            id_etf = place_limit_order(BUY, "JOY_C", price_etf_bought, quantity)
            assert(id_etf is not None)

            # sell shares at equilibrium price
            id_2 = {
                ticker: None
                for ticker in STOCK_TICKERS
            }
            for ticker in STOCK_TICKERS:
                percentage = self.rolling_prices[ticker][-1] / (eq_joy_c + z_mean)
                price_stocks_sold[ticker] = percentage * (eq_joy_c + z_mean)

                id_2[ticker] = place_limit_order(SELL, ticker, price_stocks_sold[ticker], quantity // 4)
                # add here because it's easier
                self.add_trade(ticker, price_stocks_sold[ticker], SELL, id_2[ticker], z_mean, z)
                assert(id_2[ticker] is not None)

            # add trades to queue
            self.add_trade("JOY_C", price_etf_bought, BUY, id_etf, z_mean, z)

            assert(price_etf_bought < price_etf_sold)
            for ticker in STOCK_TICKERS:
                assert(price_stocks_bought[ticker] < price_stocks_sold[ticker])

        else:
            price_etf_sold, price_etf_bought = None, None
            price_stocks_sold = {
                ticker: None
                for ticker in STOCK_TICKERS
            }
            price_stocks_bought = {
                ticker: None
                for ticker in STOCK_TICKERS
            }
            # buy ETF at current price (plus a bit)
            price_etf_bought = self.rolling_prices["JOY_C"][-1]
            id_etf = place_limit_order(BUY, "JOY_C", price_etf_bought, quantity)
            assert(id_etf is not None)

            # sell stocks at current price (minus a bit)
            id_1 = {
                ticker: None
                for ticker in STOCK_TICKERS
            }
            for ticker in ["SAD", "ANGER", "FEAR", "CRY"]:
                price = self.rolling_prices[ticker][-1]
                price_stocks_sold[ticker] = price
                id_1[ticker] = place_limit_order(SELL, ticker, price_stocks_sold[ticker], quantity // 4)
                assert(id_1[ticker] is not None)
                self.add_trade(ticker, price_stocks_sold[ticker], SELL, id_1[ticker], z_mean, z)

            # add trades to queue
            self.add_trade("JOY_C", price_etf_bought, BUY, id_etf, z_mean, z)

            # sell back ETF at equilibrium price
            price_etf_sold = eq_joy_c + z_mean
            id_etf = place_limit_order(SELL, "JOY_C", price_etf_sold, quantity)
            assert(id_etf is not None)

            # buy shares at equilibrium price
            id_2 = {
                ticker: None
                for ticker in STOCK_TICKERS
            }
            for ticker in STOCK_TICKERS:
                percentage = self.rolling_prices[ticker][-1] / (eq_joy_c + z_mean)
                price_stocks_bought[ticker] = percentage * (eq_joy_c + z_mean)
                id_2[ticker] = place_limit_order(BUY, ticker, price_stocks_bought[ticker], quantity // 4)
                # add here because it's easier
                self.add_trade(ticker, price_stocks_bought[ticker], BUY, id_2[ticker], z_mean, z)
                assert(id_2[ticker] is not None)

            # add trades to queue
            self.add_trade("JOY_C", price_etf_sold, SELL, id_etf, z_mean, z)

            assert(price_etf_bought < price_etf_sold)
            for ticker in STOCK_TICKERS:
                assert(price_stocks_bought[ticker] < price_stocks_sold[ticker])

        
    # this is only called when we have hit a tender
    def offload_for_tender(self, action, quantity):
        print("🫠 GOT HERE BRO DO SOMETHING ABOUT IT")
        if self.check_gross_limit(quantity):
            # TODO
            pass
        if self.check_net_limit(quantity, action):
            # TODO
            pass
    
    def print(self, s, std=True):
        if std:
            print(s)
        self.logger.log(s)

    # returns true if hit limit
    def check_limits(self, trade_size, action, ticker="ETF"):
        if self.check_gross_limit(trade_size):
            self.print(f"⚠ Skipping {ticker} - Would exceed GROSS LIMIT")
            return True
        if self.check_net_limit(trade_size, action):
            self.print(f"⚠ Skipping {ticker} - Would exceed NET LIMIT")
            return True
        
        return False
    
    def handle_stop_loss(self, order_id, ticker, trade_size, action, price):
        """Handles stop-loss execution logic for an order."""
        if self.check_limits(trade_size, ticker, action):
            self.print(f"❌🔄 Stop loss reached, but position limits prevent executing order {order_id} at {price} for {ticker}")
            return

        self.print(f"🔄 Stop loss triggered, closing order {order_id} at {price} for {ticker}")

        for i in range(3):
            if not delete_order(order_id):
                self.print(f"❌🔄 ERROR: Failed to delete order {order_id}, retrying...")
                self.print(get_order(order_id))
            else:
                place_market_order(action, ticker, trade_size)
                return True
        
        return False
    


        
        
    # checks all orders in self.queue, rmeove them if they hit stop loss
    def update_orders(self):
        """Fetches active orders from the API and updates self.queue."""
        ticker_prices = get_all_bid_ask()
        if not ticker_prices:
            return  # No valid bid, do nothing
        
        updated_queue = {}

        for id in list(self.queue.keys()):  # Iterates over key-value pairs
            if not id or id is None:
                continue

            order_rit = get_order(id)
            if not order_rit:
                print(f"🚨 ERROR: Failed to fetch order {id}")
                continue

            order_rit["stop/loss"] = self.queue[id]["stop/loss"]
            
            ticker = order_rit["ticker"]
            quantity = order_rit["quantity"]
            quantity_filled = order_rit["quantity_filled"]
            action = order_rit["action"]
            type_ = order_rit["type"] 
            stop_loss = order_rit["stop/loss"]
            open = order_rit["status"]
            bid, ask = ticker_prices[ticker]
            trade_size = quantity - quantity_filled

            if quantity == quantity_filled or open != "OPEN":
                continue

            stop_loss_went_through = False

            if action == BUY and stop_loss < bid:
                stop_loss_went_through |= self.handle_stop_loss(id, ticker, trade_size, BUY, bid)
            elif action == SELL and ask < stop_loss:
                stop_loss_went_through |= self.handle_stop_loss(id, ticker, trade_size, SELL, ask)

            if not stop_loss_went_through:
                updated_queue[id] = order_rit

        self.queue = updated_queue

    # checks all orders in self.queue, rmeove them if they hit stop loss
    def update_orders_based_on_ttl(self):
        """Fetches active orders from the API and updates self.queue."""
        curr_tick = get_current_tick()
        print(curr_tick)
        ticker_prices = get_all_bid_ask()
        if not ticker_prices:
            return  # No valid bid, do nothing
        
        updated_queue = {}

        for id in list(self.queue.keys()):  # Iterates over key-value pairs
            if not id or id is None:
                continue

            order_rit = get_order(id)
            print(order_rit)
            if not order_rit:
                print(f"🚨 ERROR: Failed to fetch order {id}")
                continue

            order_rit["stop/loss"] = self.queue[id]["stop/loss"]
            
            ticker = order_rit["ticker"]
            quantity = order_rit["quantity"]
            quantity_filled = order_rit["quantity_filled"]
            action = order_rit["action"]
            type_ = order_rit["type"] 
            stop_loss = order_rit["stop/loss"]
            open = order_rit["status"]
            bid, ask = ticker_prices[ticker]
            trade_size = quantity - quantity_filled

            if quantity == quantity_filled or open != "OPEN":
                continue

            stop_loss_went_through = False

            if action == BUY and stop_loss < bid:
                stop_loss_went_through |= self.handle_stop_loss(id, ticker, trade_size, BUY, bid)
            elif action == SELL and ask < stop_loss:
                stop_loss_went_through |= self.handle_stop_loss(id, ticker, trade_size, SELL, ask)

            if not stop_loss_went_through:
                updated_queue[id] = order_rit

        self.queue = updated_queue



    def log_trades(self):
        """Displays all recorded trades."""
        self.print("\n--- TRADE LOG ---", False)
        prices = get_all_bid_ask()
        # time.sleep(CHECK_INTERVAL)
        for ticker in ["FEAR", "SAD", "ANGER", "CRY"]:
            self.print(f"Position of {ticker} is {get_position(ticker)}", False)

        for order in self.queue.values():
            ticker = order["ticker"]
            action = order["action"]
            type = order["type"]
            stop = order["stop/loss"]
            price = order["price"]
            quantity = order["quantity"]
            quantity_filled = order["quantity_filled"]
            open = order["status"]
            order_id = order["order_id"]

            self.print(f"{order_id}: {open} order for {type} {action} at {price} for {ticker}. Current bid is {prices[ticker][0]} and ask is {prices[ticker][1]}. Waiting for {stop} to {SELL if action == BUY else BUY} at. {quantity_filled} out of {quantity} shares.", False)
            
        self.print("-----------------\n", False)
    