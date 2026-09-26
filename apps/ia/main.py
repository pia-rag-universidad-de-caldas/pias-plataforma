from fastapi import FastAPI

app = FastAPI(title="Servicio IA PIAs")


@app.get("/salud")
def salud():
    return {"estado": "ok"}
