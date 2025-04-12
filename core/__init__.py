# core/__init__.py
from .exchange import BinanceConnector
from .strategy_manager import StrategyManager
from .risk_management import AdvancedRiskManager
from .data_processor import DataProcessor

__all__ = [
    'BinanceConnector',
    'StrategyManager', 
    'AdvancedRiskManager',
    'DataProcessor'
]

import sqlite3
from datetime import datetime

# Vlastní adaptéry a konvertory
def adapt_datetime(dt):
    return dt.isoformat()

def convert_datetime(val):
    return datetime.fromisoformat(val.decode())

# Registrace adaptérů a konvertorů
sqlite3.register_adapter(datetime, adapt_datetime)
sqlite3.register_converter("datetime", convert_datetime)

# Při vytváření spojení s databází přidejte detekci typů
conn = sqlite3.connect(
    'data/trading_history.db',
    detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
)