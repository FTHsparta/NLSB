from fastapi import FastAPI

app = FastAPI(title="NLSB API")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
