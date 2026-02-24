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
import random
import string
import html
from io import BytesIO
from datetime import datetime
import time

# ================= TIMEZONE (BST: UTC+6) =================
def get_bst_now():
    """Return current time in Bangladesh Standard Time (BST) as formatted string."""
    try:
        # Python 3.9+ zoneinfo
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Dhaka")).strftime("%Y-%m-%d %H:%M:%S")
    except ImportError:
        # Fallback to pytz
        import pytz
        tz = pytz.timezone('Asia/Dhaka')
        return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

# ================= ENV =================
TOKEN = os.environ.get("BOT_TOKEN")
GROUP_ID = int(os.environ.get("GROUP_ID"))

# ================= STORAGE =================
user_active_ticket = {}
ticket_status = {}
ticket_user = {}
ticket_username = {}
# ticket_messages now stores (sender, message, timestamp)
ticket_messages = {}
user_tickets = {}
group_message_map = {}
ticket_created_at = {}

# New: store latest username per user (fix bug 22)
user_latest_username = {}

# New: rate limiting storage (fix bug 18)
user_message_timestamps = {}  # user_id -> list of timestamps (seconds)

# ================= HELPERS =================
def generate_ticket_id(length=8):
    chars = string.ascii_letters + string.digits + "*#@$&"
    # Fix bug 25: avoid duplicate IDs
    while True:
        tid = "BV-" + "".join(random.choice(chars) for _ in range(length))
        if tid not in ticket_status:
            return tid

def code(tid):
    """Format ticket ID in code tags for easy copying"""
    return f"<code>{html.escape(tid)}</code>"

def ticket_header(ticket_id, status):
    return f"🎫 Ticket ID: {code(ticket_id)}\nStatus: {status}\n\n"

def user_info_block(user):
    # Escape first name to avoid HTML injection
    safe_first_name = html.escape(user.first_name or "")
    return (
        "User Information\n"
        f"• User ID   : {user.id}\n"
        f"• Username  : @{html.escape(user.username or '')}\n"
        f"• Full Name : {safe_first_name}\n\n"
    )

# Rate limit check (fix bug 18)
def check_rate_limit(user_id):
    now = time.time()
    if user_id not in user_message_timestamps:
        user_message_timestamps[user_id] = []
    # Remove timestamps older than 60 seconds
    user_message_timestamps[user_id] = [t for t in user_message_timestamps[user_id] if now - t < 60]
    if len(user_message_timestamps[user_id]) >= 2:
        return False
    user_message_timestamps[user_id].append(now)
    return True

