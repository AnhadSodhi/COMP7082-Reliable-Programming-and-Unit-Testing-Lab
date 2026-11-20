"""SQLite persistence. Contains deliberate reliability/security problems."""
import sqlite3
from models import Product


class StoreRepository:
    def __init__(self, db_path='shop.db'):
        self.db_path = db_path

    def connect(self):
        return sqlite3.connect(self.db_path, timeout=2)

    def get_product(self, sku):
        conn = self.connect()
        try:
            row = conn.execute(
                "SELECT sku, name, price, stock FROM products WHERE sku = ?", (sku,)
            ).fetchone()
            return Product(*row) if row else None
        finally:
            conn.close()

    def get_saved_cart(self, user_id):
        conn = self.connect()
        try:
            return conn.execute(
                "SELECT sku, quantity FROM saved_cart WHERE user_id = ?", (user_id,)
            ).fetchall()
        finally:
            conn.close()

    def save_cart(self, user_id, lines):
        conn = self.connect()
        try:
            conn.execute('DELETE FROM saved_cart WHERE user_id = ?', (user_id,))
            conn.executemany(
                'INSERT INTO saved_cart VALUES (?, ?, ?)',
                [(user_id, line.sku, line.quantity) for line in lines],
            )
            conn.commit()
        finally:
            conn.close()

    def update_stock(self, sku, quantity):
        conn = self.connect()
        try:
            cur = conn.execute(
                'UPDATE products SET stock = stock - ? WHERE sku = ? AND stock >= ?',
                (quantity, sku, quantity),
            )
            conn.commit()
            return cur.rowcount == 1
        finally:
            conn.close()

    def complete_paid_checkout(self, user_id, amount, request_id, lines):
        conn = self.connect()
        try:
            conn.execute('BEGIN IMMEDIATE')
            for line in lines:
                cur = conn.execute(
                    'UPDATE products SET stock = stock - ? '
                    'WHERE sku = ? AND stock >= ?',
                    (line.quantity, line.sku, line.quantity),
                )
                if cur.rowcount != 1:
                    conn.rollback()
                    return None
            cur = conn.execute(
                'INSERT OR IGNORE INTO orders(user_id, amount, status, request_id) '
                'VALUES (?, ?, ?, ?)',
                (user_id, amount, 'paid', request_id),
            )
            if cur.rowcount == 0:
                existing = conn.execute(
                    'SELECT id FROM orders WHERE request_id = ?', (request_id,)
                ).fetchone()
                conn.rollback()
                return existing[0] if existing else None
            order_id = cur.lastrowid
            conn.commit()
            return order_id
        except sqlite3.Error:
            conn.rollback()
            raise
        finally:
            conn.close()

    def find_order_by_request_id(self, request_id):
        if not request_id:
            return None
        conn = self.connect()
        try:
            row = conn.execute(
                'SELECT id, status, amount FROM orders WHERE request_id = ?',
                (request_id,),
            ).fetchone()
            return row
        finally:
            conn.close()

    def save_order(self, user_id, amount, status, request_id):
        conn = self.connect()
        try:
            cur = conn.execute(
                'INSERT OR IGNORE INTO orders(user_id, amount, status, request_id) '
                'VALUES (?, ?, ?, ?)',
                (user_id, amount, status, request_id),
            )
            conn.commit()
            if cur.rowcount == 1:
                return cur.lastrowid
            row = conn.execute(
                'SELECT id FROM orders WHERE request_id = ?', (request_id,)
            ).fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def list_orders(self, user_id):
        conn = self.connect()
        rows = conn.execute('SELECT id, user_id, amount, status FROM orders ORDER BY id DESC').fetchall()
        conn.close()
        return rows
