from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    filters,
)
import os
import shutil
import sqlite3
import json
import zipfile
import io
import random
import string
import html
from datetime import datetime
import time
import threading

# ================= TIMEZONE (BST: UTC+6) =================
def get_bst_now():
    """Return current time in Bangladesh Standard Time (BST) as formatted string."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Dhaka")).strftime("%Y-%m-%d %H:%M:%S")
    except ImportError:
        import pytz
        tz = pytz.timezone('Asia/Dhaka')
        return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

# ================= ENV =================
TOKEN = os.environ.get("BOT_TOKEN")
GROUP_ID = int(os.environ.get("GROUP_ID"))
BACKUP_GROUP_ID = int(os.environ.get("BACKUP_GROUP_ID", "-1002345678901"))

# ================= STORAGE =================
user_active_ticket = {}
ticket_status = {}
ticket_user = {}
ticket_username = {}
ticket_messages = {}
user_tickets = {}
group_message_map = {}
ticket_created_at = {}
user_latest_username = {}
user_message_timestamps = {}

# ================= ব্যাকআপ কনফিগারেশন =================
BACKUP_DIR = "backups"
BACKUP_PASSWORD = "Blockveil123*#%"
AUTO_BACKUP_INTERVAL = 3 * 60 * 60  # ৩ ঘন্টা
MAX_BACKUPS = 24

if not os.path.exists(BACKUP_DIR):
    os.makedirs(BACKUP_DIR)

# ================= হেল্পার ফাংশন =================
def generate_ticket_id(length=8):
    chars = string.ascii_letters + string.digits + "*#@$&"
    while True:
        tid = "BV-" + "".join(random.choice(chars) for _ in range(length))
        if tid not in ticket_status:
            return tid

def code(tid):
    return f"<code>{html.escape(tid)}</code>"

def register_user(user):
    user_latest_username[user.id] = user.username or ""

# ================= ব্যাকআপ ফাংশন =================
def create_encrypted_zip(data_bytes, zip_path, password):
    """পাসওয়ার্ড-সুরক্ষিত জিপ ফাইল তৈরি করে"""
    import pyzipper
    
    with pyzipper.AESZipFile(zip_path, 'w', compression=pyzipper.ZIP_LZMA) as zf:
        zf.setpassword(password.encode('utf-8'))
        zf.setencryption(pyzipper.WZ_AES)
        zf.writestr('bot_data.db', data_bytes)

def create_backup(backup_type="auto"):
    """সম্পূর্ণ ডাটাবেজের পাসওয়ার্ড-সুরক্ষিত ব্যাকআপ নেয়"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{backup_type}_{timestamp}"
        
        # SQLite ডাটাবেজ ব্যাকআপ
        conn = sqlite3.connect('bot_data.db')
        backup_bytes = io.BytesIO()
        backup_conn = sqlite3.connect(':memory:')
        conn.backup(backup_conn)
        backup_conn_bytes = backup_conn.serialize()
        conn.close()
        backup_conn.close()
        
        # JSON মেটাডেটা
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
        
        # পাসওয়ার্ড-সুরক্ষিত জিপ তৈরি
        zip_filename = f"{backup_name}.zip"
        zip_path = os.path.join(BACKUP_DIR, zip_filename)
        
        # pyzipper দিয়ে এনক্রিপ্টেড জিপ তৈরি
        import pyzipper
        with pyzipper.AESZipFile(zip_path, 'w', compression=pyzipper.ZIP_LZMA) as zf:
            zf.setpassword(BACKUP_PASSWORD.encode('utf-8'))
            zf.setencryption(pyzipper.WZ_AES)
            zf.writestr('bot_data.db', backup_conn_bytes)
            zf.writestr('metadata.json', json_bytes)
        
        # পুরনো ব্যাকআপ মুছে ফেলা
        cleanup_old_backups()
        
        return zip_path, backup_type, timestamp
        
    except Exception as e:
        print(f"❌ ব্যাকআপ ব্যর্থ: {e}")
        return None, None, None