# ================= /start =================
async def start(update: Update, context):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎟️ Create Ticket", callback_data="create_ticket")]
    ])
    await update.message.reply_text(
        "Hey Sir/Mam 👋\n\n"
        "Welcome to BlockVeil Support.\n"
        "You can contact the BlockVeil team using this bot.\n\n"
        "🔐 Privacy Notice\n"
        "Your information is kept strictly confidential.\n\n"
        "Use the button below to create a support ticket.\n\n"
        "📧 support.blockveil@protonmail.com\n\n"
        "— BlockVeil Support Team",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

# ================= CREATE TICKET =================
async def create_ticket(update: Update, context):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if user.id in user_active_ticket:
        await query.message.reply_text(
            f"🎫 You already have an active ticket:\n{code(user_active_ticket[user.id])}",
            parse_mode="HTML"
        )
        return

    ticket_id = generate_ticket_id()
    user_active_ticket[user.id] = ticket_id
    ticket_status[ticket_id] = "Pending"
    ticket_user[ticket_id] = user.id
    ticket_username[ticket_id] = user.username or ""
    ticket_messages[ticket_id] = []
    ticket_created_at[ticket_id] = get_bst_now()  # BST time
    user_tickets.setdefault(user.id, []).append(ticket_id)
    # Store latest username
    user_latest_username[user.id] = user.username or ""

    await query.message.reply_text(
        f"🎫 Ticket Created: {code(ticket_id)}\n"
        "Status: Pending\n\n"
        "Please write and submit your issue or suggestion here in a clear and concise manner.\n"
        "Our support team will review it as soon as possible.",
        parse_mode="HTML"
    )

# ================= USER MESSAGE (TEXT + MEDIA) =================
async def user_message(update: Update, context):
    user = update.message.from_user

    # Rate limit check (fix bug 18)
    if not check_rate_limit(user.id):
        await update.message.reply_text(
            "⏱️ You can send at most 2 messages per minute. Please wait a moment.",
            parse_mode="HTML"
        )
        return

    if user.id not in user_active_ticket:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎟️ Create Ticket", callback_data="create_ticket")]
        ])
        await update.message.reply_text(
            "❗ Please create a ticket first.\n\n"
            "Click the button below to submit a new support ticket.",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return

    ticket_id = user_active_ticket[user.id]
    if ticket_status[ticket_id] == "Pending":
        ticket_status[ticket_id] = "Processing"

    # Update latest username
    user_latest_username[user.id] = user.username or ""

    header = ticket_header(ticket_id, ticket_status[ticket_id]) + user_info_block(user) + "Message:\n"
    caption_text = update.message.caption or ""  # Fix bug 4: capture caption
    safe_caption = html.escape(caption_text) if caption_text else ""

    sent = None
    log_text = ""
    timestamp = get_bst_now()  # BST time

    # Handle all message types (fix bug 3)
    if update.message.text:
        log_text = html.escape(update.message.text)
        full_message = header + log_text
        sent = await context.bot.send_message(
            chat_id=GROUP_ID,
            text=full_message,
            parse_mode="HTML"
        )

    elif update.message.photo:
        log_text = "[Photo]"
        full_caption = header + (safe_caption if safe_caption else log_text)
        sent = await context.bot.send_photo(
            chat_id=GROUP_ID,
            photo=update.message.photo[-1].file_id,
            caption=full_caption,
            parse_mode="HTML"
        )

    elif update.message.voice:
        log_text = "[Voice Message]"
        full_caption = header + (safe_caption if safe_caption else log_text)
        sent = await context.bot.send_voice(
            chat_id=GROUP_ID,
            voice=update.message.voice.file_id,
            caption=full_caption,
            parse_mode="HTML"
        )

    elif update.message.video:
        log_text = "[Video]"
        full_caption = header + (safe_caption if safe_caption else log_text)
        sent = await context.bot.send_video(
            chat_id=GROUP_ID,
            video=update.message.video.file_id,
            caption=full_caption,
            parse_mode="HTML"
        )

    elif update.message.document:
        log_text = "[Document]"
        full_caption = header + (safe_caption if safe_caption else log_text)
        sent = await context.bot.send_document(
            chat_id=GROUP_ID,
            document=update.message.document.file_id,
            caption=full_caption,
            parse_mode="HTML"
        )

    elif update.message.audio:
        log_text = "[Audio]"
        full_caption = header + (safe_caption if safe_caption else log_text)
        sent = await context.bot.send_audio(
            chat_id=GROUP_ID,
            audio=update.message.audio.file_id,
            caption=full_caption,
            parse_mode="HTML"
        )

    elif update.message.sticker:
        log_text = "[Sticker]"
        sent = await context.bot.send_sticker(
            chat_id=GROUP_ID,
            sticker=update.message.sticker.file_id
        )
        # Send caption separately if present
        if safe_caption:
            await context.bot.send_message(
                chat_id=GROUP_ID,
                text=header + safe_caption,
                parse_mode="HTML"
            )
        else:
            await context.bot.send_message(
                chat_id=GROUP_ID,
                text=header + log_text,
                parse_mode="HTML"
            )
        # We'll map the sticker message ID
        if sent:
            group_message_map[sent.message_id] = ticket_id

    elif update.message.animation:
        log_text = "[Animation/GIF]"
        full_caption = header + (safe_caption if safe_caption else log_text)
        sent = await context.bot.send_animation(
            chat_id=GROUP_ID,
            animation=update.message.animation.file_id,
            caption=full_caption,
            parse_mode="HTML"
        )

    elif update.message.video_note:
        log_text = "[Video Note]"
        sent = await context.bot.send_video_note(
            chat_id=GROUP_ID,
            video_note=update.message.video_note.file_id
        )
        if safe_caption:
            await context.bot.send_message(
                chat_id=GROUP_ID,
                text=header + safe_caption,
                parse_mode="HTML"
            )
        else:
            await context.bot.send_message(
                chat_id=GROUP_ID,
                text=header + log_text,
                parse_mode="HTML"
            )

    else:
        # Unsupported message type
        log_text = f"[Unsupported message type]"
        await update.message.reply_text(
            "❌ This message type is not supported. Please send text, photo, video, document, audio, sticker, etc.",
            parse_mode="HTML"
        )
        sent = await context.bot.send_message(
            chat_id=GROUP_ID,
            text=header + log_text,
            parse_mode="HTML"
        )

    if sent:
        group_message_map[sent.message_id] = ticket_id
        sender_name = f"@{user.username}" if user.username else user.first_name or "User"
        # Store with timestamp (fix bug 14)
        ticket_messages[ticket_id].append((sender_name, log_text, timestamp))

# ================= GROUP REPLY (TEXT + MEDIA) =================
async def group_reply(update: Update, context):
    if not update.message.reply_to_message:
        return

    reply_id = update.message.reply_to_message.message_id
    if reply_id not in group_message_map:
        return

    ticket_id = group_message_map[reply_id]
    user_id = ticket_user[ticket_id]

    # Fix bug 11: block reply if ticket is closed
    if ticket_status.get(ticket_id) == "Closed":
        await update.message.reply_text(
            f"⚠️ Ticket {code(ticket_id)} is already closed. Cannot send reply.",
            parse_mode="HTML"
        )
        return

    prefix = f"🎫 Ticket ID: {code(ticket_id)}\n\n"
    caption_text = update.message.caption or ""  # Fix bug 5: capture caption
    safe_caption = html.escape(caption_text) if caption_text else ""
    timestamp = get_bst_now()  # BST time

    log_text = ""

    if update.message.text:
        log_text = html.escape(update.message.text)
        await context.bot.send_message(
            chat_id=user_id,
            text=prefix + log_text,
            parse_mode="HTML"
        )

    elif update.message.photo:
        log_text = "[Photo]"
        full_caption = prefix + (safe_caption if safe_caption else log_text)
        await context.bot.send_photo(
            chat_id=user_id,
            photo=update.message.photo[-1].file_id,
            caption=full_caption,
            parse_mode="HTML"
        )

    elif update.message.voice:
        log_text = "[Voice Message]"
        full_caption = prefix + (safe_caption if safe_caption else log_text)
        await context.bot.send_voice(
            chat_id=user_id,
            voice=update.message.voice.file_id,
            caption=full_caption,
            parse_mode="HTML"
        )

    elif update.message.video:
        log_text = "[Video]"
        full_caption = prefix + (safe_caption if safe_caption else log_text)
        await context.bot.send_video(
            chat_id=user_id,
            video=update.message.video.file_id,
            caption=full_caption,
            parse_mode="HTML"
        )

    elif update.message.document:
        log_text = "[Document]"
        full_caption = prefix + (safe_caption if safe_caption else log_text)
        await context.bot.send_document(
            chat_id=user_id,
            document=update.message.document.file_id,
            caption=full_caption,
            parse_mode="HTML"
        )

    elif update.message.audio:
        log_text = "[Audio]"
        full_caption = prefix + (safe_caption if safe_caption else log_text)
        await context.bot.send_audio(
            chat_id=user_id,
            audio=update.message.audio.file_id,
            caption=full_caption,
            parse_mode="HTML"
        )

    elif update.message.sticker:
        log_text = "[Sticker]"
        await context.bot.send_sticker(
            chat_id=user_id,
            sticker=update.message.sticker.file_id
        )
        if safe_caption:
            await context.bot.send_message(
                chat_id=user_id,
                text=prefix + safe_caption,
                parse_mode="HTML"
            )
        else:
            await context.bot.send_message(
                chat_id=user_id,
                text=prefix + log_text,
                parse_mode="HTML"
            )

    elif update.message.animation:
        log_text = "[Animation/GIF]"
        full_caption = prefix + (safe_caption if safe_caption else log_text)
        await context.bot.send_animation(
            chat_id=user_id,
            animation=update.message.animation.file_id,
            caption=full_caption,
            parse_mode="HTML"
        )

    elif update.message.video_note:
        log_text = "[Video Note]"
        await context.bot.send_video_note(
            chat_id=user_id,
            video_note=update.message.video_note.file_id
        )
        if safe_caption:
            await context.bot.send_message(
                chat_id=user_id,
                text=prefix + safe_caption,
                parse_mode="HTML"
            )
        else:
            await context.bot.send_message(
                chat_id=user_id,
                text=prefix + log_text,
                parse_mode="HTML"
            )

    else:
        log_text = f"[Unsupported message type]"
        await context.bot.send_message(
            chat_id=user_id,
            text=prefix + "Unsupported message type.",
            parse_mode="HTML"
        )

    ticket_messages[ticket_id].append(("BlockVeil Support", log_text, timestamp))

# ================= /close (ARG OR REPLY) =================
async def close_ticket(update: Update, context):
    if update.effective_chat.id != GROUP_ID:
        return

    ticket_id = None

    if context.args:
        ticket_id = context.args[0]
    elif update.message.reply_to_message:
        ticket_id = group_message_map.get(update.message.reply_to_message.message_id)

    if not ticket_id or ticket_id not in ticket_status:
        await update.message.reply_text(
            "❌ Ticket not found.\nUse /close BV-XXXXX or reply with /close",
            parse_mode="HTML"
        )
        return

    if ticket_status[ticket_id] == "Closed":
        await update.message.reply_text("⚠️ Ticket already closed.", parse_mode="HTML")
        return

    user_id = ticket_user[ticket_id]
    ticket_status[ticket_id] = "Closed"
    user_active_ticket.pop(user_id, None)

    await context.bot.send_message(
        chat_id=user_id,
        text=f"🎫 Ticket ID: {code(ticket_id)}\nStatus: Closed",
        parse_mode="HTML"
    )
    # Fix bug 23: show ticket ID in confirmation
    await update.message.reply_text(f"✅ Ticket {code(ticket_id)} closed.", parse_mode="HTML")

# ================= /requestclose =================
async def request_close(update: Update, context):
    """User command to request ticket closure"""
    # Fix bug 10: allow only in private chat
    if update.effective_chat.type != "private":
        await update.message.reply_text(
            "❌ This command can only be used in private chat with the bot.",
            parse_mode="HTML"
        )
        return

    user = update.message.from_user

    if not context.args:
        await update.message.reply_text(
            "❌ Please provide a ticket ID.\n"
            "Usage: /requestclose BV-XXXXX",
            parse_mode="HTML"
        )
        return

    ticket_id = context.args[0]

    if ticket_id not in ticket_status:
        await update.message.reply_text(
            f"❌ Ticket {code(ticket_id)} not found.",
            parse_mode="HTML"
        )
        return

    if ticket_user.get(ticket_id) != user.id:
        await update.message.reply_text(
            "❌ This ticket does not belong to you.",
            parse_mode="HTML"
        )
        return

    if ticket_status[ticket_id] == "Closed":
        await update.message.reply_text(
            f"⚠️ Ticket {code(ticket_id)} is already closed.",
            parse_mode="HTML"
        )
        return

    username = f"@{user.username}" if user.username else "N/A"
    notification = (
        f"🔔 <b>Ticket Close Request</b>\n\n"
        f"User {username} [ User ID : {user.id} ] has requested to close ticket ID {code(ticket_id)}\n\n"
        f"Please review and properly close the ticket."
    )

    await context.bot.send_message(
        chat_id=GROUP_ID,
        text=notification,
        parse_mode="HTML"
    )

    await update.message.reply_text(
        f"✅ Your request to close ticket {code(ticket_id)} has been sent to the support team.\n"
        f"They will review and close it shortly.",
        parse_mode="HTML"
    )

# ================= /send =================
async def send_direct(update: Update, context):
    if update.effective_chat.id != GROUP_ID:
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage:\n"
            "/send @all <message>\n"
            "/send BV-XXXXX <message>\n"
            "/send @username <message>\n"
            "/send user_id <message>",
            parse_mode="HTML"
        )
        return

    target = context.args[0]
    message = html.escape(" ".join(context.args[1:]))

    # Handle @all broadcast
    if target == "@all":
        sent_count = 0
        failed_count = 0
        unique_users = set()

        for user_id in ticket_user.values():
            unique_users.add(user_id)

        total_users = len(unique_users)
        await update.message.reply_text(f"📢 Broadcasting to {total_users} users...", parse_mode="HTML")

        for user_id in unique_users:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"📢 Announcement from BlockVeil Support:\n\n{message}",
                    parse_mode="HTML"
                )
                sent_count += 1
            except Exception as e:
                failed_count += 1
                print(f"Failed to send to {user_id}: {e}")

        await update.message.reply_text(
            f"📊 Broadcast Complete:\n"
            f"✅ Sent: {sent_count}\n"
            f"❌ Failed: {failed_count}\n"
            f"👥 Total: {total_users}",
            parse_mode="HTML"
        )
        return

    # Handle individual messages
    user_id = None
    ticket_id = None

    if target.startswith("BV-"):
        ticket_id = target
        if ticket_id not in ticket_status:
            await update.message.reply_text("❌ Ticket not found.", parse_mode="HTML")
            return
        if ticket_status[ticket_id] == "Closed":
            await update.message.reply_text("⚠️ Ticket is closed.", parse_mode="HTML")
            return
        user_id = ticket_user[ticket_id]
        # Include ticket ID only for ticket-specific messages
        final_message = f"🎫 Ticket ID: {code(ticket_id)}\n\n{message}"

    elif target.startswith("@"):
        username = target[1:]
        # Search in latest usernames first (case-insensitive)
        username_lower = username.lower()
        for uid, uname in user_latest_username.items():
            if uname.lower() == username_lower:
                user_id = uid
                break
        if not user_id:
            for tid, uname in ticket_username.items():
                if uname.lower() == username_lower:
                    user_id = ticket_user[tid]
                    break
        if not user_id:
            await update.message.reply_text("❌ User not found.", parse_mode="HTML")
            return
        # Do not include ticket ID for username sends
        final_message = f"📩 BlockVeil Support:\n\n{message}"

    else:
        try:
            user_id = int(target)
        except ValueError:
            # Fix bug 12: show error for invalid user ID
            await update.message.reply_text("❌ Invalid user ID or target.", parse_mode="HTML")
            return
        # Do not include ticket ID for user ID sends
        final_message = f"📩 BlockVeil Support:\n\n{message}"

    if not user_id:
        await update.message.reply_text("❌ User not found.", parse_mode="HTML")
        return

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=final_message,
            parse_mode="HTML"
        )
        await update.message.reply_text("✅ Message sent successfully.", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"No user was found in the database based on the information you provided to send the message. {e}", parse_mode="HTML")

