import sqlite3
import json
import threading
import time
from datetime import datetime
from typing import List, Dict, Optional

DATABASE_NAME = "restaurant.db"

def transition_to_cooked(order_id: int):
    time.sleep(60)
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            UPDATE orders
            SET status = 'COOKED', updated_at = ?
            WHERE order_id = ? AND status = 'APPROVED'
        """, (now_str, order_id))
        conn.commit()
        if cursor.rowcount > 0:
            print(f"\n\n[System Notice] Order {order_id} is now COOKED! (1 minute has elapsed since approval)\nCustomer: ", end="", flush=True)
    except Exception as e:
        print("Cooking transition failed:", e)
    finally:
        conn.close()

def schedule_cooking(order_id: int):
    t = threading.Thread(target=transition_to_cooked, args=(order_id,), daemon=True)
    t.start()

def get_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def create_tables():
    conn = get_connection()
    cursor = conn.cursor()

    # -------------------------
    # Menu Table
    # -------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS menu (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            price REAL NOT NULL,
            available_qty INTEGER NOT NULL,
            is_active INTEGER DEFAULT 1
        )
    """)
    # -------------------------
    # Orders Table
    # -------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_thread_id TEXT NOT NULL,
            items TEXT NOT NULL,
            status TEXT NOT NULL,
            manager_note TEXT,
            inventory_deducted INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.commit()
    conn.close()

DEFAULT_MENU = [
    {
        "name": "Burger",
        "price": 120,
        "available_qty": 20
    },
    {
        "name": "Pizza",
        "price": 250,
        "available_qty": 15
    },
    {
        "name": "Fries",
        "price": 90,
        "available_qty": 30
    },
    {
        "name": "Coke",
        "price": 50,
        "available_qty": 40
    },
    {
        "name": "Coffee",
        "price": 80,
        "available_qty": 25
    }
]
# ============================================================
# INSERT DEFAULT MENU
# ============================================================

def seed_menu():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM menu")
    count = cursor.fetchone()[0]
    if count == 0:
        for item in DEFAULT_MENU:
            cursor.execute("""
                INSERT INTO menu
                (name, price, available_qty)
                VALUES (?, ?, ?)
            """, (
                item["name"],
                item["price"],
                item["available_qty"]
            ))
    conn.commit()
    conn.close()
# ============================================================
# DATABASE INITIALIZATION
# ============================================================
def initialize_database():
    create_tables()
    seed_menu()

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
if __name__ == "__main__":

    initialize_database()

    print("Database initialized successfully.")

