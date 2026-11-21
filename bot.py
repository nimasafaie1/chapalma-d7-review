import asyncio
import logging
import os
import pickle
import re
import shutil
import socket
from datetime import time

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# کنسول ویندوز به‌صورت پیش‌فرض cp1252 است و چاپ متن فارسی/ایموجی باعث
# UnicodeEncodeError و کرش شدن ربات می‌شد. خروجی را به UTF-8 تغییر می‌دهیم.
import sys as _sys

for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

from config import BOT_TOKEN, GROUP_ID, DROP_PENDING_UPDATES
from database import create_tables
from prices import TEACHERS
from keyboards import teacher_label, CUSTOM_FILE_BUTTON, EXAMS_BUTTON
from states import (
    NAME,
    CHOOSING_GRADE,
    CHOOSING_CHAPTER,
    CHOOSING_COLOR,
    CHOOSING_NAZARI_GRADE,
    CHOOSING_NAZARI_BOOKLET,
    CHOOSING_ADD_MORE,
    ORDER_ENTRY,
    CHOOSING_DELIVERY,
    CHOOSING_DELIVERY_LOCATION,
    WAITING_ADDRESS,
    WAITING_PHONE,
    WAITING_RECEIPT,
    WAITING_FILE,
    CHOOSING_FILE_OPTION,
    CHOOSING_BINDING,
    CHOOSING_EXAM_PROVIDER,
    CHOOSING_EXAM_SUBJECT,
    CHOOSING_EXAM_GRADE,
    CHOOSING_EXAM_DATE,
    CHOOSING_EXAM_ACTION,
    CHOOSING_EXAM_ANSWER_INCLUDE,
    CHOOSING_EXAM_QUANTITY,
    WAITING_EXAM_QUANTITY_CUSTOM,
    CHOOSING_EXAM_MAZ_TYPE,
    CHOOSING_EXAM_MAZ_FIELD,
    CHOOSING_EXAM_MAZ_GRADE,
    CHOOSING_EXAM_KHEILI_GRADE,
    CHOOSING_EXAM_KHEILI_FIELD,
    ADMIN_EXAM_PROVIDER,
    ADMIN_EXAM_FIELD,
    ADMIN_EXAM_SUBJECT,
    ADMIN_EXAM_GRADE,
    ADMIN_EXAM_DATE,
    ADMIN_EXAM_QUESTION_FILE,
    ADMIN_EXAM_ANSWER_FILE,
    ADMIN_BOOKLET_TEACHER,
    ADMIN_BOOKLET_SUBJECT,
    ADMIN_BOOKLET_GRADE,
    ADMIN_BOOKLET_CHAPTER,
    ADMIN_BOOKLET_TITLE,
    ADMIN_BOOKLET_VERSIONS,
    CHOOSING_KONKUR_TYPE,
    CHOOSING_KONKUR_YEAR,
    CHOOSING_KONKUR_SESSION,
    CHOOSING_KONKUR_SUBJECT,
    CHOOSING_KONKUR_ACTION,
    CHOOSING_EXAM_FINAL_ARCHIVE,
    CHOOSING_EXAM_AHRAM_GRADE,
)
from handlers import (
    start,
    get_name,
    start_order_flow,
    error_handler,
    choose_grade,
    choose_chapter,
    choose_color,
    choose_nazari_grade,
    choose_nazari_booklet,
    choose_add_more,
    receive_file,
    choose_file_option,
    choose_binding,
    choose_delivery,
    choose_delivery_location,
    receive_address,
    receive_phone,
    receive_receipt,
    handle_receipt_callback,
    cancel,
    handle_group_confirmation,
    GROUP_CONFIRM_COMMANDS,
    cmd_orders,
    cmd_exam_list,
    cmd_my_orders,
    cmd_notify_available,
    cmd_stats,
    choose_exam_provider,
    choose_exam_subject,
    choose_exam_grade,
    choose_exam_date,
    choose_exam_action,
    choose_exam_answer_include,
    choose_exam_quantity,
    receive_exam_quantity_custom,
    choose_exam_maz_type,
    choose_exam_maz_field,
    choose_exam_maz_grade,
    choose_exam_kheili_grade,
    choose_exam_kheili_field,
    choose_konkur_type,
    choose_konkur_year,
    choose_konkur_session,
    choose_konkur_subject,
    choose_konkur_action,
    choose_final_exam_archive,
    choose_exam_ahram_grade,
    cmd_add_exam,
    admin_cancel_exam,
    admin_choose_provider,
    admin_choose_exam_field,
    admin_choose_grade,
    admin_choose_subject,
    admin_receive_date,
    admin_receive_question_file,
    admin_receive_answer_file,
    cmd_add_booklet,
    admin_cancel_booklet,
    admin_choose_booklet_teacher,
    admin_choose_booklet_subject,
    admin_choose_booklet_grade,
    admin_choose_booklet_chapter,
    admin_receive_booklet_title,
    admin_choose_booklet_versions,
    admin_receive_booklet_price,
)
from jobs import (
    daily_backup,
    daily_report,
    check_unconfirmed_payments,
    cleanup_orphan_orders,
    expire_unpaid_orders_job,
)