# ================= /open =================
async def open_ticket(update: Update, context):
    if update.effective_chat.id != GROUP_ID:
        return

    if not context.args:
        return

    ticket_id = context.args[0]
    if ticket_id not in ticket_status:
        await update.message.reply_text("❌ Ticket not found.", parse_mode="HTML")
        return

    if ticket_status[ticket_id] != "Closed":
        await update.message.reply_text("⚠️ Ticket already open.", parse_mode="HTML")
        return

    ticket_status[ticket_id] = "Processing"
    user_active_ticket[ticket_user[ticket_id]] = ticket_id
    await update.message.reply_text(f"✅ Ticket {code(ticket_id)} reopened.", parse_mode="HTML")

# ================= /status =================
async def status_ticket(update: Update, context):
    if not context.args:
        await update.message.reply_text(
            "Use /status BV-XXXXX to check your ticket status.",
            parse_mode="HTML"
        )
        return

    ticket_id = context.args[0]
    if ticket_id not in ticket_status:
        await update.message.reply_text(
            f"❌ Ticket {code(ticket_id)} not found.",
            parse_mode="HTML"
        )
        return

    # Check if it's a private chat and the ticket doesn't belong to the user
    if update.effective_chat.type == "private":
        user_id = update.effective_user.id
        if ticket_user.get(ticket_id) != user_id:
            await update.message.reply_text(
                "❌ This ticket does not belong to you. Please use your correct Ticket ID.",
                parse_mode="HTML"
            )
            return

    text = f"🎫 Ticket ID: {code(ticket_id)}\nStatus: {ticket_status[ticket_id]}"
    # Fix bug 28: show creation time
    if ticket_id in ticket_created_at:
        text += f"\nCreated at: {ticket_created_at[ticket_id]} (BST)"
    if update.effective_chat.id == GROUP_ID:
        text += f"\nUser: @{ticket_username.get(ticket_id, 'N/A')}"

    await update.message.reply_text(text, parse_mode="HTML")

