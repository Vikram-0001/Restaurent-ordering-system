import sys
import os
import json
import sqlite3
from typing import List, Dict, Optional
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import db
from graph import graph
from models import AgentState, CurrentOrder, OrderItem
from langchain_core.messages import HumanMessage
from langgraph.types import Command

app = FastAPI(
    title="AI Restaurant API",
    description="Backend API for AI Restaurant Ordering & Manager Approval System",
    version="1.0.0"
)

# Enable CORS for frontend flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup: Initialize the database
@app.on_event("startup")
def startup_event():
    db.initialize_database()
    print("Database initialized and seeded.")

# Request / Response Schemas
class ChatRequest(BaseModel):
    thread_id: str
    message: str

class ChatResponse(BaseModel):
    response: str
    is_pending_approval: bool
    order_id: Optional[int] = None

class ClearRequest(BaseModel):
    thread_id: str

class DecisionRequest(BaseModel):
    order_id: int
    thread_id: str
    note: Optional[str] = ""

class MenuItemResponse(BaseModel):
    item_id: int
    name: str
    price: float
    available_qty: int
    is_active: int

# ============================================================
# API Endpoints
# ============================================================

@app.get("/api/menu", response_model=List[MenuItemResponse], tags=["Menu"])
def get_menu():
    """Retrieves all active items on the restaurant menu."""
    try:
        return db.get_menu()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/customer/chat", response_model=ChatResponse, tags=["Customer"])
def customer_chat(req: ChatRequest):
    """Sends a chat message to the AI Restaurant Assistant for a specific thread."""
    config = {"configurable": {"thread_id": req.thread_id}}
    try:
        # Run the graph
        list(graph.stream(
            {"messages": [HumanMessage(content=req.message)]},
            config,
            stream_mode="values"
        ))
    except Exception as e:
        if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
            raise HTTPException(status_code=429, detail="Gemini API rate limit exceeded. Please wait a few seconds and try again.")
        raise HTTPException(status_code=500, detail=f"Graph stream error: {str(e)}")

    # Inspect graph state to check for interrupts
    state = graph.get_state(config)
    is_pending = False
    order_id = None
    
    if state.next and len(state.tasks) > 0 and state.tasks[0].interrupts:
        is_pending = True
        interrupt_val = state.tasks[0].interrupts[0].value
        order_id = interrupt_val.get("order_id")
    
    # Also double-check latest order in db to check if it's PENDING_APPROVAL
    latest_order = db.get_latest_order_by_thread(req.thread_id)
    if latest_order and latest_order["status"] == "PENDING_APPROVAL":
        is_pending = True
        order_id = latest_order["order_id"]

    # Extract final assistant response from messages
    messages = state.values.get("messages", [])
    response_text = "I received your message, but failed to compile a response."
    if messages:
        ai_msg = next((m for m in reversed(messages) if m.type == "ai"), None)
        if ai_msg:
            content = ai_msg.content
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
                        elif "text" in part:
                            text_parts.append(part["text"])
                    elif isinstance(part, str):
                        text_parts.append(part)
                content = "".join(text_parts)
            if content.strip():
                response_text = content

    return ChatResponse(
        response=response_text,
        is_pending_approval=is_pending,
        order_id=order_id
    )