def cleanup_old_backups():
    """সর্বোচ্চ MAX_BACKUPS টি ব্যাকআপ রেখে বাকি মুছে ফেলে"""
    try:
        backups = [f for f in os.listdir(BACKUP_DIR) if f.endswith('.zip')]
        backups.sort(reverse=True)
        
        for old_backup in backups[MAX_BACKUPS:]:
            os.remove(os.path.join(BACKUP_DIR, old_backup))
            
    except Exception as e:
        print(f"❌ Cleanup ব্যর্থ: {e}")

def restore_from_backup(zip_file_path, password):
    """পাসওয়ার্ড-সুরক্ষিত ব্যাকআপ ফাইল থেকে ডাটা রিস্টোর করে"""
    temp_dir = None
    try:
        import pyzipper
        
        temp_dir = "temp_restore_" + datetime.now().strftime("%Y%m%d%H%M%S")
        os.makedirs(temp_dir, exist_ok=True)
        
        # পাসওয়ার্ড দিয়ে জিপ খুলুন
        with pyzipper.AESZipFile(zip_file_path, 'r') as zf:
            zf.setpassword(password.encode('utf-8'))
            zf.extractall(temp_dir)
        
        # SQLite ডাটাবেজ রিস্টোর
        db_path = os.path.join(temp_dir, 'bot_data.db')
        if os.path.exists(db_path):
            if os.path.exists('bot_data.db'):
                old_backup = f"bot_data_before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                shutil.copy2('bot_data.db', os.path.join(BACKUP_DIR, old_backup))
            
            shutil.copy2(db_path, 'bot_data.db')
        
        # JSON থেকে মেমোরি ডাটা রিস্টোর
        json_path = os.path.join(temp_dir, 'metadata.json')
        if os.path.exists(json_path):
            with open(json_path, 'r') as f:
                data = json.load(f)
                
                global user_active_ticket, ticket_status, ticket_user
                global ticket_username, ticket_messages, user_tickets
                global ticket_created_at, user_latest_username
                
                user_active_ticket = {k: v for k, v in data['user_active_ticket'].items()}
                ticket_status = {k: v for k, v in data['ticket_status'].items()}
                ticket_user = {k: v for k, v in data['ticket_user'].items()}
                ticket_username = {k: v for k, v in data['ticket_username'].items()}
                ticket_messages = {k: v for k, v in data['ticket_messages'].items()}
                user_tickets = {k: v for k, v in data['user_tickets'].items()}
                ticket_created_at = {k: v for k, v in data['ticket_created_at'].items()}
                user_latest_username = {k: v for k, v in data['user_latest_username'].items()}
        
        # টেম্প ফোল্ডার মুছে ফেলা
        shutil.rmtree(temp_dir)
        
        return True, "✅ রিস্টোর সম্পন্ন হয়েছে!"
        
    except Exception as e:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        return False, f"❌ রিস্টোর ব্যর্থ: {str(e)}"

# ================= অটো ব্যাকআপ থ্রেড =================
def auto_backup_loop(app):
    """পেছনে অটো ব্যাকআপ চালায়"""
    while True:
        time.sleep(AUTO_BACKUP_INTERVAL)
        
        try:
            zip_path, btype, ts = create_backup("auto")
            
            if zip_path:
                caption = f"🔐 **অটো ব্যাকআপ**\n"
                caption += f"🕒 সময়: {get_bst_now()}\n"
                caption += f"📦 ফাইল: {os.path.basename(zip_path)}\n"
                caption += f"🔑 পাসওয়ার্ড: `{BACKUP_PASSWORD}`"
                
                app.bot.send_document(
                    chat_id=BACKUP_GROUP_ID,
                    document=open(zip_path, 'rb'),
                    caption=caption,
                    parse_mode="Markdown"
                )
                
        except Exception as e:
            print(f"❌ অটো ব্যাকআপ ব্যর্থ: {e}")