# ================= /profile =================
async def profile(update: Update, context):
    """Show user's profile with their tickets"""
    # Only in private chat
    if update.effective_chat.type != "private":
        await update.message.reply_text(
            "❌ This command can only be used in private chat with the bot.",
            parse_mode="HTML"
        )
        return

    user = update.effective_user
    user_id = user.id
    first_name = html.escape(user.first_name or "")
    username = user.username or "N/A"

    # Get user's tickets
    tickets = user_tickets.get(user_id, [])
    total_tickets = len(tickets)

    response = f"👤 <b>My Dashboard</b>\n\n"
    response += f"Name: {first_name}\n"
    response += f"Username: @{html.escape(username)}\n"
    response += f"UID: <code>{user_id}</code>\n\n"
    response += f"📊 Total Tickets Created: {total_tickets}\n"

    if tickets:
        response += "\n"
        for i, ticket_id in enumerate(tickets, 1):
            status = ticket_status.get(ticket_id, "Unknown")
            created = ticket_created_at.get(ticket_id, "Unknown")
            response += f"{i}. {code(ticket_id)} — {status}\n"
            response += f"   Created: {created}\n\n"
    else:
        response += "\nNo tickets created yet.\n\n"

    response += "⚠️ Please do not share your sensitive information with this bot and never share your Ticket ID with anyone. Only provide it directly to our official support bot."

    await update.message.reply_text(response, parse_mode="HTML")

