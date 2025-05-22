import tkinter as tk
from tkinter import ttk
from tinkoff.invest import Client, InstrumentIdType, OrderBookInstrument
from tinkoff.invest.services import MarketDataStreamManager
from tinkoff.invest.schemas import OrderBook, Share

import threading

# T_API_KEY -  REPLACE WITH YOUR ACTUAL TINKOFF API KEY
T_API_KEY = ""


# Print all tickers from Tinkoff

# with Client(T_API_KEY) as client:
#     futures = client.instruments.futures().instruments
#     for future in futures:
#         print(
#             f"Ticker: {future.ticker:<10} | FIGI: {future.figi} | Class: {future.class_code} "
#             f"| Expiration: {future.expiration_date}"
#         )

from datetime import datetime, timezone

def find_closest_future_by_figi(client, figi_prefix):
    """
    Finds the closest future by FIGI prefix.
    Because only figi has strings like 'FUTSI', 'FUTCNY', 'FUTUCNY'

    """

    # Fetch all futures
    futures = client.instruments.futures().instruments
    
    # Filter futures by FIGI prefix, e.g. 'FUTSI', 'FUTCNY', 'FUTUCNY'
    filtered = [f for f in futures if f.figi.startswith(figi_prefix)]
    if not filtered:
        return None

    # Filter futures that have expiration_date and sort ascending by expiration
    filtered = [f for f in filtered if f.expiration_date]
    filtered.sort(key=lambda f: f.expiration_date)

    now = datetime.now(timezone.utc)

    for f in filtered:
        if f.expiration_date >= now:
            return f  # first future not expired

    return None  # no future found after now

with Client(T_API_KEY) as client:

    si_future = find_closest_future_by_figi(client, "FUTSI")
    cny_future = find_closest_future_by_figi(client, "FUTCNY")
    ucny_future = find_closest_future_by_figi(client, "FUTUCNY")

    if not all([si_future, cny_future, ucny_future]):
        print("Error: One or more futures not found")
        exit()

    # Extract tickers
    si_ticker = si_future.ticker
    cny_ticker = cny_future.ticker
    ucny_ticker = ucny_future.ticker

    # Print the tickers
    for figi_prefix in ["FUTSI", "FUTCNY", "FUTUCNY"]:
        closest = find_closest_future_by_figi(client, figi_prefix)
        if closest:
            print(
                f"Closest future for {figi_prefix}: "
                f"Ticker: {closest.ticker} | FIGI: {closest.figi} | Expiration: {closest.expiration_date}"
            )
        else:
            print(f"No active future found for {figi_prefix}")



class InstrumentManager:
    """
    Manages fetching and storing instrument data for given tickers.
    """
    def __init__(self, api_key: str, si_ticker: str, cny_ticker: str, ucny_ticker: str):
        self.api_key = api_key
        self.si_ticker = si_ticker
        self.cny_ticker = cny_ticker
        self.ucny_ticker = ucny_ticker

        self.si: Share = None
        self.cny: Share = None
        self.ucny: Share = None

    def fetch_instruments(self):
        """Fetches instrument data from the Tinkoff API using tickers."""
        try:
            with Client(self.api_key) as client:
                self.si = client.instruments.get_instrument_by(
                    id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_TICKER,
                    id=self.si_ticker,
                    class_code="SPBFUT"
                ).instrument

                self.cny = client.instruments.get_instrument_by(
                    id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_TICKER,
                    id=self.cny_ticker,
                    class_code="SPBFUT"
                ).instrument

                self.ucny = client.instruments.get_instrument_by(
                    id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_TICKER,
                    id=self.ucny_ticker,
                    class_code="SPBFUT"
                ).instrument

            return True
        except Exception as e:
            print(f"Error fetching instruments: {e}")
            return False

    def get_si(self): return self.si
    def get_cny(self): return self.cny
    def get_ucny(self): return self.ucny



