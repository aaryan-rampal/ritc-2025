import requests
import time

# API Credentials
API_KEY = 'BLDCD51J'
BASE_URL = 'http://localhost:9939/v1'
STOCK_TICKERS = ["SAD", "CRY", "ANGER", "FEAR"]
ETF_TICKERS = ["JOY_C", "JOY_U"]

def get_json(endpoint, params=None):
    """Fetch API data with error handling."""
    try:
        resp = requests.get(f"{BASE_URL}/{endpoint}", headers={"X-API-Key": API_KEY}, params=params)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"API Request failed: {e}")
        return None
    
    
def post_json(endpoint, params=None):
    """Send a POST request to the API with error handling."""
    try:
        resp = requests.post(
            f"{BASE_URL}/{endpoint}",
            headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
            json=params
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"API Request failed: {e}")
        return None

def delete_json(endpoint, params=None):
    """Send a DELETE request to the API with error handling."""
    try:
        resp = requests.delete(
            f"{BASE_URL}/{endpoint}",
            headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
            json=params
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"API Request failed: {e}")
        return None

def accept_tender(tender):
    """Accept a tender by sending a POST request."""
    # If not accepted, it returns none
    return post_json(f"tenders/{tender['tender_id']}")  # Corrected from GET to POST
    
def decline_tender(tender):
    """Accept a tender by sending a POST request."""
    return delete_json(f"tenders/{tender['tender_id']}")  # Corrected from GET to POST

def get_all_bid_ask():
    ticker_prices = dict()
    for ticker in STOCK_TICKERS + ETF_TICKERS:
        ticker_prices[ticker] = get_bid_ask(ticker)
    return ticker_prices

def get_current_tick():
    """
    Retrieves the current tick from the RIT REST API.

    :param api_url: Base URL of the RIT REST API (e.g., 'http://localhost:9999')
    :param api_key: Your API key for authentication
    :return: Current tick as an integer
    """
    response = get_json("case")
    
    if response:
        return response.get('tick', None)
    else:
        print("Error: Unable to retrieve case info")
        return None

def get_order_book_depth(ticker):
    order_book = get_json("securities/book", {"ticker": ticker, "limit": 1000})
    
    if order_book:
        return len(order_book["bids"]) + len(order_book["asks"])
    else:
        return None

def get_recent_ohlc(ticker, limit=50):
    ohlc = get_json("securities/history", {"ticker": ticker, "limit": limit})

    if ohlc:
        return ohlc
    else:
        return

def get_vwap(ticker):
    response = get_json("securities", {"ticker": ticker})

    if response:
        return response[0].get('vwap', None)
    else:
        return None

def get_bid_ask(ticker):
    """Fetch the best bid and ask prices for a ticker."""
    order_book = get_json("securities/book", {"ticker": ticker})
    if order_book and order_book["bids"] and order_book["asks"]:
        best_bid = max(order_book["bids"], key=lambda x: x["price"])["price"]
        best_ask = min(order_book["asks"], key=lambda x: x["price"])["price"]
        return best_bid, best_ask
    return None, None

def get_market_positions():
    """Fetch the current position of all non currency securities."""
    positions = get_json("securities")
    return {pos["ticker"]: pos["position"] for pos in positions if pos["ticker"] not in {"CAD", "USD"}} if positions else {}

def get_position(ticker):
    return get_positions()[ticker]

def get_mid_price(ticker):
    bid, ask = get_bid_ask(ticker)
    if not bid or not ask:
        return None
    return (bid + ask)/2

def get_positions():
    """Fetch the current position for all securities."""
    positions = get_json("securities")
    return {pos["ticker"]: pos["position"] for pos in positions} if positions else {}

def get_exchange_rate():
    """Fetch the CAD/USD exchange rate."""
    prices = get_json("securities")
    for sec in prices:
        if sec["ticker"] == "USD":
            return sec["last"]
    return 1.0  # Default if not found

    
def get_tenders():
    tenders = get_json("tenders")  # Fetch active tenders
    return tenders

def place_market_order(action, ticker, quantity, max_retries=3):
    order_data = {
        "ticker": ticker,
        "type": "MARKET",
        "quantity": quantity,
        "action": action,
    }

    for attempt in range(max_retries):
        resp = requests.post(f"{BASE_URL}/orders", headers={"X-API-Key": API_KEY}, params=order_data)

        if resp.ok:
            order_info = resp.json()  # Extract JSON response
            order_id = order_info.get("order_id")
            print(f"✅ MARKET {action} order placed: {quantity} {ticker} (Order ID: {order_id})")
            return order_id  # Order was successfully placed

        else:
            error_data = resp.json()
            error_code = error_data.get("code", "")

            if error_code == "TOO_MANY_REQUESTS":
                wait_time = error_data.get("wait", 0.01)  # Default to 10ms if no wait time is provided
                print(f"⚠ Rate limit exceeded for {ticker}. Waiting {wait_time:.3f} seconds before retrying...")
                time.sleep(wait_time)  # Pause before retrying
            else:
                print(f"❌ Order failed for {ticker}: {resp.text}")
                return None  # Exit if error is not related to rate limits

    print(f"❌ Max retries reached. Order for {ticker} not placed.")
    return None  # If all retries fail, return None

def place_limit_order(action, ticker, price, quantity):
    """Places a market or limit order based on security transaction fees."""
    order_data = {
        "ticker": ticker,
        "type": "LIMIT",
        "quantity": quantity,
        "action": action,
        "price": price
    }

    resp = requests.post(f"{BASE_URL}/orders", headers={"X-API-Key": API_KEY}, params=order_data)

    if resp.ok:
        order_info = resp.json()  # Extract JSON response
        order_id = order_info.get("order_id")
        print(f"✅ LIMIT {action} order placed: {quantity} {ticker} for {price} (Order ID: {order_id})")
        return order_id
    else:
        print(f"⚠ Order failed: {resp.text}")
        return None

def get_orders():
    """Fetches active orders from the API and returns them as a list."""
    try:
        resp = requests.get(f"{BASE_URL}/orders", headers={"X-API-Key": API_KEY})

        if resp.ok:
            return resp.json()  # Return the list of orders
        else:
            print(f"⚠ Failed to fetch orders: {resp.text}")
            return None
    except requests.RequestException as e:
        print(f"❌ Error while fetching orders: {e}")
        return None

def get_order(id, verbose=True):
    """Fetches active orders from the API and returns them as a list."""
    try:
        resp = requests.get(f"{BASE_URL}/orders/{id}", headers={"X-API-Key": API_KEY})

        if resp.ok:
            return resp.json()  # Return the order
        else:
            if verbose:
                print(f"⚠ Failed to fetch orders: {resp.text}")
            return None
    except requests.RequestException as e:
        print(f"❌ Error while fetching order: {e}")
        return None

def delete_order(id):
    """Fetches active orders from the API and returns them as a list."""
    try:
        resp = requests.delete(f"{BASE_URL}/orders/{id}", headers={"X-API-Key": API_KEY})

        if resp.ok:
            return True
        else:
            print(f"⚠ Failed to fetch orders: {resp.text}")
            return False
    except requests.RequestException as e:
        print(f"❌ Error while fetching order: {e}")
        return False