# ================= /list =================
async def list_tickets(update: Update, context):
    if update.effective_chat.id != GROUP_ID:
        return
    if not context.args:
        return

    mode = context.args[0].lower()
    # Fix bug 16: validate mode
    if mode not in ["open", "close"]:
        await update.message.reply_text(
            "❌ Invalid mode. Use /list open or /list close",
            parse_mode="HTML"
        )
        return

    data = []

    for tid, st in ticket_status.items():
        if mode == "open" and st != "Closed":
            data.append((tid, ticket_username.get(tid)))
        elif mode == "close" and st == "Closed":
            data.append((tid, ticket_username.get(tid)))

    if not data:
        await update.message.reply_text("No tickets found.", parse_mode="HTML")
        return

    text = "📂 Open Tickets\n\n" if mode == "open" else "📁 Closed Tickets\n\n"
    for i, (tid, uname) in enumerate(data, 1):
        text += f"{i}. {code(tid)} – @{uname or 'N/A'}\n"

    await update.message.reply_text(text, parse_mode="HTML")

# ================= /export =================
async def export_ticket(update: Update, context):
    if update.effective_chat.id != GROUP_ID or not context.args:
        return

    ticket_id = context.args[0]
    if ticket_id not in ticket_messages:
        await update.message.reply_text("❌ Ticket not found.", parse_mode="HTML")
        return

    buf = BytesIO()
    buf.write("BlockVeil Support Messages\n\n".encode())

    # Fix bug 14: include timestamp and unescape message
    for sender, message, timestamp in ticket_messages[ticket_id]:
        # Unescape the stored escaped message to get original
        import html as html_lib
        original_message = html_lib.unescape(message)
        line = f"[{timestamp}] {sender} : {original_message}\n"
        buf.write(line.encode())

    buf.seek(0)
    buf.name = f"{ticket_id}.txt"
    await context.bot.send_document(GROUP_ID, document=buf)

