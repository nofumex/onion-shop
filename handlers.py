import os
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import (
    Message, FSInputFile, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS, CHANNEL_ID, CHANNEL_USERNAME
from database import (
    load_users,
    save_users,
    get_balance,
    update_balance,
    get_user_id_by_username,
    add_user,
    add_sale,
    get_unique_buyers_count,
    get_sales_sum_day,
    get_sales_sum_month,
    get_total_orders_count,
    get_avg_ticket_today,
    get_top_buyers,
    get_username_by_user_id,
    load_sales,
)
from payments import create_crypto_invoice

# FSM для админки
class AdminStates(StatesGroup):
    wait_user_id = State()
    wait_amount = State()
    wait_user_line = State()

# Product categories (Accounts)
categories = {
    "FB Marketplace": {"folder": "fb_marketplace", "price": 5},
    "eBay": {"folder": "ebay", "price": 20},
    "Kleinanzeigen": {"folder": "kleinanzeigen", "price": 20},
    "Etsy": {"folder": "etsy", "price": 10},
    "Vinted": {"folder": "vinted", "price": 20},
    "Wallapop": {"folder": "wallapop", "price": 20},
}

# Proxy categories (SOCKS5), fixed price $3
proxies = {
    "SOCKS5 Germany": {"folder": "proxy_de", "price": 3, "flag": "🇩🇪"},
    "SOCKS5 Canada": {"folder": "proxy_ca", "price": 3, "flag": "🇨🇦"},
    "SOCKS5 Hungary": {"folder": "proxy_hu", "price": 3, "flag": "🇭🇺"},
    "SOCKS5 USA": {"folder": "proxy_us", "price": 3, "flag": "🇺🇸"},
    "SOCKS5 Singapore": {"folder": "proxy_sg", "price": 3, "flag": "🇸🇬"},
}

# Подготовка папок
os.makedirs("data", exist_ok=True)
for cat in categories.values():
    os.makedirs(f"data/{cat['folder']}", exist_ok=True)
for p in proxies.values():
    os.makedirs(f"data/{p['folder']}", exist_ok=True)

def get_item_info_by_folder(folder: str):
    for name, info in categories.items():
        if info["folder"] == folder:
            return ("account", name, info)
    for name, info in proxies.items():
        if info["folder"] == folder:
            return ("proxy", name, info)
    return (None, None, None)

async def is_user_subscribed(bot: Bot, user_id: int) -> bool:
    """Check whether the user is subscribed to the channel"""
    chat_id = CHANNEL_ID
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        status = member.status
        print(f"User {user_id} status in {chat_id}: {status}")

        # Ensure the user hasn't left or been kicked
        if status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]:
            return False

        # Subscribed: MEMBER, ADMINISTRATOR, CREATOR/OWNER, RESTRICTED
        if status in [
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR,
            ChatMemberStatus.RESTRICTED
        ]:
            return True

        return False
    except Exception as e:
        print(f"Error checking subscription for user {user_id}: {repr(e)}")
        return False

async def send_main_menu(bot: Bot, user_id: int):
    """Send main menu to the user"""
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🛍️ Products"), KeyboardButton(text="📦 Stock")],
        [KeyboardButton(text="👤 Profile")]
    ], resize_keyboard=True)

    await bot.send_photo(
        user_id,
        photo=FSInputFile("shopheader16.jpg"),
        caption=(
            "<b>👋 Welcome to ONION Shop!</b>\n\n"
            "Use the buttons below to navigate ⬇️"
        ),
        reply_markup=kb
    )

