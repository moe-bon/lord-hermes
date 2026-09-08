from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
app = FastAPI(title="apexquant-config-validation-core")
@app.get("/healthz")
def healthz(): return {"status": "ok"}
@app.get("/readyz")
def readyz(): return {"ready": True}
@app.get("/metrics")
def metrics(): return PlainTextResponse("# metrics stub\n")
