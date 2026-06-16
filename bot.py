"""
aNamaka Escrow Bot — Final Version with Premium Stickers
Uses: pyTelegramBotAPI (telebot)
"""

import telebot
from telebot import types
import json, os, datetime, threading, time, re
from html import escape

# ══════════════════════════════════════════════════
BOT_TOKEN       = os.environ.get("BOT_TOKEN", "")
VOUCH_CHANNEL   = os.environ.get("VOUCH_CHANNEL", "@YourVouchChannel")
CRYPTO_FEE      = 2
INR_FEE_PCT     = 5
DEAL_PREFIX     = "CRPTIN"
CONFIRM_TIMEOUT = 15 * 60
DATA_FILE       = "escrow_data.json"

# ── Premium Sticker File IDs ──
STICKER_LOCK        = "CAACAgIAAxkBAAIBB2hxsample_lock"        # 🔒 shown before deal card
STICKER_HANDSHAKE   = "CAACAgIAAxkBAAIBB2hxsample_handshake"  # 🤝 both confirmed
STICKER_GREEN_TICK  = "CAACAgIAAxkBAAIBB2hxsample_tick"       # ✅ deal complete
STICKER_SHIELD      = "CAACAgIAAxkBAAIBB2hxsample_shield"     # 🛡️ escrowed by

# Sticker pack numeric IDs (for sending via file_unique_id workaround)
# Using the IDs you provided — these are animated premium stickers
PACK_LOCK        = "5197288647275071607"
PACK_BUYER_SELL  = "5879770735999717115"
PACK_HANDSHAKE   = "5472284034459532343"
PACK_GREEN_TICK  = "6120635817674149717"
PACK_FEES        = "5201691993775818138"
PACK_DOLLAR      = "6098329329496758311"
PACK_SHIELD      = "6120946172010959542"
# ══════════════════════════════════════════════════

# Premium custom emoji IDs. Use these inside HTML messages, not send_sticker().
EMOJI_SHIELD     = '<tg-emoji emoji-id="5197288647275071607">🛡️</tg-emoji>'
EMOJI_USER       = '<tg-emoji emoji-id="5879770735999717115">👤</tg-emoji>'
EMOJI_HANDSHAKE  = '<tg-emoji emoji-id="5472284034459532343">🤝</tg-emoji>'
EMOJI_GREEN_TICK = '<tg-emoji emoji-id="6120635817674149717">✅</tg-emoji>'

bot = telebot.TeleBot(BOT_TOKEN)

# ─────────────────────────────────────────────────
#  STICKER SENDER — tries premium sticker IDs
# ─────────────────────────────────────────────────
def send_sticker(chat_id, sticker_id):
    """Send sticker by file_id. Silently fails if not found."""
    try:
        bot.send_sticker(chat_id, sticker_id)
    except Exception as e:
        print(f"Sticker send failed: {e}")

