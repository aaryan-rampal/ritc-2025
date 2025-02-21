import time
from order_queue import OrderQueue  # Import the OrderQueue class
from networking import *
from collections import deque
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import threading

# Trading Settings
MAX_LONG_EXPOSURE = 300_000
MAX_SHORT_EXPOSURE = 200_000
ORDER_LIMIT_STOCK = 5_000
ORDER_LIMIT_ETF = 10_000
ROLLING_WINDOW_SIZE = 500

BUY = "BUY"
SELL = "SELL"

CHECK_INTERVAL = 1 # Market-making update interval


# dict where rolling_prices[ticker] is a deque of the 20 last mid prices
rolling_prices = {
    ticker: deque(maxlen=ROLLING_WINDOW_SIZE)
    for ticker in STOCK_TICKERS + ETF_TICKERS + ["eq_joy_c", "eq_joy_u"]
}

# Initialize Order Queue
order_queue = OrderQueue()

def update_rolling_prices():
    """
    Fetch the latest bid/ask for each security, compute the mid-price,
    and append to the rolling deque.
    """
    for ticker in STOCK_TICKERS + ETF_TICKERS:
        bid, ask = get_bid_ask(ticker)  
        if bid is not None and ask is not None:
            mid_price = (bid + ask) / 2
            rolling_prices[ticker].append(mid_price)
    
    stock_mid_price = sum(rolling_prices[p][-1] for p in STOCK_TICKERS)
    rolling_prices["eq_joy_c"].append(stock_mid_price)

    exchange_rate = get_exchange_rate()
    eq_joy_u_value = stock_mid_price / exchange_rate
    rolling_prices["eq_joy_u"].append(eq_joy_u_value)

def calculate_etf_values():
    """Calculate theoretical values for JOY_C and JOY_U based on stock prices."""
    stock_prices = {}
    for ticker in STOCK_TICKERS:
        if not rolling_prices[ticker]:
            # Missing price data
            return None, None
        stock_prices[ticker] = rolling_prices[ticker][-1]

    # If any of the most recent prices are None, skip
    if any(price is None for price in stock_prices.values()):
        return None, None

    # JOY_C is simply the sum of these four stock mid-prices
    joy_c_value = sum(stock_prices.values())

    # Convert JOY_C to USD for JOY_U
    exchange_rate = get_exchange_rate()
    joy_u_value = joy_c_value / exchange_rate

    return joy_c_value, joy_u_value

def sell_all(positions):
    for ticker, quantity in positions.items():
        if quantity > 0:
            while quantity != 0:
                trade_size = min(5_000, quantity)
                print(f"📉 Selling {quantity} of {ticker}")
                place_market_order("SELL", ticker, trade_size)
                quantity -= trade_size
        elif quantity < 0:
            while quantity != 0:
                trade_size = min(5_000, -quantity)
                print(f"📈 Buying {-quantity} of {ticker}")
                place_market_order("BUY", ticker, trade_size)
                quantity += trade_size


    

# returns True if hit limits after trade
def check_limits(trade_size, gross, net):
    if gross + (2 * trade_size) > MAX_LONG_EXPOSURE:
        print(f"⚠ Skipping - {gross} + {trade_size} Would exceed GROSS LIMIT")
        return True

    if net - trade_size < -MAX_SHORT_EXPOSURE or net + trade_size > MAX_SHORT_EXPOSURE:
        print(f"⚠ Skipping - {net} and {trade_size} Would exceed NET LIMIT")
        return True
    
    return False

def arbitrage():
    joy_c_mid, joy_u_mid  = rolling_prices["JOY_C"][-1], rolling_prices["JOY_U"][-1]
    eq_joy_c, eq_joy_u = calculate_etf_values()

    trade_size = 1_000

    positions = get_market_positions()
    gross_exposure = sum(abs(v) for v in positions.values())
    net_exposure = sum(positions.values())

    if eq_joy_c - joy_c_mid > 0.2:
        if check_limits(trade_size * 5, gross_exposure, net_exposure):
            return

        place_market_order(BUY, "JOY_C", trade_size)
        for ticker in STOCK_TICKERS:
            place_market_order(SELL, ticker, trade_size)
    elif eq_joy_c - joy_c_mid < -0.2:
        if check_limits(trade_size * 5, gross_exposure, net_exposure):
            return

        place_market_order(SELL, "JOY_C", trade_size)
        for ticker in STOCK_TICKERS:
            place_market_order(BUY, ticker, trade_size)
    
    # if eq_joy_u - joy_u_mid > 0.2:
    #     if check_limits(trade_size * 5, gross_exposure, net_exposure):
    #         return

    #     place_market_order(BUY, "JOY_U", trade_size)
    #     for ticker in STOCK_TICKERS:
    #         place_market_order(SELL, ticker, trade_size)
    # elif eq_joy_u - joy_u_mid < -0.2:
    #     if check_limits(trade_size * 5, gross_exposure, net_exposure):
    #         return

    #     place_market_order(SELL, "JOY_U", trade_size)
    #     for ticker in STOCK_TICKERS:
    #         place_market_order(BUY, ticker, trade_size)
    
