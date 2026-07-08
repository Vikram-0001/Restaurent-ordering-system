from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt
from langchain_core.messages import SystemMessage
from models import AgentState, CurrentOrder, OrderItem
from tools import get_menu, check_item_availability, check_order_feasibility, create_order, modify_order, get_order_status, update_order_status
from config import llm
from prompts import SYSTEM_PROMPT
import db

# List of tools for ToolNode and binding
tools = [
    get_menu,
    check_item_availability,
    check_order_feasibility,
    create_order,
    modify_order,
    get_order_status,
    update_order_status
]

tools_node = ToolNode(tools)

def agent_node(state: AgentState, config):
    thread_id = config["configurable"].get("thread_id", "customer_001")
    
    # Sync current order state from DB
    db_order = db.get_latest_order_by_thread(thread_id)
    current_order = state.get("current_order")
    if not current_order:
        current_order = CurrentOrder(customer_thread_id=thread_id)
        
    if db_order:
        current_order.order_id = db_order["order_id"]
        current_order.customer_thread_id = db_order["customer_thread_id"]
        current_order.status = db_order["status"]
        current_order.manager_note = db_order["manager_note"] or ""
        current_order.items = [OrderItem(item=item["item"], qty=item["qty"]) for item in db_order["items"]]

    # Build prompt dynamically ensuring the agent knows the active customer thread ID
    clean_messages = []
    for m in state["messages"]:
        if isinstance(m, SystemMessage) and "You are a helpful, professional" in m.content:
            continue
        clean_messages.append(m)
        
    system_prompt = SYSTEM_PROMPT + f"\n\nIMPORTANT: Use this customer thread ID for all order-related tool calls: {thread_id}"
    messages = [SystemMessage(content=system_prompt)] + clean_messages
    
    bound_llm = llm.bind_tools(tools)
    response = bound_llm.invoke(messages)
    
    return {
        "messages": [response],
        "current_order": current_order,
        "customer_thread_id": thread_id
    }

def manager_review_node(state: AgentState):
    current_order = state["current_order"]
    order_id = current_order.order_id
    
    # Suspend execution for manager approval
    resume_data = interrupt({
        "order_id": order_id,
        "items": [item.dict() for item in current_order.items],
        "status": current_order.status,
        "message": f"Order {order_id} requires manager approval."
    })
    
    # Process manager's input
    return {
        "tool_result": {
            "order_id": order_id,
            "decision": resume_data.get("decision"),
            "note": resume_data.get("note", "")
        },
        "pending_approval": False
    }

def update_order_status_node(state: AgentState):
    tool_result = state.get("tool_result") or {}
    order_id = tool_result.get("order_id")
    decision = tool_result.get("decision")
    note = tool_result.get("note", "")
    
    if order_id and decision:
        success = db.update_order_status(order_id, decision, note)
        
        status_msg = f"System Notice: Manager has {decision} the order {order_id}."
        if note:
            status_msg += f" Note from manager: '{note}'"
            
        if not success:
            status_msg = f"System Error: Failed to update order {order_id} to {decision}. Check inventory levels."

        # Re-sync current order state
        db_order = db.get_order(order_id)
        if db_order:
            state["current_order"].status = db_order["status"]
            state["current_order"].manager_note = db_order["manager_note"] or ""
            
        return {
            "messages": [SystemMessage(content=status_msg)],
            "current_order": state["current_order"]
        }
    return {}

def route_agent(state: AgentState):
    messages = state["messages"]
    last_message = messages[-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "__end__"

def route_after_tools(state: AgentState, config):
    thread_id = config["configurable"].get("thread_id", "customer_001")
    db_order = db.get_latest_order_by_thread(thread_id)
    if db_order and db_order["status"] == "PENDING_APPROVAL":
        return "manager_review"
    return "agent"

# Build Graph
workflow = StateGraph(AgentState)

workflow.add_node("agent", agent_node)
workflow.add_node("tools", tools_node)
workflow.add_node("manager_review", manager_review_node)
workflow.add_node("update_order_status_node", update_order_status_node)

workflow.set_entry_point("agent")

workflow.add_conditional_edges(
    "agent",
    route_agent,
    {
        "tools": "tools",
        "__end__": "__end__"
    }
)

workflow.add_conditional_edges(
    "tools",
    route_after_tools,
    {
        "manager_review": "manager_review",
        "agent": "agent"
    }
)

workflow.add_edge("manager_review", "update_order_status_node")
workflow.add_edge("update_order_status_node", "agent")

memory = MemorySaver()
graph = workflow.compile(checkpointer=memory)