# ─────────────────────────────────────────────────
#  ADMIN CHECK
# ─────────────────────────────────────────────────
def is_admin(chat_id, user_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except:
        return False

def is_in_group(chat_id, user_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ("member", "administrator", "creator", "restricted")
    except:
        return False

# ─────────────────────────────────────────────────
#  CURRENCY DETECTION
# ─────────────────────────────────────────────────
CRYPTO_KEYWORDS = {"usdt","usdc","btc","eth","bnb","trx","sol","ltc","xrp","crypto","usd","$","dollar"}

def detect_currency(amount_str, network_str):
    combined = (amount_str + " " + network_str).lower()
    for kw in CRYPTO_KEYWORDS:
        if kw in combined:
            sym = "USDT"
            for c in ["usdt","usdc","btc","eth","bnb","trx","sol","ltc","xrp"]:
                if c in combined:
                    sym = c.upper()
                    break
            return "CRYPTO", sym
    return "INR", "₹"

def fmt(amount):
    try:
        f = float(amount)
        return f"{int(f):,}" if f == int(f) else f"{f:,.2f}"
    except:
        return str(amount)

# ─────────────────────────────────────────────────
#  DATA LAYER
# ─────────────────────────────────────────────────
def load():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"deals": {}, "users": {}, "counter": 1}

def save(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def next_id(data):
    n = data["counter"]
    data["counter"] += 1
    save(data)
    return f"{DEAL_PREFIX}{str(n).zfill(5)}"

def _parse_deal_id(raw):
    raw = raw.lstrip("#").upper()
    if not raw.startswith(DEAL_PREFIX):
        return f"{DEAL_PREFIX}{raw.zfill(5)}"
    return raw

def ensure_user(data, username, user_id=None):
    uname = username.lstrip("@").lower()
    for uid_key, u in data["users"].items():
        if u.get("username","").lower() == uname:
            if user_id and not u.get("user_id"):
                u["user_id"] = user_id
            return uid_key
    uid_key = str(user_id) if user_id else f"u_{uname}"
    data["users"][uid_key] = {
        "username": username.lstrip("@"),
        "user_id": user_id or 0,
        "total_deals": 0,
        "completed_deals": 0,
        "total_volume": 0.0,
        "ongoing_deals": 0,
        "as_buyer": 0,
        "as_seller": 0,
        "as_escrow": 0,
        "deal_ids": [],
        "joined": datetime.datetime.now().isoformat()
    }
    return uid_key

# ─────────────────────────────────────────────────
#  FORM PARSER — dash "-" format
# ─────────────────────────────────────────────────
def parse_form(text):
    result = {}
    terms_lines = []
    in_terms = False

    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        low = line.lower()

        if in_terms:
            terms_lines.append(line)
            continue

        if "-" not in line and ":" not in line:
            if "terms" in low or "condition" in low:
                in_terms = True
            continue

        val = line.split("-", 1)[1].strip() if "-" in line else line.split(":", 1)[1].strip()

        if not val:
            if "terms" in low or "condition" in low:
                in_terms = True
            continue

        if re.search(r"\bbuyer\b", low) and "seller" not in low:
            result["buyer"] = val.lstrip("@").split()[0].strip(".,")
        elif re.search(r"\bseller\b", low):
            result["seller"] = val.lstrip("@").split()[0].strip(".,")
        elif "time" in low:
            result["timeframe"] = val
        elif "amount" in low:
            result["amount_raw"] = val
            clean = re.sub(r"[₹$€£\s]", " ", val)
            match = re.search(r"[\d,]+\.?\d*", clean)
            if match:
                try:
                    result["amount"] = float(match.group(0).replace(",",""))
                except:
                    result["amount"] = 0.0
        elif "network" in low:
            result["network"] = val
        elif "terms" in low or "condition" in low:
            in_terms = True
            result["condition"] = val if "-" in line else ""

    if terms_lines:
        extra = " ".join(terms_lines)
        result["condition"] = (result.get("condition","") + " " + extra).strip()
    if not result.get("condition"):
        result["condition"] = "Release after confirmation"

    return result

# ─────────────────────────────────────────────────
pending = {}

# ─────────────────────────────────────────────────
#  /form /dd — Blank Form (exactly like Image 5)
# ─────────────────────────────────────────────────
BLANK_FORM = (
    "Username of Buyer - \n"
    "Username of Seller - \n"
    "Time to complete - \n"
    "Amount - \n"
    "Network - \n\n"
    "Terms and Condition [ Mention terms , dont regret later]"
)

@bot.message_handler(commands=["form","dd"])
def cmd_form(message):
    bot.send_message(message.chat.id, BLANK_FORM)

# ─────────────────────────────────────────────────
#  /deal — Group Admin replies to filled form
#  Design: Image 2 — deal card with buttons
# ─────────────────────────────────────────────────
@bot.message_handler(commands=["deal"])
def cmd_deal(message):
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ Only group admins can use /deal.")
        return

    escrow_uname = message.from_user.username or message.from_user.first_name
    escrow_id    = message.from_user.id

    if not message.reply_to_message:
        bot.reply_to(message, "ℹ️ Reply to the filled form and type /deal.")
        return

    form_text = message.reply_to_message.text or ""
    if "buyer" not in form_text.lower() or "seller" not in form_text.lower():
        bot.reply_to(message, "❌ This does not look like a valid escrow form.")
        return

    form    = parse_form(form_text)
    missing = [f for f in ["buyer","seller","amount","timeframe","network"] if not form.get(f)]
    if missing:
        bot.reply_to(message,
            "❌ Missing fields:\n" + "\n".join(f"  • {m}" for m in missing))
        return

    data    = load()
    deal_id = next_id(data)
    amount  = form["amount"]
    network = form.get("network","")
    ctype, csym = detect_currency(form.get("amount_raw",""), network)

    if ctype == "CRYPTO":
        fee        = CRYPTO_FEE
        total      = round(amount + fee, 2)
        fee_text   = f"{fee}% (${fmt(fee)})"
        total_text = f"${fmt(total)}"
        amt_text   = f"${fmt(amount)}"
    else:
        fee        = round(amount * INR_FEE_PCT / 100, 2)
        total      = round(amount + fee, 2)
        fee_text   = f"{INR_FEE_PCT}% (₹{fmt(fee)})"
        total_text = f"₹{fmt(total)}"
        amt_text   = f"₹{fmt(amount)}"

    pending[deal_id] = {
        "deal_id":          deal_id,
        "buyer":            form["buyer"],
        "seller":           form["seller"],
        "escrow":           escrow_uname,
        "escrow_id":        escrow_id,
        "condition":        form["condition"],
        "timeframe":        form["timeframe"],
        "amount":           amount,
        "network":          network,
        "currency_type":    ctype,
        "currency_sym":     csym,
        "fee":              fee,
        "total":            total,
        "confirmed_buyer":  False,
        "confirmed_seller": False,
        "chat_id":          message.chat.id,
        "status":           "AWAITING_CONFIRM",
        "created_at":       datetime.datetime.now().isoformat(),
    }

    # ── Deal card — exactly like Image 2 ──
    card = (
        f"🆔 DEAL ID: #{deal_id}\n\n"
        f"👤 Buyer: @{form['buyer']}\n"
        f"👤 Seller: @{form['seller']}\n"
        f"🔒 Escrow Condition: {form['condition']}\n"
        f"⏱ Timeframe: {form['timeframe']}\n"
        f"💰 Deal Amount: {amt_text}\n"
        f"🌐 Mode of Payment: {network}\n"
        f"💸 Escrow Fee: {fee_text}\n"
        f"💵 Total Payable: {total_text}\n\n"
        f"🔐 Escrower: @{escrow_uname}\n\n"
        f"📋 Please review and confirm the deal.\n"
        f"Auto-cancels in 15 minutes if not confirmed."
    )

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Seller Confirm", callback_data=f"cs_{deal_id}"),
        types.InlineKeyboardButton("✅ Buyer Confirm",  callback_data=f"cb_{deal_id}")
    )
    markup.add(types.InlineKeyboardButton("❌ Cancel Deal", callback_data=f"cx_{deal_id}"))

    # 🔒 sticker before deal card
    send_sticker(message.chat.id, PACK_LOCK)

    sent = bot.send_message(message.chat.id, card, reply_markup=markup)
    pending[deal_id]["msg_id"] = sent.message_id

    # Auto cancel thread
    def _auto_cancel():
        time.sleep(CONFIRM_TIMEOUT)
        if deal_id in pending and pending[deal_id]["status"] == "AWAITING_CONFIRM":
            del pending[deal_id]
            try:
                bot.edit_message_reply_markup(message.chat.id, sent.message_id, reply_markup=None)
                bot.send_message(message.chat.id,
                    f"⏰ Deal #{deal_id} auto-cancelled (not confirmed in 15 min).")
            except: pass
    threading.Thread(target=_auto_cancel, daemon=True).start()

# ─────────────────────────────────────────────────
#  CONFIRM / CANCEL CALLBACKS
# ─────────────────────────────────────────────────
@bot.callback_query_handler(func=lambda c: c.data[:3] in ("cs_","cb_","cx_"))
def handle_confirm(call):
    prefix    = call.data[:3]
    deal_id   = call.data[3:]
    caller_u  = (call.from_user.username or call.from_user.first_name or "").lower()
    caller_id = call.from_user.id

    if deal_id not in pending:
        bot.answer_callback_query(call.id, "❌ Deal not found or expired.")
        return

    state = pending[deal_id]

    # Cancel
    if prefix == "cx_":
        if caller_id != state["escrow_id"] and not is_admin(call.message.chat.id, caller_id):
            bot.answer_callback_query(call.id, "❌ Only the escrower can cancel.", show_alert=True)
            return
        del pending[deal_id]
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except: pass
        bot.send_message(call.message.chat.id, f"❌ Deal #{deal_id} has been cancelled.")
        bot.answer_callback_query(call.id, "Cancelled.")
        return

    # Seller confirm
    if prefix == "cs_":
        if caller_u != state["seller"].lower():
            bot.answer_callback_query(call.id,
                f"❌ Only seller @{state['seller']} can confirm.", show_alert=True)
            return
        if state["confirmed_seller"]:
            bot.answer_callback_query(call.id, "You already confirmed!")
            return
        state["confirmed_seller"] = True
        bot.answer_callback_query(call.id, "✅ Seller confirmed!")
        # Image 2 style confirm message
        bot.send_message(call.message.chat.id,
            f"✅ Seller @{state['seller']} has confirmed the deal for #{deal_id}.")

    # Buyer confirm
    elif prefix == "cb_":
        if caller_u != state["buyer"].lower():
            bot.answer_callback_query(call.id,
                f"❌ Only buyer @{state['buyer']} can confirm.", show_alert=True)
            return
        if state["confirmed_buyer"]:
            bot.answer_callback_query(call.id, "You already confirmed!")
            return
        state["confirmed_buyer"] = True
        bot.answer_callback_query(call.id, "✅ Buyer confirmed!")
        bot.send_message(call.message.chat.id,
            f"✅ Buyer @{state['buyer']} has confirmed the deal for #{deal_id}.")

    _update_buttons(call.message.chat.id, call.message.message_id, state, deal_id)

    if state["confirmed_buyer"] and state["confirmed_seller"]:
        _activate_deal(call.message.chat.id, call.message.message_id, deal_id, state)


def _update_buttons(chat_id, msg_id, state, deal_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(
            "Seller ✅ Confirmed" if state["confirmed_seller"] else "✅ Seller Confirm",
            callback_data=f"cs_{deal_id}"),
        types.InlineKeyboardButton(
            "Buyer ✅ Confirmed" if state["confirmed_buyer"] else "✅ Buyer Confirm",
            callback_data=f"cb_{deal_id}")
    )
    if not (state["confirmed_buyer"] and state["confirmed_seller"]):
        markup.add(types.InlineKeyboardButton("❌ Cancel Deal", callback_data=f"cx_{deal_id}"))
    try:
        bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=markup)
    except: pass


