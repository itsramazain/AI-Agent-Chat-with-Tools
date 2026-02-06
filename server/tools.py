import json
from typing import Any, Dict, List, Literal, Optional, Tuple

from server.db import tx

LowStockThreshold = 3

import re

def normalize_isbn(isbn: str) -> str:
    # Remove hyphens, spaces, and anything that's not digit or X/x
    return re.sub(r"[^0-9Xx]", "", isbn)


def _log_tool_call(conn, session_id: str, name: str, args: Dict[str, Any], result: Dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO tool_calls(session_id, name, args_json, result_json) VALUES (?,?,?,?)",
        (session_id, name, json.dumps(args, ensure_ascii=False), json.dumps(result, ensure_ascii=False)),
    )

def find_books(session_id: str, q: str, by: Literal["title", "author"]) -> Dict[str, Any]:
    with tx() as conn:
        like = f"%{q}%"
        if by == "title":
            rows = conn.execute(
                "SELECT isbn,title,author,stock,price FROM books WHERE title LIKE ? ORDER BY title LIMIT 50",
                (like,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT isbn,title,author,stock,price FROM books WHERE author LIKE ? ORDER BY author, title LIMIT 50",
                (like,),
            ).fetchall()

        result = {"matches": [dict(r) for r in rows]}
        _log_tool_call(conn, session_id, "find_books", {"q": q, "by": by}, result)
        return result

def restock_book(session_id: str, isbn: str, qty: int) -> Dict[str, Any]:
    if qty <= 0:
        return {"error": "qty must be > 0"}
    with tx() as conn:
        row = conn.execute("SELECT isbn,title,stock FROM books WHERE isbn = ?", (isbn,)).fetchone()
        if not row:
            result = {"error": f"Book not found for isbn={isbn}"}
            _log_tool_call(conn, session_id, "restock_book", {"isbn": isbn, "qty": qty}, result)
            return result

        conn.execute(
            "UPDATE books SET stock = stock + ?, updated_at = datetime('now') WHERE isbn = ?",
            (qty, isbn),
        )
        updated = conn.execute("SELECT isbn,title,stock FROM books WHERE isbn = ?", (isbn,)).fetchone()
        result = {"isbn": updated["isbn"], "title": updated["title"], "new_stock": updated["stock"]}
        _log_tool_call(conn, session_id, "restock_book", {"isbn": isbn, "qty": qty}, result)
        return result

def update_price(session_id: str, isbn: str, price: float) -> Dict[str, Any]:
    if price < 0:
        return {"error": "price must be >= 0"}
    with tx() as conn:
        row = conn.execute("SELECT isbn,title,price FROM books WHERE isbn = ?", (isbn,)).fetchone()
        if not row:
            result = {"error": f"Book not found for isbn={isbn}"}
            _log_tool_call(conn, session_id, "update_price", {"isbn": isbn, "price": price}, result)
            return result

        conn.execute(
            "UPDATE books SET price = ?, updated_at = datetime('now') WHERE isbn = ?",
            (price, isbn),
        )
        updated = conn.execute("SELECT isbn,title,price FROM books WHERE isbn = ?", (isbn,)).fetchone()
        result = {"isbn": updated["isbn"], "title": updated["title"], "new_price": updated["price"]}
        _log_tool_call(conn, session_id, "update_price", {"isbn": isbn, "price": price}, result)
        return result

def order_status(session_id: str, order_id: int) -> Dict[str, Any]:
    with tx() as conn:
        order = conn.execute(
            "SELECT id, customer_id, status, created_at FROM orders WHERE id = ?",
            (order_id,),
        ).fetchone()
        if not order:
            result = {"error": f"Order not found for id={order_id}"}
            _log_tool_call(conn, session_id, "order_status", {"order_id": order_id}, result)
            return result

        items = conn.execute(
            """SELECT oi.isbn, b.title, oi.qty, oi.unit_price
               FROM order_items oi
               JOIN books b ON b.isbn = oi.isbn
               WHERE oi.order_id = ?""",
            (order_id,),
        ).fetchall()

        result = {
            "order": dict(order),
            "items": [dict(r) for r in items],
        }
        _log_tool_call(conn, session_id, "order_status", {"order_id": order_id}, result)
        return result

def inventory_summary(session_id: str) -> Dict[str, Any]:
    with tx() as conn:
        totals = conn.execute(
            "SELECT COUNT(*) AS total_titles, COALESCE(SUM(stock),0) AS total_stock FROM books"
        ).fetchone()
        low = conn.execute(
            "SELECT isbn,title,author,stock,price FROM books WHERE stock <= ? ORDER BY stock ASC, title LIMIT 50",
            (LowStockThreshold,),
        ).fetchall()

        result = {
            "total_titles": int(totals["total_titles"]),
            "total_stock": int(totals["total_stock"]),
            "low_stock_threshold": LowStockThreshold,
            "low_stock": [dict(r) for r in low],
        }
        _log_tool_call(conn, session_id, "inventory_summary", {}, result)
        return result

def create_order(session_id: str, customer_id: int, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Validate items early
    if not items:
        return {"error": "items cannot be empty"}
    for it in items:
        if "isbn" not in it or "qty" not in it:
            return {"error": "Each item must have isbn and qty"}
        if int(it["qty"]) <= 0:
            return {"error": "qty must be > 0 for each item"}

    with tx() as conn:
        # Ensure customer exists
        cust = conn.execute("SELECT id,name,email FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if not cust:
            result = {"error": f"Customer not found for id={customer_id}"}
            _log_tool_call(conn, session_id, "create_order", {"customer_id": customer_id, "items": items}, result)
            return result

        # Check all books exist + stock sufficient
        checked: List[Tuple[str, int, float, str, int]] = []
        # tuple: (isbn, qty, unit_price, title, current_stock)
        for it in items:
            isbn = normalize_isbn(str(it["isbn"]))
            qty = int(it["qty"])
            book = conn.execute(
                "SELECT isbn,title,stock,price FROM books WHERE isbn = ?",
                (isbn,),
            ).fetchone()
            if not book:
                result = {"error": f"Book not found for isbn={isbn}"}
                _log_tool_call(conn, session_id, "create_order", {"customer_id": customer_id, "items": items}, result)
                return result
            if int(book["stock"]) < qty:
                result = {
                    "error": "Insufficient stock",
                    "isbn": isbn,
                    "title": book["title"],
                    "requested_qty": qty,
                    "available_stock": int(book["stock"]),
                }
                _log_tool_call(conn, session_id, "create_order", {"customer_id": customer_id, "items": items}, result)
                return result
            checked.append((isbn, qty, float(book["price"]), str(book["title"]), int(book["stock"])))

        # Create order
        cur = conn.execute(
            "INSERT INTO orders(customer_id, status) VALUES (?, 'created')",
            (customer_id,),
        )
        order_id = int(cur.lastrowid)

        # Insert items + decrement stock
        for (isbn, qty, unit_price, _title, _stock) in checked:
            conn.execute(
                "INSERT INTO order_items(order_id, isbn, qty, unit_price) VALUES (?,?,?,?)",
                (order_id, isbn, qty, unit_price),
            )
            conn.execute(
                "UPDATE books SET stock = stock - ?, updated_at = datetime('now') WHERE isbn = ?",
                (qty, isbn),
            )

        # Return updated stock for purchased ISBNs
        updated_rows = conn.execute(
            "SELECT isbn,title,stock FROM books WHERE isbn IN ({})".format(
                ",".join(["?"] * len(checked))
            ),
            [x[0] for x in checked],
        ).fetchall()

        result = {
            "order_id": order_id,
            "customer": dict(cust),
            "items": [{"isbn": x[0], "qty": x[1], "unit_price": x[2], "title": x[3]} for x in checked],
            "updated_stock": [dict(r) for r in updated_rows],
        }
        _log_tool_call(conn, session_id, "create_order", {"customer_id": customer_id, "items": items}, result)
        return result