# ================= ফিল্টার: শুধু ব্যাকআপ গ্রুপের জন্য =================
class BackupGroupFilter(filters.BaseFilter):
    def filter(self, message):
        return message.chat_id == BACKUP_GROUP_ID

backup_group = BackupGroupFilter()

# ================= ব্যাকআপ কমান্ড =================
async def backup_command(update: Update, context):
    """ম্যানুয়াল ব্যাকআপ নেওয়ার কমান্ড"""
    if update.effective_chat.id != BACKUP_GROUP_ID:
        return
    
    status_msg = await update.message.reply_text("🔄 ব্যাকআপ নেওয়া হচ্ছে...")
    
    zip_path, btype, ts = create_backup("manual")
    
    if zip_path:
        caption = f"🔐 **ম্যানুয়াল ব্যাকআপ**\n"
        caption += f"🕒 সময়: {get_bst_now()}\n"
        caption += f"👤 অ্যাডমিন: @{update.effective_user.username or 'N/A'}\n"
        caption += f"📦 ফাইল: {os.path.basename(zip_path)}\n"
        caption += f"🔑 পাসওয়ার্ড: `{BACKUP_PASSWORD}`"
        
        await context.bot.send_document(
            chat_id=BACKUP_GROUP_ID,
            document=open(zip_path, 'rb'),
            caption=caption,
            parse_mode="Markdown"
        )
        await status_msg.delete()
    else:
        await status_msg.edit_text("❌ ব্যাকআপ ব্যর্থ হয়েছে!")