def _activate_deal(chat_id, msg_id, deal_id, state):
    data = load()
    try:
        bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=None)
    except: pass

    record = {k: v for k, v in state.items()
              if k not in ("confirmed_buyer","confirmed_seller","msg_id")}
    record["status"]       = "AWAITING_PAYMENT"
    record["activated_at"] = datetime.datetime.now().isoformat()
    data["deals"][deal_id] = record

    for uname, role in [(state["buyer"],"buyer"), (state["seller"],"seller")]:
        uk = ensure_user(data, uname)
        u  = data["users"][uk]
        u["total_deals"]   += 1
        u[f"as_{role}"]    += 1
        u["ongoing_deals"] += 1
        if deal_id not in u["deal_ids"]:
            u["deal_ids"].append(deal_id)

    ek = ensure_user(data, state["escrow"], state["escrow_id"])
    e  = data["users"][ek]
    e["total_deals"]   += 1
    e["as_escrow"]     += 1
    e["ongoing_deals"] += 1
    if deal_id not in e["deal_ids"]:
        e["deal_ids"].append(deal_id)

    save(data)
    if deal_id in pending:
        del pending[deal_id]

    ctype = state["currency_type"]
    amt   = state["amount"]
    fee   = state["fee"]
    total = state["total"]

    if ctype == "CRYPTO":
        fee_line = f"${fmt(fee)}"
        amt_line = f"${fmt(amt)}"
    else:
        fee_line = f"₹{fmt(fee)}"
        amt_line = f"₹{fmt(amt)}"

    # ── Image 1 style — Deal Confirmed card ──
    send_sticker(chat_id, PACK_GREEN_TICK)
    bot.send_message(chat_id,
        f"✅ Deal Confirmed\n\n"
        f"🛡️ ID: #{deal_id}\n"
        f"🤝 Escrower - @{state['escrow']}\n"
        f"👤 Seller - @{state['seller']}\n"
        f"👤 Buyer - @{state['buyer']}\n"
        f"💰 Fees - {fee_line}\n"
        f"💵 Amount - {amt_line}"
    )

    # ── Image 3 style — Pay to Escrower ──
    send_sticker(chat_id, PACK_HANDSHAKE)
    buyer_html = escape(state["buyer"])
    seller_html = escape(state["seller"])
    escrow_html = escape(state["escrow"])
    deal_id_html = escape(deal_id)
    bot.send_message(chat_id,
        f"{EMOJI_SHIELD} DEAL ID: #{deal_id_html}\n\n"
        f"{EMOJI_USER} Buyer - @{buyer_html}\n"
        f"{EMOJI_USER} Seller - @{seller_html}\n\n"
        f"{EMOJI_HANDSHAKE} Both Buyer And Seller Have Confirmed The Deal. {EMOJI_GREEN_TICK}\n\n"
        f"Please Pay To Your Escrower\n"
        f"@{escrow_html} To Continue Your Deal {EMOJI_HANDSHAKE}",
        parse_mode="HTML"
    )

