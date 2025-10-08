"""
Systematic Stock Trading (SST) Strategy - Dhan Automation
Strategy: Averaging Down with Profit Target on Bajaj Finance

Trading Parameters:
- Per transaction: ₹10,000
- Max positions: 5
- Buy triggers: 0%, -2%, -4%, -6%, -8% from average price
- Sell target: +5% from weighted average price
- Re-entry: Next day's open price after exit
"""

import time
import json
from datetime import datetime, timedelta
from dhanhq import dhanhq

# ========================
# CONFIGURATION
# ========================
class Config:
    # Dhan API Credentials (Replace with your actual credentials)
    CLIENT_ID = "YOUR_CLIENT_ID"
    ACCESS_TOKEN = "YOUR_ACCESS_TOKEN"
    
    # Trading Parameters
    SYMBOL = "BAJFINANCE"
    SECURITY_ID = "500490"  # NSE security ID for Bajaj Finance
    EXCHANGE = "NSE"
    
    INVESTMENT_PER_TRADE = 10000
    MAX_POSITIONS = 5
    SELL_TARGET_PERCENT = 5.0
    
    # Buy trigger levels from average price
    BUY_TRIGGERS = [0, -2, -4, -6, -8]  # Percentages
    
    # Timing
    CHECK_INTERVAL_SECONDS = 30  # How often to check prices
    MARKET_OPEN_TIME = "09:15"
    MARKET_CLOSE_TIME = "15:30"

# ========================
# POSITION TRACKER
# ========================
class PositionTracker:
    def __init__(self):
        self.positions = []  # List of dicts: {price, quantity, amount}
        self.current_position_count = 0
        self.waiting_for_reentry = False
        self.reentry_date = None
        
    def add_position(self, price, quantity, amount):
        """Add a new position"""
        self.positions.append({
            'price': price,
            'quantity': quantity,
            'amount': amount,
            'timestamp': datetime.now()
        })
        self.current_position_count += 1
        
    def get_weighted_average_price(self):
        """Calculate weighted average price of all positions"""
        if not self.positions:
            return 0
        
        total_quantity = sum(p['quantity'] for p in self.positions)
        weighted_sum = sum(p['price'] * p['quantity'] for p in self.positions)
        
        return weighted_sum / total_quantity if total_quantity > 0 else 0
    
    def get_total_quantity(self):
        """Get total quantity held"""
        return sum(p['quantity'] for p in self.positions)
    
    def get_total_investment(self):
        """Get total amount invested"""
        return sum(p['amount'] for p in self.positions)
    
    def clear_positions(self):
        """Clear all positions after exit"""
        self.positions = []
        self.current_position_count = 0
        
    def get_next_buy_trigger_price(self):
        """Calculate the price for next buy based on average"""
        if self.current_position_count >= Config.MAX_POSITIONS:
            return None
        
        avg_price = self.get_weighted_average_price()
        if avg_price == 0:
            return None
        
        next_trigger_percent = Config.BUY_TRIGGERS[self.current_position_count]
        trigger_price = avg_price * (1 + next_trigger_percent / 100)
        
        return trigger_price
    
    def get_sell_target_price(self):
        """Calculate sell target price"""
        avg_price = self.get_weighted_average_price()
        return avg_price * (1 + Config.SELL_TARGET_PERCENT / 100)

# ========================
# DHAN API HANDLER
# ========================
class DhanAPIHandler:
    def __init__(self):
        self.dhan = dhanhq(Config.CLIENT_ID, Config.ACCESS_TOKEN)
        
    def get_ltp(self):
        """Get Last Traded Price"""
        try:
            quote = self.dhan.get_ltp_data(
                exchange_segment=Config.EXCHANGE,
                security_id=Config.SECURITY_ID
            )
            return quote['data']['LTP']
        except Exception as e:
            print(f"Error fetching LTP: {e}")
            return None
    
    def place_buy_order(self, quantity):
        """Place market buy order"""
        try:
            order = self.dhan.place_order(
                security_id=Config.SECURITY_ID,
                exchange_segment=Config.EXCHANGE,
                transaction_type='BUY',
                quantity=quantity,
                order_type='MARKET',
                product_type='CNC',  # Use CNC for delivery
                validity='DAY'
            )
            print(f"✅ BUY Order Placed: {quantity} shares | Order ID: {order['data']['orderId']}")
            return order
        except Exception as e:
            print(f"❌ Error placing BUY order: {e}")
            return None
    
    def place_sell_order(self, quantity):
        """Place market sell order"""
        try:
            order = self.dhan.place_order(
                security_id=Config.SECURITY_ID,
                exchange_segment=Config.EXCHANGE,
                transaction_type='SELL',
                quantity=quantity,
                order_type='MARKET',
                product_type='CNC',
                validity='DAY'
            )
            print(f"✅ SELL Order Placed: {quantity} shares | Order ID: {order['data']['orderId']}")
            return order
        except Exception as e:
            print(f"❌ Error placing SELL order: {e}")
            return None
    
    def get_order_status(self, order_id):
        """Check order execution status"""
        try:
            order_status = self.dhan.get_order_by_id(order_id)
            return order_status
        except Exception as e:
            print(f"Error fetching order status: {e}")
            return None

