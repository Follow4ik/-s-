# -*- coding: utf-8 -*-
import asyncio
import logging
import os
import re
from datetime import datetime, timezone, timedelta

import aiosqlite
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, ContentType
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramForbiddenError
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

# Для хостинга: задай переменные окружения BOT_TOKEN, GROUP_ID, PANEL_PASSWORD
# Локально работают значения по умолчанию
BOT_TOKEN = os.getenv("BOT_TOKEN", "8828150896:AAFYjY_z2bfxiep6FCwENTQGQfJwVOsWEpU")
GROUP_ID = int(os.getenv("GROUP_ID", "-1004486903203"))
PANEL_PASSWORD = os.getenv("PANEL_PASSWORD", "imprizrakatmetg13sudskyalediomikezetazeronobstovjdnd")
SUPPORT_BOT = os.getenv("SUPPORT_BOT", "@tehpoddershka67_bot")

WELCOME_TEXT = """Здравствуй, с тобой на связи бот «небо отчуждение»

Правила:
1. Не просить у админов юзы
2. Не оскорблять админов
3. Не кидать 18+
4. Не затрагивать политику
5. Не спамить
6. Тег писать не обязательно
7. Если вы неправильно написали имя админа, продублируйте снова с правильным именем

Также хочу напомнить, что у нас есть:
• ТГК — @sky_of_alienation
• Бот для анкет — @sky_of_alienation_ankety_bot
• Техническая поддержка — @tehpoddershka67_bot

Прошу выбрать, какая категория тебе нужна:"""

DB_PATH = "bot_data.db"
KYIV = timezone(timedelta(hours=3))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()


class PanelStates(StatesGroup):
    waiting_password = State()
    waiting_broadcast_text = State()
    waiting_broadcast_user = State()
    waiting_broadcast_date = State()
    waiting_unmute_id = State()
    waiting_delete_user = State()
    waiting_edit_stats = State()
    waiting_add_admin = State()
    waiting_del_admin = State()
    waiting_tester = State()
    waiting_hi_tag = State()
    waiting_hi_text = State()
    waiting_note_tag = State()
    waiting_note_text = State()
    waiting_user_note = State()