# ساخت دیتابیس در صورت نبودن
create_tables()


# ---------------------------------------------------------------------------
# Workaround: принудительно используем IPv4 для DNS-разрешения غیرهمزمان
#
# مشکل: وقتی ربات از طریق asyncio/httpx به api.telegram.org متصل می‌شود،
# DNS ممکن است هم IPv4 و هم IPv6 برگرداند. آدرس IPv6 اغلب از طریق VPN
# قابل مسیریابی نیست و باعث httpx.ConnectError می‌شود.
# درخواست‌های همزمان (httpx.get مستقیم) کار می‌کند، چون مسیر DNS متفاوتی دارند.
#
# راه‌حل: asyncio.BaseEventLoop.getaddrinfo را پچ می‌کنیم تا فقط از
# family=AF_INET (IPv4) استفاده کند. این فقط روی فرآیند فعلی پایتون اعمال
# می‌شود و تنظیمات سراسری شبکهٔ ویندوز را تغییر نمی‌دهد.
# ---------------------------------------------------------------------------

_original_loop_getaddrinfo = asyncio.BaseEventLoop.getaddrinfo


async def _ipv4_getaddrinfo(self, host, port, *, family=0, type=0, proto=0, flags=0):
    return await _original_loop_getaddrinfo(
        self, host, port, family=socket.AF_INET, type=type, proto=proto, flags=flags
    )


asyncio.BaseEventLoop.getaddrinfo = _ipv4_getaddrinfo


builder = Application.builder().token(BOT_TOKEN)

# --------------------------------------------------------------------------
# حافظه‌ی دائمی: وضعیت مکالمه‌ها روی دیسک ذخیره میشه، پس اگه ربات ری‌استارت
# بشه (کرش، آپدیت، قطعی برق)، مشتری‌هایی که وسط سفارش بودن از همون‌جا ادامه
# می‌دن، نه از اول.
# --------------------------------------------------------------------------
try:
    from telegram.ext import PicklePersistence
    persistence = PicklePersistence(filepath="bot_persistence.pkl")
    builder = builder.persistence(persistence)
    HAS_PERSISTENCE = True
except ImportError:
    print("⚠️ PicklePersistence در دسترس نیست؛ ربات بدون حافظه‌ی دائمی اجرا میشه.")
    HAS_PERSISTENCE = False

app = builder.build()