def get_menu():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT *
        FROM menu
        WHERE is_active = 1
        ORDER BY name
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_item(item_name: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT *
        FROM menu
        WHERE LOWER(name)=LOWER(?)
        AND is_active=1
    """, (item_name,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def check_item_availability(item_name: str, qty: int):
    item = get_item(item_name)
    if item is None:
        return False, f"{item_name} is not available on the menu."
    if item["available_qty"] <= 0:
        return False, f"{item_name} is currently out of stock."
    if qty > item["available_qty"]:
        return (
            False,
            f"Only {item['available_qty']} {item_name}(s) are available."
        )
    return True, "Available"

def check_order_feasibility(items: List[Dict]):
    total_price = 0
    for order_item in items:
        item_name = order_item["item"]
        qty = order_item["qty"]
        ok, reason = check_item_availability(item_name, qty)
        if not ok:
            return {
                "success": False,
                "message": reason
            }
        menu_item = get_item(item_name)
        total_price += menu_item["price"] * qty
    return {
        "success": True,
        "message": "Order is feasible.",
        "total_price": total_price
    }

def deduct_inventory(items: List[Dict]):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        for order_item in items:
            cursor.execute("""
                UPDATE menu
                SET available_qty = available_qty - ?
                WHERE LOWER(name)=LOWER(?)
            """, (
                order_item["qty"],
                order_item["item"]
            ))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print("Inventory deduction failed:", e)
        return False
    finally:
        conn.close()

def restore_inventory(items: List[Dict]):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        for order_item in items:
            cursor.execute("""
                UPDATE menu
                SET available_qty = available_qty + ?
                WHERE LOWER(name)=LOWER(?)
            """, (
                order_item["qty"],
                order_item["item"]
            ))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print("Inventory restoration failed:", e)
        return False
    finally:
        conn.close()

def print_menu():
    menu = get_menu()
    print("\n========== MENU ==========")
    for item in menu:
        print(
            f"{item['name']:10}"
            f" ₹{item['price']:4} "
            f"Stock:{item['available_qty']}"
        )
    print("==========================\n")

def create_order(customer_thread_id: str, items: List[Dict]) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    items_json = json.dumps(items)
    cursor.execute("""
        INSERT INTO orders (customer_thread_id, items, status, inventory_deducted, created_at, updated_at)
        VALUES (?, ?, ?, 0, ?, ?)
    """, (customer_thread_id, items_json, "DRAFT", now_str, now_str))
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return order_id

def get_order(order_id: int) -> Optional[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        res = dict(row)
        res["items"] = json.loads(res["items"])
        return res
    return None

def get_latest_order_by_thread(customer_thread_id: str) -> Optional[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM orders 
        WHERE customer_thread_id = ? 
        ORDER BY order_id DESC LIMIT 1
    """, (customer_thread_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        res = dict(row)
        res["items"] = json.loads(res["items"])
        return res
    return None

def get_order_status(order_id: int) -> Optional[str]:
    order = get_order(order_id)
    if order:
        return order["status"]
    return None

def modify_order(order_id: int, items: List[Dict]) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False
    
    order = dict(row)
    current_status = order["status"]
    inventory_deducted = order["inventory_deducted"]
    old_items = json.loads(order["items"])
    
    try:
        # If inventory was deducted, restore it first (regardless of status, e.g. APPROVED or COOKED)
        if inventory_deducted == 1:
            restore_success = restore_inventory(old_items)
            if not restore_success:
                conn.close()
                return False
            cursor.execute("""
                UPDATE orders 
                SET inventory_deducted = 0 
                WHERE order_id = ?
            """, (order_id,))
            
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        items_json = json.dumps(items)
        
        # Modify the order items and reset status to DRAFT
        cursor.execute("""
            UPDATE orders
            SET items = ?, status = ?, updated_at = ?
            WHERE order_id = ?
        """, (items_json, "DRAFT", now_str, order_id))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print("Order modification failed:", e)
        return False
    finally:
        conn.close()

def update_order_status(order_id: int, status: str, manager_note: str = "") -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False
    
    order = dict(row)
    current_status = order["status"]
    items = json.loads(order["items"])
    inventory_deducted = order["inventory_deducted"]
    
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        should_schedule = (status == "APPROVED" and inventory_deducted == 0)
        
        # If transitioning to APPROVED and inventory not yet deducted
        if status == "APPROVED" and inventory_deducted == 0:
            # Check feasibility
            feasibility = check_order_feasibility(items)
            if not feasibility["success"]:
                conn.close()
                return False
            
            # Deduct inventory
            deduct_success = deduct_inventory(items)
            if not deduct_success:
                conn.close()
                return False
            
            cursor.execute("""
                UPDATE orders
                SET status = ?, manager_note = ?, inventory_deducted = 1, updated_at = ?
                WHERE order_id = ?
            """, (status, manager_note if manager_note else order["manager_note"], now_str, order_id))
            
        # If moving AWAY from APPROVED and COOKED (e.g. to REJECTED or PENDING_APPROVAL) and inventory was deducted, restore it
        elif status not in ("APPROVED", "COOKED") and inventory_deducted == 1:
            restore_success = restore_inventory(items)
            if not restore_success:
                conn.close()
                return False
            
            cursor.execute("""
                UPDATE orders
                SET status = ?, manager_note = ?, inventory_deducted = 0, updated_at = ?
                WHERE order_id = ?
            """, (status, manager_note if manager_note else order["manager_note"], now_str, order_id))
        else:
            # Standard transition
            cursor.execute("""
                UPDATE orders
                SET status = ?, manager_note = ?, updated_at = ?
                WHERE order_id = ?
            """, (status, manager_note if manager_note else order["manager_note"], now_str, order_id))
            
        conn.commit()
        if should_schedule:
            schedule_cooking(order_id)
        return True
    except Exception as e:
        conn.rollback()
        print("Status update failed:", e)
        return False
    finally:
        conn.close()