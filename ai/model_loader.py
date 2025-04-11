# ai/model_loader.py
import tensorflow as tf

class ModelLoader:
    def __init__(self, model_path):
        self.model_path = model_path
        
    def load(self):
        return tf.keras.models.load_model(self.model_path)