# ---------------------------------------------------------------------------
# تایید پرداخت توسط ادمین، با ریپلای کردن "تایید" روی پیام فیش داخل گروه
# ---------------------------------------------------------------------------
#
# چرا این هندلر باید *اول* ثبت شود؟
#
# در PTB، در هر گروه هندلر فقط اولین هندلری که پیام را بگیرد اجرا می‌شود و
# بقیه‌ی هندلرهای همان گروه دیده نمی‌شوند. هر سه ConversationHandler پروژه
# (order_conv، admin_exam_conv و admin_booklet_conv) در وضعیت‌های میانی خود
# هر پیام متنیِ گروه را می‌گیرند (فیلترشان filters.TEXT است).
#
# نتیجه: اگر ادمین همان لحظه داخل یکی از آن گفتگوها (مثلاً در حال ثبت آزمون با
# /addexam یا ثبت جزوه با /booklet) باشد، پیامِ «تایید» روی پیام رسید، توسط همان
# گفتگو بلعیده می‌شد و سفارش هرگز تأیید نمی‌شد؛ بدون هیچ پیام خطایی برای ادمین.
# ثبت این هندلر پیش از ConversationHandlerها این اولویت را تضمین می‌کند.
#
# چرا فیلتر روی متنِ دقیقِ دستورها می‌چسبد؟
#
# چون این هندلر حالا زودتر از همه ثبت می‌شود، نباید پیام‌های متنیِ عادی گروه را
# هم ببلعد (مثلاً نام استاد در جریان /booklet). پس فیلتر فقط پیام‌هایی را
# قبول می‌کند که دقیقاً یکی از دستورهای تأیید باشند. فهرست دستورها از
# handlers.GROUP_CONFIRM_COMMANDS می‌آید تا فیلتر و منطقِ هندلر یکی بمانند.
group_confirm_regex = re.compile(
    r"^\s*(?:%s)\s*$" % "|".join(re.escape(cmd) for cmd in GROUP_CONFIRM_COMMANDS)
)

app.add_handler(
    MessageHandler(
        filters.Chat(chat_id=GROUP_ID)
        & filters.REPLY
        & filters.TEXT
        & filters.Regex(group_confirm_regex),
        handle_group_confirmation,
    )
)


# ---------------------------------------------------------------------------
# ثبت‌نام کاربر جدید
# ---------------------------------------------------------------------------
registration_conv = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)]
    },
    fallbacks=[],
    name="registration_conv",
    persistent=HAS_PERSISTENCE,
)
app.add_handler(registration_conv)

# ---------------------------------------------------------------------------
# سفارش (جزوه آماده یا جزوه دلخواه) تا پرداخت
#
# نکته: ورودی‌های این گفتگو فقط چت خصوصی (PM با ربات) فعال هستند.
# گروه مخصوص دستورهای ادمین (/booklet، /addexam، ...) و تایید پرداخت است؛
# بدون این فیلتر، هنگامی که ادمین داخل گروه در جریان /booklet دکمه‌ی یکی
# از اساتید را می‌زند، نقطه‌ی ورود order_conv (که زودتر ثبت شده و فیلتر
# چت ندارد) آن پیام را می‌رباید و مکالمه‌ی ثبت جزوه خراب می‌شود.
# ---------------------------------------------------------------------------
teacher_regex = "^(" + "|".join(re.escape(teacher_label(t)) for t in TEACHERS) + ")$"

