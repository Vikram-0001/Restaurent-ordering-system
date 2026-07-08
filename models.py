from typing import Annotated, List, Dict, Optional, TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field

class OrderItem(BaseModel):
    item: str
    qty: int

class CurrentOrder(BaseModel):
    order_id: Optional[int] = None
    customer_thread_id: str = ""
    items: List[OrderItem] = Field(default_factory=list)
    status: str = "DRAFT"
    manager_note: str = ""

class ManagerDecision(BaseModel):
    decision: str
    note: str = ""

class AgentState(TypedDict):


   # Conversation history
    messages: Annotated[List[BaseMessage], add_messages]

    # Current order being worked on
    current_order: CurrentOrder

    # Whether graph should go to manager approval
    pending_approval: bool

    # Current customer thread
    customer_thread_id: str

    # Last tool output
    tool_result: Dict

    # Final response
    response: str

DEFAULT_STATE: AgentState = {
    "messages": [],
    "current_order": CurrentOrder(),
    "pending_approval": False,
    "customer_thread_id": "",
    "tool_result": {},
    "response": "",
}