# ─────────────────────────────────────────────────
#  /received — Admin marks payment received
# ─────────────────────────────────────────────────
@bot.message_handler(commands=["received","got"])
def cmd_received(message):
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ Only group admins can use this.")
        return

    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /received CRPTIN00001")
        return

    deal_id = _parse_deal_id(parts[1])
    data    = load()

    if deal_id not in data["deals"]:
        bot.reply_to(message, f"❌ Deal #{deal_id} not found.")
        return

    deal = data["deals"][deal_id]
    if deal.get("received"):
        bot.reply_to(message, f"⚠️ Already marked received.")
        return

    ctype = deal.get("currency_type","INR")
    amt   = deal["amount"]
    fee   = deal["fee"]
    total = deal["total"]

    if ctype == "CRYPTO":
        fee_line = f"${fmt(fee)}"
        tot_line = f"${fmt(total)}"
        amt_line = f"${fmt(amt)}"
    else:
        fee_line = f"₹{fmt(fee)}"
        tot_line = f"₹{fmt(total)}"
        amt_line = f"₹{fmt(amt)}"

    deal["received"]    = True
    deal["status"]      = "IN_PROGRESS"
    deal["received_at"] = datetime.datetime.now().isoformat()
    save(data)

    send_sticker(message.chat.id, PACK_DOLLAR)
    bot.send_message(message.chat.id,
        f"💰 Payment Received!\n\n"
        f"🆔 Trade ID: #{deal_id}\n"
        f"💵 Received: {tot_line}\n"
        f"📤 Release Amount: {amt_line}\n"
        f"💸 Escrow Fee: {fee_line}\n\n"
        f"👤 Buyer: @{deal['buyer']}\n"
        f"👤 Seller: @{deal['seller']}\n"
        f"🔐 Escrower: @{deal['escrow']}\n\n"
        f"➡️ Now proceed with the deal."
    )

