# from fastapi import FastAPI
# from fastapi.middleware.cors import CORSMiddleware
# from backend.api.chat import router as chat_router
#
# app = FastAPI(title="企业智能知识库", version="0.1.0")
#
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )
#
# app.include_router(chat_router, prefix="/api")
#
# @app.get("/")
# def root():
#     return {"status": "ok", "message": "企业智能知识库后端运行中"}
#
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)