# ========================
# STRATEGY ENGINE
# ========================
class SSTStrategy:
    def __init__(self):
        self.api = DhanAPIHandler()
        self.tracker = PositionTracker()
        self.logger = self.setup_logger()
        
    def setup_logger(self):
        """Setup trade logging"""
        import logging
        logging.basicConfig(
            filename=f'sst_strategy_{datetime.now().strftime("%Y%m%d")}.log',
            level=logging.INFO,
            format='%(asctime)s - %(message)s'
        )
        return logging.getLogger()
    
    def is_market_open(self):
        """Check if market is open"""
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        
        # Check if it's a weekday
        if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return False
        
        return Config.MARKET_OPEN_TIME <= current_time <= Config.MARKET_CLOSE_TIME
    
    def execute_first_buy(self, ltp):
        """Execute the first buy at current market price"""
        quantity = int(Config.INVESTMENT_PER_TRADE / ltp)
        
        if quantity == 0:
            print(f"⚠️ Cannot buy: Investment ₹{Config.INVESTMENT_PER_TRADE} too low for price ₹{ltp}")
            return False
        
        order = self.api.place_buy_order(quantity)
        
        if order:
            # Wait a bit for order execution
            time.sleep(2)
            
            # Record position (using LTP as approximation)
            actual_amount = quantity * ltp
            self.tracker.add_position(ltp, quantity, actual_amount)
            
            msg = f"🎯 FIRST BUY: {quantity} shares @ ₹{ltp:.2f} | Investment: ₹{actual_amount:.2f}"
            print(msg)
            self.logger.info(msg)
            
            return True
        
        return False
    
    def execute_averaging_buy(self, ltp):
        """Execute averaging down buy"""
        quantity = int(Config.INVESTMENT_PER_TRADE / ltp)
        
        if quantity == 0:
            print(f"⚠️ Cannot buy: Investment ₹{Config.INVESTMENT_PER_TRADE} too low for price ₹{ltp}")
            return False
        
        order = self.api.place_buy_order(quantity)
        
        if order:
            time.sleep(2)
            
            actual_amount = quantity * ltp
            self.tracker.add_position(ltp, quantity, actual_amount)
            
            avg_price = self.tracker.get_weighted_average_price()
            msg = f"📉 AVERAGING BUY #{self.tracker.current_position_count}: {quantity} shares @ ₹{ltp:.2f} | New Avg: ₹{avg_price:.2f}"
            print(msg)
            self.logger.info(msg)
            
            return True
        
        return False
    
    def execute_sell(self, ltp):
        """Execute sell at target"""
        total_quantity = self.tracker.get_total_quantity()
        
        if total_quantity == 0:
            return False
        
        order = self.api.place_sell_order(total_quantity)
        
        if order:
            time.sleep(2)
            
            avg_price = self.tracker.get_weighted_average_price()
            total_invested = self.tracker.get_total_investment()
            sell_value = total_quantity * ltp
            profit = sell_value - total_invested
            profit_percent = (profit / total_invested) * 100
            
            msg = f"🎉 TARGET HIT! SOLD: {total_quantity} shares @ ₹{ltp:.2f} | Avg Buy: ₹{avg_price:.2f} | Profit: ₹{profit:.2f} ({profit_percent:.2f}%)"
            print(msg)
            self.logger.info(msg)
            
            # Clear positions and set reentry flag
            self.tracker.clear_positions()
            self.tracker.waiting_for_reentry = True
            self.tracker.reentry_date = datetime.now().date() + timedelta(days=1)
            
            return True
        
        return False
    
    def check_and_execute_reentry(self, ltp):
        """Check if we should re-enter on next day's open"""
        if not self.tracker.waiting_for_reentry:
            return False
        
        today = datetime.now().date()
        
        # Check if it's time to re-enter (next trading day)
        if today >= self.tracker.reentry_date:
            current_time = datetime.now().strftime("%H:%M")
            
            # Re-enter near market open (between 9:15 and 9:30)
            if "09:15" <= current_time <= "09:30":
                print(f"🔄 RE-ENTRY TIME: Starting fresh cycle")
                self.tracker.waiting_for_reentry = False
                return self.execute_first_buy(ltp)
        
        return False
    
    def run_strategy_cycle(self):
        """Main strategy execution cycle"""
        print(f"\n{'='*60}")
        print(f"⏰ Strategy Check: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")
        
        # Get current price
        ltp = self.api.get_ltp()
        if not ltp:
            print("⚠️ Could not fetch LTP, skipping cycle")
            return
        
        print(f"💰 Current LTP: ₹{ltp:.2f}")
        
        # Check for re-entry
        if self.tracker.waiting_for_reentry:
            print(f"⏳ Waiting for re-entry on {self.tracker.reentry_date}")
            self.check_and_execute_reentry(ltp)
            return
        
        # If no positions, make first buy
        if self.tracker.current_position_count == 0:
            print("🚀 No positions held. Initiating first buy...")
            self.execute_first_buy(ltp)
            return
        
        # Display current position status
        avg_price = self.tracker.get_weighted_average_price()
        total_qty = self.tracker.get_total_quantity()
        total_invested = self.tracker.get_total_investment()
        current_value = total_qty * ltp
        unrealized_pnl = current_value - total_invested
        unrealized_pnl_percent = (unrealized_pnl / total_invested) * 100
        
        print(f"\n📊 CURRENT POSITION:")
        print(f"   Positions: {self.tracker.current_position_count}/{Config.MAX_POSITIONS}")
        print(f"   Total Quantity: {total_qty}")
        print(f"   Average Price: ₹{avg_price:.2f}")
        print(f"   Total Invested: ₹{total_invested:.2f}")
        print(f"   Current Value: ₹{current_value:.2f}")
        print(f"   Unrealized P&L: ₹{unrealized_pnl:.2f} ({unrealized_pnl_percent:.2f}%)")
        
        # Check sell condition
        sell_target = self.tracker.get_sell_target_price()
        print(f"\n🎯 Sell Target: ₹{sell_target:.2f}")
        
        if ltp >= sell_target:
            print("✅ TARGET REACHED! Executing sell...")
            self.execute_sell(ltp)
            return
        
        # Check buy condition (if we haven't reached max positions)
        if self.tracker.current_position_count < Config.MAX_POSITIONS:
            next_buy_trigger = self.tracker.get_next_buy_trigger_price()
            print(f"📉 Next Buy Trigger: ₹{next_buy_trigger:.2f}")
            
            if ltp <= next_buy_trigger:
                print("✅ BUY TRIGGER HIT! Executing averaging buy...")
                self.execute_averaging_buy(ltp)
                return
        else:
            print("⚠️ Max positions reached. Waiting for sell target...")
    
    def run(self):
        """Main loop - runs continuously"""
        print("\n" + "="*60)
        print("🚀 SST STRATEGY STARTED")
        print("="*60)
        print(f"Symbol: {Config.SYMBOL}")
        print(f"Investment per trade: ₹{Config.INVESTMENT_PER_TRADE:,}")
        print(f"Max positions: {Config.MAX_POSITIONS}")
        print(f"Sell target: +{Config.SELL_TARGET_PERCENT}%")
        print(f"Buy triggers: {Config.BUY_TRIGGERS}")
        print("="*60 + "\n")
        
        while True:
            try:
                if self.is_market_open():
                    self.run_strategy_cycle()
                else:
                    print(f"⏸️ Market closed. Next check in {Config.CHECK_INTERVAL_SECONDS}s...")
                
                time.sleep(Config.CHECK_INTERVAL_SECONDS)
                
            except KeyboardInterrupt:
                print("\n\n⛔ Strategy stopped by user")
                break
            except Exception as e:
                print(f"❌ Error in main loop: {e}")
                self.logger.error(f"Error: {e}")
                time.sleep(Config.CHECK_INTERVAL_SECONDS)

# ========================
# MAIN EXECUTION
# ========================
if __name__ == "__main__":
    # Initialize and run strategy
    strategy = SSTStrategy()
    strategy.run()