# ─────────────────────────────────────────────────
#  /complete — Deal complete + vouch
#  Design: Image 4
# ─────────────────────────────────────────────────
@bot.message_handler(commands=["complete","close"])
def cmd_complete(message):
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ Only group admins can use this.")
        return

    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /complete CRPTIN00001")
        return

    deal_id = _parse_deal_id(parts[1])
    data    = load()

    if deal_id not in data["deals"]:
        bot.reply_to(message, f"❌ Deal #{deal_id} not found.")
        return

    deal = data["deals"][deal_id]
    if not deal.get("received"):
        bot.reply_to(message, f"⚠️ Run /received {deal_id} first.")
        return
    if deal.get("completed"):
        bot.reply_to(message, f"⚠️ Already completed.")
        return

    ctype  = deal.get("currency_type","INR")
    amt    = deal["amount"]
    csym   = "$" if ctype == "CRYPTO" else "₹"
    date_str = datetime.datetime.now().strftime("%d %b %Y")

    deal["completed"]    = True
    deal["status"]       = "COMPLETED"
    deal["completed_at"] = datetime.datetime.now().isoformat()

    for uid_key, u in data["users"].items():
        uname = u.get("username","").lower()
        if uname in [deal["buyer"].lower(), deal["seller"].lower(), deal["escrow"].lower()]:
            u["completed_deals"] = u.get("completed_deals",0) + 1
            u["ongoing_deals"]   = max(0, u.get("ongoing_deals",1) - 1)
            u["total_volume"]    = round(u.get("total_volume",0) + amt, 2)
    save(data)

    # ── Image 4 style — Deal Completed ──
    send_sticker(message.chat.id, PACK_GREEN_TICK)
    bot.send_message(message.chat.id,
        f"✅ Deal Completed\n\n"
        f"🛡️ Trade ID: #{deal_id}\n"
        f"💵 Released Amount: {csym}{fmt(amt)}\n"
        f"👤 Buyer: @{deal['buyer']}\n"
        f"👤 Seller: @{deal['seller']}\n"
        f"🛡️ Escrowed By: @{deal['escrow']}"
    )

    # Vouch channel
    vouch = (
        f"✅ Deal Completed\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🛡️ Trade ID: #{deal_id}\n"
        f"💵 Released Amount: {csym}{fmt(amt)}\n"
        f"👤 Buyer: @{deal['buyer']}\n"
        f"👤 Seller: @{deal['seller']}\n"
        f"🛡️ Escrowed By: @{deal['escrow']}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 {date_str}"
    )
    try:
        bot.send_message(VOUCH_CHANNEL, vouch)
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Vouch channel error: {e}")