class OrderBookWatcher:
    """
    Watches order book updates and calculates price differences.
    """

    def __init__(self, api_key: str, instrument_manager: InstrumentManager, root: tk.Tk, result_label: tk.Label):
        self.api_key = api_key
        self.instrument_manager = instrument_manager
        self.last_order_books = {}
        self.result_label = result_label
        self.root = root  # Store the root window
        self.dragging = False
        self.offset_x = 0
        self.offset_y = 0

    def set_last_order_books(self):
        """Initializes the last_order_books dictionary with None values."""
        si = self.instrument_manager.get_si()
        cny = self.instrument_manager.get_cny()
        ucny = self.instrument_manager.get_ucny()
        if si and cny and ucny:
            self.last_order_books[si.figi] = None
            self.last_order_books[cny.figi] = None
            self.last_order_books[ucny.figi] = None
        else:
            self.result_label.config(text="Instruments not initialized.")
            print("Instruments not initialized.  Cannot set last order books.")

    def watch_order_books(self):
        """Subscribes to order book updates for si and cny."""
        si = self.instrument_manager.get_si()
        cny = self.instrument_manager.get_cny()
        ucny = self.instrument_manager.get_ucny()
        if not si or not cny or not ucny:
            self.result_label.config(text="Instruments not initialized.")
            print("Instruments not initialized.  Cannot watch order books.")
            return

        try:
            with Client(self.api_key) as client:
                market_data_stream: MarketDataStreamManager = client.create_market_data_stream()
                market_data_stream.order_book.subscribe(
                    [
                        OrderBookInstrument(instrument_id=si.figi, depth=1),
                        OrderBookInstrument(instrument_id=cny.figi, depth=1),
                        OrderBookInstrument(instrument_id=ucny.figi, depth=1),
                    ]
                )

                for marketdata in market_data_stream:
                    if marketdata.orderbook:
                        self._handle_orderbook(marketdata.orderbook)
        except Exception as e:
            self.result_label.config(text=f"Error watching order books: {e}")  # Update label with error
            print(f"Error watching order books: {e}")

    def _handle_orderbook(self, orderbook: OrderBook):
        """Handles incoming order book updates."""
        self.last_order_books[orderbook.figi] = orderbook
        self.short_long_calculate()

    def short_long_calculate(self):
        """Calculates and displays the difference between si max sell price and cny min buy price."""
        si = self.instrument_manager.get_si()
        cny = self.instrument_manager.get_cny()
        ucny = self.instrument_manager.get_ucny()
        if not si or not cny or not ucny:
            self.result_label.config(text="Instruments not initialized.")
            return


        try:
            si_order_book: OrderBook = self.last_order_books[si.figi]
            cny_order_book: OrderBook = self.last_order_books[cny.figi]
            ucny_order_book: OrderBook = self.last_order_books[ucny.figi]


            if not all([si_order_book, cny_order_book, ucny_order_book]):
                self.result_label.config(text="Order books not initialized.")
                return

            si_max_sell_price = si_order_book.bids[0].price.units + si_order_book.bids[0].price.nano / 1e9
            cny_min_buy_price = cny_order_book.asks[0].price.units + cny_order_book.asks[0].price.nano / 1e9
            ucny_min_buy_price = ucny_order_book.asks[0].price.units + ucny_order_book.asks[0].price.nano / 1e9
            result_open = round(si_max_sell_price/cny_min_buy_price/ucny_min_buy_price, 4)


            si_min_buy_price = si_order_book.asks[0].price.units + si_order_book.asks[0].price.nano / 1e9
            cny_max_sell_price = cny_order_book.bids[0].price.units + cny_order_book.bids[0].price.nano / 1e9
            ucny_max_sell_price = ucny_order_book.bids[0].price.units + ucny_order_book.bids[0].price.nano / 1e9
            result_close = round(si_min_buy_price/cny_max_sell_price/ucny_max_sell_price, 4)

            #self.result_label.config(text=str(result))  # Update the Tkinter label
            formatted = (f"OPEN: {si_max_sell_price:.3f} / {cny_min_buy_price:.3f} / {ucny_min_buy_price:.3f}= {result_open:.2f}\n\n"
                        f"CLOSE: {si_min_buy_price:.3f} / {cny_max_sell_price:.3f} / {ucny_max_sell_price:.3f}= {result_close:.2f}")
            self.result_label.config(text=formatted)

        except (AttributeError, KeyError) as e:  # Handle both AttributeError and KeyError
            self.result_label.config(text="No data or incomplete data")  # Update label with error message

    def start_move(self, event):
        """Records the starting position of the window for dragging."""
        self.dragging = True
        self.offset_x = event.x
        self.offset_y = event.y

    def move_window(self, event):
        """Moves the window based on the mouse position."""
        if self.dragging:
            x = self.root.winfo_pointerx() - self.offset_x
            y = self.root.winfo_pointery() - self.offset_y
            self.root.geometry(f"+{x}+{y}")

    def stop_move(self, event):
        """Stops the window movement."""
        self.dragging = False

    def make_window_draggable(self):
        """Makes the main window draggable."""
        # Bind to the whole label (or any other widget you want to drag from)
        self.result_label.bind("<ButtonPress-1>", self.start_move)
        self.result_label.bind("<B1-Motion>", self.move_window)
        self.result_label.bind("<ButtonRelease-1>", self.stop_move)  # Stop dragging

    def get_root(self) -> tk.Tk:
        return self.root


# Tkinter setup
root = tk.Tk()
root.title("SI/CNY/UCNY - на сход к 1000 сверху вниз")  # Keep the title!

root.geometry("400x100")  # Adjust as needed

# Label to display the result
result_label = ttk.Label(root, text="Initializing...", padding=10, font=("Helvetica", 14))  # Larger font
#result_label.pack(pady=50)  # Add some padding
result_label.place(relx=0.5, rely=0.5, anchor="center")

# Create instances of the helper classes
instrument_manager = InstrumentManager(
    api_key=T_API_KEY,
    si_ticker=si_ticker,
    cny_ticker=cny_ticker,
    ucny_ticker=ucny_ticker
)

if not instrument_manager.fetch_instruments():
    print("Failed to fetch instruments")
    exit()
    
orderbook_watcher = OrderBookWatcher(T_API_KEY, instrument_manager, root, result_label)

# Make the window draggable
orderbook_watcher.make_window_draggable()


def start_watching(instrument_manager: InstrumentManager, orderbook_watcher: OrderBookWatcher):
    """Starts the background threads."""
    # Fetch instruments in a separate thread to avoid blocking the UI
    instrument_thread = threading.Thread(target=instrument_manager.fetch_instruments)
    instrument_thread.daemon = True  # Allow the main thread to exit even if this thread is running
    instrument_thread.start()
    instrument_thread.join()  # Wait for instruments to load
    orderbook_watcher.set_last_order_books()  # Set order books AFTER instruments

    # Watch order books in a separate thread to avoid blocking the UI
    order_book_thread = threading.Thread(target=orderbook_watcher.watch_order_books)
    order_book_thread.daemon = True  # Allow the main thread to exit even if this thread is running
    order_book_thread.start()


# Start watching immediately
start_watching(instrument_manager, orderbook_watcher)

root.mainloop()
