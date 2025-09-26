import os
import json
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone
from collections import defaultdict
from config import ADMIN_IDS

# Работа с пользователями
USER_FILE = "users.json"
SALES_FILE = "sales.json"

def load_users() -> Dict[str, Any]:
    """Загружает данные пользователей из файла"""
    try:
        with open(USER_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        with open(USER_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)
        return {}

def save_users(users: Dict[str, Any]) -> None:
    """Сохраняет данные пользователей в файл"""
    with open(USER_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=4, ensure_ascii=False)

def get_balance(user_id: int) -> int:
    """Получает баланс пользователя"""
    users = load_users()
    return users.get(str(user_id), {}).get("balance", 0)

def update_balance(user_id: int, amount: int) -> None:
    """Обновляет баланс пользователя"""
    users = load_users()
    user = users.setdefault(str(user_id), {"balance": 0, "username": ""})
    user["balance"] += amount
    save_users(users)

def get_user_id_by_username(username: str) -> Optional[int]:
    """Находит user_id по username"""
    users = load_users()
    username = username.lstrip("@").lower()
    for uid, data in users.items():
        if data.get("username", "").lower() == username:
            return int(uid)
    return None

def add_user(user_id: int, username: str = "") -> None:
    """Добавляет нового пользователя или обновляет username"""
    users = load_users()
    user_id_str = str(user_id)
    if user_id_str not in users:
        users[user_id_str] = {"balance": 0, "username": username}
    else:
        if users[user_id_str].get("username", "") != username:
            users[user_id_str]["username"] = username
    save_users(users)

# -------------------- Продажи и статистика --------------------

def _ensure_sales_file() -> None:
    if not os.path.exists(SALES_FILE):
        with open(SALES_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)

def load_sales() -> List[Dict[str, Any]]:
    """Загружает список продаж"""
    try:
        with open(SALES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        _ensure_sales_file()
        return []

def save_sales(sales: List[Dict[str, Any]]) -> None:
    with open(SALES_FILE, "w", encoding="utf-8") as f:
        json.dump(sales, f, indent=4, ensure_ascii=False)

def add_sale(user_id: int, total_price: int, quantity: int, folder: str, item_type: str) -> None:
    """Добавляет запись о продаже"""
    # Не учитываем покупки администраторов в статистике
    try:
        if int(user_id) in [int(x) for x in ADMIN_IDS]:
            return
    except Exception:
        pass
    sales = load_sales()
    sales.append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "user_id": int(user_id),
        "total_price": int(total_price),
        "quantity": int(quantity),
        "folder": folder,
        "item_type": item_type,
    })
    save_sales(sales)

def _is_same_day(ts_iso: str, ref: datetime) -> bool:
    try:
        ts = datetime.fromisoformat(ts_iso)
    except Exception:
        return False
    return ts.date() == ref.date()

def _is_same_month(ts_iso: str, ref: datetime) -> bool:
    try:
        ts = datetime.fromisoformat(ts_iso)
    except Exception:
        return False
    return ts.year == ref.year and ts.month == ref.month

def get_unique_buyers_count() -> int:
    sales = load_sales()
    admin_set = {int(x) for x in ADMIN_IDS}
    return len({str(s.get("user_id")) for s in sales if int(s.get("user_id", 0)) not in admin_set})

def get_sales_sum_day() -> int:
    sales = load_sales()
    now = datetime.now(timezone.utc)
    admin_set = {int(x) for x in ADMIN_IDS}
    return sum(int(s.get("total_price", 0)) for s in sales if int(s.get("user_id", 0)) not in admin_set and _is_same_day(s.get("ts", ""), now))

def get_sales_sum_month() -> int:
    sales = load_sales()
    now = datetime.now(timezone.utc)
    admin_set = {int(x) for x in ADMIN_IDS}
    return sum(int(s.get("total_price", 0)) for s in sales if int(s.get("user_id", 0)) not in admin_set and _is_same_month(s.get("ts", ""), now))

def get_total_orders_count() -> int:
    admin_set = {int(x) for x in ADMIN_IDS}
    return len([s for s in load_sales() if int(s.get("user_id", 0)) not in admin_set])

def get_avg_ticket_today() -> float:
    sales = load_sales()
    now = datetime.now(timezone.utc)
    admin_set = {int(x) for x in ADMIN_IDS}
    today_sales = [int(s.get("total_price", 0)) for s in sales if int(s.get("user_id", 0)) not in admin_set and _is_same_day(s.get("ts", ""), now)]
    if not today_sales:
        return 0.0
    return sum(today_sales) / len(today_sales)

def get_top_buyers(limit: int = 5) -> List[Tuple[int, int]]:
    """Возвращает список (user_id, total_spent) отсортированный по сумме, ограничение limit"""
    sales = load_sales()
    spent_by_user: Dict[int, int] = defaultdict(int)
    admin_set = {int(x) for x in ADMIN_IDS}
    for s in sales:
        if int(s.get("user_id", 0)) in admin_set:
            continue
        spent_by_user[int(s.get("user_id", 0))] += int(s.get("total_price", 0))
    items = sorted(spent_by_user.items(), key=lambda kv: kv[1], reverse=True)
    return items[:limit]

def get_username_by_user_id(user_id: int) -> str:
    users = load_users()
    return users.get(str(user_id), {}).get("username", "")
