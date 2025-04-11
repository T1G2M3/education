# ai/prediction_api.py
from fastapi import FastAPI
from pydantic import BaseModel
from ai.model_loader import ModelLoader
import numpy as np

app = FastAPI()

class PredictionRequest(BaseModel):
    data: list

class PredictionAPI:
    def __init__(self, model_path='ai/models/prod_model_v1.h5'):
        self.model = ModelLoader(model_path).load()
        
    async def predict(self, data):
        processed_data = self.preprocess(data)
        prediction = self.model.predict(processed_data)
        return {"prediction": float(prediction[0][0])}
    
    def preprocess(self, raw_data):
        return np.array(raw_data).reshape(1, -1)

@app.post("/predict")
async def predict_endpoint(request: PredictionRequest):
    api = PredictionAPI()
    return await api.predict(request.data)
