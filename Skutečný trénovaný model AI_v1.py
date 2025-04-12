# create_model.py
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense
import os

# Vytvoření adresáře pro modely
os.makedirs("ai/models", exist_ok=True)

# Jednoduchá LSTM architektura
model = Sequential([
    LSTM(64, input_shape=(60, 1), return_sequences=True),
    LSTM(32),
    Dense(1, activation='sigmoid')
])

model.compile(optimizer='adam', loss='binary_crossentropy')
model.save("ai/models/prod_model_v1.h5")
print("Základní model vytvořen!")