def process_tenders():
    """Checks for tenders and accepts profitable ones, then offloads ETF positions."""
    tenders = get_tenders()

    # No tenders available
    if not tenders:
        return  

    for tender in tenders:
        ticker = tender["ticker"]
        action = tender["action"] 
        price = tender["price"]
        quantity = tender["quantity"]

        # using market orders here so I only care about bid
        best_bid, _ = get_bid_ask(ticker)
        if not best_bid:
            continue  # Skip if market data is unavailable

        if action == "BUY" and price < best_bid:
            if order_queue.check_limits(quantity, action):
                order_queue.offload_for_tender(action, quantity)
            # make sure tender is still valid here
            if accept_tender(tender):
                print(f"🚀 Accepting BUY tender for {ticker}: {quantity} @ {price} (Market Bid: {best_bid})")
                order_queue.offload_etf(ticker, "BUY", quantity)  # Offload position

        # Accept SELL tender if price is above current best ask
        # can buy immediately at a profit 
        elif action == "SELL" and price > best_bid:
            if order_queue.check_limits(quantity, action):
                order_queue.offload_for_tender(action, quantity)
            # make sure tender is still valid here
            if accept_tender(tender):
                print(f"🚀 Accepting SELL tender for {ticker}: {quantity} @ {price} (Market Bid: {best_bid})")
                order_queue.offload_etf(ticker, "SELL", quantity)  # Offload position
        else:
            decline_tender(tender)


def main():
    tick = get_current_tick()
    while tick != 0:
        update_rolling_prices()
        arbitrage()
        process_tenders()
        time.sleep(CHECK_INTERVAL)
        tick = get_current_tick()
        print(rolling_prices["eq_joy_u"])



# === Matplotlib Real-time Graph ===

# Initialize the figure and axes
fig, ax = plt.subplots(1, 2, figsize=(12, 6))
joy_c_plot, = ax[0].plot([], [], label="JOY_C Mid Price", color='blue')
eq_joy_c_plot, = ax[0].plot([], [], label="eq_joy_c Price", color='red')

joy_u_plot, = ax[1].plot([], [], label="JOY_U Mid Price", color='blue')
eq_joy_u_plot, = ax[1].plot([], [], label="eq_joy_u Price", color='red')

ax[0].set_title("JOY_C Mid Price vs eq_joy_c")
ax[1].set_title("JOY_U Mid Price vs eq_joy_u")
for a in ax:
    a.set_xlabel("Time")
    a.set_ylabel("Price")
    a.legend()


def update_plot(frame):
    """Fetches data and updates the plots dynamically."""
    if len(rolling_prices["JOY_C"]) < 2 or len(rolling_prices["JOY_U"]) < 2:
        return

    # Get data for JOY_C and eq_joy_c
    x_data = list(range(len(rolling_prices["JOY_C"])))
    joy_c_plot.set_data(x_data, list(rolling_prices["JOY_C"]))
    eq_joy_c_plot.set_data(x_data, list(rolling_prices["eq_joy_c"]))
    ax[0].relim()
    ax[0].autoscale_view()

    # Get data for JOY_U and eq_joy_u
    x_data = list(range(len(rolling_prices["JOY_U"])))
    joy_u_plot.set_data(x_data, list(rolling_prices["JOY_U"]))
    eq_joy_u_plot.set_data(x_data, list(rolling_prices["eq_joy_u"]))
    ax[1].relim()
    ax[1].autoscale_view()

    return joy_c_plot, eq_joy_c_plot, joy_u_plot, eq_joy_u_plot


# Use threading to run the trading logic separately
trading_thread = threading.Thread(target=main, daemon=True)
trading_thread.start()

# Animate the graph
ani = animation.FuncAnimation(fig, update_plot, interval=500)

plt.show()