@app.get("/api/customer/chat-history/{thread_id}", tags=["Customer"])
def get_chat_history(thread_id: str):
    """Retrieves all chat messages for a specific customer thread from the LangGraph checkpointer."""
    try:
        config = {"configurable": {"thread_id": thread_id}}
        state = graph.get_state(config)
        messages = state.values.get("messages", [])
        
        chat_history = []
        for msg in messages:
            if msg.type == "system":
                if "You are a helpful, professional" in msg.content or "SYSTEM_PROMPT" in msg.content:
                    continue
                chat_history.append({"role": "system", "content": msg.content})
            elif msg.type == "human":
                chat_history.append({"role": "user", "content": msg.content})
            elif msg.type == "ai":
                content = msg.content
                if isinstance(content, list):
                    text_parts = []
                    for part in content:
                        if isinstance(part, dict):
                            if part.get("type") == "text":
                                text_parts.append(part.get("text", ""))
                            elif "text" in part:
                                text_parts.append(part["text"])
                        elif isinstance(part, str):
                            text_parts.append(part)
                    content = "".join(text_parts)
                
                if content.strip():
                    chat_history.append({"role": "assistant", "content": content})
                    
        return chat_history
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/customer/clear-chat", tags=["Customer"])
def clear_chat(req: ClearRequest):
    """Deletes conversation history and state for the given customer thread."""
    try:
        if hasattr(graph, "checkpointer") and hasattr(graph.checkpointer, "delete_thread"):
            graph.checkpointer.delete_thread(req.thread_id)
            return {"status": "success", "message": f"Chat history cleared for thread {req.thread_id}"}
        
        # If delete_thread is not available, we can just delete from the database checkpointer table if applicable,
        # but since LangGraph MemorySaver is in-memory, we can't easily selectively delete without delete_thread.
        # We will report success if it ran.
        return {"status": "warning", "message": "In-memory checkpointer cannot clear history without delete_thread method."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/customer/order-history/{thread_id}", tags=["Customer"])
def get_customer_order_history(thread_id: str):
    """Retrieves all past orders submitted by this customer thread."""
    conn = db.get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT * FROM orders WHERE customer_thread_id = ? ORDER BY order_id DESC",
            (thread_id,)
        )
        rows = cursor.fetchall()
        orders = []
        for row in rows:
            d = dict(row)
            d["items"] = json.loads(d["items"])
            orders.append(d)
        return orders
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get("/api/manager/pending-orders", tags=["Manager"])
def get_pending_orders():
    """Retrieves all orders currently awaiting approval from the manager."""
    conn = db.get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT * FROM orders WHERE status = 'PENDING_APPROVAL' ORDER BY order_id DESC"
        )
        rows = cursor.fetchall()
        orders = []
        for row in rows:
            d = dict(row)
            d["items"] = json.loads(d["items"])
            orders.append(d)
        return orders
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.post("/api/manager/approve", tags=["Manager"])
def approve_order(req: DecisionRequest):
    """Approves a pending order, resumes the LangGraph flow, and deducts inventory."""
    config = {"configurable": {"thread_id": req.thread_id}}
    state = graph.get_state(config)
    
    # Check if there is an active interrupt in the workflow
    if state.next and len(state.tasks) > 0 and state.tasks[0].interrupts:
        try:
            list(graph.stream(
                Command(resume={"decision": "APPROVED", "note": req.note}),
                config,
                stream_mode="values"
            ))
            return {"status": "success", "message": f"Order #{req.order_id} approved. Workflow resumed."}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Workflow resume failed: {str(e)}")
    else:
        # Fallback to direct DB modification if no active graph flow
        success = db.update_order_status(req.order_id, "APPROVED", req.note)
        if success:
            return {"status": "success", "message": f"Order #{req.order_id} approved directly in database."}
        raise HTTPException(status_code=400, detail="Failed to approve order directly. Verify stock levels.")

@app.post("/api/manager/reject", tags=["Manager"])
def reject_order(req: DecisionRequest):
    """Rejects a pending order, resumes the LangGraph flow, and cancels the order."""
    config = {"configurable": {"thread_id": req.thread_id}}
    state = graph.get_state(config)
    
    # Check if there is an active interrupt in the workflow
    if state.next and len(state.tasks) > 0 and state.tasks[0].interrupts:
        try:
            list(graph.stream(
                Command(resume={"decision": "REJECTED", "note": req.note}),
                config,
                stream_mode="values"
            ))
            return {"status": "success", "message": f"Order #{req.order_id} rejected. Workflow resumed."}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Workflow resume failed: {str(e)}")
    else:
        # Fallback to direct DB modification
        success = db.update_order_status(req.order_id, "REJECTED", req.note)
        if success:
            return {"status": "success", "message": f"Order #{req.order_id} rejected directly in database."}
        raise HTTPException(status_code=400, detail="Failed to reject order directly.")

# Mount static files for HTML web UI if static folder exists
static_path = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index():
        with open(os.path.join(static_path, "index.html"), "r", encoding="utf-8") as f:
            return f.read()

    @app.get("/manager", response_class=HTMLResponse, include_in_schema=False)
    def manager_portal():
        with open(os.path.join(static_path, "manager.html"), "r", encoding="utf-8") as f:
            return f.read()
else:
    @app.get("/", include_in_schema=False)
    def root_redirect():
        return RedirectResponse(url="/docs")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
