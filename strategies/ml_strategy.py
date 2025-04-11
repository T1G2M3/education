import numpy as np
import pandas as pd
import talib
import logging
import os
import time
from core.data_processor import DataProcessor
from tensorflow.keras.models import load_model

class MLStrategy:
    def __init__(self, model_path: str, **kwargs):
        self.logger = logging.getLogger(__name__)
        self.config = kwargs  # Uložení celé konfigurace
        self.model_path = model_path
        self.data_processor = DataProcessor(self.config)  # Předání konfigurace
        
        # Inicializace proměnných pro kontrolu aktualizací
        self.last_model_check = time.time()
        self.model_version = None
        
        self.model = self._load_model()
        
        # Extrakce parametrů z konfigurace
        self.confidence_threshold = self.config.get('confidence_threshold', 0.7)
        self.lookback_window = self.config.get('lookback_window', 60)
        self.timeframe = self.config.get('timeframe', '15m')  
        self.dynamic_threshold = self.config.get('dynamic_threshold', True) 

    def _load_model(self):
        try:
            model = load_model(self.model_path)
            self.model_version = os.path.getmtime(self.model_path)
            self.logger.info(f"Model {self.model_path} úspěšně načten")
            return model
        except Exception as e:
            self.logger.error(f"Chyba při načítání modelu: {str(e)}")
            raise

    def analyze(self, data):
        try:
            if len(data) < self.lookback_window * 2:
                self.logger.warning("Nedostatek dat pro analýzu")
                return "HOLD"
                
            processed_data = self._preprocess_data(data)
            
            # Kontrola, zda processed_data není prázdné
            if processed_data.size == 0:
                self.logger.warning("Zpracovaná data jsou prázdná")
                return "HOLD"
                
            prediction = self.model.predict(processed_data, verbose=0)
            
            # Ověření, že prediction není prázdné
            if len(prediction) == 0:
                return "HOLD"
                
            return self._interpret_prediction(prediction[-1][0])
            
        except Exception as e:
            self.logger.error(f"Chyba v analyze: {str(e)}")
            return "HOLD"

    def _preprocess_data(self, raw_data):
        # Důležitá oprava - metoda process_data už vrací správný tvar pro model
        processed_data = self.data_processor.process_data(raw_data)
        return processed_data  # Už nepotřebujeme další transformaci

    def _interpret_prediction(self, prediction):
        threshold = self.confidence_threshold
        if self.dynamic_threshold:
            threshold = max(threshold, prediction * 0.9)
            
        if prediction > threshold:
            return "BUY"
        elif prediction < (1 - threshold):
            return "SELL"
        return "HOLD"

    def check_for_updates(self):
        if not hasattr(self, 'last_model_check'):
            self.last_model_check = time.time()
            return
            
        if time.time() - self.last_model_check > 300:
            try:
                current_version = os.path.getmtime(self.model_path)
                if current_version != self.model_version:
                    self.logger.info("Detekována aktualizace modelu")
                    self.model = self._load_model()
            except Exception as e:
                self.logger.error(f"Chyba při kontrole aktualizací: {str(e)}")
            finally:
                self.last_model_check = time.time()

    def get_params(self):
        return {
            'model_path': self.model_path,
            'confidence_threshold': self.confidence_threshold,
            'timeframe': self.timeframe,
            'lookback_window': self.lookback_window,
            'dynamic_threshold': self.dynamic_threshold
        }

    def set_params(self, **params):
        for key, value in params.items():
            if hasattr(self, key):
                setattr(self, key, value)
