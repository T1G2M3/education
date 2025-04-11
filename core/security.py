# core/security.py
from decouple import config

API_KEY = config('BINANCE_API_KEY')
API_SECRET = config('BINANCE_API_SECRET')

def encrypt_credentials():
    from cryptography.fernet import Fernet
    key = Fernet.generate_key()
    cipher = Fernet(key)
    encrypted = cipher.encrypt(f"{API_KEY}:{API_SECRET}".encode())
    
    with open("config/secrets.key", "wb") as f:
        f.write(key)
    
    with open("config/secrets.enc", "wb") as f:
        f.write(encrypted)