order_conv = ConversationHandler(
    entry_points=[
        MessageHandler(filters.ChatType.PRIVATE & filters.Regex(teacher_regex), start_order_flow),
        MessageHandler(filters.ChatType.PRIVATE & filters.Regex(f"^{re.escape(CUSTOM_FILE_BUTTON)}$"), start_order_flow),
        MessageHandler(filters.ChatType.PRIVATE & filters.Regex(f"^{re.escape(EXAMS_BUTTON)}$"), start_order_flow),
    ],
    states={
        CHOOSING_GRADE: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_grade)],
        CHOOSING_CHAPTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_chapter)],
        CHOOSING_COLOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_color)],
        CHOOSING_NAZARI_GRADE: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_nazari_grade)],
        CHOOSING_NAZARI_BOOKLET: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_nazari_booklet)],
        CHOOSING_ADD_MORE: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_add_more)],
        ORDER_ENTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, start_order_flow)],

        WAITING_FILE: [MessageHandler(filters.ALL & ~filters.COMMAND, receive_file)],
        CHOOSING_FILE_OPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_file_option)],
        CHOOSING_BINDING: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_binding)],

        CHOOSING_EXAM_PROVIDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_exam_provider)],
        CHOOSING_EXAM_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_exam_subject)],
        CHOOSING_EXAM_GRADE: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_exam_grade)],
        CHOOSING_EXAM_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_exam_date)],
        CHOOSING_EXAM_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_exam_action)],
        CHOOSING_EXAM_ANSWER_INCLUDE: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_exam_answer_include)],
        CHOOSING_EXAM_QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_exam_quantity)],
        WAITING_EXAM_QUANTITY_CUSTOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_exam_quantity_custom)],

        CHOOSING_EXAM_MAZ_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_exam_maz_type)],
        CHOOSING_EXAM_MAZ_FIELD: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_exam_maz_field)],
        CHOOSING_EXAM_MAZ_GRADE: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_exam_maz_grade)],

        CHOOSING_EXAM_KHEILI_GRADE: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_exam_kheili_grade)],
        CHOOSING_EXAM_KHEILI_FIELD: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_exam_kheili_field)],

        CHOOSING_KONKUR_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_konkur_type)],
        CHOOSING_KONKUR_YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_konkur_year)],
        CHOOSING_KONKUR_SESSION: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_konkur_session)],
        CHOOSING_KONKUR_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_konkur_subject)],
        CHOOSING_KONKUR_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_konkur_action)],

        CHOOSING_EXAM_FINAL_ARCHIVE: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_final_exam_archive)],

        CHOOSING_EXAM_AHRAM_GRADE: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_exam_ahram_grade)],

        CHOOSING_DELIVERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_delivery)],
        CHOOSING_DELIVERY_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_delivery_location)],
        WAITING_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_address)],
        WAITING_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phone)],
        WAITING_RECEIPT: [MessageHandler(filters.ALL & ~filters.COMMAND, receive_receipt)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    name="order_conv",
    persistent=HAS_PERSISTENCE,
)
app.add_handler(order_conv)


# ---------------------------------------------------------------------------
# ثبت آزمون جدید توسط ادمین — داخل گروه و فقط برای ADMIN_IDS: /addexam
#
# نکته‌ی امنیتی: فیلترِ Chat فقط مشخص می‌کند دستور از کدام گروه پذیرفته شود.
# مجوز واقعی بر اساس Telegram user ID و در خودِ هندلر بررسی می‌شود
# (handlers._require_admin). این کار عمداً انجام شده تا کاربر غیرادمین به‌جای
# سکوت، پیام مناسب دریافت کند و هیچ اطلاعاتی افشا نشود.
# ============================ ترتیب اصلاح‌شده ============================
admin_exam_conv = ConversationHandler(
    entry_points=[
        CommandHandler("addexam", cmd_add_exam, filters=filters.Chat(chat_id=GROUP_ID))
    ],
    states={
        ADMIN_EXAM_PROVIDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_choose_provider)],
        ADMIN_EXAM_FIELD: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_choose_exam_field)],
        ADMIN_EXAM_GRADE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_choose_grade)],
        ADMIN_EXAM_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_choose_subject)],
        ADMIN_EXAM_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_date)],
        ADMIN_EXAM_QUESTION_FILE: [MessageHandler(filters.ALL & ~filters.COMMAND, admin_receive_question_file)],
        ADMIN_EXAM_ANSWER_FILE: [MessageHandler(filters.ALL & ~filters.COMMAND, admin_receive_answer_file)],
    },
    fallbacks=[CommandHandler("cancel", admin_cancel_exam)],
    name="admin_exam_conv",
    persistent=HAS_PERSISTENCE,
)
app.add_handler(admin_exam_conv)