def register_handlers(dp: Dispatcher, bot: Bot):
    """Register all handlers"""
    
    # /start with subscription check
    @dp.message(CommandStart())
    async def cmd_start(message: Message):
        user_id = message.from_user.id
        username = message.from_user.username or ""
        add_user(user_id, username)

        # Always show menu to admin without subscription check
        if user_id in ADMIN_IDS:
            await send_main_menu(bot, user_id)
            return

        subscribed = await is_user_subscribed(bot, user_id)
        if not subscribed:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Subscribe", url=f"https://t.me/{CHANNEL_USERNAME}")],
                [InlineKeyboardButton(text="Check subscription", callback_data="check_sub")]
            ])
            await message.answer(
                "❗ To use this bot, please subscribe to @{}\n\n"
                "After subscribing, tap \"Check subscription\".".format(CHANNEL_USERNAME),
                reply_markup=kb
            )
            return

        # Пользователь подписан, показываем стартовое меню
        await send_main_menu(bot, user_id)

    # Subscription check button
    @dp.callback_query(F.data == "check_sub")
    async def check_subscription(callback: types.CallbackQuery):
        user_id = callback.from_user.id
        chat_id = CHANNEL_ID

        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            status = member.status
            print(f"User {user_id} status in {chat_id}: {status}")

            if status not in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]:
                await callback.message.edit_text(
                    "✅ You are subscribed! You can now use the bot.",
                    reply_markup=None
                )
                await send_main_menu(bot, user_id)
            else:
                await callback.answer("❌ You are not subscribed. Please subscribe.", show_alert=True)
        except Exception as e:
            print(f"Subscription check error: {repr(e)}")
            await callback.answer("⚠️ Failed to check subscription. Try again later.", show_alert=True)

    # Admin panel
    @dp.message(Command("admin"))
    async def admin_panel(message: Message, state: FSMContext):
        if message.from_user.id not in ADMIN_IDS:
            # Разрешаем также администраторам канала
            try:
                member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=message.from_user.id)
                if member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
                    return
            except Exception:
                return
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Statistics", callback_data="admin_stats")],
            [InlineKeyboardButton(text="💰 Adjust balance", callback_data="admin_adjust_balance")],
            [InlineKeyboardButton(text="🏆 Top buyers", callback_data="admin_top_buyers")],
        ])
        await message.answer("🔐 Admin panel:", reply_markup=kb)

    @dp.message(AdminStates.wait_user_id)
    async def process_user_id(message: Message, state: FSMContext):
        text = message.text.strip()
        if text.startswith("@"):
            user_id = get_user_id_by_username(text)
            if user_id is None:
                await message.answer("❌ Username not found.")
                return
        elif text.isdigit():
            user_id = int(text)
        else:
            await message.answer("❌ Enter a valid @username or numeric user ID.")
            return

        await state.update_data(user_id=user_id)
        await message.answer("💰 Enter amount to adjust:")
        await state.set_state(AdminStates.wait_amount)

    @dp.message(AdminStates.wait_amount)
    async def process_amount(message: Message, state: FSMContext):
        text = message.text.strip()

        # Validate number (can be signed)
        try:
            amount = int(text)
        except ValueError:
            await message.answer("❌ Enter a valid number (e.g., 100 or -50).")
            return

        data = await state.get_data()
        user_id = data["user_id"]

        # Update balance
        update_balance(user_id, amount)

        # Operation type
        if amount > 0:
            operation_text = f"credited {amount}$"
            user_text = f"💰 Your balance was credited by {amount}$ by admin."
        elif amount < 0:
            operation_text = f"debited {-amount}$"
            user_text = f"⚠️ {-amount}$ was debited from your balance by admin."
        else:
            await message.answer("❌ Amount cannot be zero.")
            return

        await message.answer(f"✅ User with ID {user_id} {operation_text}.")

        # Отправляем уведомление пользователю
        try:
            await bot.send_message(user_id, user_text)
        except Exception as e:
            print(f"Error sending message to user {user_id}: {e}")

        await state.clear()

    # Новый упрощенный ввод: "@username 100" или "@username -100"
    @dp.callback_query(F.data == "admin_adjust_balance")
    async def admin_adjust_balance_start(callback: types.CallbackQuery, state: FSMContext):
        await callback.message.answer("Enter on one line: @username amount (e.g., @user 100 or @user -50)")
        await state.set_state(AdminStates.wait_user_line)
        await callback.answer()

    @dp.message(AdminStates.wait_user_line)
    async def admin_adjust_balance_process(message: Message, state: FSMContext):
        text = (message.text or "").strip()
        parts = text.split()
        if len(parts) != 2 or not parts[0].startswith("@"):
            await message.answer("Format: @username amount. Example: @user 100")
            return
        username, amount_str = parts
        try:
            amount = int(amount_str)
        except ValueError:
            await message.answer("Amount must be a number. Example: @user 100")
            return
        user_id = get_user_id_by_username(username)
        if user_id is None:
            await message.answer("❌ This @username not found in DB. The user must write to the bot once.")
            return
        update_balance(user_id, amount)
        # Сообщение пользователю
        try:
            if amount > 0:
                await message.bot.send_message(user_id, f"💰 Your balance was credited by {amount}$ by admin.")
            else:
                await message.bot.send_message(user_id, f"⚠️ {-amount}$ was debited from your balance by admin.")
        except Exception:
            pass
        sign = "+" if amount > 0 else ""
        await message.answer(f"✅ Balance of {username} changed by {sign}{amount}$")
        await state.clear()

    @dp.callback_query(F.data == "admin_stats")
    async def admin_stats(callback: types.CallbackQuery):
        users = load_users()
        total_users = len(users)
        unique_buyers = get_unique_buyers_count()
        sales_day = get_sales_sum_day()
        sales_month = get_sales_sum_month()
        orders_total = get_total_orders_count()
        avg_ticket = get_avg_ticket_today()
        sales_all = sum(int(s.get("total_price", 0)) for s in load_sales())
        conversion = (unique_buyers / total_users * 100) if total_users else 0
        text = (
            "📊 Statistics:\n"
            f"👥 Total users: {total_users}\n"
            f"🛒 Unique buyers: {unique_buyers}\n"
            f"📈 Conversion: {conversion:.1f}%\n"
            f"💵 Sales today: {sales_day}$\n"
            f"💵 Sales this month: {sales_month}$\n"
            f"💳 Avg ticket today: {avg_ticket:.2f}$\n"
            f"🧾 Total orders: {orders_total}\n"
            f"💰 Revenue total: {sales_all}$\n"
        )
        await callback.message.answer(text)
        await callback.answer()

    @dp.callback_query(F.data == "admin_top_buyers")
    async def admin_top_buyers(callback: types.CallbackQuery):
        top = get_top_buyers(limit=5)
        if not top:
            await callback.message.answer("No purchases yet.")
            await callback.answer()
            return
        lines = ["🏆 Top buyers:"]
        for idx, (uid, spent) in enumerate(top, start=1):
            uname = get_username_by_user_id(uid)
            display = f"@{uname}" if uname else str(uid)
            lines.append(f"{idx}. {display} — {spent}$")
        await callback.message.answer("\n".join(lines))
        await callback.answer()

    # Категории товаров
    @dp.message(F.text == "🛍️ Products")
    async def show_categories(message: Message):
        kb = InlineKeyboardBuilder()
        kb.button(text="🧾 Accounts", callback_data="cat_accounts")
        kb.button(text="🧰 Proxies", callback_data="cat_proxies")
        kb.button(text="◀ Back", callback_data="back_main")
        kb.adjust(2, 1)
        await message.answer("Choose a section:", reply_markup=kb.as_markup())

    @dp.callback_query(F.data == "back_main")
    async def back_to_main(callback: types.CallbackQuery):
        await send_main_menu(bot, callback.from_user.id)
        await callback.answer()

    @dp.callback_query(F.data == "cat_root")
    async def show_root(callback: types.CallbackQuery):
        kb = InlineKeyboardBuilder()
        kb.button(text="🧾 Accounts", callback_data="cat_accounts")
        kb.button(text="🧰 Proxies", callback_data="cat_proxies")
        kb.button(text="◀ Back", callback_data="back_main")
        kb.adjust(2, 1)
        await callback.message.answer("Choose a section:", reply_markup=kb.as_markup())
        await callback.answer()

    @dp.callback_query(F.data == "cat_accounts")
    async def show_accounts_categories(callback: types.CallbackQuery):
        kb = InlineKeyboardBuilder()
        for name in categories:
            kb.button(text=name, callback_data=name)
        kb.button(text="◀ Back", callback_data="cat_root")
        kb.adjust(2, 1)
        await callback.message.answer("Choose an account category:", reply_markup=kb.as_markup())
        await callback.answer()

    @dp.callback_query(F.data.in_(categories.keys()))
    async def show_items(callback: types.CallbackQuery):
        cat_name = callback.data
        info = categories[cat_name]
        folder_path = f"data/{info['folder']}"
        files = os.listdir(folder_path)
        kb = InlineKeyboardBuilder()
        if files:
            kb.button(text=f"Account | {info['price']}$", callback_data=f"buy:{info['folder']}")
        kb.button(text="◀ Back", callback_data="cat_accounts")
        kb.adjust(1)
        if not files:
            await callback.message.answer(f"❌ No items in <b>{cat_name}</b> category.", reply_markup=kb.as_markup())
        else:
            await callback.message.answer(
                f"📃 Category: <b>{cat_name}</b>",
                reply_markup=kb.as_markup()
            )
        await callback.answer()

    @dp.callback_query(F.data == "cat_proxies")
    async def show_proxies(callback: types.CallbackQuery):
        kb = InlineKeyboardBuilder()
        for name, p in proxies.items():
            kb.button(text=f"{name} {p['flag']}", callback_data=name)
        kb.button(text="◀ Back", callback_data="cat_root")
        kb.adjust(1)
        await callback.message.answer("Choose a SOCKS5 option:", reply_markup=kb.as_markup())
        await callback.answer()

    @dp.callback_query(F.data.in_(proxies.keys()))
    async def show_proxy_item(callback: types.CallbackQuery):
        name = callback.data
        info = proxies[name]
        folder_path = f"data/{info['folder']}"
        files = os.listdir(folder_path)
        kb = InlineKeyboardBuilder()
        if files:
            kb.button(text=f"SOCKS5 | {name.split(' ', 1)[1]} | {info['price']}$", callback_data=f"buy:{info['folder']}")
        kb.button(text="◀ Back", callback_data="cat_proxies")
        kb.adjust(1)
        if not files:
            await callback.message.answer(f"❌ Option <b>{name}</b> is out of stock.", reply_markup=kb.as_markup())
        else:
            await callback.message.answer(f"📡 Proxy: <b>{name}</b>", reply_markup=kb.as_markup())
        await callback.answer()

    @dp.callback_query(F.data.startswith("buy:"))
    async def choose_quantity(callback: types.CallbackQuery):
        folder = callback.data.split(":")[1]
        _type, _name, info = get_item_info_by_folder(folder)
        price = info["price"] if info else None

        kb = InlineKeyboardBuilder()
        for qty in range(1, 6):  # from 1 to 5
            kb.button(text=str(qty), callback_data=f"buy_qty:{folder}:{qty}")
        # Back to item view depending on type
        if _type == "account":
            kb.button(text="◀ Back", callback_data="cat_accounts")
        elif _type == "proxy":
            kb.button(text="◀ Back", callback_data="cat_proxies")

        kb.adjust(5, 1)

        title = "accounts" if _type == "account" else "proxies"
        await callback.message.answer(
            f"Choose quantity of {title} at {price}$ each:",
            reply_markup=kb.as_markup()
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("buy_qty:"))
    async def process_purchase(callback: types.CallbackQuery):
        _, folder, qty_str = callback.data.split(":")
        quantity = int(qty_str)
        user_id = str(callback.from_user.id)
        users = load_users()
        _type, _name, info = get_item_info_by_folder(folder)
        price = info["price"] if info else None
        total_price = price * quantity

        if not os.path.exists(f"data/{folder}"):
            await callback.message.answer("❌ Category not found.")
            return

        files = os.listdir(f"data/{folder}")
        if len(files) < quantity:
            await callback.message.answer(f"❌ Not enough items in stock. Only {len(files)} available.")
            return

        if users.get(user_id, {}).get("balance", 0) < total_price:
            await callback.message.answer(
                f"❌ Insufficient funds. Your balance: {users.get(user_id, {}).get('balance', 0)}$, required {total_price}$.")
            return

        try:
            update_balance(callback.from_user.id, -total_price)
            for i in range(quantity):
                filename = files[i]
                path = f"data/{folder}/{filename}"
                await callback.message.answer_document(document=FSInputFile(path),
                                                       caption=f"Your item 🍪 ({i + 1}/{quantity})")
                os.remove(path)
            # Логируем продажу
            add_sale(callback.from_user.id, total_price, quantity, folder, _type or "unknown")
        except Exception as e:
            await callback.message.answer(f"❌ Error while delivering item: {str(e)}")
            return

        noun = "accounts" if _type == "account" else "proxies"
        await callback.answer(f"✅ You purchased {quantity} {noun} for {total_price}$.")

    # Проверка наличия
    @dp.message(F.text == "📦 Stock")
    async def check_stock(message: Message):
        text = "➖➖➖ Accounts ➖➖➖\n"
        for name, info in categories.items():
            folder = f"data/{info['folder']}"
            count = len(os.listdir(folder))
            text += f"{name} | {info['price']}$ | {count} pcs\n"
        text += "\n➖➖➖🧰 SOCKS5 Proxies ➖➖➖\n"
        for name, info in proxies.items():
            folder = f"data/{info['folder']}"
            count = len(os.listdir(folder))
            country = name.split(' ', 1)[1]
            text += f"{country} | {info.get('flag','')} | {info['price']}$ | {count} pcs\n"
        await message.answer(text)

    # Профиль
    @dp.message(F.text == "👤 Profile")
    async def profile(message: Message):
        balance = get_balance(message.from_user.id)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Top up", callback_data="topup")],
            [InlineKeyboardButton(text="Rules", callback_data="rules")],
            [InlineKeyboardButton(text="Help", callback_data="help")]
        ])
        await message.answer(f"Name: {message.from_user.full_name}\n💰 Balance: {balance}$", reply_markup=kb)

    @dp.callback_query(F.data == "topup")
    async def topup_start(callback: types.CallbackQuery):
        await callback.message.answer("💸 Send the top-up amount:")
        await callback.answer()

    @dp.message(lambda m: m.text and m.text.isdigit())
    async def handle_amount(message: Message):
        amount = int(message.text)
        if amount <= 0:
            await message.answer("❌ Amount must be positive.")
            return
        url = create_crypto_invoice(message.from_user.id, amount)
        if url:
            btn = InlineKeyboardButton(text="💳 Proceed to payment", url=url)
            markup = InlineKeyboardMarkup(inline_keyboard=[[btn]])
            await message.answer(f"Amount: {amount}$\nClick the button below to pay via CryptoBot:", reply_markup=markup)
        else:
            await message.answer("❌ Failed to create invoice. Try again later.")

    @dp.callback_query(F.data == "rules")
    async def rules(callback: types.CallbackQuery):
        await callback.message.answer(
            "📜 Rules / Правила:\n\n"
            "EN:\n"
            "1) Do not use items from this shop for actions that violate the laws of your country.\n"
            "2) By purchasing, you automatically accept all rules and take full responsibility for your use.\n"
            "3) Replacement or refund to balance is possible only if support confirms the item is invalid. Evidence is required (screenshots/video). Any fraud attempt leads to denial and possible ban.\n"
            "4) No refunds for misuse, lack of skills, service/proxy blocks or limits, changes in service rules/policies, or if the item was partially used or shared with third parties.\n"
            "5) Check the item immediately after purchase — validity and operability are time‑limited.\n\n"
            "RU:\n"
            "1) Запрещено использовать товары из этого магазина для действий, противоречащих законам вашей страны.\n"
            "2) Покупая товар, вы автоматически соглашаетесь с правилами и берёте полную ответственность на себя.\n"
            "3) Замена или возврат на баланс возможны только при подтверждённой саппортом недействительности товара. Нужны доказательства (скриншоты/видео). Попытка обмана ведёт к отказу и блокировке.\n"
            "4) Возврат не делается из‑за неправильного использования, отсутствия навыков, блокировок/лимитов со стороны сервисов и прокси, изменений их правил/политик, а также если товар частично использован или передан третьим лицам.\n"
            "5) Проверяйте товар сразу после покупки — актуальность и работоспособность ограничены временем.\n"
        )
        await callback.answer()

    @dp.callback_query(F.data == "help")
    async def help_msg(callback: types.CallbackQuery):
        await callback.message.answer("🔧 Support: @OnionSupport1\n📬 For any questions — write to us.")
        await callback.answer()

    # Загрузка товаров админом
    @dp.message(F.document)
    async def handle_cookie_upload(message: Message):
        # Allow upload for global ADMIN_IDS or channel admins/owner
        is_admin = (message.from_user.id in ADMIN_IDS)
        if not is_admin:
            try:
                member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=message.from_user.id)
                if member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
                    is_admin = True
            except Exception:
                pass
        if not is_admin:
            return
        file = message.document
        filename = (file.file_name or "").lower()

        if not filename.endswith(".txt"):
            await message.answer("❌ Only .txt files are allowed.")
            return

        # Сначала проверяем аккаунты
        for name, cat in categories.items():
            if cat['folder'] in filename:
                path = f"data/{cat['folder']}/{filename}"
                await bot.download(file=file.file_id, destination=path)
                await message.answer(f"✅ File added to category: {name}")
                return

        # Затем проверяем прокси
        for name, p in proxies.items():
            if p['folder'] in filename:
                path = f"data/{p['folder']}/{filename}"
                await bot.download(file=file.file_id, destination=path)
                await message.answer(f"✅ File added to category: {name}")
                return

        await message.answer("❌ Could not determine category from filename.")
