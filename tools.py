from langchain_core.tools import tool
import db
from typing import List, Dict

@tool
def get_menu() -> str:
    """Retrieves the list of active menu items, their prices, and available stock quantities."""
    menu = db.get_menu()
    if not menu:
        return "The menu is currently empty."
    
    result = "========== MENU ==========\n"
    for item in menu:
        result += f"- {item['name']}: Rs. {item['price']} (Available: {item['available_qty']})\n"
    result += "=========================="
    return result

@tool
def check_item_availability(item_name: str, qty: int) -> str:
    """Checks if a specific quantity of a menu item is available in stock.
    
    Args:
        item_name: The name of the menu item (e.g., 'Burger', 'Pizza', 'Fries', 'Coke', 'Coffee').
        qty: The quantity requested.
    """
    available, message = db.check_item_availability(item_name, qty)
    return f"Availability: {available}. Detail: {message}"

@tool
def check_order_feasibility(items: List[Dict]) -> str:
    """Validates if the entire list of items in an order can be fulfilled from current inventory
    and calculates the total price if feasible.
    
    Args:
        items: A list of dicts, each having 'item' (str) and 'qty' (int).
               Example: [{"item": "Burger", "qty": 2}, {"item": "Coke", "qty": 1}]
    """
    res = db.check_order_feasibility(items)
    if res["success"]:
        return f"Feasibility: True. Message: {res['message']} Total Price: Rs. {res.get('total_price', 0)}"
    else:
        return f"Feasibility: False. Message: {res['message']}"

@tool
def create_order(customer_thread_id: str, items: List[Dict]) -> str:
    """Creates a new order in DRAFT status with the specified items.
    
    Args:
        customer_thread_id: The unique thread/customer identifier.
        items: A list of dicts, each having 'item' (str) and 'qty' (int).
               Example: [{"item": "Burger", "qty": 2}]
    """
    order_id = db.create_order(customer_thread_id, items)
    return f"Order created successfully. Order ID: {order_id}. Status: DRAFT. Items: {items}"

@tool
def modify_order(order_id: int, items: List[Dict]) -> str:
    """Modifies the items of an existing order. If the order was already APPROVED,
    its inventory will be restored, and its status will be reset to PENDING_APPROVAL.
    
    Args:
        order_id: The ID of the order to modify.
        items: The new list of items for the order, e.g., [{"item": "Pizza", "qty": 1}].
    """
    success = db.modify_order(order_id, items)
    if success:
        return f"Order {order_id} modified successfully. Items updated to {items}. Status reset to PENDING_APPROVAL."
    return f"Failed to modify order {order_id}. Please check if the order exists or check stock availability."

@tool
def get_order_status(order_id: int) -> str:
    """Gets the current status of an order.
    
    Args:
        order_id: The ID of the order.
    """
    status = db.get_order_status(order_id)
    if status:
        return f"Order {order_id} status: {status}."
    return f"Order {order_id} not found."

@tool
def update_order_status(order_id: int, status: str, manager_note: str = "") -> str:
    """Updates the status of an order. Setting the status to APPROVED will automatically
    deduct the items from the inventory. Setting to REJECTED will restore/not deduct items.
    
    Args:
        order_id: The ID of the order.
        status: The target status (e.g., 'PENDING_APPROVAL', 'APPROVED', 'REJECTED', 'DELIVERED').
        manager_note: Optional note from the manager.
    """
    success = db.update_order_status(order_id, status, manager_note)
    if success:
        return f"Order {order_id} status updated to {status} successfully. Note: '{manager_note}'"
    return f"Failed to update status for order {order_id}. This could be due to invalid status transition, non-existent order, or insufficient inventory to approve."