# ---------------------------------------------------------------------------
# ثبت جزوه جدید توسط ادمین — داخل گروه و فقط برای ADMIN_IDS: /booklet
# ---------------------------------------------------------------------------
admin_booklet_conv = ConversationHandler(
    entry_points=[
        CommandHandler("booklet", cmd_add_booklet, filters=filters.Chat(chat_id=GROUP_ID))
    ],
    states={
        ADMIN_BOOKLET_TEACHER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_choose_booklet_teacher)],
        ADMIN_BOOKLET_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_choose_booklet_subject)],
        ADMIN_BOOKLET_GRADE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_choose_booklet_grade)],
        ADMIN_BOOKLET_CHAPTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_choose_booklet_chapter)],
        ADMIN_BOOKLET_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_booklet_title)],
        ADMIN_BOOKLET_VERSIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_choose_booklet_versions)],
    },
    fallbacks=[CommandHandler("cancel", admin_cancel_booklet)],
    name="admin_booklet_conv",
    persistent=HAS_PERSISTENCE,
)
app.add_handler(admin_booklet_conv)

# الگوی callback دکمه‌های مدیریت رسید — باید دقیقاً با فرمت‌های واقعی
# callback_data در handlers.py هم‌خوان باشد:
#   pay_confirm:{payment_id}
#   pay_reject:{payment_id}
#   pay_reject_reason:{reason}:{payment_id}
#   pay_stage_ready:{payment_id}[:{order_id}]
#   pay_stage_preparing:{payment_id}[:{order_id}]
#   pay_stage_done:{payment_id}[:{order_id}]
#
# نکته: reason یک کلید متنی است (مثل unreadable) نه عدد؛ الگوی قبلی برای همه‌ی
# شاخه‌ها \d+ می‌گذاشت، پس callbackهای «علت رد» هرگز به هندلر نمی‌رسیدند.
# فهرست reasonها با handlers.REJECT_REASON_* هم‌خوان است و در
# tests/test_pay_callback_regex.py بررسی می‌شود.
app.add_handler(
    CallbackQueryHandler(
        handle_receipt_callback,
        pattern=(
            r"^(?:"
            r"pay_confirm:\d+"
            r"|pay_reject:\d+"
            r"|pay_reject_reason:"
            r"(?:unreadable|invalid|low_amount|high_amount):\d+"
            r"|pay_stage_(?:ready|preparing|done):\d+(?::\d+)?"
            r")$"
        ),
    )
)


# ---------------------------------------------------------------------------
# پاک‌سازی خودکار conversation های گیرکرده در حافظه‌ی دائمی
#
# ریشه‌ی مشکل: اگر هندلری در یک ConversationHandler مقداری برگرداند که آن
# ConversationHandler هیچ هندلری برایش ندارد (مثلاً order_conv که حالت NAME=1
# registration را برمی‌گرداند)، آن کاربر برای همیشه در آن مرحله گیر می‌کند و
# هیچ پیامی هم جواب نمی‌گیرد.
#
# این تابع فقط وضعیت‌هایی را حذف می‌کند که «نامعتبر» هستند؛ وضعیت‌های معتبر
# (مثلاً WAITING_RECEIPT برای سفارش در جریان) و user_data (سبد، checkout)
# دست‌نخورده می‌مانند تا اطلاعات سفارش واقعی از دست نرود.
# ---------------------------------------------------------------------------

def sanitize_pickled_conversations(conversations: dict, allowed_states: dict,
                                   user_data: dict = None):
    """
    ورودی: conversations (همان دیکشنری داخل pickle) و نگاشت نام گفتگو -> حالت‌های مجاز.

    خروجی: (conversations پاک‌شده, فهرست کلیدهای حذف‌شده)
    """
    cleaned = {}
    removed = []

    for name, entries in conversations.items():
        if not isinstance(entries, dict):
            cleaned[name] = entries
            continue

        allowed = allowed_states.get(name)
        if allowed is None:
            # گفتگویی که اصلاً در برنامه ثبت نشده (مثلاً نسخه‌ی قدیمی‌تر ربات)
            cleaned[name] = {}
            removed.extend((name, key, state) for key, state in entries.items())
            continue

        kept = {}
        for key, state in entries.items():
            if state in allowed:
                kept[key] = state
            else:
                removed.append((name, key, state))
        cleaned[name] = kept

    # user_data اصلاً دست نمی‌خورد؛ این فقط برای اطمینان و برای تست است.
    if user_data is not None:
        assert isinstance(user_data, dict)

    return cleaned, removed