# ==================== DB ====================

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                topic_id INTEGER,
                mode TEXT DEFAULT 'none',
                banned INTEGER DEFAULT 0,
                blocked_bot INTEGER DEFAULT 0,
                muted_until TEXT,
                warns INTEGER DEFAULT 0,
                username TEXT,
                full_name TEXT,
                msg_from_user INTEGER DEFAULT 0,
                msg_from_group INTEGER DEFAULT 0,
                last_msg_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        for col in [
            "ALTER TABLE users ADD COLUMN blocked_bot INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN muted_until TEXT",
            "ALTER TABLE users ADD COLUMN warns INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN msg_from_user INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN msg_from_group INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN last_msg_at TEXT",
            "ALTER TABLE users ADD COLUMN admin_tag TEXT",
        ]:
            try:
                await db.execute(col)
            except Exception:
                pass
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sticker_spam (
                user_id INTEGER PRIMARY KEY,
                sticker_id TEXT,
                count INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS text_spam (
                user_id INTEGER PRIMARY KEY,
                text_hash TEXT,
                count INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                tag TEXT UNIQUE NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS stats_override (
                key TEXT PRIMARY KEY,
                value INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS msg_map (
                user_id INTEGER,
                user_msg_id INTEGER,
                group_msg_id INTEGER,
                topic_id INTEGER,
                PRIMARY KEY (user_id, user_msg_id)
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_msg_map_group ON msg_map(group_msg_id)"
        )
        await db.execute("""
            CREATE TABLE IF NOT EXISTS testers (
                name TEXT PRIMARY KEY,
                on_rest INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_hi (
                tag_key TEXT PRIMARY KEY,
                tag TEXT,
                greeting TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_notes (
                tag_key TEXT PRIMARY KEY,
                tag TEXT,
                note TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_notes (
                user_id INTEGER PRIMARY KEY,
                note TEXT,
                updated_at TEXT
            )
        """)
        await db.commit()



async def save_msg_map(user_id: int, user_msg_id: int, group_msg_id: int, topic_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO msg_map
               (user_id, user_msg_id, group_msg_id, topic_id)
               VALUES (?, ?, ?, ?)""",
            (user_id, user_msg_id, group_msg_id, topic_id),
        )
        await db.commit()


async def get_map_by_user_msg(user_id: int, user_msg_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM msg_map WHERE user_id = ? AND user_msg_id = ?",
            (user_id, user_msg_id),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_map_by_group_msg(group_msg_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM msg_map WHERE group_msg_id = ?",
            (group_msg_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def create_user(user_id: int, topic_id: int, username=None, full_name=None):
    """Один user_id = одна запись. Старого пользователя не затираем."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO users
               (user_id, topic_id, mode, banned, blocked_bot, warns, username, full_name,
                msg_from_user, msg_from_group, created_at)
               VALUES (?, ?, 'none', 0, 0, 0, ?, ?, 0, 0, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 topic_id = excluded.topic_id,
                 username = COALESCE(excluded.username, users.username),
                 full_name = COALESCE(excluded.full_name, users.full_name)
            """,
            (user_id, topic_id, username, full_name,
             datetime.now(KYIV).strftime("%Y-%m-%d %H:%M:%S")),
        )
        await db.commit()


async def update_topic_id(user_id: int, topic_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET topic_id = ? WHERE user_id = ?",
            (topic_id, user_id),
        )
        await db.commit()


async def topic_alive(topic_id: int) -> bool:
    if not topic_id:
        return False
    try:
        await bot.send_chat_action(
            chat_id=GROUP_ID,
            action="typing",
            message_thread_id=int(topic_id),
        )
        return True
    except Exception as e:
        err = str(e).lower()
        if "thread" in err or "topic" in err or "not found" in err:
            return False
        # другие ошибки сети не считаем что темы нет
        return True


async def ensure_topic_for_user(message: Message, user: dict | None) -> int:
    """Всегда одна тема на один Telegram ID."""
    user_id = message.from_user.id
    if user and user.get("topic_id"):
        tid = int(user["topic_id"])
        if await topic_alive(tid):
            await create_user(
                user_id, tid,
                message.from_user.username, message.from_user.full_name,
            )
            return tid
    topic_id = await create_topic(message)
    if user:
        await update_topic_id(user_id, topic_id)
        await create_user(
            user_id, topic_id,
            message.from_user.username, message.from_user.full_name,
        )
    else:
        await create_user(
            user_id, topic_id,
            message.from_user.username, message.from_user.full_name,
        )
    return topic_id


async def update_mode(user_id: int, mode: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET mode = ?, blocked_bot = 0 WHERE user_id = ?",
            (mode, user_id),
        )
        await db.commit()


async def set_banned(user_id: int, banned: bool = True):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET banned = ? WHERE user_id = ?",
            (1 if banned else 0, user_id),
        )
        await db.commit()


async def set_blocked_bot(user_id: int, blocked: bool = True):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET blocked_bot = ? WHERE user_id = ?",
            (1 if blocked else 0, user_id),
        )
        await db.commit()


async def mark_active(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET blocked_bot = 0 WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()


async def set_muted(user_id: int, until_iso):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET muted_until = ? WHERE user_id = ?",
            (until_iso, user_id),
        )
        await db.commit()


async def is_muted(user_id: int) -> bool:
    user = await get_user(user_id)
    if not user or not user.get("muted_until"):
        return False
    try:
        until = datetime.fromisoformat(user["muted_until"])
        if until.tzinfo is None:
            until = until.replace(tzinfo=KYIV)
        return datetime.now(KYIV) < until
    except Exception:
        return False


async def add_warn(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET warns = COALESCE(warns, 0) + 1 WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()
        async with db.execute(
            "SELECT warns FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def reset_warns(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET warns = 0 WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()


async def get_user_by_topic(topic_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE topic_id = ?", (topic_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def inc_msg(user_id: int, from_user: bool = True):
    col = "msg_from_user" if from_user else "msg_from_group"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE users SET {col} = COALESCE({col},0)+1, last_msg_at = ? WHERE user_id = ?",
            (datetime.now(KYIV).strftime("%Y-%m-%d %H:%M:%S"), user_id),
        )
        await db.commit()


async def delete_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM sticker_spam WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM text_spam WHERE user_id = ?", (user_id,))
        await db.commit()


async def set_admin_tag_for_user(user_id: int, tag: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET admin_tag = ? WHERE user_id = ?",
            (tag, user_id),
        )
        await db.commit()


async def get_override(key: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT value FROM stats_override WHERE key = ?", (key,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def set_override(key: str, value: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO stats_override (key, value) VALUES (?, ?)",
            (key, value),
        )
        await db.commit()


async def get_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            total = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE banned = 1"
        ) as cur:
            banned = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE blocked_bot = 1"
        ) as cur:
            blocked = (await cur.fetchone())[0]
        async with db.execute(
            """SELECT COUNT(*) FROM users
               WHERE mode != 'none' AND banned = 0 AND blocked_bot = 0"""
        ) as cur:
            active = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COALESCE(SUM(msg_from_user),0)+COALESCE(SUM(msg_from_group),0) FROM users"
        ) as cur:
            messages = (await cur.fetchone())[0]

    # overrides
    for key, var in [
        ("total", "total"),
        ("banned", "banned"),
        ("blocked", "blocked"),
        ("active", "active"),
        ("messages", "messages"),
    ]:
        ov = await get_override(key)
        if ov is not None:
            if key == "total":
                total = ov
            elif key == "banned":
                banned = ov
            elif key == "blocked":
                blocked = ov
            elif key == "active":
                active = ov
            elif key == "messages":
                messages = ov

    return {
        "total": total,
        "banned": banned,
        "blocked": blocked,
        "active": active,
        "messages": messages,
    }


async def get_user_ids(kind: str = "all", before_dt: str = None, user_ref: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        if kind == "one":
            ref = (user_ref or "").strip().lstrip("@")
            if ref.isdigit():
                async with db.execute(
                    "SELECT user_id FROM users WHERE user_id = ? AND banned = 0",
                    (int(ref),),
                ) as cur:
                    return [r[0] for r in await cur.fetchall()]
            async with db.execute(
                "SELECT user_id FROM users WHERE username = ? AND banned = 0",
                (ref,),
            ) as cur:
                return [r[0] for r in await cur.fetchall()]

        if kind == "active":
            q = """SELECT user_id FROM users
                   WHERE banned = 0 AND blocked_bot = 0 AND mode != 'none'"""
            async with db.execute(q) as cur:
                return [r[0] for r in await cur.fetchall()]
        elif kind == "before":
            q = """SELECT user_id FROM users
                   WHERE banned = 0 AND blocked_bot = 0 AND created_at <= ?"""
            async with db.execute(q, (before_dt,)) as cur:
                return [r[0] for r in await cur.fetchall()]
        else:
            q = "SELECT user_id FROM users WHERE banned = 0 AND blocked_bot = 0"
            async with db.execute(q) as cur:
                return [r[0] for r in await cur.fetchall()]


async def list_admins():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM admins ORDER BY name") as cur:
            return [dict(r) for r in await cur.fetchall()]


async def add_admin(name: str, tag: str):
    tag = tag.upper().lstrip("#")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO admins (name, tag) VALUES (?, ?)",
            (name, tag),
        )
        await db.commit()


async def del_admin(tag: str):
    tag = tag.upper().lstrip("#")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM admins WHERE tag = ?", (tag,))
        await db.commit()


async def get_topics_by_admin(tag: str):
    tag = tag.upper().lstrip("#")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM users WHERE admin_tag = ? OR admin_tag LIKE ?
               ORDER BY last_msg_at DESC NULLS LAST""",
            (tag, f"%{tag}%"),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def list_all_topics(limit=30):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM users WHERE topic_id IS NOT NULL
               ORDER BY last_msg_at DESC NULLS LAST, created_at DESC LIMIT ?""",
            (limit,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]



async def list_testers():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT name, on_rest FROM testers ORDER BY name") as cur:
            return [dict(r) for r in await cur.fetchall()]


async def set_tester(name: str, on_rest: bool):
    name = name.strip()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO testers (name, on_rest) VALUES (?, ?)",
            (name, 1 if on_rest else 0),
        )
        await db.commit()


async def del_tester(name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM testers WHERE name = ?", (name.strip(),))
        await db.commit()


def format_testers(rows):
    if not rows:
        return "Ресты:\nПока никого нет."
    lines = ["Ресты:\n"]
    for r in rows:
        status = "в ресте" if r["on_rest"] else "не в ресте"
        lines.append(f"• {r['name']} — {status}")
    return "\n".join(lines)



def norm_tag(tag: str) -> str:
    return (tag or "").strip().lstrip("#").casefold()


async def set_admin_hi(tag: str, greeting: str):
    key = norm_tag(tag)
    display = (tag or "").strip().lstrip("#")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO admin_hi (tag_key, tag, greeting) VALUES (?, ?, ?)",
            (key, display, greeting),
        )
        await db.commit()


async def get_admin_hi(tag: str):
    key = norm_tag(tag)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT tag, greeting FROM admin_hi WHERE tag_key = ?", (key,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def list_admin_hi():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT tag, greeting FROM admin_hi ORDER BY tag") as cur:
            return [dict(r) for r in await cur.fetchall()]


async def del_admin_hi(tag: str):
    key = norm_tag(tag)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM admin_hi WHERE tag_key = ?", (key,))
        await db.commit()


async def set_admin_note(tag: str, note: str):
    key = norm_tag(tag)
    display = (tag or "").strip().lstrip("#")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO admin_notes (tag_key, tag, note) VALUES (?, ?, ?)",
            (key, display, note),
        )
        await db.commit()


async def get_admin_note(tag: str):
    key = norm_tag(tag)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT tag, note FROM admin_notes WHERE tag_key = ?", (key,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def list_admin_notes():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT tag, note FROM admin_notes ORDER BY tag") as cur:
            return [dict(r) for r in await cur.fetchall()]


async def del_admin_note(tag: str):
    key = norm_tag(tag)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM admin_notes WHERE tag_key = ?", (key,))
        await db.commit()



async def get_user_note(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT note FROM user_notes WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def set_user_note(user_id: int, note: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO user_notes (user_id, note, updated_at)
               VALUES (?, ?, ?)""",
            (user_id, note, datetime.now(KYIV).strftime("%Y-%m-%d %H:%M:%S")),
        )
        await db.commit()


async def del_user_note(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM user_notes WHERE user_id = ?", (user_id,))
        await db.commit()


# ==================== KEYBOARDS ====================


BTN_REVIEW = "Оставить отзыв"
BTN_TESTS = "Ресты"
BTN_SITE = "Наш сайт"
BTN_NOTES = "Заметки"

USER_MENU_BUTTONS = {BTN_REVIEW, BTN_TESTS, BTN_SITE, BTN_NOTES}

REVIEWS_BOT = "@sky_of_Alienation_reviews"


def user_menu_kb():
    b = ReplyKeyboardBuilder()
    b.button(text=BTN_REVIEW)
    b.button(text=BTN_TESTS)
    b.button(text=BTN_SITE)
    b.button(text=BTN_NOTES)
    b.adjust(1, 1, 1, 1)
    return b.as_markup(resize_keyboard=True)


def mode_kb():
    b = InlineKeyboardBuilder()
    b.button(text="Общение", callback_data="mode:obshchenie")
    b.button(text="Поддержка", callback_data="mode:podderzhka")
    b.button(text="Универсал", callback_data="mode:universal")
    b.adjust(1)
    return b.as_markup()


def admin_kb():
    b = InlineKeyboardBuilder()
    b.button(text="Статистика", callback_data="admin:stats")
    b.button(text="Рассылка", callback_data="admin:broadcast_menu")
    b.button(text="Снять мут", callback_data="admin:unmute")
    b.button(text="Удалить пользователя", callback_data="admin:del_user")
    b.button(text="Править статистику", callback_data="admin:edit_stats")
    b.button(text="Админы", callback_data="admin:admins")
    b.button(text="Ветки", callback_data="admin:topics")
    b.button(text="Ресты", callback_data="admin:testers")
    b.button(text="Приветствия /hi", callback_data="admin:hi")
    b.button(text="Заметки админов", callback_data="admin:notes")
    b.button(text="Закрыть", callback_data="admin:close")
    b.adjust(1)
    return b.as_markup()


def broadcast_kb():
    b = InlineKeyboardBuilder()
    b.button(text="Отправить всем", callback_data="bc:all")
    b.button(text="Отправить активным", callback_data="bc:active")
    b.button(text="Отправить до даты (Киев)", callback_data="bc:before")
    b.button(text="Отправить одному (ID/username)", callback_data="bc:one")
    b.button(text="Назад", callback_data="admin:back")
    b.adjust(1)
    return b.as_markup()


def cancel_kb():
    b = ReplyKeyboardBuilder()
    b.button(text="Отмена")
    return b.as_markup(resize_keyboard=True)


# ==================== HELPERS ====================

def parse_duration(text: str):
    text = (text or "").strip().lower()
    m = re.fullmatch(r"(\d+)\s*(s|sec|m|min|h|hr|d|day|w|week)?", text)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2) or "m"
    if unit in ("s", "sec"):
        return timedelta(seconds=n)
    if unit in ("m", "min"):
        return timedelta(minutes=n)
    if unit in ("h", "hr"):
        return timedelta(hours=n)
    if unit in ("d", "day"):
        return timedelta(days=n)
    if unit in ("w", "week"):
        return timedelta(weeks=n)
    return None


def extract_admin_tag(text: str):
    """Ищем #TAG или #A_B в тексте/названии"""
    if not text:
        return None
    m = re.search(r"#([A-Za-z0-9_]+)", text)
    return m.group(1).upper() if m else None


async def create_topic(message: Message) -> int:
    name = (message.from_user.full_name or "User")[:40]
    if message.from_user.username:
        name = f"{name} (@{message.from_user.username})"
    name = f"{name} [{message.from_user.id}]"[:128]
    topic = await bot.create_forum_topic(chat_id=GROUP_ID, name=name)
    return topic.message_thread_id


async def rename_topic(topic_id: int, new_name: str):
    try:
        await bot.edit_forum_topic(
            chat_id=GROUP_ID, message_thread_id=topic_id, name=new_name[:128]
        )
    except Exception as e:
        logger.error(f"rename: {e}")


async def copy_to_topic(message: Message, topic_id: int):
    try:
        mid = await message.copy_to(chat_id=GROUP_ID, message_thread_id=topic_id)
        await save_msg_map(
            message.from_user.id, message.message_id, mid.message_id, topic_id
        )
    except Exception as e:
        logger.error(f"copy topic: {e}")


async def copy_to_user(message: Message, user_id: int):
    try:
        mid = await message.copy_to(chat_id=user_id)
        await save_msg_map(
            user_id, mid.message_id, message.message_id, message.message_thread_id
        )
        await mark_active(user_id)
    except TelegramForbiddenError:
        await set_blocked_bot(user_id, True)
    except Exception as e:
        logger.error(f"copy user: {e}")


async def apply_edit(chat_id: int, message_id: int, src: Message):
    try:
        if src.text is not None:
            await bot.edit_message_text(
                text=src.text,
                chat_id=chat_id,
                message_id=message_id,
                entities=src.entities,
            )
        elif src.caption is not None:
            await bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption=src.caption,
                caption_entities=src.caption_entities,
            )
    except Exception as e:
        logger.error(f"apply_edit: {e}")


async def do_broadcast(message: Message, user_ids: list):
    if not user_ids:
        await message.answer("Нет пользователей для рассылки.", reply_markup=admin_kb())
        return
    started = datetime.now(KYIV).strftime("%d.%m.%Y %H:%M:%S")
    ok = fail = 0
    status = await message.answer(f"Рассылка запущена\n{started}")
    for i, uid in enumerate(user_ids, 1):
        try:
            await message.copy_to(uid)
            ok += 1
            await mark_active(uid)
        except TelegramForbiddenError:
            await set_blocked_bot(uid, True)
            fail += 1
        except Exception:
            fail += 1
        if i % 15 == 0:
            try:
                await status.edit_text(f"Рассылка запущена\n{started}\n{i}/{len(user_ids)}")
            except Exception:
                pass
            await asyncio.sleep(0.05)
    await status.edit_text(
        f"💥 Рассылка отправлена успешно!\n{started}\nУспешно: {ok}\nОшибок: {fail}"
    )
    await message.answer("Панель", reply_markup=admin_kb())


async def apply_mute_5_days(user_id: int, reason: str, topic_id: int = None):
    until = (datetime.now(KYIV) + timedelta(days=5)).isoformat()
    await set_muted(user_id, until)
    await reset_warns(user_id)
    try:
        await bot.send_message(
            user_id,
            f"Вам выдан мут на 5 дней.\nПричина: {reason}\n"
            f"Если хотите оспорить — напишите в техническую поддержку: {SUPPORT_BOT}",
        )
    except Exception:
        pass
    if topic_id:
        try:
            await bot.send_message(
                GROUP_ID,
                f"Авто-мут 5 дней: {reason}",
                message_thread_id=topic_id,
            )
        except Exception:
            pass


async def check_sticker_spam(user_id: int, sticker_id: str, topic_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT sticker_id, count FROM sticker_spam WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
        if row and row[0] == sticker_id:
            count = row[1] + 1
        else:
            count = 1
        await db.execute(
            """INSERT OR REPLACE INTO sticker_spam (user_id, sticker_id, count)
               VALUES (?, ?, ?)""",
            (user_id, sticker_id, count),
        )
        await db.commit()
    if count >= 10:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM sticker_spam WHERE user_id = ?", (user_id,)
            )
            await db.commit()
        await apply_mute_5_days(
            user_id, "10 одинаковых стикеров подряд", topic_id
        )
        return True
    return False


async def check_text_spam(user_id: int, text: str, topic_id: int) -> bool:
    if not text or not text.strip():
        return False
    text_hash = text.strip()[:200]
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT text_hash, count FROM text_spam WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
        if row and row[0] == text_hash:
            count = row[1] + 1
        else:
            count = 1
        await db.execute(
            """INSERT OR REPLACE INTO text_spam (user_id, text_hash, count)
               VALUES (?, ?, ?)""",
            (user_id, text_hash, count),
        )
        await db.commit()
    if count >= 20:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM text_spam WHERE user_id = ?", (user_id,)
            )
            await db.commit()
        await apply_mute_5_days(
            user_id, "20 одинаковых сообщений подряд", topic_id
        )
        return True
    return False



async def handle_user_menu(message: Message, user: dict) -> bool:
    text = (message.text or "").strip()
    if text not in USER_MENU_BUTTONS:
        return False

    if text == BTN_REVIEW:
        await message.answer(
            f"Оставьте отзыв тут: {REVIEWS_BOT}",
            reply_markup=user_menu_kb(),
        )
        return True

    if text == BTN_TESTS:
        rows = await list_testers()
        await message.answer(format_testers(rows), reply_markup=user_menu_kb())
        return True

    if text == BTN_SITE:
        await message.answer(
            "Сайт находится в разработке",
            reply_markup=user_menu_kb(),
        )
        return True

    if text == BTN_NOTES:
        note = await get_user_note(message.from_user.id)
        b = InlineKeyboardBuilder()
        b.button(text="Написать / изменить", callback_data="unote:edit")
        b.button(text="Удалить заметку", callback_data="unote:del")
        b.adjust(1)
        if note:
            body = f"Твои заметки:\n\n{note}"
        else:
            body = "У тебя пока нет заметок.\nНажми «Написать / изменить»."
        await message.answer(body, reply_markup=b.as_markup())
        await message.answer("Меню", reply_markup=user_menu_kb())
        return True

    return False


# ==================== USER HANDLERS ====================

@router.message(CommandStart(), F.chat.type == "private", StateFilter(None))
@router.message(
    F.chat.type == "private",
    F.text,
    ~F.text.startswith("/"),
    StateFilter(None),
)
@router.message(
    F.chat.type == "private",
    F.content_type.in_({
        ContentType.PHOTO, ContentType.VIDEO, ContentType.DOCUMENT,
        ContentType.VOICE, ContentType.AUDIO, ContentType.STICKER,
        ContentType.ANIMATION, ContentType.VIDEO_NOTE
    }),
    StateFilter(None),
)
async def private_msg(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user(user_id)

    if user and user.get("banned"):
        await message.answer(
            f"Вы заблокированы в этом боте.\nОбратитесь в поддержку: {SUPPORT_BOT}",
            reply_markup=user_menu_kb(),
        )
        return

    if await is_muted(user_id):
        await message.answer(
            "Вы сейчас в муте.\n"
            f"Если хотите оспорить — напишите в техническую поддержку: {SUPPORT_BOT}",
            reply_markup=user_menu_kb(),
        )
        return

    await mark_active(user_id)

    if message.text and await handle_user_menu(message, user):
        return

    try:
        topic_id = await ensure_topic_for_user(message, user)
    except Exception:
        logger.exception("ensure topic")
        await message.answer("Ошибка. Попробуй позже.", reply_markup=user_menu_kb())
        return

    user = await get_user(user_id)

    if not user or user.get("mode") in (None, "none"):
        await message.answer(WELCOME_TEXT, reply_markup=mode_kb())
        await message.answer("Меню всегда внизу.", reply_markup=user_menu_kb())
        await copy_to_topic(message, topic_id)
        return

    if message.sticker:
        if await check_sticker_spam(
            user_id, message.sticker.file_unique_id, topic_id
        ):
            return
    elif message.text and not message.text.startswith("/"):
        if await check_text_spam(user_id, message.text, topic_id):
            return

    await copy_to_topic(message, topic_id)
    await inc_msg(user_id, from_user=True)



@router.callback_query(F.data == "unote:edit")
async def user_note_edit(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PanelStates.waiting_user_note)
    await callback.message.answer(
        "Напиши заметку себе. Она видна только тебе.\nИли Отмена",
        reply_markup=user_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "unote:del")
async def user_note_del(callback: CallbackQuery):
    await del_user_note(callback.from_user.id)
    await callback.message.answer("Заметка удалена.", reply_markup=user_menu_kb())
    await callback.answer()


@router.message(PanelStates.waiting_user_note, F.text)
async def user_note_save(message: Message, state: FSMContext):
    raw = (message.text or "").strip()
    if raw in ("Отмена", BTN_NOTES, BTN_REVIEW, BTN_TESTS, BTN_SITE):
        await state.clear()
        if raw in USER_MENU_BUTTONS:
            user = await get_user(message.from_user.id)
            await handle_user_menu(message, user)
            return
        await message.answer("Отменено", reply_markup=user_menu_kb())
        return
    await set_user_note(message.from_user.id, message.text)
    await state.clear()
    await message.answer("Заметка сохранена.", reply_markup=user_menu_kb())


@router.callback_query(F.data.startswith("mode:"))
async def mode_choice(callback: CallbackQuery):
    mode = callback.data.split(":")[1]
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала напиши боту", show_alert=True)
        return
    if user.get("banned"):
        await callback.answer("Заблокирован", show_alert=True)
        return

    await update_mode(callback.from_user.id, mode)
    await callback.message.edit_reply_markup(reply_markup=None)

    if mode == "obshchenie":
        name = "Общение"
        txt = "Вы выбрали: Общение\nАдминистратор скоро ответит."
        topic_txt = "Пользователь выбрал: <b>Общение</b>"
    elif mode == "podderzhka":
        name = "Поддержка"
        txt = "Вы выбрали: Поддержка\nАдминистратор скоро ответит."
        topic_txt = "Пользователь выбрал: <b>Поддержка</b>"
    else:
        name = "Универсал"
        txt = "Вы выбрали: Универсал\nАдминистратор скоро ответит."
        topic_txt = "Пользователь выбрал: <b>Универсал</b>"

    base = (callback.from_user.full_name or "User")[:30]
    unique = f"{base} | {name} | {callback.from_user.id}"[:128]
    await rename_topic(user["topic_id"], unique)
    await callback.message.answer(txt, reply_markup=user_menu_kb())
    try:
        await bot.send_message(
            GROUP_ID, topic_txt,
            message_thread_id=user["topic_id"], parse_mode=ParseMode.HTML
        )
    except Exception:
        pass
    try:
        await bot.send_message(
            GROUP_ID,
            f"🔔 Новый пользователь — <b>{name}</b>",
            parse_mode=ParseMode.HTML,
            disable_notification=False,
        )
    except Exception:
        pass
    await callback.answer()


# ==================== GROUP HANDLERS ====================

@router.message(F.chat.id == GROUP_ID, F.message_thread_id)
async def group_msg(message: Message):
    # Только люди. Боты (Iris и др.) игнорируем
    if message.from_user and message.from_user.is_bot:
        return

    user = await get_user_by_topic(message.message_thread_id)
    if not user:
        return

    user_id = user["user_id"]
    text = (message.text or "").strip()

    # Если в сообщении/названии есть #TAG — привязываем к админу
    tag = extract_admin_tag(text)
    if tag:
        await set_admin_tag_for_user(user_id, tag)

    if text.lower() in ("/ban", "ban"):
        await set_banned(user_id, True)
        try:
            await bot.send_message(
                user_id,
                f"Вы заблокированы в этом боте.\nОбратитесь в поддержку: {SUPPORT_BOT}",
            )
        except TelegramForbiddenError:
            await set_blocked_bot(user_id, True)
        except Exception:
            pass
        await message.reply(f"Пользователь {user_id} заблокирован.")
        return

    if text.lower() in ("/unban", "unban"):
        await set_banned(user_id, False)
        try:
            await bot.send_message(user_id, "Вы разблокированы. Можете снова писать.")
        except Exception:
            pass
        await message.reply(f"Пользователь {user_id} разблокирован.")
        return

    if text.lower().startswith("/mute") or text.lower().startswith("mute "):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await message.reply("Использование: /mute 5m  (или 2h, 1d, 1w)")
            return
        td = parse_duration(parts[1])
        if not td:
            await message.reply("Не понял время. Пример: /mute 5m")
            return
        until = (datetime.now(KYIV) + td).isoformat()
        await set_muted(user_id, until)
        mins = max(1, int(td.total_seconds() // 60))
        try:
            await bot.send_message(
                user_id,
                f"Вам выдан мут на {mins} мин.\n"
                f"Если хотите снова писать или оспорить мут — "
                f"напишите в техническую поддержку: {SUPPORT_BOT}",
            )
        except Exception:
            pass
        await message.reply(f"Мут выдан на {mins} мин.")
        return

    if text.lower() in ("/unmute", "unmute"):
        await set_muted(user_id, None)
        await reset_warns(user_id)
        try:
            await bot.send_message(user_id, "Мут снят. Можете писать.")
        except Exception:
            pass
        await message.reply("Мут снят.")
        return

    if text.lower() in ("/warn", "warn"):
        warns = await add_warn(user_id)
        try:
            await bot.send_message(
                user_id,
                f"Вам выдано предупреждение ({warns}/10).\n"
                f"При 10 предупреждениях — мут на 5 дней.\n"
                f"Оспорить: {SUPPORT_BOT}",
            )
        except Exception:
            pass
        if warns >= 10:
            until = (datetime.now(KYIV) + timedelta(days=5)).isoformat()
            await set_muted(user_id, until)
            await reset_warns(user_id)
            try:
                await bot.send_message(
                    user_id,
                    "10 предупреждений. Мут на 5 дней.\n"
                    f"Оспорить: техническая поддержка {SUPPORT_BOT}",
                )
            except Exception:
                pass
            await message.reply("10 варнов — мут на 5 дней.")
        else:
            await message.reply(f"Варн выдан. Всего: {warns}/10")
        return

    # /hi рихтер  — отправить пользователю приветствие админа
    low = text.lower()
    if low.startswith("/hi ") or low.startswith("hi "):
        tag = text.split(maxsplit=1)[1].strip()
        row = await get_admin_hi(tag)
        if not row or not row.get("greeting"):
            await message.reply("Приветствие для этого тега не задано. Задай его в /panel.")
            return
        try:
            await bot.send_message(user_id, row["greeting"])
            await message.reply(f"Приветствие #{row.get('tag') or tag} отправлено пользователю.")
        except TelegramForbiddenError:
            await set_blocked_bot(user_id, True)
            await message.reply("Пользователь заблокировал бота.")
        except Exception as e:
            await message.reply(f"Не отправилось: {e}")
        return

    # Привязка админа: /tag Z_K
    if text.lower().startswith("/tag "):
        t = text.split(maxsplit=1)[1].strip().lstrip("#").upper()
        await set_admin_tag_for_user(user_id, t)
        await message.reply(f"Тема привязана к админу #{t}")
        return

    if user.get("banned"):
        await message.reply("Этот пользователь заблокирован.")
        return

    await copy_to_user(message, user_id)
    await inc_msg(user_id, from_user=False)



@router.edited_message(F.chat.type == "private")
async def edited_private(message: Message):
    user = await get_user(message.from_user.id)
    if not user or user.get("banned"):
        return
    if await is_muted(message.from_user.id):
        return
    mapped = await get_map_by_user_msg(message.from_user.id, message.message_id)
    if not mapped:
        return
    await apply_edit(GROUP_ID, mapped["group_msg_id"], message)


@router.edited_message(F.chat.id == GROUP_ID)
async def edited_group(message: Message):
    if message.from_user and message.from_user.is_bot:
        return
    mapped = await get_map_by_group_msg(message.message_id)
    if not mapped:
        return
    await apply_edit(mapped["user_id"], mapped["user_msg_id"], message)


# ==================== ADMIN PANEL ====================

@router.message(Command("panel"), F.chat.type == "private")
async def panel_cmd(message: Message, state: FSMContext):
    await state.set_state(PanelStates.waiting_password)
    await message.answer("Введите пароль:")


@router.message(PanelStates.waiting_password, F.text)
async def panel_pass(message: Message, state: FSMContext):
    if message.text.strip() != PANEL_PASSWORD:
        await message.answer("Неверный пароль")
        await state.clear()
        return
    await state.clear()
    await message.answer("Админ-панель", reply_markup=admin_kb())


@router.callback_query(F.data == "admin:stats")
async def admin_stats(callback: CallbackQuery):
    s = await get_stats()
    text = (
        f"<b>Статистика</b>\n\n"
        f"Всего пользователей: <b>{s['total']}</b>\n"
        f"Забанено нами: <b>{s['banned']}</b>\n"
        f"Заблокировали бота: <b>{s['blocked']}</b>\n"
        f"Активных: <b>{s['active']}</b>\n"
        f"Всего сообщений: <b>{s['messages']}</b>"
    )
    await callback.message.edit_text(
        text, parse_mode=ParseMode.HTML, reply_markup=admin_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "admin:broadcast_menu")
async def admin_bc_menu(callback: CallbackQuery):
    await callback.message.edit_text("Рассылка:", reply_markup=broadcast_kb())
    await callback.answer()


@router.callback_query(F.data == "admin:back")
async def admin_back(callback: CallbackQuery):
    await callback.message.edit_text("Админ-панель", reply_markup=admin_kb())
    await callback.answer()


@router.callback_query(F.data == "admin:close")
async def admin_close(callback: CallbackQuery):
    await callback.message.edit_text("Закрыто")
    await callback.answer()


@router.callback_query(F.data == "admin:unmute")
async def admin_unmute_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PanelStates.waiting_unmute_id)
    await callback.message.answer(
        "Введите ID пользователя для снятия мута\n(или Отмена)",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(PanelStates.waiting_unmute_id, F.text)
async def admin_unmute_do(message: Message, state: FSMContext):
    if message.text.strip() == "Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=admin_kb())
        return
    if not message.text.strip().isdigit():
        await message.answer("Нужен числовой ID.")
        return
    uid = int(message.text.strip())
    await set_muted(uid, None)
    await reset_warns(uid)
    try:
        await bot.send_message(uid, "Мут снят. Можете писать.")
    except Exception:
        pass
    await message.answer(f"Мут снят у {uid}", reply_markup=admin_kb())
    await state.clear()


@router.callback_query(F.data == "admin:del_user")
async def admin_del_user_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PanelStates.waiting_delete_user)
    await callback.message.answer(
        "Введите ID пользователя для удаления из базы\n(или Отмена)",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(PanelStates.waiting_delete_user, F.text)
async def admin_del_user_do(message: Message, state: FSMContext):
    if message.text.strip() == "Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=admin_kb())
        return
    if not message.text.strip().isdigit():
        await message.answer("Нужен числовой ID.")
        return
    uid = int(message.text.strip())
    await delete_user(uid)
    await message.answer(f"Пользователь {uid} удалён из базы.", reply_markup=admin_kb())
    await state.clear()


@router.callback_query(F.data == "admin:edit_stats")
async def admin_edit_stats_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PanelStates.waiting_edit_stats)
    await callback.message.answer(
        "Правка статистики.\n"
        "Формат: ключ=число\n"
        "Ключи: total, banned, blocked, active, messages\n"
        "Пример: blocked=5\n"
        "Сбросить ключ: total=reset\n"
        "Или Отмена",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(PanelStates.waiting_edit_stats, F.text)
async def admin_edit_stats_do(message: Message, state: FSMContext):
    if message.text.strip() == "Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=admin_kb())
        return
    text = message.text.strip()
    if "=" not in text:
        await message.answer("Формат: ключ=число  (total, banned, blocked, active, messages)")
        return
    key, val = text.split("=", 1)
    key = key.strip().lower()
    val = val.strip()
    if key not in ("total", "banned", "blocked", "active", "messages"):
        await message.answer("Ключ: total / banned / blocked / active / messages")
        return
    if val.lower() == "reset":
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM stats_override WHERE key = ?", (key,))
            await db.commit()
        await message.answer(f"Сброшено: {key}", reply_markup=admin_kb())
        await state.clear()
        return
    if not val.lstrip("-").isdigit():
        await message.answer("Значение должно быть числом.")
        return
    await set_override(key, int(val))
    await message.answer(f"Установлено: {key} = {val}", reply_markup=admin_kb())
    await state.clear()


@router.callback_query(F.data == "admin:admins")
async def admin_admins_menu(callback: CallbackQuery):
    admins = await list_admins()
    b = InlineKeyboardBuilder()
    for a in admins:
        b.button(
            text=f"{a['name']} (#{a['tag']})",
            callback_data=f"admview:{a['tag']}",
        )
    b.button(text="➕ Добавить админа", callback_data="admin:add_admin")
    b.button(text="➖ Удалить админа", callback_data="admin:del_admin")
    b.button(text="Назад", callback_data="admin:back")
    b.adjust(1)
    text = "Админы:" if admins else "Админов пока нет. Добавьте."
    await callback.message.edit_text(text, reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("admview:"))
async def admin_view_topics(callback: CallbackQuery):
    tag = callback.data.split(":", 1)[1]
    topics = await get_topics_by_admin(tag)
    if not topics:
        await callback.answer("Нет веток у этого админа", show_alert=True)
        return
    lines = [f"<b>Ветки админа #{tag}</b>\n"]
    for t in topics[:20]:
        name = t.get("full_name") or "—"
        mode = t.get("mode") or "—"
        mu = t.get("msg_from_user") or 0
        mg = t.get("msg_from_group") or 0
        last = t.get("last_msg_at") or "—"
        created = t.get("created_at") or "—"
        uname = t.get("username") or "нет"
        lines.append(
            f"• {name} | {mode}\n"
            f"  @{uname} | ID: <code>{t['user_id']}</code>\n"
            f"  Сообщ. юзер/группа: {mu}/{mg}\n"
            f"  Создана: {created}\n"
            f"  Последнее: {last}\n"
        )
    b = InlineKeyboardBuilder()
    b.button(text="Назад к админам", callback_data="admin:admins")
    await callback.message.edit_text(
        "\n".join(lines)[:4000],
        parse_mode=ParseMode.HTML,
        reply_markup=b.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin:add_admin")
async def admin_add_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PanelStates.waiting_add_admin)
    await callback.message.answer(
        "Формат: Имя #ТЕГ\nПример: Закат #Z_K\nИли Отмена",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(PanelStates.waiting_add_admin, F.text)
async def admin_add_do(message: Message, state: FSMContext):
    if message.text.strip() == "Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=admin_kb())
        return
    text = message.text.strip()
    m = re.match(r"(.+?)\s*#([A-Za-z0-9_]+)$", text)
    if not m:
        await message.answer("Формат: Имя #ТЕГ  (пример: Закат #Z_K)")
        return
    name, tag = m.group(1).strip(), m.group(2).upper()
    await add_admin(name, tag)
    await message.answer(f"Добавлен: {name} (#{tag})", reply_markup=admin_kb())
    await state.clear()


@router.callback_query(F.data == "admin:del_admin")
async def admin_del_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PanelStates.waiting_del_admin)
    await callback.message.answer(
        "Введите тег админа для удаления, например: Z_K\nИли Отмена",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(PanelStates.waiting_del_admin, F.text)
async def admin_del_do(message: Message, state: FSMContext):
    if message.text.strip() == "Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=admin_kb())
        return
    tag = message.text.strip().lstrip("#").upper()
    await del_admin(tag)
    await message.answer(f"Админ #{tag} удалён.", reply_markup=admin_kb())
    await state.clear()





@router.callback_query(F.data == "admin:notes")
async def admin_notes_start(callback: CallbackQuery, state: FSMContext):
    rows = await list_admin_notes()
    lines = ["Заметки админов:\n"]
    if rows:
        for r in rows:
            preview = (r.get("note") or "")[:80]
            lines.append(f"#{r['tag']}: {preview}")
    else:
        lines.append("Пока пусто.")
    lines.append("\nВведи тег админа, например: #рихтер\nИли удалить рихтер\nИли Отмена")
    await state.set_state(PanelStates.waiting_note_tag)
    await callback.message.answer("\n".join(lines), reply_markup=cancel_kb())
    await callback.answer()


@router.message(PanelStates.waiting_note_tag, F.text)
async def admin_note_tag(message: Message, state: FSMContext):
    raw = message.text.strip()
    if raw == "Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=admin_kb())
        return
    if raw.lower().startswith("удалить "):
        tag = raw.split(" ", 1)[1].strip()
        await del_admin_note(tag)
        await state.clear()
        await message.answer(f"Заметки #{norm_tag(tag)} удалены.", reply_markup=admin_kb())
        return
    tag = raw.lstrip("#").strip()
    if not tag:
        await message.answer("Введи тег, например #рихтер")
        return
    await state.update_data(note_tag=tag)
    await state.set_state(PanelStates.waiting_note_text)
    await message.answer(
        f"Админ: #{tag}\nТеперь пришли текст заметки для пользователей.\nИли Отмена",
        reply_markup=cancel_kb(),
    )


@router.message(PanelStates.waiting_note_text)
async def admin_note_text(message: Message, state: FSMContext):
    if (message.text or "").strip() == "Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=admin_kb())
        return
    data = await state.get_data()
    tag = data.get("note_tag")
    note = message.text or message.caption
    if not tag or not note:
        await message.answer("Нужен текст заметки.")
        return
    await set_admin_note(tag, note)
    await state.clear()
    await message.answer(
        f"Заметка для #{tag} сохранена. Пользователи увидят её в кнопке Заметки.",
        reply_markup=admin_kb(),
    )


@router.callback_query(F.data == "admin:hi")
async def admin_hi_start(callback: CallbackQuery, state: FSMContext):
    rows = await list_admin_hi()
    lines = ["Приветствия админов (/hi):\n"]
    if rows:
        for r in rows:
            preview = (r.get("greeting") or "")[:80]
            lines.append(f"#{r['tag']}: {preview}")
    else:
        lines.append("Пока пусто.")
    lines.append("\nВведи тег, например: #рихтер\nИли удалить рихтер\nИли Отмена")
    await state.set_state(PanelStates.waiting_hi_tag)
    await callback.message.answer("\n".join(lines), reply_markup=cancel_kb())
    await callback.answer()


@router.message(PanelStates.waiting_hi_tag, F.text)
async def admin_hi_tag(message: Message, state: FSMContext):
    raw = message.text.strip()
    if raw == "Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=admin_kb())
        return
    if raw.lower().startswith("удалить "):
        tag = raw.split(" ", 1)[1].strip()
        await del_admin_hi(tag)
        await state.clear()
        await message.answer(f"Приветствие #{norm_tag(tag)} удалено.", reply_markup=admin_kb())
        return
    tag = raw.lstrip("#").strip()
    if not tag:
        await message.answer("Введи тег, например #рихтер")
        return
    await state.update_data(hi_tag=tag)
    await state.set_state(PanelStates.waiting_hi_text)
    await message.answer(
        f"Тег: #{tag}\nТеперь пришли текст приветствия для пользователя.\nИли Отмена",
        reply_markup=cancel_kb(),
    )


@router.message(PanelStates.waiting_hi_text)
async def admin_hi_text(message: Message, state: FSMContext):
    if (message.text or "").strip() == "Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=admin_kb())
        return
    data = await state.get_data()
    tag = data.get("hi_tag")
    greeting = message.text or message.caption
    if not tag or not greeting:
        await message.answer("Нужен текст приветствия.")
        return
    await set_admin_hi(tag, greeting)
    await state.clear()
    await message.answer(
        f"Готово. В теме пиши: /hi {tag}",
        reply_markup=admin_kb(),
    )


@router.callback_query(F.data == "admin:testers")
async def admin_testers(callback: CallbackQuery, state: FSMContext):
    rows = await list_testers()
    await state.set_state(PanelStates.waiting_tester)
    await callback.message.answer(
        format_testers(rows) + "\n\n"
        "Обновить:\n"
        "Имя rest — в ресте\n"
        "Имя active — не в ресте\n"
        "удалить Имя — убрать\n"
        "Или Отмена",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(PanelStates.waiting_tester, F.text)
async def admin_testers_do(message: Message, state: FSMContext):
    raw = message.text.strip()
    if raw == "Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=admin_kb())
        return
    low = raw.lower()
    if low.startswith("удалить "):
        name = raw.split(" ", 1)[1].strip()
        await del_tester(name)
        await state.clear()
        await message.answer(f"Удалён: {name}", reply_markup=admin_kb())
        return
    parts = raw.rsplit(" ", 1)
    if len(parts) != 2 or parts[1].lower() not in ("rest", "active", "рест"):
        await message.answer("Формат: Имя rest   или   Имя active   или   удалить Имя")
        return
    name, st = parts[0].strip(), parts[1].lower()
    on_rest = st in ("rest", "рест")
    await set_tester(name, on_rest)
    await state.clear()
    await message.answer(
        f"{name}: {'в ресте' if on_rest else 'не в ресте'}",
        reply_markup=admin_kb(),
    )


@router.callback_query(F.data == "admin:topics")
async def admin_topics(callback: CallbackQuery):
    topics = await list_all_topics(25)
    if not topics:
        await callback.answer("Веток нет", show_alert=True)
        return
    lines = ["<b>Последние ветки</b>\n"]
    for t in topics:
        name = t.get("full_name") or "—"
        mode = t.get("mode") or "—"
        tag = t.get("admin_tag") or "—"
        mu = t.get("msg_from_user") or 0
        mg = t.get("msg_from_group") or 0
        uname = t.get("username") or "нет"
        lines.append(
            f"• {name} | {mode} | #{tag}\n"
            f"  @{uname} | ID: <code>{t['user_id']}</code>\n"
            f"  сообщ: {mu}/{mg}\n"
        )
    b = InlineKeyboardBuilder()
    b.button(text="Назад", callback_data="admin:back")
    await callback.message.edit_text(
        "\n".join(lines)[:4000],
        parse_mode=ParseMode.HTML,
        reply_markup=b.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.in_({"bc:all", "bc:active", "bc:before", "bc:one"}))
async def bc_choose(callback: CallbackQuery, state: FSMContext):
    kind = callback.data.split(":")[1]
    await state.update_data(bc_kind=kind)
    if kind == "before":
        await state.set_state(PanelStates.waiting_broadcast_date)
        await callback.message.answer(
            "Введите дату и время по Киеву\nФормат: 2026-08-25 14:00\nИли Отмена",
            reply_markup=cancel_kb(),
        )
    elif kind == "one":
        await state.set_state(PanelStates.waiting_broadcast_user)
        await callback.message.answer(
            "Введите ID или username\nИли Отмена",
            reply_markup=cancel_kb(),
        )
    else:
        await state.set_state(PanelStates.waiting_broadcast_text)
        await callback.message.answer(
            "Отправьте сообщение для рассылки\nИли Отмена",
            reply_markup=cancel_kb(),
        )
    await callback.answer()


@router.message(PanelStates.waiting_broadcast_date, F.text)
async def bc_date(message: Message, state: FSMContext):
    if message.text.strip() == "Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=admin_kb())
        return
    raw = message.text.strip()
    try:
        datetime.strptime(raw, "%Y-%m-%d %H:%M")
    except ValueError:
        await message.answer("Формат: 2026-08-25 14:00")
        return
    await state.update_data(bc_before=raw)
    await state.set_state(PanelStates.waiting_broadcast_text)
    await message.answer("Теперь сообщение для рассылки\nИли Отмена", reply_markup=cancel_kb())


@router.message(PanelStates.waiting_broadcast_user, F.text)
async def bc_user(message: Message, state: FSMContext):
    if message.text.strip() == "Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=admin_kb())
        return
    await state.update_data(bc_user=message.text.strip())
    await state.set_state(PanelStates.waiting_broadcast_text)
    await message.answer("Теперь сообщение для рассылки\nИли Отмена", reply_markup=cancel_kb())


@router.message(PanelStates.waiting_broadcast_text, F.text == "Отмена")
async def bc_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено", reply_markup=admin_kb())


@router.message(PanelStates.waiting_broadcast_text)
async def bc_send(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    kind = data.get("bc_kind", "all")
    if kind == "before":
        users = await get_user_ids("before", before_dt=data.get("bc_before"))
    elif kind == "one":
        users = await get_user_ids("one", user_ref=data.get("bc_user"))
    elif kind == "active":
        users = await get_user_ids("active")
    else:
        users = await get_user_ids("all")
    await do_broadcast(message, users)


async def main():
    await init_db()
    dp.include_router(router)
    print("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
