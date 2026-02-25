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
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Dhaka")).strftime("%Y-%m-%d %H:%M:%S")
    except ImportError:
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
ticket_username = {}  # username at ticket creation (kept for history)
ticket_messages = {}  # (sender, message, timestamp)
user_tickets = {}
group_message_map = {}
ticket_created_at = {}
user_latest_username = {}  # current username per user (all users who ever interacted)
user_message_timestamps = {}  # rate limiting

# ================= HELPER: Register any user interaction =================
def register_user(user):
    """Store or update user information when they interact with the bot."""
    user_latest_username[user.id] = user.username or ""

# ================= HELPERS =================
def generate_ticket_id(length=8):
    chars = string.ascii_letters + string.digits + "*#@$&"
    while True:
        tid = "BV-" + "".join(random.choice(chars) for _ in range(length))
        if tid not in ticket_status:
            return tid

def code(tid):
    return f"<code>{html.escape(tid)}</code>"

def ticket_header(ticket_id, status):
    return f"🎫 Ticket ID: {code(ticket_id)}\nStatus: {status}\n\n"

def user_info_block(user):
    safe_first_name = html.escape(user.first_name or "")
    return (
        "User Information\n"
        f"• User ID   : {user.id}\n"
        f"• Username  : @{html.escape(user.username or '')}\n"
        f"• Full Name : {safe_first_name}\n\n"
    )

def check_rate_limit(user_id):
    now = time.time()
    if user_id not in user_message_timestamps:
        user_message_timestamps[user_id] = []
    user_message_timestamps[user_id] = [t for t in user_message_timestamps[user_id] if now - t < 60]
    if len(user_message_timestamps[user_id]) >= 2:
        return False
    user_message_timestamps[user_id].append(now)
    return True

# ================= /start =================
async def start(update: Update, context):
    user = update.effective_user
    register_user(user)  # Ensure user is known even without ticket

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎟️ Create Ticket", callback_data="create_ticket")],
        [InlineKeyboardButton("👤 My Profile", callback_data="profile")]
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
    register_user(user)  # Update user info

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
    ticket_created_at[ticket_id] = get_bst_now()
    user_tickets.setdefault(user.id, []).append(ticket_id)

    await query.message.reply_text(
        f"🎫 Ticket Created: {code(ticket_id)}\n"
        "Status: Pending\n\n"
        "Please write and submit your issue or suggestion here in a clear and concise manner.\n"
        "Our support team will review it as soon as possible.",
        parse_mode="HTML"
    )

# ================= USER MESSAGE =================
async def user_message(update: Update, context):
    user = update.message.from_user
    register_user(user)  # Ensure user is known even if no ticket

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

    # Update username again in case it changed
    register_user(user)

    header = ticket_header(ticket_id, ticket_status[ticket_id]) + user_info_block(user) + "Message:\n"
    caption_text = update.message.caption or ""
    safe_caption = html.escape(caption_text) if caption_text else ""

    sent = None
    log_text = ""
    timestamp = get_bst_now()

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
        log_text = "[Unsupported message type]"
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
        ticket_messages[ticket_id].append((sender_name, log_text, timestamp))

# ================= GROUP REPLY =================
async def group_reply(update: Update, context):
    if not update.message.reply_to_message:
        return

    reply_id = update.message.reply_to_message.message_id
    if reply_id not in group_message_map:
        return

    ticket_id = group_message_map[reply_id]
    user_id = ticket_user[ticket_id]

    if ticket_status.get(ticket_id) == "Closed":
        await update.message.reply_text(
            f"⚠️ Ticket {code(ticket_id)} is already closed. Cannot send reply.",
            parse_mode="HTML"
        )
        return

    prefix = f"🎫 Ticket ID: {code(ticket_id)}\n\n"
    caption_text = update.message.caption or ""
    safe_caption = html.escape(caption_text) if caption_text else ""
    timestamp = get_bst_now()
    log_text = ""

    try:
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
            log_text = "[Unsupported message type]"
            await context.bot.send_message(
                chat_id=user_id,
                text=prefix + "Unsupported message type.",
                parse_mode="HTML"
            )
    except Exception as e:
        await update.message.reply_text(
            f"❌ Failed to send reply to user: {e}",
            parse_mode="HTML"
        )
        return

    ticket_messages[ticket_id].append(("BlockVeil Support", log_text, timestamp))