def sanitize_persistence_file(filepath, allowed_states, backup_suffix="_pre_repair"):
    """
    فایل pickle حافظه‌ی دائمی را می‌خواند، conversation های نامعتبر را حذف می‌کند
    و در صورت تغییر، از نسخه‌ی اصلی یک بک‌آپ می‌گیرد.

    هیچ خطایی نباید اجرای ربات را متوقف کند.
    """
    if not os.path.exists(filepath):
        return []

    try:
        with open(filepath, "rb") as fh:
            data = pickle.load(fh)
    except Exception as exc:
        print(f"⚠️ خواندن حافظه‌ی دائمی ناموفق بود (نادیده گرفته شد): {type(exc).__name__}")
        return []

    if not isinstance(data, dict) or not isinstance(data.get("conversations"), dict):
        return []

    cleaned, removed = sanitize_pickled_conversations(
        data["conversations"], allowed_states, user_data=data.get("user_data")
    )

    if not removed:
        return []

    data["conversations"] = cleaned

    backup = f"{filepath}{backup_suffix}.bak"
    try:
        shutil.copy2(filepath, backup)
    except OSError as exc:
        print(f"⚠️ بک‌آپ گرفتن از حافظه‌ی دائمی ناموفق بود: {type(exc).__name__}")

    try:
        with open(filepath, "wb") as fh:
            pickle.dump(data, fh)
    except Exception as exc:
        print(f"⚠️ ذخیره‌ی حافظه‌ی دائمی ناموفق بود: {type(exc).__name__}")
        return []

    for name, key, state in removed:
        user_part = key[-1] if isinstance(key, tuple) and key else "?"
        print(f"🧹 conversation گیرکرده پاک شد: {name} | user={user_part} | state={state}")

    return removed


def _collect_allowed_states() -> dict:
    """حالت‌های معتبر هر ConversationHandler را از خودِ هندلرها استخراج می‌کند."""
    return {
        "registration_conv": set(registration_conv.states.keys()),
        "order_conv": set(order_conv.states.keys()) | {ORDER_ENTRY},
        "admin_exam_conv": set(admin_exam_conv.states.keys()),
        "admin_booklet_conv": set(admin_booklet_conv.states.keys()),
    }


# پیش از ساخت اپلیکیشن، حافظه‌ی دائمی از conversation های نامعتبر پاک می‌شود.
# حالت‌های معتبر (سفارش در جریان، در انتظار فیش) حذف نمی‌شوند.
if os.path.exists("bot_persistence.pkl"):
    sanitize_persistence_file("bot_persistence.pkl", _collect_allowed_states())


# ---------------------------------------------------------------------------
# گزارش سفارش‌های یک روز — داخل گروه و فقط برای ADMIN_IDS
# /orders یا /orders 2026-07-26
# مجوز بر اساس Telegram user ID در handlers.cmd_orders بررسی می‌شود.
# ---------------------------------------------------------------------------
app.add_handler(
    CommandHandler("orders", cmd_orders, filters=filters.Chat(chat_id=GROUP_ID))
)

# ---------------------------------------------------------------------------
# لیست/خلاصه‌ی آزمون‌های ثبت‌شده — فقط داخل گروه: /examlist
# ---------------------------------------------------------------------------
app.add_handler(
    CommandHandler("examlist", cmd_exam_list, filters=filters.Chat(chat_id=GROUP_ID))
)

# ---------------------------------------------------------------------------
# پیگیری سفارش توسط خود مشتری — /myorders (توی چت خصوصی با ربات)
# ---------------------------------------------------------------------------
app.add_handler(CommandHandler("myorders", cmd_my_orders))