# ─────────────────────────────────────────────────
#  /cancel
# ─────────────────────────────────────────────────
@bot.message_handler(commands=["cancel"])
def cmd_cancel(message):
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ Only group admins can cancel.")
        return

    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /cancel CRPTIN00001")
        return

    deal_id = _parse_deal_id(parts[1])

    if deal_id in pending:
        del pending[deal_id]
        bot.send_message(message.chat.id, f"❌ Deal #{deal_id} cancelled.")
        return

    data = load()
    if deal_id not in data["deals"]:
        bot.reply_to(message, f"❌ Deal #{deal_id} not found.")
        return

    deal = data["deals"][deal_id]
    if deal.get("completed"):
        bot.reply_to(message, "❌ Completed deal cannot be cancelled.")
        return

    deal["status"]       = "CANCELLED"
    deal["cancelled_at"] = datetime.datetime.now().isoformat()
    for uid_key, u in data["users"].items():
        if u.get("username","").lower() in [deal["buyer"].lower(), deal["seller"].lower()]:
            u["ongoing_deals"] = max(0, u.get("ongoing_deals",1) - 1)
    save(data)

    bot.send_message(message.chat.id,
        f"❌ Deal #{deal_id} cancelled.\n"
        f"👤 Buyer: @{deal['buyer']}\n"
        f"👤 Seller: @{deal['seller']}\n"
        f"🔐 Escrow: @{deal['escrow']}"
    )

