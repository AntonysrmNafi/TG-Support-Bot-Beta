# backup_manager.py

import os
import shutil
import sqlite3
import json
import time
import threading
from datetime import datetime

BACKUP_DIR = "backups"
BACKUP_PASSWORD = "Blockveil123*#%"
AUTO_BACKUP_INTERVAL = 3 * 60 * 60  # 3 hours
MAX_BACKUPS = 24

# Global data references (will be set from main.py)
user_active_ticket = None
ticket_status = None
ticket_user = None
ticket_username = None
ticket_messages = None
user_tickets = None
ticket_created_at = None
user_latest_username = None

def set_data_refs(active_ticket, status, user, username, messages, tickets, created_at, latest_username):
    global user_active_ticket, ticket_status, ticket_user, ticket_username
    global ticket_messages, user_tickets, ticket_created_at, user_latest_username
    user_active_ticket = active_ticket
    ticket_status = status
    ticket_user = user
    ticket_username = username
    ticket_messages = messages
    user_tickets = tickets
    ticket_created_at = created_at
    user_latest_username = latest_username

if not os.path.exists(BACKUP_DIR):
    os.makedirs(BACKUP_DIR)

def create_backup(backup_type="auto"):
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{backup_type}_{timestamp}"
        
        conn = sqlite3.connect('bot_data.db')
        backup_conn = sqlite3.connect(':memory:')
        conn.backup(backup_conn)
        conn.close()
        
        backup_conn_bytes = backup_conn.serialize()
        backup_conn.close()
        
        json_backup = {
            'user_active_ticket': dict(user_active_ticket),
            'ticket_status': dict(ticket_status),
            'ticket_user': dict(ticket_user),
            'ticket_username': dict(ticket_username),
            'ticket_messages': dict(ticket_messages),
            'user_tickets': dict(user_tickets),
            'ticket_created_at': dict(ticket_created_at),
            'user_latest_username': dict(user_latest_username),
            'timestamp': timestamp,
            'backup_type': backup_type
        }
        json_bytes = json.dumps(json_backup, default=str).encode('utf-8')
        
        zip_filename = f"{backup_name}.zip"
        zip_path = os.path.join(BACKUP_DIR, zip_filename)
        
        import pyzipper
        with pyzipper.AESZipFile(zip_path, 'w', compression=pyzipper.ZIP_LZMA) as zf:
            zf.setpassword(BACKUP_PASSWORD.encode('utf-8'))
            zf.setencryption(pyzipper.WZ_AES)
            zf.writestr('bot_data.db', backup_conn_bytes)
            zf.writestr('metadata.json', json_bytes)
        
        cleanup_old_backups()
        return zip_path, backup_type, timestamp
    except Exception as e:
        print(f"Backup failed: {e}")
        return None, None, None

def cleanup_old_backups():
    try:
        backups = [f for f in os.listdir(BACKUP_DIR) if f.endswith('.zip')]
        backups.sort(reverse=True)
        for old in backups[MAX_BACKUPS:]:
            os.remove(os.path.join(BACKUP_DIR, old))
    except Exception as e:
        print(f"Cleanup failed: {e}")

def restore_from_backup(zip_file_path, password):
    temp_dir = None
    try:
        import pyzipper
        temp_dir = "temp_restore_" + datetime.now().strftime("%Y%m%d%H%M%S")
        os.makedirs(temp_dir, exist_ok=True)
        
        with pyzipper.AESZipFile(zip_file_path, 'r') as zf:
            zf.setpassword(password.encode('utf-8'))
            zf.extractall(temp_dir)
        
        db_path = os.path.join(temp_dir, 'bot_data.db')
        if os.path.exists(db_path):
            if os.path.exists('bot_data.db'):
                old_backup = f"bot_data_before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                shutil.copy2('bot_data.db', os.path.join(BACKUP_DIR, old_backup))
            shutil.copy2(db_path, 'bot_data.db')
        
        json_path = os.path.join(temp_dir, 'metadata.json')
        if os.path.exists(json_path):
            with open(json_path, 'r') as f:
                data = json.load(f)
                
                user_active_ticket.clear()
                user_active_ticket.update(data['user_active_ticket'])
                ticket_status.clear()
                ticket_status.update(data['ticket_status'])
                ticket_user.clear()
                ticket_user.update(data['ticket_user'])
                ticket_username.clear()
                ticket_username.update(data['ticket_username'])
                ticket_messages.clear()
                ticket_messages.update(data['ticket_messages'])
                user_tickets.clear()
                user_tickets.update(data['user_tickets'])
                ticket_created_at.clear()
                ticket_created_at.update(data['ticket_created_at'])
                user_latest_username.clear()
                user_latest_username.update(data['user_latest_username'])
        
        shutil.rmtree(temp_dir)
        return True, "✅ Restore completed successfully!"
    except Exception as e:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        return False, f"❌ Restore failed: {str(e)}"

def auto_backup_loop(app, backup_group_id):
    while True:
        time.sleep(AUTO_BACKUP_INTERVAL)
        try:
            zip_path, btype, ts = create_backup("auto")
            if zip_path:
                from telegram import ParseMode
                caption = (
                    f"🔐 **Automatic Backup**\n"
                    f"🕒 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"📦 File: {os.path.basename(zip_path)}\n"
                    f"🔑 Password: `{BACKUP_PASSWORD}`"
                )
                app.bot.send_document(
                    chat_id=backup_group_id,
                    document=open(zip_path, 'rb'),
                    caption=caption,
                    parse_mode="Markdown"
                )
        except Exception as e:
            print(f"Auto backup failed: {e}")