# ---------------------------------------------------------------------------
# اطلاع‌رسانی وقتی یه فصل قفل‌شده باز میشه — داخل گروه و فقط برای ADMIN_IDS
# /notify_available <استاد> <پایه> <فصل>
# مجوز بر اساس Telegram user ID در handlers.cmd_notify_available بررسی می‌شود.
# ---------------------------------------------------------------------------
app.add_handler(
    CommandHandler("notify_available", cmd_notify_available, filters=filters.Chat(chat_id=GROUP_ID))
)

# ---------------------------------------------------------------------------
# آمار ربات — فقط برای مالک ربات: /stats
# مجوز بر اساس Telegram user ID در handlers._require_owner بررسی می‌شود.
# ---------------------------------------------------------------------------
app.add_handler(CommandHandler("stats", cmd_stats))


# ---------------------------------------------------------------------------
# error handler سراسری
#
# هر استثنای مدیریت‌نشده‌ای اینجا می‌آید: کاربر یک پیام فارسیِ ساده می‌گیرد
# (بدون traceback و بدون جزئیات فنی) و جزئیات کامل فقط در لاگ سرور ثبت می‌شود.
# ---------------------------------------------------------------------------
app.add_error_handler(error_handler)


# ---------------------------------------------------------------------------
# جاب‌های زمان‌بندی‌شده
# نکته: ساعت‌ها بر اساس UTC هستن. تهران UTC+3:30 هست، پس مثلاً برای اجرا
# ساعت ۲۳:۵۹ به وقت تهران، باید عدد ساعت رو ۳٫۵ ساعت عقب‌تر (۲۰:۲۹ UTC) بذاری.
# ---------------------------------------------------------------------------
if app.job_queue is not None:
    # بک‌آپ روزانه‌ی دیتابیس — ساعت ۲۰:۲۹ UTC (= ۲۳:۵۹ به وقت تهران)
    app.job_queue.run_daily(daily_backup, time=time(hour=20, minute=29))

    # گزارش فروش پایان روز — همون موقع، چند دقیقه بعد از بک‌آپ
    app.job_queue.run_daily(daily_report, time=time(hour=20, minute=30))

    # چک کردن پرداخت‌های تاییدنشده — هر ۳۰ دقیقه یک‌بار
    app.job_queue.run_repeating(check_unconfirmed_payments, interval=1800, first=60)

    # پاک‌سازی سفارش‌های یتیم — هر ۶ ساعت، اولین اجرا ۵ دقیقه بعد از بالا آمدن ربات.
    # فقط سفارش‌های «پوسته‌ی خالی»: بدون پرداخت، بدون آیتم، بدون اطلاعات مشتری،
    # قدیمی‌تر از ۷۲ ساعت. سفارش‌های ۲ و ۳ هرگز حذف نمی‌شوند.
    # توجه: به‌صورت پیش‌فرض در حالت dry-run است (ORPHAN_CLEANUP_DRY_RUN).
    app.job_queue.run_repeating(cleanup_orphan_orders, interval=6 * 3600, first=300)

    # انقضای خودکار سفارش‌های بدون پرداخت — هر ۳۰ دقیقه، اولین اجرا ۶۰ ثانیه بعد از بالا آمدن.
    app.job_queue.run_repeating(expire_unpaid_orders_job, interval=1800, first=60)
else:
    print(
        "⚠️ JobQueue در دسترس نیست — برای فعال شدن بک‌آپ خودکار/گزارش روزانه/"
        "یادآوری پرداخت/پاک‌سازی سفارش‌های یتیم، این رو نصب کن:\n"
        "   pip install \"python-telegram-bot[job-queue]\""
    )


def main():
    """نقطه‌ی شروع ربات. جدا بودن این تابع باعث می‌شود ماژول قابل import باشد
    (برای تست‌ها) و فقط اجرای مستقیم، polling را شروع کند."""
    print("🤖 ربات چاپ آلما فعال شد...")

    app.run_polling(drop_pending_updates=DROP_PENDING_UPDATES)


if __name__ == "__main__":
    main()