# ─────────────────────────────────────────────────
#  /mydeal
# ─────────────────────────────────────────────────
@bot.message_handler(commands=["mydeal"])
def cmd_mydeal(message):
    caller_u = (message.from_user.username or "").lower()
    data     = load()
    active   = []

    for did, d in data["deals"].items():
        if d.get("completed") or d.get("status") == "CANCELLED":
            continue
        involved = [d.get("buyer","").lower(), d.get("seller","").lower(), d.get("escrow","").lower()]
        if caller_u and caller_u in involved:
            active.append((did, d))

    if not active:
        bot.reply_to(message, "✅ You have no active deals right now.")
        return

    text = f"📋 Your Active Deals ({len(active)})\n" + "─"*24 + "\n"
    for did, d in active:
        ctype = d.get("currency_type","INR")
        csym  = "$" if ctype == "CRYPTO" else "₹"
        status = d.get("status","").replace("_"," ").title()
        text += (
            f"\n🆔 #{did}\n"
            f"💰 {csym}{fmt(d['amount'])} | {status}\n"
            f"👤 Buyer: @{d.get('buyer','?')}\n"
            f"👤 Seller: @{d.get('seller','?')}\n"
            f"🔐 Escrow: @{d.get('escrow','?')}\n"
        )
    bot.reply_to(message, text)

# ─────────────────────────────────────────────────
#  /kickall
# ─────────────────────────────────────────────────
@bot.message_handler(commands=["kickall"])
def cmd_kickall(message):
    if message.chat.type not in ["group","supergroup"]:
        bot.reply_to(message, "❌ Only works in groups.")
        return
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ Only admins can use /kickall.")
        return

    data = load()
    protected = set()
    for did, deal in data["deals"].items():
        if not deal.get("completed") and deal.get("status") != "CANCELLED":
            protected.add(deal["buyer"].lower())
            protected.add(deal["seller"].lower())
            protected.add(deal.get("escrow","").lower())

    try:
        admins    = bot.get_chat_administrators(message.chat.id)
        admin_ids = {a.user.id for a in admins}
    except:
        admin_ids = {message.from_user.id}

    kicked, protected_list = [], []

    for uid_key, u in data["users"].items():
        uid_int = u.get("user_id", 0)
        uname   = u.get("username","")
        if not isinstance(uid_int, int) or uid_int == 0:
            continue
        if uid_int in admin_ids:
            continue
        if not is_in_group(message.chat.id, uid_int):
            continue
        if uname.lower() in protected:
            protected_list.append(f"@{uname}")
            continue
        try:
            bot.ban_chat_member(message.chat.id, uid_int)
            bot.unban_chat_member(message.chat.id, uid_int)
            kicked.append(f"@{uname}")
        except:
            pass

    try:
        total = bot.get_chat(message.chat.id).members_count or 0
    except:
        total = 0

    result = (
        f"✅ Kick Done!\n\n"
        f"👥 Total Members: {total}\n"
        f"🦵 Kicked: {len(kicked)}\n"
        f"🔒 Protected (Active Deals): {len(protected_list)}\n"
    )
    if kicked:
        result += "\n🦵 Kicked:\n" + "\n".join(f"• {k}" for k in kicked)
    if protected_list:
        result += "\n\n🔒 Protected:\n" + "\n".join(f"• {p}" for p in protected_list)
    result += "\n\nℹ️ Kicked users can rejoin via invite link."
    bot.send_message(message.chat.id, result)

