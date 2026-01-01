
import os
import sys
import datetime
import logging

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from hantubot.strategies.base_strategy import BaseStrategy
from hantubot.reporting.notifier import Notifier
from hantubot.study.repository import StudyDatabase, get_study_db
from hantubot.core.portfolio import Portfolio

# Mock Objects
class MockBroker: pass
class MockClock: pass

class TestStrategy(BaseStrategy):
    async def generate_signal(self, current_data, portfolio):
        return []

def test_base_strategy_config():
    print("\n--- Test BaseStrategy Configuration ---")
    config = {
        'strategy_name': 'test', 
        '_global': {
            'risk_management': {'buy_cash_ratio': 0.5}
        }
    }
    broker = MockBroker()
    clock = MockClock()
    notifier = Notifier()
    
    strategy = TestStrategy('test_strat', config, broker, clock, notifier)
    
    # Test calculate_buy_quantity
    cash = 10_000_000
    price = 10_000
    qty = strategy.calculate_buy_quantity(price, cash)
    
    expected_qty = int((cash * 0.5) // price)
    print(f"Cash: {cash}, Price: {price}, Ratio: 0.5")
    print(f"Calculated Qty: {qty}, Expected: {expected_qty}")
    
    assert qty == expected_qty
    print("✅ BaseStrategy config injection & buy quantity calculation passed.")

def test_notifier_dedup():
    print("\n--- Test Notifier Dedup ---")
    notifier = Notifier()
    key = f"TEST_KEY_{datetime.datetime.now().timestamp()}"
    
    # First call - should send (return False from check)
    is_duplicate_1 = notifier._check_and_update_dedup(key)
    print(f"First call (is_duplicate): {is_duplicate_1}")
    assert is_duplicate_1 == False
    
    # Second call - should be duplicate (return True)
    is_duplicate_2 = notifier._check_and_update_dedup(key)
    print(f"Second call (is_duplicate): {is_duplicate_2}")
    assert is_duplicate_2 == True
    
    print("✅ Notifier dedup logic passed.")

def test_db_schema():
    print("\n--- Test DB Schema ---")
    db_path = "data/test_study.db"
    if os.path.exists(db_path):
        os.remove(db_path)
        
    db = StudyDatabase(db_path)
    
    # Check tables
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"Tables found: {tables}")
        
        required_tables = ['closing_candidates', 'closing_candidate_results']
        for table in required_tables:
            assert table in tables
            print(f"Table '{table}' exists.")
            
    # Clean up
    if os.path.exists(db_path):
        try:
            # Close connection properly before removing? 
            # Context manager handles it, but maybe file lock exists.
            pass
        except:
            pass
    print("✅ DB Schema check passed.")

if __name__ == "__main__":
    try:
        test_base_strategy_config()
        test_notifier_dedup()
        test_db_schema()
        print("\n🎉 All verifications passed!")
    except AssertionError as e:
        print(f"\n❌ Verification Failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected Error: {e}")
        sys.exit(1)
