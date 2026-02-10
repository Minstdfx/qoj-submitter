from typing import Dict, Optional, Set
import asyncio
import datetime
import uuid

from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="QOJ Submit Bridge")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConnectionManager:
    def __init__(self) -> None:
        self.active: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.active.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self.active.discard(websocket)

    async def broadcast(self, message: dict) -> None:
        dead = []
        for ws in list(self.active):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)


manager = ConnectionManager()
pending_results: Dict[str, asyncio.Future] = {}


def create_request_id() -> str:
    return uuid.uuid4().hex


def register_pending(request_id: str) -> asyncio.Future:
    fut: asyncio.Future = asyncio.get_event_loop().create_future()
    pending_results[request_id] = fut
    return fut


def resolve_pending(request_id: str, payload: dict) -> None:
    fut: Optional[asyncio.Future] = pending_results.pop(request_id, None)
    if fut and not fut.done():
        fut.set_result(payload)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        while True:
            # Keep the connection alive; client messages are ignored.
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)


@app.post("/submit")
async def submit_code(
    problem_code: str = Form(...),
    language: str = Form("C++26"),
    file: UploadFile = File(...),
) -> dict:
    request_id = create_request_id()
    raw = await file.read()
    code = raw.decode("utf-8", errors="replace")
    print("code:")
    print(code)
    payload = {
        "problemCode": problem_code,
        "language": language,
        "code": code,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "requestId": request_id,
    }
    register_pending(request_id)
    await manager.broadcast(payload)
    return {"status": "queued", "sent_to_clients": len(manager.active), "request_id": request_id}


@app.post("/submission-report")
async def submission_report(
    request_id: str = Form(...),
    sid: str = Form(...),
    surl: str = Form(...),
    stime: str = Form(...),
) -> dict:
    payload = {"sid": sid, "surl": surl, "stime": stime}
    resolve_pending(request_id, payload)
    return {"status": "ok"}


@app.get("/submission-result/{request_id}")
async def submission_result(request_id: str, timeout: float = 30.0) -> dict:
    fut = pending_results.get(request_id)
    if fut is None:
        return {"status": "unknown"}
    try:
        result = await asyncio.wait_for(fut, timeout=timeout)
        return {"status": "done", **result}
    except asyncio.TimeoutError:
        return {"status": "pending"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