# ================= /history =================
async def ticket_history(update: Update, context):
    if update.effective_chat.id != GROUP_ID or not context.args:
        return

    target = context.args[0]
    user_id = None

    if target.startswith("@"):
        username = target[1:]
        username_lower = username.lower()
        # Search in latest usernames first (case-insensitive)
        for uid, uname in user_latest_username.items():
            if uname.lower() == username_lower:
                user_id = uid
                break
        if not user_id:
            for tid, uname in ticket_username.items():
                if uname.lower() == username_lower:
                    user_id = ticket_user[tid]
                    break
    else:
        try:
            user_id = int(target)
        except:
            pass

    if user_id not in user_tickets:
        await update.message.reply_text("❌ User not found.", parse_mode="HTML")
        return

    text = f"📋 Ticket History for {target}\n\n"
    for i, tid in enumerate(user_tickets[user_id], 1):
        status = ticket_status.get(tid, "Unknown")
        created = ticket_created_at.get(tid, "")
        text += f"{i}. {code(tid)} - {status}"
        if created:
            text += f" (Created: {created} BST)"
        text += "\n"

    await update.message.reply_text(text, parse_mode="HTML")

# ================= /user =================
async def user_list(update: Update, context):
    if update.effective_chat.id != GROUP_ID:
        return

    buf = BytesIO()
    seen_users = set()
    count = 1

    for tid, user_id in ticket_user.items():
        if user_id in seen_users:
            continue
        seen_users.add(user_id)
        # Fix bug 22: use latest username
        username = user_latest_username.get(user_id, ticket_username.get(tid, "N/A"))
        buf.write(f"{count} - @{username} - {user_id}\n".encode())
        count += 1

    if count == 1:
        await update.message.reply_text("❌ No users found.", parse_mode="HTML")
        return

    buf.seek(0)
    buf.name = "users_list.txt"
    await context.bot.send_document(GROUP_ID, document=buf)

