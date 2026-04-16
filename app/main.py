from fastapi import FastAPI
import os

app = FastAPI(title="FastAPI Blue-Green Demo")

APP_VERSION = os.getenv("APP_VERSION", "v2.0.0")
APP_COLOR = os.getenv("APP_COLOR", "blue")


@app.get("/")
def root():
    return {
        "message": "FastAPI Blue-Green Deployment Demo",
        "version": APP_VERSION,
        "color": APP_COLOR,
    }


@app.get("/health")
def health():
    return {"status": "healthy", "version": APP_VERSION, "color": APP_COLOR}


@app.get("/info")
def info():
    return {
        "app": "fastapi-blue-green",
        "version": APP_VERSION,
        "color": APP_COLOR,
        "pod_name": os.getenv("POD_NAME", "unknown"),
        "namespace": os.getenv("POD_NAMESPACE", "unknown"),
    }