# ─────────────────────────────────────────────────
#  /escrowstats
# ─────────────────────────────────────────────────
@bot.message_handler(commands=["escrowstats"])
def cmd_escrowstats(message):
    data = load()
    now  = datetime.datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_name  = now.strftime("%B %Y")

    escrow_stats = {}
    total_deals = total_inr = total_crypto = 0
    crypto_sym_group = "USDT"

    for did, deal in data["deals"].items():
        if not deal.get("completed"):
            continue
        try:
            dt = datetime.datetime.fromisoformat(deal.get("completed_at",""))
            if dt < month_start:
                continue
        except:
            continue

        escrow = deal.get("escrow","")
        if not escrow:
            continue

        ekey   = escrow.lower()
        amount = deal.get("amount", 0)
        ctype  = deal.get("currency_type", "INR")
        csym   = deal.get("currency_sym", "₹")

        if ekey not in escrow_stats:
            escrow_stats[ekey] = {
                "username": escrow, "deals": 0,
                "inr_volume": 0.0, "inr_deals": 0,
                "crypto_volume": 0.0, "crypto_deals": 0, "crypto_sym": "USDT"
            }

        escrow_stats[ekey]["deals"] += 1
        if ctype == "INR":
            escrow_stats[ekey]["inr_volume"] = round(escrow_stats[ekey]["inr_volume"] + amount, 2)
            escrow_stats[ekey]["inr_deals"]  += 1
            total_inr = round(total_inr + amount, 2)
        else:
            escrow_stats[ekey]["crypto_volume"] = round(escrow_stats[ekey]["crypto_volume"] + amount, 2)
            escrow_stats[ekey]["crypto_deals"]  += 1
            escrow_stats[ekey]["crypto_sym"]    = csym
            crypto_sym_group = csym
            total_crypto = round(total_crypto + amount, 2)
        total_deals += 1

    if not escrow_stats:
        bot.reply_to(message, f"📊 Escrow Leaderboard — {month_name}\n\nNo completed deals this month.")
        return

    ranked = sorted(escrow_stats.values(), key=lambda x: x["deals"], reverse=True)
    medals = ["🥇","🥈","🥉"]
    text   = f"🏆 Escrow Leaderboard — {month_name}\n━━━━━━━━━━━━━━━━━━━━\n\n"

    for i, e in enumerate(ranked, 1):
        medal = medals[i-1] if i <= 3 else f"#{i}"
        text += f"{medal} @{e['username']} — {e['deals']} Deal{'s' if e['deals']!=1 else ''}\n"
        if e["inr_deals"] > 0:
            text += f"   💵 INR: ₹{fmt(e['inr_volume'])} ({e['inr_deals']} deals)\n"
        if e["crypto_deals"] > 0:
            text += f"   💲 Crypto: ${fmt(e['crypto_volume'])} ({e['crypto_deals']} deals)\n"
        text += "\n"

    text += f"━━━━━━━━━━━━━━━━━━━━\n📊 Group Total — {month_name}\n\n"
    text += f"📦 Total Deals: {total_deals}\n"
    if total_inr > 0:
        text += f"💵 Total INR: ₹{fmt(total_inr)}\n"
    if total_crypto > 0:
        text += f"💲 Total Crypto: ${fmt(total_crypto)}\n"
    text += "━━━━━━━━━━━━━━━━━━━━"
    bot.reply_to(message, text)

# ─────────────────────────────────────────────────
#  /start /help
# ─────────────────────────────────────────────────
@bot.message_handler(commands=["start","help"])
def cmd_help(message):
    bot.send_message(message.chat.id,
        "🤖 aNamaka Escrow Bot\n"
        "─────────────────────────\n"
        "/form or /dd       → Get blank deal form\n"
        "/deal              → Reply on form to create deal (Admin)\n"
        "/received [ID]     → Mark payment received (Admin)\n"
        "/complete [ID]     → Complete deal + vouch (Admin)\n"
        "/cancel [ID]       → Cancel a deal (Admin)\n"
        "/mydeal            → Your active deals\n"
        "/kickall           → Kick inactive users (Admin)\n"
        "/escrowstats       → Monthly leaderboard\n"
        "─────────────────────────\n"
        f"💸 INR Fee: {INR_FEE_PCT}%  |  Crypto Fee: ${CRYPTO_FEE} flat"
    )

# ─────────────────────────────────────────────────
#  USER TRACKER
# ─────────────────────────────────────────────────
@bot.message_handler(func=lambda m: True, content_types=["text"])
def track(message):
    if not message.from_user or not message.from_user.username:
        return
    data    = load()
    uid_key = str(message.from_user.id)
    uname   = message.from_user.username
    if uid_key not in data["users"]:
        ensure_user(data, uname, message.from_user.id)
        save(data)
    elif data["users"].get(uid_key,{}).get("username") != uname:
        if uid_key in data["users"]:
            data["users"][uid_key]["username"] = uname
            save(data)

# ─────────────────────────────────────────────────
#  RUN
# ─────────────────────────────────────────────────
print(f"🤖 aNamaka Escrow Bot LIVE | INR: {INR_FEE_PCT}% | Crypto: ${CRYPTO_FEE} flat")
bot.infinity_polling(timeout=60, long_polling_timeout=60)