# ================= /which =================
async def which_user(update: Update, context):
    if update.effective_chat.id != GROUP_ID or not context.args:
        return

    target = context.args[0]
    user_id = None
    username = None

    if target.startswith("@"):
        username_target = target[1:]
        username_lower = username_target.lower()
        # Fix bug 22: search in latest usernames first (case-insensitive)
        for uid, uname in user_latest_username.items():
            if uname.lower() == username_lower:
                user_id = uid
                username = uname
                break
        if not user_id:
            for tid, uname in ticket_username.items():
                if uname.lower() == username_lower:
                    user_id = ticket_user[tid]
                    username = uname
                    break

    elif target.startswith("BV-"):
        ticket_id = target
        if ticket_id in ticket_user:
            user_id = ticket_user[ticket_id]
            username = user_latest_username.get(user_id, ticket_username.get(ticket_id, "N/A"))

    else:
        try:
            user_id = int(target)
            username = user_latest_username.get(user_id, "")
        except:
            pass

    if not user_id:
        await update.message.reply_text("❌ User not found.", parse_mode="HTML")
        return

    user_ticket_list = user_tickets.get(user_id, [])

    if not user_ticket_list:
        await update.message.reply_text("No user was found in the database based on the information you provided.", parse_mode="HTML")
        return

    response = f"👤 <b>User Information</b>\n\n"
    response += f"• User ID : {user_id}\n"
    response += f"• Username : @{html.escape(username) if username else 'N/A'}\n\n"
    response += f"📊 <b>Created total {len(user_ticket_list)} tickets.</b>\n\n"

    for i, ticket_id in enumerate(user_ticket_list, 1):
        status = ticket_status.get(ticket_id, "Unknown")
        created = ticket_created_at.get(ticket_id, "")
        response += f"{i}. {code(ticket_id)} - {status}"
        if created:
            response += f" (Created: {created} BST)"
        response += "\n"

    await update.message.reply_text(response, parse_mode="HTML")

# ================= INIT =================
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("close", close_ticket))
app.add_handler(CommandHandler("open", open_ticket))
app.add_handler(CommandHandler("send", send_direct))
app.add_handler(CommandHandler("status", status_ticket))
app.add_handler(CommandHandler("profile", profile))
app.add_handler(CommandHandler("list", list_tickets))
app.add_handler(CommandHandler("export", export_ticket))
app.add_handler(CommandHandler("history", ticket_history))
app.add_handler(CommandHandler("user", user_list))
app.add_handler(CommandHandler("which", which_user))
app.add_handler(CommandHandler("requestclose", request_close))
app.add_handler(CallbackQueryHandler(create_ticket, pattern="create_ticket"))
app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, user_message))
app.add_handler(MessageHandler(filters.ChatType.GROUPS & ~filters.COMMAND, group_reply))

app.run_polling()
