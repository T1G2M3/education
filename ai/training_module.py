# ai/training_module.py
import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.preprocessing import MinMaxScaler

class ModelTrainer:
    def __init__(self):
        self.scaler = MinMaxScaler(feature_range=(0, 1))
        self.model = self.build_model()

    def build_model(self):
        model = tf.keras.Sequential([
            tf.keras.layers.LSTM(64, return_sequences=True, input_shape=(60, 1)),
            tf.keras.layers.Dropout(0.2),
            tf.keras.layers.LSTM(32),
            tf.keras.layers.Dense(1, activation='sigmoid')
        ])
        
        model.compile(
            optimizer='adam',
            loss='binary_crossentropy',
            metrics=['accuracy']
        )
        return model

    def preprocess_data(self, data):
        scaled = self.scaler.fit_transform(data)
        X, y = [], []
        
        for i in range(60, len(scaled)):
            X.append(scaled[i-60:i])
            y.append(1 if data.iloc[i] > data.iloc[i-1] else 0)
            
        return np.array(X), np.array(y)

    def train(self, historical_data, epochs=50):
        X, y = self.preprocess_data(historical_data)
        self.model.fit(X, y, epochs=epochs, validation_split=0.2)
        self.model.save('ai/models/prod_model_v1.h5')
