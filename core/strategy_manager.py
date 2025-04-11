from strategies.base_strategy import BaseStrategy
from strategies.rsi_strategy import RSIStrategy
from strategies.ml_strategy import MLStrategy
import importlib.util

class StrategyManager:
    def __init__(self, config):
        self.config = config
        self.strategies = {
            'rsi_strategy': RSIStrategy,
            'ml_strategy': MLStrategy
        }
        
    def get_strategy(self):
        strategy_name = self.config['strategies']['active']
        strategy_class = self.strategies.get(strategy_name)
        
        if not strategy_class:
            raise ValueError(f"Neplatná strategie: {strategy_name}")
            
        return strategy_class(**self.config['strategies']['params'])
    
    def load_custom_strategy(self, path):
        spec = importlib.util.spec_from_file_location("custom_strategy", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.CustomStrategy