# ================= /close =================
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

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"🎫 Ticket ID: {code(ticket_id)}\nStatus: Closed",
            parse_mode="HTML"
        )
    except Exception as e:
        await update.message.reply_text(
            f"⚠️ Ticket closed but failed to notify user: {e}",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(f"✅ Ticket {code(ticket_id)} closed.", parse_mode="HTML")

# ================= /requestclose =================
async def request_close(update: Update, context):
    if update.effective_chat.type != "private":
        await update.message.reply_text(
            "❌ This command can only be used in private chat with the bot.",
            parse_mode="HTML"
        )
        return

    user = update.message.from_user
    register_user(user)  # Update user info

    if not context.args:
        await update.message.reply_text(
            "❌ Please provide a ticket ID.\nUsage: /requestclose BV-XXXXX",
            parse_mode="HTML"
        )
        return

    ticket_id = context.args[0]
    if ticket_id not in ticket_status:
        await update.message.reply_text(f"❌ Ticket {code(ticket_id)} not found.", parse_mode="HTML")
        return
    if ticket_user.get(ticket_id) != user.id:
        await update.message.reply_text("❌ This ticket does not belong to you.", parse_mode="HTML")
        return
    if ticket_status[ticket_id] == "Closed":
        await update.message.reply_text(f"⚠️ Ticket {code(ticket_id)} is already closed.", parse_mode="HTML")
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

# ================= /send (text only) =================
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

    if target == "@all":
        sent_count = 0
        failed_count = 0
        unique_users = set(user_latest_username.keys())
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
            f"📊 Broadcast Complete:\n✅ Sent: {sent_count}\n❌ Failed: {failed_count}\n👥 Total: {total_users}",
            parse_mode="HTML"
        )
        return

    user_id = None
    ticket_id = None
    final_message = ""

    if target.startswith("BV-"):
        ticket_id = target
        if ticket_id not in ticket_status:
            await update.message.reply_text("❌ Ticket not found.", parse_mode="HTML")
            return
        if ticket_status[ticket_id] == "Closed":
            await update.message.reply_text("⚠️ Ticket is closed.", parse_mode="HTML")
            return
        user_id = ticket_user[ticket_id]
        final_message = f"🎫 Ticket ID: {code(ticket_id)}\n\n{message}"

    elif target.startswith("@"):
        username = target[1:]
        # Fix: empty username check
        if not username:
            await update.message.reply_text("❌ Username cannot be empty.", parse_mode="HTML")
            return
        username_lower = username.lower()
        for uid, uname in user_latest_username.items():
            if uname.lower() == username_lower:
                user_id = uid
                break
        if not user_id:
            await update.message.reply_text("❌ User not found.", parse_mode="HTML")
            return
        final_message = f"📩 BlockVeil Support:\n\n{message}"

    else:
        try:
            user_id = int(target)
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID or target.", parse_mode="HTML")
            return
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
        # Log the message if it was sent to a ticket
        if ticket_id:
            timestamp = get_bst_now()
            ticket_messages[ticket_id].append(("BlockVeil Support", message, timestamp))
        await update.message.reply_text("✅ Message sent successfully.", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to send: {e}", parse_mode="HTML")

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

    user_id = ticket_user[ticket_id]

    # Check if user already has an active ticket
    if user_id in user_active_ticket:
        await update.message.reply_text(
            "❌ This user already has an active ticket, so reopening this ticket at the moment is not possible.",
            parse_mode="HTML"
        )
        return

    ticket_status[ticket_id] = "Processing"
    user_active_ticket[user_id] = ticket_id

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"🎫 Your ticket {code(ticket_id)} has been reopened by support.",
            parse_mode="HTML"
        )
    except Exception as e:
        await update.message.reply_text(
            f"⚠️ Ticket reopened but failed to notify user: {e}",
            parse_mode="HTML"
        )
    else:
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
        await update.message.reply_text(f"❌ Ticket {code(ticket_id)} not found.", parse_mode="HTML")
        return

    if update.effective_chat.type == "private":
        user_id = update.effective_user.id
        register_user(update.effective_user)  # Update user info
        if ticket_user.get(ticket_id) != user_id:
            await update.message.reply_text(
                "❌ This ticket does not belong to you. Please use your correct Ticket ID.",
                parse_mode="HTML"
            )
            return

    text = f"🎫 Ticket ID: {code(ticket_id)}\nStatus: {ticket_status[ticket_id]}"
    if ticket_id in ticket_created_at:
        text += f"\nCreated at: {ticket_created_at[ticket_id]} (BST)"
    if update.effective_chat.id == GROUP_ID:
        uid = ticket_user[ticket_id]
        current_username = user_latest_username.get(uid, ticket_username.get(ticket_id, "N/A"))
        text += f"\nUser: @{current_username}"

    await update.message.reply_text(text, parse_mode="HTML")

