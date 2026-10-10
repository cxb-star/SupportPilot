"""FastAPI 入口：集中加载配置、初始化 SQLite、注册路由与静态 demo。"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from config import BASE_DIR, settings
from logging_config import setup_logging
from store.session import init_db

setup_logging(getattr(logging, settings.LOG_LEVEL, logging.INFO))
init_db(settings.SQLITE_PATH)

app = FastAPI(title="Agent Knowledge Service", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.routes import router

from fastapi import Request
from fastapi.responses import JSONResponse

app.include_router(router)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    import logging
    logging.getLogger("app").exception("unhandled_exception error=%s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})



@app.get("/")
def index() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