async def restore_command(update: Update, context):
    """ফাইল রিপ্লাই করে রিস্টোর করার কমান্ড"""
    if update.effective_chat.id != BACKUP_GROUP_ID:
        return
    
    if not update.message.reply_to_message or not update.message.reply_to_message.document:
        await update.message.reply_text(
            "❌ **ভুল ব্যবহার!**\n\n"
            "একটি ব্যাকআপ জিপ ফাইলে রিপ্লাই করে `/restore` লিখুন।",
            parse_mode="Markdown"
        )
        return
    
    document = update.message.reply_to_message.document
    if not document.file_name.endswith('.zip'):
        await update.message.reply_text("❌ শুধু .zip ফাইল রিস্টোর করা যাবে!")
        return
    
    # পাসওয়ার্ড চাওয়ার জন্য বাটন
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 পাসওয়ার্ড দিন", callback_data="ask_password")]
    ])
    
    await update.message.reply_text(
        f"📦 ফাইল: `{document.file_name}`\n\n"
        f"রিস্টোর করতে পাসওয়ার্ড দিন:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    
    context.user_data['restore_file_id'] = document.file_id
    context.user_data['restore_file_name'] = document.file_name

async def password_callback(update: Update, context):
    """পাসওয়ার্ড দেওয়ার জন্য কলব্যাক"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "ask_password":
        await query.edit_message_text(
            "🔑 **পাসওয়ার্ড দিন**\n\n"
            "নিচের ফরম্যাটে পাসওয়ার্ড দিন:\n"
            "`/password Blockveil123*#%`",
            parse_mode="Markdown"
        )

async def password_command(update: Update, context):
    """পাসওয়ার্ড গ্রহণ এবং রিস্টোর সম্পন্ন করা"""
    if update.effective_chat.id != BACKUP_GROUP_ID:
        return
    
    if not context.args:
        await update.message.reply_text("❌ পাসওয়ার্ড দিন! যেমন: `/password Blockveil123*#%`")
        return
    
    password = context.args[0]
    file_id = context.user_data.get('restore_file_id')
    
    if not file_id:
        await update.message.reply_text("❌ আগে একটি ফাইল সিলেক্ট করুন!")
        return
    
    status_msg = await update.message.reply_text("🔄 রিস্টোর করা হচ্ছে...")
    
    try:
        # ফাইল ডাউনলোড
        file = await context.bot.get_file(file_id)
        temp_path = os.path.join(BACKUP_DIR, f"temp_restore_{datetime.now().strftime('%Y%m%d%H%M%S')}.zip")
        await file.download_to_drive(temp_path)
        
        # রিস্টোর
        success, message = restore_from_backup(temp_path, password)
        
        # টেম্প ফাইল মুছুন
        os.remove(temp_path)
        
        if success:
            await status_msg.edit_text(
                f"✅ {message}\n\n"
                f"📊 মোট টিকিট: {len(ticket_status)}\n"
                f"👥 মোট ইউজার: {len(user_latest_username)}"
            )
        else:
            await status_msg.edit_text(f"{message}")
            
    except Exception as e:
        await status_msg.edit_text(f"❌ রিস্টোর ব্যর্থ: {e}")
    
    # ক্লিনআপ
    context.user_data.pop('restore_file_id', None)
    context.user_data.pop('restore_file_name', None)

async def unknown_command(update: Update, context):
    """ব্যাকআপ গ্রুপে অন্যান্য কমান্ড ব্লক"""
    if update.effective_chat.id == BACKUP_GROUP_ID:
        await update.message.reply_text(
            "❌ এই গ্রুপে শুধু নিচের কমান্ডগুলো কাজ করে:\n"
            "• `/backup` - নতুন ব্যাকআপ\n"
            "• `/restore` - ফাইল রিস্টোর\n"
            "• `/password <pass>` - পাসওয়ার্ড দিয়ে রিস্টোর",
            parse_mode="Markdown"
        )

# ================= মূল বটের কমান্ড =================
async def start(update: Update, context):
    """Start command"""
    user = update.effective_user
    register_user(user)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎟️ Create Ticket", callback_data="create_ticket")],
        [InlineKeyboardButton("👤 My Profile", callback_data="profile")]
    ])
    
    await update.message.reply_text(
        "Welcome to BlockVeil Support Bot!",
        reply_markup=keyboard
    )

async def create_ticket_callback(update: Update, context):
    """Create ticket callback"""
    query = update.callback_query
    await query.answer()
    user = query.from_user
    register_user(user)
    
    # আপনার existing create ticket logic
    await query.message.reply_text("Ticket created!")

async def profile_callback(update: Update, context):
    """Profile callback"""
    query = update.callback_query
    await query.answer()
    user = query.from_user
    register_user(user)
    
    # আপনার existing profile logic
    await query.message.reply_text("Profile info")

# ================= মেইন ফাংশন =================
def main():
    # ডাটাবেজ চেক
    if not os.path.exists('bot_data.db'):
        conn = sqlite3.connect('bot_data.db')
        conn.close()
    
    # অ্যাপ্লিকেশন বিল্ড
    app = ApplicationBuilder().token(TOKEN).build()
    
    # ===== ব্যাকআপ গ্রুপের হ্যান্ডলার =====
    app.add_handler(CommandHandler("backup", backup_command, filters=backup_group))
    app.add_handler(CommandHandler("restore", restore_command, filters=backup_group))
    app.add_handler(CommandHandler("password", password_command, filters=backup_group))
    app.add_handler(CallbackQueryHandler(password_callback, pattern="^ask_password$"))
    app.add_handler(MessageHandler(filters.COMMAND & backup_group, unknown_command))
    
    # ===== মূল বটের হ্যান্ডলার =====
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(create_ticket_callback, pattern="create_ticket"))
    app.add_handler(CallbackQueryHandler(profile_callback, pattern="profile"))
    
    # ===== অটো ব্যাকআপ থ্রেড =====
    backup_thread = threading.Thread(target=auto_backup_loop, args=(app,), daemon=True)
    backup_thread.start()
    
    print("🤖 বট চালু হয়েছে...")
    print(f"📊 সাপোর্ট গ্রুপ: {GROUP_ID}")
    print(f"📦 ব্যাকআপ গ্রুপ: {BACKUP_GROUP_ID}")
    print(f"🔑 ব্যাকআপ পাসওয়ার্ড: {BACKUP_PASSWORD}")
    
    app.run_polling()

if __name__ == "__main__":
    main()
