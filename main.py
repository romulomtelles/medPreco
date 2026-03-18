from fastapi import FastAPI, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from scrapers import search_all
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="MedPreço - Comparador de Remédios")

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))


@app.get("/api/search")
async def search(q: str = Query(..., min_length=2, description="Nome do medicamento")):
    if not q.strip():
        raise HTTPException(status_code=400, detail="Informe o nome do medicamento")

    results = await search_all(q.strip())

    if not results:
        return {"query": q, "results": [], "top3": [], "rest": [], "total": 0}

    return {
        "query": q,
        "results": results,
        "top3": results[:3],
        "rest": results[3:],
        "total": len(results),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
