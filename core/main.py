# core/main.py
import time
import yaml
import logging
from core.exchange import BinanceConnector
from core.strategy_manager import StrategyManager
from core.risk_management import AdvancedRiskManager

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    file_handler = logging.FileHandler('logs/trading_bot.log', encoding='utf-8')
    file_handler.setFormatter(formatter)

class TradingBot:
    def __init__(self):
        try:
            self.config = self.load_config()
            self.exchange = BinanceConnector(self.config) 
            self.strategy = StrategyManager(self.config).get_strategy()
            self.risk_manager = AdvancedRiskManager(self.config, self.exchange)
            self.running = True
            self.logger = logging.getLogger(__name__)
        except Exception as e:
            logging.critical(f"Chyba při inicializaci: {str(e)}")
            raise


    def load_config(self):
        with open("config/config.yaml", encoding='utf-8') as f:
            return yaml.safe_load(f)

    def run(self):
        self.logger.info("🚀 Spouštím trading bot...")
        while self.running:
            try:
                # Získání aktuálních dat
                current_price = self.exchange.get_current_price()
                portfolio_value = self.exchange.get_portfolio_value()
                
                data = self.exchange.get_real_time_data(
                    timeframe=self.config['strategies']['params']['timeframe']
                )
                
                # Analýza a rozhodování
                decision = self.strategy.analyze(data)
                
                # Risk management
                decision = self.risk_manager.evaluate_risk(
                    decision, 
                    current_price,
                    {'value': portfolio_value}
                )
                
                # Provedení obchodu
                if decision != 'HOLD':
                    self.execute_trade(decision, current_price)
                
                time.sleep(self.config['api_settings']['refresh_interval'])
                
            except KeyboardInterrupt:
                self.shutdown()
            except Exception as e:
                self.logger.error(f"Kritická chyba: {str(e)}", exc_info=True)
                time.sleep(10)

    def execute_trade(self, decision, current_price):
        amount = self.config['risk_management']['max_trade_size']
        symbol = f"{self.config['base_currency']}/USDT"
        
        try:
            if self.config['mode'] == 'dry':
                self.logger.info(f"[DRY RUN] {decision} {amount} {symbol}")
                return True
                
            if decision == "BUY":
                self.exchange.client.create_market_buy_order(symbol, amount)
            elif decision == "SELL":
                self.exchange.client.create_market_sell_order(symbol, amount)
                
            self.logger.info(f"Úspěšný obchod: {decision} {amount} {symbol}")
            return True
            
        except Exception as e:
            self.logger.error(f"Chyba obchodu: {str(e)}")
            return False

    def shutdown(self):
        self.running = False
        self.logger.info("🛑 Bezpečné vypínání bota...")
        
    def setup_logging():
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        file_handler = logging.FileHandler('logs/trading_bot.log', encoding='utf-8')
        file_handler.setFormatter(formatter)       


        
        # Console handler s nahrazením problematických znaků
        class SafeStreamHandler(logging.StreamHandler):
            def emit(self, record):
                try:
                    msg = self.format(record)
                    msg = msg.encode('utf-8', errors='replace').decode('utf-8')
                    self.stream.write(msg + self.terminator)
                    self.flush()
                except Exception:
                    self.handleError(record)
                    
        console_handler = SafeStreamHandler()
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)


if __name__ == "__main__":
    setup_logging()
    bot = TradingBot()
    bot.run()