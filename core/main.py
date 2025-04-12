# core/main.py
import time
import yaml
import logging
import sqlite3
import pandas as pd
from datetime import datetime
from core.exchange import BinanceConnector
from core.strategy_manager import StrategyManager
from core.risk_management import AdvancedRiskManager

class TradingBot:
    def __init__(self):
        self._load_config()
        self._init_components()
        self.running = True
        self.logger = logging.getLogger(self.__class__.__name__)
        self._init_database()

    def _load_config(self):
        """Načte konfiguraci s explicitním UTF-8 kódováním"""
        with open("config/config.yaml", "r", encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        self.base_currency = self.config['base_currency']
        self.market_type = self.config['market_type']

    def _init_components(self):
        """Inicializuje hlavní komponenty"""
        self.exchange = BinanceConnector(self.config)
        self.strategy_manager = StrategyManager(self.config)
        self.risk_manager = AdvancedRiskManager(self.config, self.exchange)
        self.strategy = self.strategy_manager.get_strategy()

    def _init_database(self):
        """Vytvoří chybějící databázové tabulky"""
        with sqlite3.connect('data/trading_history.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS model_metrics (
                    id INTEGER PRIMARY KEY,
                    timestamp DATETIME,
                    accuracy REAL,
                    precision REAL,
                    recall REAL,
                    f1_score REAL
                )
            ''')
            conn.commit()

    def run(self):
        """Hlavní smyčka obchodního bota"""
        self.logger.info("🚀 Initializing QuantumTrader AI Engine...")
        symbol = f"{self.base_currency}/USDT"
        
        while self.running:
            try:
                # 1. Získání dat
                ohlcv_data = self.exchange.get_real_time_data(
                    symbol=symbol,
                    timeframe=self.config['strategies']['ml_strategy']['timeframe']
                )
                
                # 2. AI analýza
                analysis_report = self.strategy.analyze(ohlcv_data)
                
                # 3. Risk management
                risk_assessment = self.risk_manager.evaluate(
                    signal=analysis_report['signal'],
                    confidence=analysis_report['confidence']
                )
                
                # 4. Provedení obchodu
                if risk_assessment['approved']:
                    self._execute_trade(
                        signal=analysis_report['signal'],
                        amount=risk_assessment['amount'],
                        symbol=symbol
                    )
                
                # 5. Aktualizace metrik
                self._update_metrics(analysis_report)
                
                time.sleep(self.config['api_settings']['refresh_interval'])
                
            except KeyboardInterrupt:
                self.shutdown()
            except Exception as e:
                self.logger.error(f"Critical path failure: {str(e)}", exc_info=True)
                time.sleep(10)

    def _execute_trade(self, signal, amount, symbol):
        """Provádí obchod s rozšířeným loggingem"""
        try:
            if self.config['mode'] == 'dry':
                self.logger.info(f"🔮 [SIMULATION] {signal} {amount} {symbol}")
                return

            order_result = self.exchange.execute_order(
                symbol=symbol,
                side=signal.lower(),
                amount=amount,
                order_type='MARKET'
            )
            
            self.logger.info(f"💰 Order executed: {order_result}")
            self._log_trade(order_result)

        except Exception as e:
            self.logger.error(f"💥 Trade execution failed: {str(e)}")

    def _update_metrics(self, analysis):
        """Ukládá metriky AI modelu"""
        with sqlite3.connect('data/trading_history.db') as conn:
            conn.execute('''
                INSERT INTO model_metrics 
                (timestamp, accuracy, precision, recall, f1_score)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                datetime.now(),
                analysis.get('accuracy', 0),
                analysis.get('precision', 0),
                analysis.get('recall', 0),
                analysis.get('f1_score', 0)
            ))

    def shutdown(self):
        """Elegantní vypnutí systému"""
        self.running = False
        self.logger.info("🛑 QuantumTrader shutting down...")
        self.exchange.close()
        self._cleanup_resources()

def setup_logging():
    """Pokročilá konfigurace logování"""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s - %(module)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler s rotací logů
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        'logs/quantum_trader.log',
        maxBytes=10*1024*1024,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    
    # Konzolový handler s barevnými výpisy
    try:
        from colorlog import ColoredFormatter
        color_formatter = ColoredFormatter(
            "%(log_color)s[%(asctime)s] %(levelname)s - %(module)s - %(message)s",
            datefmt='%Y-%m-%d %H:%M:%S',
            reset=True,
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            }
        )
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(color_formatter)
    except ImportError:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

if __name__ == "__main__":
    setup_logging()
    try:
        bot = TradingBot()
        bot.run()
    except Exception as e:
        logging.critical(f"🔥 Critical initialization failure: {str(e)}", exc_info=True)