# ================= /profile =================
async def profile(update: Update, context):
    # Works for both command and callback
    if update.callback_query:
        await update.callback_query.answer()
        user = update.callback_query.from_user
        chat_id = update.callback_query.message.chat_id
    else:
        if update.effective_chat.type != "private":
            await update.message.reply_text(
                "❌ This command can only be used in private chat with the bot.",
                parse_mode="HTML"
            )
            return
        user = update.effective_user
        chat_id = update.message.chat_id

    register_user(user)  # Update user info

    user_id = user.id
    first_name = html.escape(user.first_name or "")
    username = user.username or "N/A"

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

    await context.bot.send_message(chat_id=chat_id, text=response, parse_mode="HTML")

# ================= /list =================
async def list_tickets(update: Update, context):
    if update.effective_chat.id != GROUP_ID:
        return
    if not context.args:
        return

    mode = context.args[0].lower()
    if mode not in ["open", "close"]:
        await update.message.reply_text(
            "❌ Invalid mode. Use /list open or /list close",
            parse_mode="HTML"
        )
        return

    data = []
    for tid, st in ticket_status.items():
        if (mode == "open" and st != "Closed") or (mode == "close" and st == "Closed"):
            uid = ticket_user[tid]
            current_username = user_latest_username.get(uid, ticket_username.get(tid, "N/A"))
            data.append((tid, current_username))

    if not data:
        await update.message.reply_text("No tickets found.", parse_mode="HTML")
        return

    text = "📂 Open Tickets\n\n" if mode == "open" else "📁 Closed Tickets\n\n"
    for i, (tid, uname) in enumerate(data, 1):
        text += f"{i}. {code(tid)} – @{uname}\n"

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
    for sender, message, timestamp in ticket_messages[ticket_id]:
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
        # Search in all known users (user_latest_username)
        for uid, uname in user_latest_username.items():
            if uname.lower() == username_lower:
                user_id = uid
                break
        if not user_id:
            # Fallback to ticket usernames (old)
            for tid, uname in ticket_username.items():
                if uname.lower() == username_lower:
                    user_id = ticket_user[tid]
                    break
    else:
        try:
            user_id = int(target)
        except:
            pass

    # If user_id is None, user not found
    if user_id is None:
        await update.message.reply_text("❌ User not found.", parse_mode="HTML")
        return

    # Check if user has any tickets
    if user_id not in user_tickets:
        # User exists in user_latest_username? (if found from ticket_username, they would have tickets)
        if user_id in user_latest_username:
            await update.message.reply_text("❌ User has no tickets.", parse_mode="HTML")
        else:
            # This case should not happen if we found from ticket_username, but just in case
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
    count = 1
    # List all known users from user_latest_username (everyone who interacted)
    for user_id, username in user_latest_username.items():
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
        # Search in all known users first
        for uid, uname in user_latest_username.items():
            if uname.lower() == username_lower:
                user_id = uid
                username = uname
                break
        if not user_id:
            # Fallback to ticket usernames
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
        # Still show user info even if no tickets
        response = f"👤 <b>User Information</b>\n\n"
        response += f"• User ID : {user_id}\n"
        response += f"• Username : @{html.escape(username) if username else 'N/A'}\n\n"
        response += "📊 No tickets created yet."
    else:
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

