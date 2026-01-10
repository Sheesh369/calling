import sqlite3
from datetime import datetime
from passlib.context import CryptContext
from loguru import logger

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class Database:
    def __init__(self, db_path="data/users.db"):
        self.db_path = db_path
        # Ensure data directory exists
        import os
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.init_db()
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def init_db(self):
        """Initialize database with users and calls tables"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS calls (
                call_uuid TEXT PRIMARY KEY,
                phone_number TEXT NOT NULL,
                customer_name TEXT,
                invoice_number TEXT,
                status TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL,
                ended_at TIMESTAMP,
                hangup_cause TEXT,
                hangup_source TEXT,
                custom_data TEXT,
                plivo_call_uuid TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        
        # Create default super admin if not exists
        cursor.execute("SELECT * FROM users WHERE username = 'admin'")
        if not cursor.fetchone():
            password_hash = pwd_context.hash("admin123")
            cursor.execute("""
                INSERT INTO users (username, email, password_hash, role)
                VALUES (?, ?, ?, ?)
            """, ("admin", "admin@hummingbird.com", password_hash, "super_admin"))
            logger.info("Default super admin created: username='admin', password='admin123'")
        
        conn.commit()
        conn.close()
    
    def create_user(self, username, email, password, role="user"):
        """Create a new user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            password_hash = pwd_context.hash(password)
            cursor.execute("""
                INSERT INTO users (username, email, password_hash, role)
                VALUES (?, ?, ?, ?)
            """, (username, email, password_hash, role))
            
            user_id = cursor.lastrowid
            conn.commit()
            logger.info(f"User created: {username} (ID: {user_id}, Role: {role})")
            return user_id
        except sqlite3.IntegrityError as e:
            logger.error(f"Error creating user: {e}")
            raise Exception("Username or email already exists")
        finally:
            conn.close()
    
    def get_user_by_username(self, username):
        """Get user by username"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "id": row[0],
                "username": row[1],
                "email": row[2],
                "password_hash": row[3],
                "role": row[4],
                "created_at": row[5],
                "is_active": bool(row[6])
            }
        return None
    
    def get_user_by_id(self, user_id):
        """Get user by ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "id": row[0],
                "username": row[1],
                "email": row[2],
                "password_hash": row[3],
                "role": row[4],
                "created_at": row[5],
                "is_active": bool(row[6])
            }
        return None
    
    def get_all_users(self):
        """Get all users"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, username, email, role, created_at, is_active FROM users ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "id": row[0],
                "username": row[1],
                "email": row[2],
                "role": row[3],
                "created_at": row[4],
                "is_active": bool(row[5])
            }
            for row in rows
        ]
    
    def update_user(self, user_id, email=None, is_active=None):
        """Update user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        updates = []
        params = []
        
        if email is not None:
            updates.append("email = ?")
            params.append(email)
        
        if is_active is not None:
            updates.append("is_active = ?")
            params.append(1 if is_active else 0)
        
        if not updates:
            conn.close()
            return
        
        params.append(user_id)
        query = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
        
        cursor.execute(query, params)
        conn.commit()
        conn.close()
        logger.info(f"User {user_id} updated")
    
    def delete_user(self, user_id):
        """Soft delete user (set is_active to False)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        logger.info(f"User {user_id} deactivated")
    
    def change_password(self, user_id, new_password):
        """Change user password"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        password_hash = pwd_context.hash(new_password)
        cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
        conn.commit()
        conn.close()
        logger.info(f"Password changed for user {user_id}")
    
    def verify_password(self, plain_password, password_hash):
        """Verify password"""
        return pwd_context.verify(plain_password, password_hash)

    # ============================================================================
    # CALL HISTORY METHODS
    # ============================================================================
    
    def create_call(self, call_uuid, phone_number, customer_name, invoice_number, user_id, custom_data, created_at):
        """Create a new call record"""
        import json
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO calls (call_uuid, phone_number, customer_name, invoice_number, status, user_id, created_at, custom_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (call_uuid, phone_number, customer_name, invoice_number, "initiated", user_id, created_at, json.dumps(custom_data)))
            
            conn.commit()
            logger.info(f"Call record created: {call_uuid}")
        except Exception as e:
            logger.error(f"Error creating call record: {e}")
        finally:
            conn.close()
    
    def update_call_status(self, call_uuid, status, ended_at=None, hangup_cause=None, hangup_source=None, plivo_call_uuid=None):
        """Update call status and related fields"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            updates = ["status = ?"]
            params = [status]
            
            if ended_at is not None:
                updates.append("ended_at = ?")
                params.append(ended_at)
            
            if hangup_cause is not None:
                updates.append("hangup_cause = ?")
                params.append(hangup_cause)
            
            if hangup_source is not None:
                updates.append("hangup_source = ?")
                params.append(hangup_source)
            
            if plivo_call_uuid is not None:
                updates.append("plivo_call_uuid = ?")
                params.append(plivo_call_uuid)
            
            params.append(call_uuid)
            query = f"UPDATE calls SET {', '.join(updates)} WHERE call_uuid = ?"
            
            cursor.execute(query, params)
            conn.commit()
            logger.info(f"Call {call_uuid} status updated to: {status}")
        except Exception as e:
            logger.error(f"Error updating call status: {e}")
        finally:
            conn.close()
    
    def get_calls(self, user_id=None):
        """Get all calls or filter by user_id"""
        import json
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if user_id is None:
            cursor.execute("SELECT * FROM calls ORDER BY created_at DESC")
        else:
            cursor.execute("SELECT * FROM calls WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        calls = []
        for row in rows:
            try:
                custom_data = json.loads(row[10]) if row[10] else {}
            except:
                custom_data = {}
            
            calls.append({
                "call_uuid": row[0],
                "phone_number": row[1],
                "customer_name": row[2],
                "invoice_number": row[3],
                "status": row[4],
                "user_id": row[5],
                "created_at": row[6],
                "ended_at": row[7],
                "hangup_cause": row[8],
                "hangup_source": row[9],
                "custom_data": custom_data,
                "plivo_call_uuid": row[11]
            })
        
        return calls
    
    def get_call(self, call_uuid):
        """Get a single call by UUID"""
        import json
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM calls WHERE call_uuid = ?", (call_uuid,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            try:
                custom_data = json.loads(row[10]) if row[10] else {}
            except:
                custom_data = {}
            
            return {
                "call_uuid": row[0],
                "phone_number": row[1],
                "customer_name": row[2],
                "invoice_number": row[3],
                "status": row[4],
                "user_id": row[5],
                "created_at": row[6],
                "ended_at": row[7],
                "hangup_cause": row[8],
                "hangup_source": row[9],
                "custom_data": custom_data,
                "plivo_call_uuid": row[11]
            }
        return None
