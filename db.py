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


    # ----------------------------------
    # SCHEMAS
    # ----------------------------------

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
            total_price REAL DEFAULT 0.0,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    # -------------------------
    # Settings Table
    # -------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # Schema migration: check if total_price column exists in orders
    cursor.execute("PRAGMA table_info(orders)")
    columns = [row[1] for row in cursor.fetchall()]
    if columns and "total_price" not in columns:
        cursor.execute("ALTER TABLE orders ADD COLUMN total_price REAL DEFAULT 0.0")

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

def seed_settings():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM settings WHERE key = 'restaurant_status'")
    count = cursor.fetchone()[0]
    if count == 0:
        cursor.execute("INSERT INTO settings (key, value) VALUES ('restaurant_status', 'OPEN')")
    conn.commit()
    conn.close()

def migrate_historical_orders():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Select all orders that have 0.0 total price (or NULL)
        cursor.execute("SELECT order_id, items FROM orders WHERE total_price IS NULL OR total_price = 0.0")
        rows = cursor.fetchall()
        for row in rows:
            order_id = row[0]
            try:
                items = json.loads(row[1])
            except Exception:
                continue
            
            total_price = 0.0
            for item in items:
                name = item.get("item") or item.get("name")
                qty = item.get("qty") or item.get("quantity") or 0
                if name:
                    cursor.execute("SELECT price FROM menu WHERE LOWER(name) = LOWER(?)", (name,))
                    price_row = cursor.fetchone()
                    if price_row:
                        total_price += price_row[0] * qty
            
            cursor.execute("UPDATE orders SET total_price = ? WHERE order_id = ?", (total_price, order_id))
        conn.commit()
        print("Historical orders migrated successfully.")
    except Exception as e:
        print("Error migrating historical orders:", e)
    finally:
        conn.close()

# ============================================================
# DATABASE INITIALIZATION
# ============================================================
def initialize_database():
    create_tables()
    seed_menu()
    seed_settings()
    migrate_historical_orders()

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def is_restaurant_open() -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'restaurant_status'")
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0] == "OPEN"
    return True

def set_restaurant_status(status: str) -> bool:
    if status not in ("OPEN", "CLOSED"):
        return False
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('restaurant_status', ?)", (status,))
    conn.commit()
    conn.close()
    return True

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
    
    total_price = 0.0
    for item in items:
        cursor.execute("SELECT price FROM menu WHERE LOWER(name) = LOWER(?)", (item["item"],))
        row = cursor.fetchone()
        if row:
            total_price += row[0] * item["qty"]
            
    cursor.execute("""
        INSERT INTO orders (customer_thread_id, items, status, inventory_deducted, total_price, created_at, updated_at)
        VALUES (?, ?, ?, 0, ?, ?, ?)
    """, (customer_thread_id, items_json, "DRAFT", total_price, now_str, now_str))
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
        
        total_price = 0.0
        for item in items:
            cursor.execute("SELECT price FROM menu WHERE LOWER(name) = LOWER(?)", (item["item"],))
            row = cursor.fetchone()
            if row:
                total_price += row[0] * item["qty"]
                
        # Modify the order items and reset status to DRAFT
        cursor.execute("""
            UPDATE orders
            SET items = ?, status = ?, total_price = ?, updated_at = ?
            WHERE order_id = ?
        """, (items_json, "DRAFT", total_price, now_str, order_id))
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

def get_all_orders() -> List[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM orders ORDER BY order_id DESC")
        rows = cursor.fetchall()
        orders = []
        for row in rows:
            d = dict(row)
            d["items"] = json.loads(d["items"])
            orders.append(d)
        return orders
    except Exception as e:
        print("Error getting all orders:", e)
        return []
    finally:
        conn.close()

def get_all_menu_items() -> List[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM menu ORDER BY name")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        print("Error getting all menu items:", e)
        return []
    finally:
        conn.close()

def add_menu_item(name: str, price: float, available_qty: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO menu (name, price, available_qty, is_active)
            VALUES (?, ?, ?, 1)
        """, (name, price, available_qty))
        conn.commit()
        return True
    except Exception as e:
        print("Error adding menu item:", e)
        return False
    finally:
        conn.close()

def edit_menu_item(item_id: int, name: str, price: float, available_qty: int, is_active: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE menu
            SET name = ?, price = ?, available_qty = ?, is_active = ?
            WHERE item_id = ?
        """, (name, price, available_qty, is_active, item_id))
        conn.commit()
        return True
    except Exception as e:
        print("Error editing menu item:", e)
        return False
    finally:
        conn.close()

def toggle_menu_item_active(item_id: int, is_active: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE menu
            SET is_active = ?
            WHERE item_id = ?
        """, (is_active, item_id))
        conn.commit()
        return True
    except Exception as e:
        print("Error toggling menu item:", e)
        return False
    finally:
        conn.close()

def update_menu_item_stock(item_id: int, qty: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE menu
            SET available_qty = ?
            WHERE item_id = ?
        """, (qty, item_id))
        conn.commit()
        return True
    except Exception as e:
        print("Error updating stock:", e)
        return False
    finally:
        conn.close()