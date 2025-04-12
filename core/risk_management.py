# core/risk_management.py
import sqlite3
import logging
from datetime import datetime
import numpy as np

class AdvancedRiskManager:
    def __init__(self, config, exchange):
        self.config = config
        self.exchange = exchange
        self.logger = logging.getLogger(self.__class__.__name__)
        self._init_database()
        self.peak_balance = self._get_initial_balance()
        self.current_drawdown = 0.0

    @classmethod
    def _init_database(cls):
        """Inicializuje databázové tabulky pro risk management"""
        conn = sqlite3.connect('data/trading_history.db')
        cursor = conn.cursor()
        
        # Opravený SQL dotaz bez neplatného komentáře
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS risk_metrics (
            id INTEGER PRIMARY KEY,
            timestamp DATETIME,  -- Platný SQL komentář
            current_balance REAL,
            peak_balance REAL,
            drawdown REAL,
            risk_score REAL
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS risk_config (
            id INTEGER PRIMARY KEY,
            param_name TEXT UNIQUE,
            param_value TEXT
        )
        ''')
        
        conn.commit()
        conn.close()



    def _get_initial_balance(self):
        """Získá počáteční zůstatek účtu"""
        return self.exchange.get_portfolio_value()

    def evaluate(self, signal, confidence):
        """Hlavní metoda pro hodnocení rizika obchodu"""
        risk_assessment = {
            'approved': False,
            'amount': 0.0,
            'stop_loss': None,
            'take_profit': None,
            'reason': ''
        }

        try:
            # 1. Kontrola základních parametrů
            if not signal or confidence < self.config['strategies']['ml_strategy']['confidence_threshold']:
                risk_assessment['reason'] = 'Nízká důvěra modelu'
                return risk_assessment

            # 2. Výpočet aktuálního zůstatku a drawdownu
            current_balance = self.exchange.get_portfolio_value()
            self._update_drawdown(current_balance)
            
            # 3. Kontrola maximálního povoleného drawdownu
            max_drawdown = float(self.config['risk_management']['max_drawdown'].strip('%')) / 100
            if self.current_drawdown > max_drawdown:
                risk_assessment['reason'] = f'Maximální drawdown překročen: {self.current_drawdown*100:.2f}%'
                return risk_assessment

            # 4. Výpočet velikosti pozice
            current_price = self.exchange.get_current_price(f"{self.config['base_currency']}/USDT")
            position_size = self._calculate_position_size(current_balance, current_price)
            
            # 5. Nastavení stop-loss a take-profit
            stop_loss_pct = float(self.config['risk_management']['stop_loss'].strip('%')) / 100
            take_profit_pct = float(self.config['risk_management']['take_profit'].strip('%')) / 100
            
            risk_assessment.update({
                'approved': True,
                'amount': position_size,
                'stop_loss': current_price * (1 - stop_loss_pct),
                'take_profit': current_price * (1 + take_profit_pct)
            })
            
            # 6. Záznam metrik do databáze
            self._log_risk_metrics(current_balance)
            
        except Exception as e:
            self.logger.error(f"Chyba při hodnocení rizika: {str(e)}")
            risk_assessment['reason'] = str(e)
        
        return risk_assessment

    def _calculate_position_size(self, balance, price):
        """Vypočítá bezpečnou velikost pozice"""
        max_risk = float(self.config['risk_management']['max_trade_size'])
        return min(balance * max_risk / price, balance * max_risk)

    def _update_drawdown(self, current_balance):
        """Aktualizuje hodnotu maximálního drawdownu"""
        self.peak_balance = max(self.peak_balance, current_balance)
        self.current_drawdown = abs(self.peak_balance - current_balance) / self.peak_balance

    def _log_risk_metrics(self, current_balance):
        """Ukládá metriky rizik do databáze"""
        try:
            conn = sqlite3.connect(
                'data/trading_history.db',
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
            )
            cursor = conn.cursor()
            
            cursor.execute('''
            INSERT INTO risk_metrics 
            (timestamp, current_balance, peak_balance, drawdown)
            VALUES (?, ?, ?, ?)
            ''', (
                datetime.now(),
                current_balance,
                self.peak_balance,
                self.current_drawdown
            ))
            
            conn.commit()
            conn.close()
        except Exception as e:
            self.logger.error(f"Chyba při ukládání metrik: {str(e)}")


    def reset_risk_parameters(self):
        """Resetuje risk management do výchozího stavu"""
        self.peak_balance = self._get_initial_balance()
        self.current_drawdown = 0.0
        self.logger.info("Risk parametry resetovány do výchozího stavu")
