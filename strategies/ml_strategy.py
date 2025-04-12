import numpy as np
import pandas as pd
import logging
import os
import sqlite3
import time
from datetime import datetime
from core.data_processor import DataProcessor
from tensorflow.keras.models import load_model

class MLStrategy:
    def __init__(self, model_path: str, **kwargs):
        self.logger = logging.getLogger(__name__)
        self.config = kwargs
        self.model_path = model_path
        self.data_processor = DataProcessor(self.config)
        
        # Inicializace proměnných pro kontrolu aktualizací
        self.last_model_check = time.time()
        self.model_version = None
        
        self.model = self._load_model()
        
        # Extrakce parametrů z konfigurace
        self.confidence_threshold = self.config.get('confidence_threshold', 0.7)
        self.lookback_window = self.config.get('lookback_window', 60)
        self.timeframe = self.config.get('timeframe', '15m')
        self.dynamic_threshold = self.config.get('dynamic_threshold', True)
        
        # Inicializace databáze pro ukládání predikci
        self._init_database()
        
        self.logger.info(f"ML Strategie inicializována s thresholdem {self.confidence_threshold}")

    def _init_database(self):
        """Inicializace databáze pro ukládání predikcí a signálů"""
        conn = sqlite3.connect('data/trading_history.db')
        cursor = conn.cursor()
        
        # Tabulka pro predikce modelu
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS model_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME,
            symbol TEXT,
            prediction REAL,
            confidence REAL,
            signal TEXT
        )
        ''')
        
        conn.commit()
        conn.close()

    def _load_model(self):
        """Načte model z disku"""
        try:
            model = load_model(self.model_path)
            self.model_version = os.path.getmtime(self.model_path)
            self.logger.info(f"Model {self.model_path} úspěšně načten")
            return model
        except Exception as e:
            self.logger.error(f"Chyba při načítání modelu: {str(e)}")
            raise

    def analyze(self, data):
        """Provede predikci a vrátí strukturovaný výsledek"""
        try:
            if len(data) < 180:
                return {
                    'signal': 'HOLD',
                    'confidence': 0.0,
                    'error': 'Nedostatek dat pro analýzu: potřebováno 180 svíček'
                }

            processed_data = self.preprocess_data(data)
            prediction = self.model.predict(processed_data)[0][0]
            
            return {
                'signal': 'BUY' if prediction > 0.5 else 'SELL',
                'confidence': abs(prediction - 0.5) * 2,
                'error': None
            }
            
        except Exception as e:
            return {
                'signal': 'HOLD',
                'confidence': 0.0,
                'error': f"Chyba v analýze: {str(e)}"
            }


    def _preprocess_data(self, raw_data):
        """Předzpracování dat pro predikční model"""
        return self.data_processor.process_data(raw_data)

    def _interpret_prediction(self, prediction):
        """Interpretace hodnoty predikce na obchodní signál"""
        threshold = self.confidence_threshold
        
        if self.dynamic_threshold:
            threshold = max(threshold, prediction * 0.9)
            
        if prediction > threshold:
            return "BUY"
        elif prediction < (1 - threshold):
            return "SELL"
        return "HOLD"

    def _save_prediction(self, prediction, symbol=None):
        """Uloží predikci do databáze"""
        if not symbol:
            symbol = "UNKNOWN"
            
        try:
            conn = sqlite3.connect('data/trading_history.db')
            cursor = conn.cursor()
            
            cursor.execute(
                """
                INSERT INTO model_predictions (timestamp, symbol, prediction, confidence, signal)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(),
                    symbol,
                    float(prediction),
                    abs(float(prediction) - 0.5) * 2,  # Převod na confidence 0-1
                    "BUY" if prediction > 0.5 else "SELL"
                )
            )
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Chyba při ukládání predikce: {str(e)}")

    def _save_decision(self, signal, prediction, symbol=None):
        """Uloží rozhodnutí do databáze"""
        if not symbol:
            symbol = "UNKNOWN"
            
        try:
            conn = sqlite3.connect('data/trading_history.db')
            cursor = conn.cursor()
            
            # Kontrola, zda tabulka decisions existuje
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME,
                symbol TEXT,
                signal TEXT,
                confidence REAL,
                action_taken TEXT
            )
            ''')
            
            # Uložení rozhodnutí
            cursor.execute(
                """
                INSERT INTO decisions (timestamp, symbol, signal, confidence, action_taken)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(),
                    symbol,
                    signal,
                    abs(float(prediction) - 0.5) * 2,  # Převod na confidence 0-1
                    "Pending"
                )
            )
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Chyba při ukládání rozhodnutí: {str(e)}")

    def check_for_updates(self):
        """Kontroluje, zda je k dispozici novější verze modelu"""
        if not hasattr(self, 'last_model_check'):
            self.last_model_check = time.time()
            return
            
        if time.time() - self.last_model_check > 300:  # Kontrola každých 5 minut
            try:
                current_version = os.path.getmtime(self.model_path)
                if current_version != self.model_version:
                    self.logger.info(f"Detekována aktualizace modelu: {self.model_path}")
                    self.model = self._load_model()
            except Exception as e:
                self.logger.error(f"Chyba při kontrole aktualizací: {str(e)}")
            finally:
                self.last_model_check = time.time()

    def get_params(self):
        """Vrátí aktuální parametry strategie"""
        return {
            'model_path': self.model_path,
            'confidence_threshold': self.confidence_threshold,
            'timeframe': self.timeframe,
            'lookback_window': self.lookback_window,
            'dynamic_threshold': self.dynamic_threshold
        }

    def set_params(self, **params):
        """Nastaví parametry strategie"""
        for key, value in params.items():
            if hasattr(self, key):
                setattr(self, key, value)
                
        # Pokud se změnila cesta k modelu, znovu načteme model
        if 'model_path' in params:
            self._load_model()
            
        self.logger.info(f"Parametry strategie aktualizovány: {params}")