# ================= MEDIA SEND COMMANDS (reply-based) =================
async def send_media(update: Update, context, media_type):
    """Generic handler for sending media by replying to a media message."""
    if update.effective_chat.id != GROUP_ID:
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            f"❌ Please reply to a {media_type} message with this command.",
            parse_mode="HTML"
        )
        return

    replied = update.message.reply_to_message
    has_media = False
    file_id = None
    media_caption = replied.caption or ""

    if media_type == "photo" and replied.photo:
        file_id = replied.photo[-1].file_id
        has_media = True
    elif media_type == "document" and replied.document:
        file_id = replied.document.file_id
        has_media = True
    elif media_type == "audio" and replied.audio:
        file_id = replied.audio.file_id
        has_media = True
    elif media_type == "voice" and replied.voice:
        file_id = replied.voice.file_id
        has_media = True
    elif media_type == "video" and replied.video:
        file_id = replied.video.file_id
        has_media = True
    elif media_type == "animation" and replied.animation:
        file_id = replied.animation.file_id
        has_media = True
    elif media_type == "sticker" and replied.sticker:
        file_id = replied.sticker.file_id
        has_media = True

    if not has_media:
        await update.message.reply_text(
            f"❌ The replied message does not contain a {media_type}.",
            parse_mode="HTML"
        )
        return

    if len(context.args) < 1:
        await update.message.reply_text(
            f"Usage: Reply to a {media_type} with /send_{media_type} @username or /send_{media_type} BV-XXXXX or /send_{media_type} user_id",
            parse_mode="HTML"
        )
        return

    target = context.args[0]
    # Optional caption: remaining args
    if len(context.args) > 1:
        custom_caption = html.escape(" ".join(context.args[1:]))
    else:
        custom_caption = ""

    # Resolve target user_id
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
        prefix = f"🎫 Ticket ID: {code(ticket_id)}\n"
    elif target.startswith("@"):
        username = target[1:]
        if not username:
            await update.message.reply_text("❌ Username cannot be empty.", parse_mode="HTML")
            return
        username_lower = username.lower()
        for uid, uname in user_latest_username.items():
            if uname.lower() == username_lower:
                user_id = uid
                break
        if not user_id:
            await update.message.reply_text("❌ User not found.", parse_mode="HTML")
            return
        prefix = "📩 BlockVeil Support:\n"
    else:
        try:
            user_id = int(target)
        except ValueError:
            await update.message.reply_text("❌ Invalid target.", parse_mode="HTML")
            return
        prefix = "📩 BlockVeil Support:\n"

    if not user_id:
        await update.message.reply_text("❌ User not found.", parse_mode="HTML")
        return

    # Build caption
    if custom_caption:
        final_caption = prefix + custom_caption
        log_text = custom_caption  # store without prefix
    else:
        final_caption = prefix + (media_caption if media_caption else "")
        log_text = media_caption if media_caption else f"[{media_type.capitalize()}]"

    # Send media
    try:
        if media_type == "photo":
            await context.bot.send_photo(chat_id=user_id, photo=file_id, caption=final_caption, parse_mode="HTML")
        elif media_type == "document":
            await context.bot.send_document(chat_id=user_id, document=file_id, caption=final_caption, parse_mode="HTML")
        elif media_type == "audio":
            await context.bot.send_audio(chat_id=user_id, audio=file_id, caption=final_caption, parse_mode="HTML")
        elif media_type == "voice":
            await context.bot.send_voice(chat_id=user_id, voice=file_id, caption=final_caption, parse_mode="HTML")
        elif media_type == "video":
            await context.bot.send_video(chat_id=user_id, video=file_id, caption=final_caption, parse_mode="HTML")
        elif media_type == "animation":
            await context.bot.send_animation(chat_id=user_id, animation=file_id, caption=final_caption, parse_mode="HTML")
        elif media_type == "sticker":
            await context.bot.send_sticker(chat_id=user_id, sticker=file_id)
            if final_caption:
                await context.bot.send_message(chat_id=user_id, text=final_caption, parse_mode="HTML")
                log_text = final_caption  # for sticker, caption is separate message
            else:
                log_text = "[Sticker]"
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to send: {e}", parse_mode="HTML")
        return

    # Log the message if it was sent to a ticket
    if ticket_id:
        timestamp = get_bst_now()
        ticket_messages[ticket_id].append(("BlockVeil Support", log_text, timestamp))

    await update.message.reply_text("✅ Media sent successfully.", parse_mode="HTML")

# Individual command handlers
async def send_photo(update: Update, context):
    await send_media(update, context, "photo")

async def send_document(update: Update, context):
    await send_media(update, context, "document")

async def send_audio(update: Update, context):
    await send_media(update, context, "audio")

async def send_voice(update: Update, context):
    await send_media(update, context, "voice")

async def send_video(update: Update, context):
    await send_media(update, context, "video")

async def send_animation(update: Update, context):
    await send_media(update, context, "animation")

async def send_sticker(update: Update, context):
    await send_media(update, context, "sticker")

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

# Media send commands
app.add_handler(CommandHandler("send_photo", send_photo))
app.add_handler(CommandHandler("send_document", send_document))
app.add_handler(CommandHandler("send_audio", send_audio))
app.add_handler(CommandHandler("send_voice", send_voice))
app.add_handler(CommandHandler("send_video", send_video))
app.add_handler(CommandHandler("send_animation", send_animation))
app.add_handler(CommandHandler("send_sticker", send_sticker))

app.add_handler(CallbackQueryHandler(create_ticket, pattern="create_ticket"))
app.add_handler(CallbackQueryHandler(profile, pattern="profile"))

app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, user_message))
app.add_handler(MessageHandler(filters.ChatType.GROUPS & ~filters.COMMAND, group_reply))

app.run_polling()
