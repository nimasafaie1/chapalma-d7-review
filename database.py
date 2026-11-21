import sqlite3
import re
from datetime import datetime, timedelta

DB_NAME = "orders.db"

# Persian month name to number mapping
_PERSIAN_MONTHS = {
    "فروردین": 1,
    "اردیبهشت": 2,
    "خرداد": 3,
    "تیر": 4,
    "مرداد": 5,
    "شهریور": 6,
    "مهر": 7,
    "آبان": 8,
    "آذر": 9,
    "دی": 10,
    "بهمن": 11,
    "اسفند": 12,
}

# Persian digits to English digits
_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_ENGLISH_DIGITS = "0123456789"
_DIGIT_TRANS = str.maketrans(_PERSIAN_DIGITS, _ENGLISH_DIGITS)


def _parse_persian_date(date_str: str):
    """
    Parse a Persian date string like '۱۸ آبان ۱۴۰۳' into (year, month, day) tuple.
    Returns (0, 0, 0) for invalid/empty dates so they sort to the end.
    """
    if not date_str or not isinstance(date_str, str):
        return (0, 0, 0)
    
    # Convert Persian digits to English
    date_str = date_str.translate(_DIGIT_TRANS).strip()
    
    # Expected format: "day month year" (e.g., "18 آبان 1403")
    parts = date_str.split()
    if len(parts) != 3:
        return (0, 0, 0)
    
    day_str, month_str, year_str = parts
    
    try:
        day = int(day_str)
        year = int(year_str)
    except ValueError:
        return (0, 0, 0)
    
    month = _PERSIAN_MONTHS.get(month_str)
    if month is None:
        return (0, 0, 0)
    
    return (year, month, day)


def _persian_date_sort_key(date_str: str):
    """
    Sort key for Persian dates: newest first (DESC).
    Invalid dates get (0, 0, 0) and sort to the end.
    """
    year, month, day = _parse_persian_date(date_str)
    # Negative for descending order
    return (-year, -month, -day)


def connect():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _add_column_if_missing(cursor, table, column, definition):
    cursor.execute(f"PRAGMA table_info({table})")
    existing = [row[1] for row in cursor.fetchall()]
    if column not in existing:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")



def _to_persian_digits(s: str) -> str:
    trans = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    return s.translate(trans)


def migrate_maz_exam_fields(conn):
    """
    Idempotent migration for Maz exams: normalize subject/date and fill field.
    Only provider='ماز'. No rows deleted; file_id/pages unchanged.
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, provider, subject, grade, exam_date, field FROM exams WHERE provider = ?",
        ("ماز",),
    )
    rows = cursor.fetchall()
    for row in rows:
        exam_id, provider, subject, grade, exam_date, field = row
        new_subject = subject or ""
        new_date = exam_date or ""
        new_field = field

        # a) strip grade suffix if not starting with آزمون جامع
        if new_subject and grade and not new_subject.startswith("آزمون جامع"):
            suffix = f" {grade}"
            if new_subject.endswith(suffix):
                new_subject = new_subject[: -len(suffix)]

        # b) normalize parsable Persian date to DD PersianMonth YYYY with Persian digits
        parsed = _parse_persian_date(new_date)
        if parsed != (0, 0, 0):
            y, m, d = parsed
            # find Persian month name by number
            month_name = None
            for name, num in _PERSIAN_MONTHS.items():
                if num == m:
                    month_name = name
                    break
            if month_name:
                new_date = _to_persian_digits(f"{d:02d}") + f" {month_name} " + _to_persian_digits(str(y))

        # c) fill field for non-jame rows where field is NULL
        if new_field is None and not (new_subject or "").startswith("آزمون جامع"):
            subj = (new_subject or "").strip()
            if subj == "زیست":
                new_field = "تجربی"
            elif subj in ("ریاضی", "فیزیک", "شیمی"):
                new_field = "ریاضی فیزیک,تجربی"

        if new_subject != subject or new_date != exam_date or new_field != field:
            cursor.execute(
                "UPDATE exams SET subject = ?, exam_date = ?, field = ? WHERE id = ?",
                (new_subject, new_date, new_field, exam_id),
            )
    conn.commit()


# وضعیت‌های بررسی رسید (payments.status)
PAYMENT_STATUS_WAITING = "در انتظار پرداخت"
PAYMENT_STATUS_WAITING_LOW_AMOUNT = "در انتظار فیش جدید به دلیل مبلغ کمتر"
PAYMENT_STATUS_WAITING_UNREADABLE = "در انتظار فیش جدید به دلیل ناخوانا بودن"
PAYMENT_STATUS_WAITING_INVALID = "در انتظار فیش جدید به دلیل نامعتبر بودن"
PAYMENT_STATUS_WAITING_HIGH_AMOUNT = "در انتظار فیش جدید به دلیل بیشتر بودن مبلغ واریزی"
PAYMENT_STATUS_CONFIRMED = "پرداخت تایید شد"

# وضعیت کل سفارش (orders.status) — برای کل سفارش مشترک است، نه هر آیتم جداگانه
ORDER_STATUS_WAITING_PAYMENT = "در انتظار پرداخت"
ORDER_STATUS_PAYMENT_CONFIRMED = "پرداخت تایید شد"
ORDER_STATUS_READY_HANDOVER = "آماده تحویل"
ORDER_STATUS_HANDOVER_DONE = "تحویل حضوری انجام شد"
ORDER_STATUS_PREPARING = "در حال آماده‌سازی"
ORDER_STATUS_SHIPPED = "ارسال شد"
ORDER_STATUS_EXPIRED = "منقضی شده"

# حداقل سن سفارش برای انقضای خودکار به دلیل عدم پرداخت (ساعت).
EXPIRY_ORDER_MIN_AGE_HOURS = 48

_VALID_DELIVERIES = {
    "تحویل حضوری",
    "ارسال به آموزشگاه پگاه و پویا",
    "ارسال به آدرس شخصی",
}


def _validate_delivery(delivery):
    if delivery not in _VALID_DELIVERIES:
        raise ValueError(f"روش تحویل نامعتبر: {delivery!r}")


_PAYMENT_RESUBMISSION_REASONS = {
    "مبلغ کمتر": PAYMENT_STATUS_WAITING_LOW_AMOUNT,
    "ناخوانا": PAYMENT_STATUS_WAITING_UNREADABLE,
    "نامعتبر": PAYMENT_STATUS_WAITING_INVALID,
    "amount": PAYMENT_STATUS_WAITING_LOW_AMOUNT,
    "unreadable": PAYMENT_STATUS_WAITING_UNREADABLE,
    "invalid": PAYMENT_STATUS_WAITING_INVALID,
}

# دلایل رد پرداخت که وضعیت اختصاصی در دیتابیس دارند.
_REJECT_REASON_TO_PAYMENT_STATUS = {
    "unreadable": PAYMENT_STATUS_WAITING_UNREADABLE,
    "invalid": PAYMENT_STATUS_WAITING_INVALID,
    "low_amount": PAYMENT_STATUS_WAITING_LOW_AMOUNT,
    "high_amount": PAYMENT_STATUS_WAITING_HIGH_AMOUNT,
}

_REJECT_REASON_KEYS = frozenset(
    {
        "unreadable",
        "invalid",
        "low_amount",
        "high_amount",
    }
)


def _reject_status_for_reason(reason_key):
    target = _REJECT_REASON_TO_PAYMENT_STATUS.get(reason_key)
    if target is not None:
        return target
    return f"رد شده: {reason_key}"


def _delivery_is_in_person(delivery):
    _validate_delivery(delivery)
    return delivery == "تحویل حضوری"


def _final_status_by_delivery(delivery):
    _validate_delivery(delivery)
    if _delivery_is_in_person(delivery):
        return ORDER_STATUS_HANDOVER_DONE
    return ORDER_STATUS_SHIPPED


def _pre_ship_allowed_statuses(delivery):
    _validate_delivery(delivery)
    if _delivery_is_in_person(delivery):
        return {ORDER_STATUS_PAYMENT_CONFIRMED, ORDER_STATUS_READY_HANDOVER}
    return {ORDER_STATUS_PAYMENT_CONFIRMED, ORDER_STATUS_PREPARING}


def create_tables():
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE,
        username TEXT,
        full_name TEXT,
        phone TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        teacher TEXT,
        grade TEXT,
        chapter TEXT,
        print_type TEXT,
        copies INTEGER,
        delivery TEXT,
        address TEXT,
        price INTEGER,
        pages INTEGER,
        file_name TEXT,
        phone TEXT,
        status TEXT DEFAULT 'در انتظار پرداخت',
        discount_code TEXT,
        discount_amount INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tracking_cases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL UNIQUE,
        user_id INTEGER,
        tracking_code TEXT NOT NULL UNIQUE,
        current_status TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE RESTRICT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tracking_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tracking_case_id INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        old_status TEXT,
        new_status TEXT,
        description TEXT,
        reason_code TEXT,
        actor_id INTEGER,
        payment_id INTEGER,
        idempotency_key TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tracking_case_id) REFERENCES tracking_cases(id) ON DELETE RESTRICT,
        UNIQUE(tracking_case_id, idempotency_key)
    )
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_tracking_events_case_created
    ON tracking_events (tracking_case_id, created_at, id)
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER,
        user_chat_id INTEGER,
        group_message_id INTEGER,
        confirmed INTEGER DEFAULT 0,
        shipped INTEGER DEFAULT 0,
        reminded INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    _add_column_if_missing(cursor, "payments", "group_chat_id", "INTEGER")
    _add_column_if_missing(cursor, "payments", "status", "TEXT DEFAULT 'Ø¯Ø± Ø§Ù†ØªØ¸Ø§Ø± Ù¾Ø±Ø¯Ø§Ø®Øª'")
    _add_column_if_missing(cursor, "payments", "rejected", "INTEGER DEFAULT 0")
    _add_column_if_missing(cursor, "payments", "rejected_by", "INTEGER")
    _add_column_if_missing(cursor, "payments", "rejected_reason", "TEXT")
    _add_column_if_missing(cursor, "payments", "rejected_at", "TIMESTAMP")
    _add_column_if_missing(cursor, "payments", "submission_uid", "TEXT")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_submission_uid ON payments(submission_uid) WHERE submission_uid IS NOT NULL")
    cursor.execute(
        "UPDATE payments SET status = ? WHERE confirmed = 1 AND status = ?",
        (PAYMENT_STATUS_CONFIRMED, PAYMENT_STATUS_WAITING),
    )
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_payments_group_lookup
        ON payments(group_chat_id, group_message_id)
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER,
        teacher TEXT,
        grade TEXT,
        chapter TEXT,
        print_type TEXT,
        price INTEGER,
        pages INTEGER,
        file_name TEXT,
        binding TEXT,
        quantity INTEGER DEFAULT 1
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS discount_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        percent INTEGER,
        amount INTEGER,
        active INTEGER DEFAULT 1,
        max_uses INTEGER,
        used_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chapter_interest (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        teacher TEXT,
        grade TEXT,
        chapter TEXT,
        notified INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS exams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider TEXT NOT NULL,
        subject TEXT NOT NULL,
        grade TEXT NOT NULL,
        exam_date TEXT NOT NULL,
        question_file_id TEXT,
        question_pages INTEGER,
        answer_file_id TEXT,
        answer_pages INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_exams_lookup ON exams(provider, subject, grade)
    """)

    # ================================================================
    # جدول جزوه‌ها (برای ثبت دستی توسط ادمین)
    # ================================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS booklets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        teacher TEXT NOT NULL,
        subject TEXT NOT NULL,
        grade TEXT NOT NULL,
        chapter TEXT NOT NULL,
        title TEXT NOT NULL,
        has_bw INTEGER DEFAULT 0,
        has_color INTEGER DEFAULT 0,
        price_bw INTEGER,
        price_color INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(teacher, subject, grade, chapter, title)
    )
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_booklets_lookup ON booklets(teacher, subject, grade, chapter)
    """)

    # ================================================================
    # میگریشن‌های ایمن برای کنکور سراسری
    # اگر ستون از قبل وجود داشته باشد، دوباره ایجاد نمی‌شود.
    # ================================================================
    _add_column_if_missing(cursor, "exams", "exam_type", "TEXT")
    _add_column_if_missing(cursor, "exams", "year", "TEXT")
    _add_column_if_missing(cursor, "exams", "session", "TEXT")


    # میگریشن‌های ایمن برای آرشیو جامع امتحان نهایی
    _add_column_if_missing(cursor, "exams", "year_from", "TEXT")
    _add_column_if_missing(cursor, "exams", "year_to", "TEXT")
    _add_column_if_missing(cursor, "exams", "is_archive", "INTEGER DEFAULT 0")
    _add_column_if_missing(cursor, "exams", "field", "TEXT")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS import_progress (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id INTEGER,
        message_id INTEGER,
        status TEXT,
        attempts INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(channel_id, message_id)
    )
    """)

    # ================================================================
    # جدول فعالیت کاربران — برای آمار DAU / MAU / کاربران جدید
    # actividad هر کاربر در هر روز فقط یک بار ثبت می‌شود (UNIQUE).
    # ================================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_activity (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER NOT NULL,
        activity_date TEXT NOT NULL,
        activity_type TEXT NOT NULL DEFAULT 'message',
        is_first_seen INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(telegram_id, activity_date, activity_type)
    )
    """)


    cursor.execute("""
    CREATE TABLE IF NOT EXISTS discount_usages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        code TEXT,
        order_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, code)
    )
    """)
    conn.commit()
    migrate_maz_exam_fields(conn)
    conn.close()


# ================================================================
# توابع کاربران
# ================================================================

def save_user(telegram_id, username, full_name, phone):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (telegram_id, username, full_name, phone)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET
            username = excluded.username,
            full_name = excluded.full_name,
            phone = excluded.phone
    """, (telegram_id, username, full_name, phone))
    conn.commit()
    conn.close()


def get_user(telegram_id):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    user = cursor.fetchone()
    conn.close()
    return user


def update_user_phone(telegram_id, phone):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET phone = ? WHERE telegram_id = ?", (phone, telegram_id))
    conn.commit()
    conn.close()


# ================================================================
# توابع آمار و فعالیت کاربران
# ================================================================

def get_local_date() -> str:
    """تاریخ امروز به صورت YYYY-MM-DD به وقت تهران."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Tehran")).strftime("%Y-%m-%d")
    except Exception:
        from datetime import timezone
        return datetime.now(timezone(timedelta(hours=3, minutes=30))).strftime("%Y-%m-%d")


def record_user_activity(telegram_id, activity_type="message"):
    """
    ثبت فعالیت یک کاربر در روز جاری.

    هر کاربر در هر روز و برای هر نوع فعالیت فقط یک بار شمارش می‌شود
    (به‌دلیل محدودیت UNIQUE). اجرای مکرر /start در یک روز کاربر را
    چند بار نمی‌شمارند.
    """
    today = get_local_date()
    conn = connect()
    cursor = conn.cursor()

    # آیا این کاربر قبلاً هرگونه فعالیت ثبت کرده باشد؟
    cursor.execute("SELECT 1 FROM user_activity WHERE telegram_id = ? LIMIT 1", (telegram_id,))
    ever_seen = cursor.fetchone() is not None

    cursor.execute("""
        INSERT OR IGNORE INTO user_activity (telegram_id, activity_date, activity_type, is_first_seen)
        VALUES (?, ?, ?, ?)
    """, (telegram_id, today, activity_type, 0 if ever_seen else 1))

    conn.commit()
    conn.close()


def count_total_users():
    """تعداد کل کاربران ثبت‌شده در جدول users."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def count_users_with_phone():
    """تعداد کاربران ثبت‌شده که شماره تلفن دارند."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users WHERE phone IS NOT NULL AND phone != ''")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def count_total_orders():
    """تعداد کل سفارش‌ها در جدول orders."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM orders")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def count_orders_by_status(status):
    """تعداد سفارش‌هایی که وضعیتشان برابر با `status` باشد."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM orders WHERE status = ?", (status,))
    count = cursor.fetchone()[0]
    conn.close()
    return count


def count_orders_today():
    """تعداد سفارش‌های ثبت‌شده امروز (بر اساس created_at)."""
    today = get_local_date()
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM orders WHERE date(created_at, '+3 hours', '+30 minutes') = ?", (today,))
    count = cursor.fetchone()[0]
    conn.close()
    return count


def count_dau(date_str=None):
    """
    Daily Active Users — تعداد کاربران فعال یک روز خاص (بر اساس telegram_id یکتا).
    """
    if date_str is None:
        date_str = get_local_date()
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(DISTINCT telegram_id) FROM user_activity WHERE activity_date = ?",
        (date_str,),
    )
    count = cursor.fetchone()[0]
    conn.close()
    return count


def count_mau(reference_date_str=None):
    """
    Monthly Active Users — تعداد کاربران فعال در ۳۰ روز گذشته (شامل روز مرجع).
    """
    if reference_date_str is None:
        reference_date_str = get_local_date()
    ref = datetime.strptime(reference_date_str, "%Y-%m-%d")
    start = (ref - timedelta(days=29)).strftime("%Y-%m-%d")
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT COUNT(DISTINCT telegram_id) FROM user_activity
        WHERE activity_date BETWEEN ? AND ?
        """,
        (start, reference_date_str),
    )
    count = cursor.fetchone()[0]
    conn.close()
    return count


def count_new_users(date_str=None):
    """
    تعداد کاربران جدید (اوّلین بار دیده‌شده) در یک روز خاص.
    این tally از tally کاربران فعال جدا نگه‌داشته می‌شود.
    """
    if date_str is None:
        date_str = get_local_date()
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM user_activity WHERE activity_date = ? AND is_first_seen = 1",
        (date_str,),
    )
    count = cursor.fetchone()[0]
    conn.close()
    return count


# ================================================================
# توابع سفارشات
# ================================================================

def save_order_with_items(user_id, items, delivery, address, phone, price,
                            discount_code=None, discount_amount=0):
    conn = connect()
    cursor = conn.cursor()
    try:
        final_price = price
        final_discount_code = None
        final_discount_amount = 0
        if discount_code:
            norm_code = normalize_discount_code(discount_code)
            if DISCOUNT_ONE_PER_USER:
                cursor.execute(
                    "SELECT 1 FROM discount_usages WHERE user_id = ? AND code = ?",
                    (user_id, norm_code)
                )
                if cursor.fetchone():
                    norm_code = None
            if norm_code:
                cursor.execute(
                    "UPDATE discount_codes SET used_count = used_count + 1 "
                    "WHERE lower(code)=lower(?) AND active=1 AND (max_uses IS NULL OR used_count < max_uses)",
                    (norm_code,)
                )
                if cursor.rowcount != 1:
                    norm_code = None
            if norm_code:
                final_discount_code = norm_code
                final_discount_amount = discount_amount or 0
            else:
                final_price = (price or 0) + (discount_amount or 0)
                final_discount_code = None
                final_discount_amount = 0
        else:
            final_price = price
            final_discount_code = None
            final_discount_amount = discount_amount or 0

        cursor.execute("""
            INSERT INTO orders
            (user_id, copies, delivery, address, price, phone, discount_code, discount_amount)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, len(items), delivery, address, final_price, phone, final_discount_code, final_discount_amount))

        order_id = cursor.lastrowid

        if final_discount_code and DISCOUNT_ONE_PER_USER:
            cursor.execute(
                "INSERT INTO discount_usages (user_id, code, order_id) VALUES (?, ?, ?)",
                (user_id, final_discount_code, order_id)
            )

        for item in items:
            cursor.execute("""
                INSERT INTO order_items
                (order_id, teacher, grade, chapter, print_type, price, pages, file_name, binding, quantity)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order_id,
                item.get("teacher"),
                item.get("grade"),
                item.get("chapter"),
                item.get("print_type"),
                item.get("price"),
                item.get("pages"),
                item.get("file_name"),
                item.get("binding"),
                item.get("quantity", 1),
            ))

        import uuid, sqlite3 as _sq
        for _attempt in range(5):
            tracking_code = "TRK-" + uuid.uuid4().hex[:12].upper()
            try:
                cursor.execute("""
                    INSERT INTO tracking_cases (order_id, user_id, tracking_code, current_status)
                    VALUES (?, ?, ?, ?)
                """, (order_id, user_id, tracking_code, "Ø¯Ø± Ø§Ù†ØªØ¸Ø§Ø± Ù¾Ø±Ø¯Ø§Ø®Øª"))
                tc_id = cursor.lastrowid
                cursor.execute("""
                    INSERT INTO tracking_events (tracking_case_id, event_type, new_status, description, idempotency_key)
                    VALUES (?, 'order_created', 'Ø¯Ø± Ø§Ù†ØªØ¸Ø§Ø± Ù¾Ø±Ø¯Ø§Ø®Øª', 'Order created', ?)
                """, (tc_id, f"order_created:{order_id}"))
                break
            except _sq.IntegrityError as e:
                if "tracking_code" in str(e).lower() or "unique" in str(e).lower():
                    if _attempt == 4:
                        raise
                    continue
                raise

        conn.commit()
        return order_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def save_payment(order_id, user_chat_id, group_message_id, group_chat_id=None, operation_type=None, submission_uid=None):
    if isinstance(order_id, (list, tuple)):
        order_id = ",".join(str(i) for i in order_id)
    if operation_type != "receipt_submitted":
        raise ValueError(f"Unsupported payment operation type: {operation_type!r}")
    if not submission_uid:
        raise ValueError("submission_uid is required for receipt_submitted")
    conn = connect()
    conn.isolation_level = None
    cur = conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        # idempotency: existing submission
        cur.execute("SELECT id FROM payments WHERE submission_uid = ?", (submission_uid,))
        row = cur.fetchone()
        if row is not None:
            cur.execute("COMMIT")
            return row[0]
        cur.execute("""
            INSERT INTO payments (order_id, user_chat_id, group_message_id, group_chat_id, submission_uid)
            VALUES (?, ?, ?, ?, ?)
        """, (order_id, user_chat_id, group_message_id, group_chat_id, submission_uid))
        payment_id = cur.lastrowid
        order_ids = [int(x) for x in str(order_id).split(",")] if str(order_id).strip() else []
        for oid in order_ids:
            cur.execute("SELECT status FROM orders WHERE id = ?", (oid,))
            orow = cur.fetchone()
            if orow is None:
                cur.execute("ROLLBACK")
                raise ValueError(f"سفارش #{oid} یافت نشد.")
            if orow[0] != ORDER_STATUS_WAITING_PAYMENT:
                cur.execute("ROLLBACK")
                raise ValueError(
                    f"ثبت فیش برای سفارش #{oid} در وضعیت «{orow[0]}» مجاز نیست."
                )
            tc = get_tracking_case_by_order(oid, conn)
            if tc is None:
                cur.execute("ROLLBACK")
                raise ValueError(f"Tracking Case برای سفارش #{oid} یافت نشد.")
            append_tracking_event(
                conn, tc["id"], "receipt_submitted",
                f"receipt_submitted:{submission_uid}",
                description="Receipt submitted", payment_id=payment_id,
            )
        cur.execute("COMMIT")
        return payment_id
    except Exception:
        try:
            cur.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def get_payment_by_group_message(group_message_id, group_chat_id=None):
    """
    رکورد پرداختِ مربوط به یک پیام گروه (فقط خواندن).

    اگر group_chat_id ارائه شود، جست‌وجو دقیق بر اساس (group_chat_id,
    group_message_id) انجام می‌شود (راه‌حل تداخل شماره پیام بین گروه‌های مختلف).
    در غیر این صورت رفتار قبلی حفظ می‌شود: جدیدترین رکورد با group_message_id
    مطابقت برمی‌گردد.
    """
    conn = connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if group_chat_id is not None:
        cursor.execute(
            "SELECT * FROM payments WHERE group_chat_id = ? AND group_message_id = ? ORDER BY id DESC LIMIT 1",
            (group_chat_id, group_message_id),
        )
    else:
        cursor.execute(
            "SELECT * FROM payments WHERE group_message_id = ? ORDER BY id DESC LIMIT 1",
            (group_message_id,),
        )
    payment = cursor.fetchone()
    conn.close()
    return payment


def get_payment_by_order(order_id):
    """
    جدیدترین رکورد پرداختِ ثبت‌شده برای یک سفارش (فقط خواندن).

    برای این استفاده می‌شود که اگر کاربر فیش را دوباره بفرستد، وضعیت آخرین
    رسید بررسی شود (نه رسید رد‌شدهٔ قدیمی‌تر). ترتیب نزولی است تا «تأیید
    رسید جدید» به‌درستی دیده شود و رسید سوم پس از تأیید رسید دوم ساخته نشود.

    توجه: order_id ممکن است چند شماره با کاما باشد، پس با الگوی متنی بررسی می‌شود.
    """
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM payments WHERE ',' || order_id || ',' LIKE ? ORDER BY id DESC LIMIT 1",
        (f"%,{order_id},%",)
    )
    payment = cursor.fetchone()
    conn.close()
    return payment


def get_order(order_id):
    """یک سفارش را با شناسه برمی‌گرداند (فقط خواندن) یا در صورت نبود None."""
    conn = connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    row = cursor.fetchone()
    conn.close()
    return row


def confirm_payment(payment_id):
    conn = connect()
    conn.isolation_level = None
    cur = conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        cur.execute("SELECT status, rejected, order_id FROM payments WHERE id = ?", (payment_id,))
        row = cur.fetchone()
        if row is None:
            cur.execute("ROLLBACK")
            raise ValueError(f"پرداخت #{payment_id} یافت نشد.")
        pstatus, rejected, order_id_raw = row
        if rejected == 1:
            cur.execute("ROLLBACK")
            raise ValueError(
                f"پرداخت #{payment_id} قبلاً رد شده است؛ تأیید آن مجاز نیست."
            )
        if pstatus == PAYMENT_STATUS_CONFIRMED:
            cur.execute("COMMIT")
            return {"payment_id": payment_id, "order_ids": [], "already_confirmed": True}
        if pstatus != PAYMENT_STATUS_WAITING:
            cur.execute("ROLLBACK")
            raise ValueError(
                f"تأیید پرداخت فقط از وضعیت «{PAYMENT_STATUS_WAITING}» مجاز است (جاری: «{pstatus}»)."
            )
        order_ids = [int(x) for x in str(order_id_raw).split(",")] if order_id_raw else []
        for oid in order_ids:
            cur.execute("SELECT status FROM orders WHERE id = ?", (oid,))
            orow = cur.fetchone()
            if orow is None:
                cur.execute("ROLLBACK")
                raise ValueError(f"سفارش #{oid} یافت نشد.")
            ostatus = orow[0]
            if ostatus == ORDER_STATUS_PAYMENT_CONFIRMED:
                continue
            if ostatus != ORDER_STATUS_WAITING_PAYMENT:
                cur.execute("ROLLBACK")
                raise ValueError(
                    f"انتقال غیرمجاز وضعیت سفارش #{oid} از «{ostatus}» به «{ORDER_STATUS_PAYMENT_CONFIRMED}»."
                )
            cur.execute(
                "UPDATE orders SET status = ? WHERE id = ?",
                (ORDER_STATUS_PAYMENT_CONFIRMED, oid),
            )
            tc = get_tracking_case_by_order(oid, conn)
            if tc is None:
                cur.execute("ROLLBACK")
                raise ValueError(f"Tracking Case برای سفارش #{oid} یافت نشد.")
            append_tracking_event(
                conn, tc["id"], "payment_confirmed",
                f"payment_confirmed:{payment_id}",
                old_status=ostatus, new_status=ORDER_STATUS_PAYMENT_CONFIRMED,
                description="Payment confirmed", payment_id=payment_id,
            )
            cur.execute(
                "UPDATE tracking_cases SET current_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (ORDER_STATUS_PAYMENT_CONFIRMED, tc["id"]),
            )
        cur.execute(
            "UPDATE payments SET status = ?, confirmed = 1 WHERE id = ?",
            (PAYMENT_STATUS_CONFIRMED, payment_id),
        )
        cur.execute("COMMIT")
        return {"payment_id": payment_id, "order_ids": order_ids, "already_confirmed": False}
    except Exception:
        try:
            cur.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def mark_order_shipped(payment_id):
    conn = connect()
    conn.isolation_level = None
    cur = conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        cur.execute("SELECT status, order_id FROM payments WHERE id = ?", (payment_id,))
        row = cur.fetchone()
        if row is None:
            cur.execute("ROLLBACK")
            raise ValueError(f"پرداخت #{payment_id} یافت نشد.")
        pstatus, order_id_raw = row
        if pstatus != PAYMENT_STATUS_CONFIRMED:
            cur.execute("ROLLBACK")
            raise ValueError(
                f"ارسال سفارش فقط بعد از تایید پرداخت مجاز است (جاری: «{pstatus}»)."
            )
        order_ids = [int(x) for x in str(order_id_raw).split(",")] if order_id_raw else []
        shipped_order_ids = []
        for oid in order_ids:
            cur.execute("SELECT status, delivery FROM orders WHERE id = ?", (oid,))
            orow = cur.fetchone()
            if orow is None:
                cur.execute("ROLLBACK")
                raise ValueError(f"سفارش #{oid} یافت نشد.")
            ostatus, delivery = orow
            target = _final_status_by_delivery(delivery)
            if ostatus == target:
                continue
            if _delivery_is_in_person(delivery):
                required = ORDER_STATUS_READY_HANDOVER
            else:
                required = ORDER_STATUS_PREPARING
            if ostatus != required:
                cur.execute("ROLLBACK")
                raise ValueError(
                    f"انتقال غیرمجاز وضعیت سفارش #{oid} از «{ostatus}» به «{target}»."
                )
            cur.execute(
                "UPDATE orders SET status = ? WHERE id = ?",
                (target, oid),
            )
            tc = get_tracking_case_by_order(oid, conn)
            if tc is None:
                cur.execute("ROLLBACK")
                raise ValueError(f"Tracking Case برای سفارش #{oid} یافت نشد.")
            event_type = "handover_done" if _delivery_is_in_person(delivery) else "shipped"
            old_status = required
            append_tracking_event(
                conn, tc["id"], event_type,
                f"{event_type}:{oid}:{old_status}->{target}",
                old_status=old_status, new_status=target,
                description="Order shipped/handover", payment_id=payment_id,
            )
            cur.execute(
                "UPDATE tracking_cases SET current_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (target, tc["id"]),
            )
            shipped_order_ids.append(oid)
        cur.execute("UPDATE payments SET shipped = 1 WHERE id = ?", (payment_id,))
        cur.execute("COMMIT")
        return {
            "payment_id": payment_id,
            "order_ids": order_ids,
            "shipped_order_ids": shipped_order_ids,
        }
    except Exception:
        try:
            cur.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


_ALLOWED_PAYMENT_TRANSITIONS = {
    PAYMENT_STATUS_WAITING: {
        PAYMENT_STATUS_CONFIRMED,
        PAYMENT_STATUS_WAITING_LOW_AMOUNT,
        PAYMENT_STATUS_WAITING_UNREADABLE,
        PAYMENT_STATUS_WAITING_INVALID,
        PAYMENT_STATUS_WAITING_HIGH_AMOUNT,
    },
    PAYMENT_STATUS_WAITING_LOW_AMOUNT: {PAYMENT_STATUS_CONFIRMED},
    PAYMENT_STATUS_WAITING_UNREADABLE: {PAYMENT_STATUS_CONFIRMED},
    PAYMENT_STATUS_WAITING_INVALID: {PAYMENT_STATUS_CONFIRMED},
    PAYMENT_STATUS_WAITING_HIGH_AMOUNT: {PAYMENT_STATUS_CONFIRMED},
    PAYMENT_STATUS_CONFIRMED: {PAYMENT_STATUS_CONFIRMED},
}


def record_review_result(payment_id, new_status):
    _all_payment_statuses = {
        PAYMENT_STATUS_WAITING,
        PAYMENT_STATUS_WAITING_LOW_AMOUNT,
        PAYMENT_STATUS_WAITING_UNREADABLE,
        PAYMENT_STATUS_WAITING_INVALID,
        PAYMENT_STATUS_WAITING_HIGH_AMOUNT,
        PAYMENT_STATUS_CONFIRMED,
    }
    if new_status not in _all_payment_statuses:
        raise ValueError(f"وضعیت پرداخت نامعتبر: {new_status}")
    conn = connect()
    conn.isolation_level = None
    cur = conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        cur.execute(
            "SELECT status, rejected, order_id FROM payments WHERE id = ?", (payment_id,)
        )
        row = cur.fetchone()
        if row is None:
            cur.execute("ROLLBACK")
            raise ValueError(f"پرداخت #{payment_id} یافت نشد.")
        old_status, rejected, order_id_raw = row
        if rejected == 1:
            cur.execute("ROLLBACK")
            raise ValueError(
                f"پرداخت #{payment_id} رد شده است؛ تغییر وضعیت آن مجاز نیست."
            )
        if new_status == old_status:
            cur.execute("COMMIT")
            return {"payment_id": payment_id, "status": new_status, "changed": False}
        allowed = _ALLOWED_PAYMENT_TRANSITIONS.get(old_status, set())
        if new_status not in allowed:
            cur.execute("ROLLBACK")
            raise ValueError(
                f"انتقال غیرمجاز وضعیت پرداخت از «{old_status}» به «{new_status}»."
            )
        changed = new_status != old_status
        if new_status == PAYMENT_STATUS_CONFIRMED:
            cur.execute(
                "UPDATE payments SET status = ?, confirmed = 1 WHERE id = ?",
                (new_status, payment_id),
            )
        else:
            cur.execute("UPDATE payments SET status = ? WHERE id = ?", (new_status, payment_id))
        if changed and new_status == PAYMENT_STATUS_CONFIRMED:
            order_ids = [int(x) for x in str(order_id_raw).split(",")] if order_id_raw else []
            for oid in order_ids:
                cur.execute("SELECT status FROM orders WHERE id = ?", (oid,))
                orow = cur.fetchone()
                if orow is None:
                    cur.execute("ROLLBACK")
                    raise ValueError(f"سفارش #{oid} یافت نشد.")
                ostatus = orow[0]
                if ostatus == ORDER_STATUS_PAYMENT_CONFIRMED:
                    continue
                if ostatus != ORDER_STATUS_WAITING_PAYMENT:
                    cur.execute("ROLLBACK")
                    raise ValueError(
                        f"هم‌سازی غیرمجاز وضعیت سفارش #{oid} از «{ostatus}»."
                    )
                cur.execute(
                    "UPDATE orders SET status = ? WHERE id = ?",
                    (ORDER_STATUS_PAYMENT_CONFIRMED, oid),
                )
        if changed and new_status != PAYMENT_STATUS_CONFIRMED:
            order_ids = [int(x) for x in str(order_id_raw).split(",")] if order_id_raw else []
            for oid in order_ids:
                tc = get_tracking_case_by_order(oid, conn)
                if tc is None:
                    cur.execute("ROLLBACK")
                    raise ValueError(f"Tracking Case برای سفارش #{oid} یافت نشد.")
                append_tracking_event(
                    conn, tc["id"], "review_result",
                    f"review_result:{payment_id}:{old_status}->{new_status}",
                    old_status=old_status, new_status=new_status,
                    description="Payment review result", payment_id=payment_id,
                )
        if changed and new_status == PAYMENT_STATUS_CONFIRMED:
            order_ids = [int(x) for x in str(order_id_raw).split(",")] if order_id_raw else []
            for oid in order_ids:
                tc = get_tracking_case_by_order(oid, conn)
                if tc is None:
                    cur.execute("ROLLBACK")
                    raise ValueError(f"Tracking Case برای سفارش #{oid} یافت نشد.")
                append_tracking_event(
                    conn, tc["id"], "review_result",
                    f"review_result:{payment_id}:{old_status}->{new_status}",
                    old_status=old_status, new_status=new_status,
                    description="Payment review result", payment_id=payment_id,
                )
                cur.execute(
                    "UPDATE tracking_cases SET current_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (ORDER_STATUS_PAYMENT_CONFIRMED, tc["id"]),
                )
        cur.execute("COMMIT")
        return {"payment_id": payment_id, "status": new_status, "changed": changed}
    except Exception:
        try:
            cur.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def request_resubmission(payment_id, reason):
    target = _PAYMENT_RESUBMISSION_REASONS.get(reason)
    if target is None:
        raise ValueError(f"علت درخواست رسید نامعتبر: {reason}")
    return record_review_result(payment_id, target)


def reject_payment(payment_id, reason_key, admin_id=None):
    """ثبت اتمیک رد پرداخت.

    تمام فیلدهای وضعیت/رد در یک تراکنش نوشته می‌شوند:
      status، rejected، rejected_by، rejected_reason، rejected_at.

    خروجی:
      {"payment_id", "changed", "reason", "status", "rejected_reason"}
      reason ∈ {"rejected", "already_rejected", "already_confirmed",
                "already_processed"}

    فقط فراخوانی‌ای که changed=True برگرداند، برندهٔ واقعی است و اجازه دارد پیام
    مشتری را ارسال کند. هیچ فراخوانی شبکه‌ای داخل تراکنش انجام نمی‌شود.
    """
    if reason_key not in _REJECT_REASON_KEYS:
        raise ValueError(f"علت رد نامعتبر: {reason_key!r}")

    conn = connect()
    conn.isolation_level = None
    cur = conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        cur.execute(
            "SELECT status, rejected, rejected_reason, order_id FROM payments WHERE id = ?",
            (payment_id,),
        )
        row = cur.fetchone()
        if row is None:
            cur.execute("ROLLBACK")
            raise ValueError(f"پرداخت #{payment_id} یافت نشد.")
        old_status, rejected, old_reason, order_id_raw = row

        if rejected == 1:
            cur.execute("COMMIT")
            return {
                "payment_id": payment_id,
                "changed": False,
                "reason": "already_rejected",
                "status": old_status,
                "rejected_reason": old_reason,
            }

        if old_status == PAYMENT_STATUS_CONFIRMED:
            cur.execute("COMMIT")
            return {
                "payment_id": payment_id,
                "changed": False,
                "reason": "already_confirmed",
                "status": old_status,
                "rejected_reason": old_reason,
            }

        if old_status != PAYMENT_STATUS_WAITING:
            cur.execute("COMMIT")
            return {
                "payment_id": payment_id,
                "changed": False,
                "reason": "already_processed",
                "status": old_status,
                "rejected_reason": old_reason,
            }

        # صحت همهٔ سفارش‌های مرتبط بررسی می‌شود (پرداخت چندسفارشی)؛ هیچ
        # تغییری در وضعیت سفارش‌ها داده نمی‌شود، چون رد به معنای لغو سفارش نیست.
        order_ids = (
            [int(x) for x in str(order_id_raw).split(",")] if order_id_raw else []
        )
        for oid in order_ids:
            cur.execute("SELECT status FROM orders WHERE id = ?", (oid,))
            if cur.fetchone() is None:
                cur.execute("ROLLBACK")
                raise ValueError(f"سفارش #{oid} یافت نشد.")

        new_status = _reject_status_for_reason(reason_key)

        cur.execute(
            "UPDATE payments SET status = ?, rejected = 1, rejected_by = ?, "
            "rejected_reason = ?, rejected_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND rejected = 0 AND status = ?",
            (new_status, admin_id, reason_key, payment_id, PAYMENT_STATUS_WAITING),
        )
        if cur.rowcount != 1:
            cur.execute("ROLLBACK")
            return {
                "payment_id": payment_id,
                "changed": False,
                "reason": "already_processed",
                "status": old_status,
                "rejected_reason": old_reason,
            }

        for oid in order_ids:
            tc = get_tracking_case_by_order(oid, conn)
            if tc is None:
                cur.execute("ROLLBACK")
                raise ValueError(f"Tracking Case برای سفارش #{oid} یافت نشد.")
            append_tracking_event(
                conn, tc["id"], "payment_rejected",
                f"payment_rejected:{payment_id}:{reason_key}",
                old_status=old_status, new_status=new_status,
                description="Payment rejected", reason_code=reason_key,
                payment_id=payment_id,
            )

        cur.execute("COMMIT")
        return {
            "payment_id": payment_id,
            "changed": True,
            "reason": "rejected",
            "status": new_status,
            "rejected_reason": reason_key,
        }
    except Exception:
        try:
            cur.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def advance_order_to_next_stage(order_id):
    conn = connect()
    conn.isolation_level = None
    cur = conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        cur.execute("SELECT status, delivery FROM orders WHERE id = ?", (order_id,))
        row = cur.fetchone()
        if row is None:
            cur.execute("ROLLBACK")
            raise ValueError(f"سفارش #{order_id} یافت نشد.")
        ostatus, delivery = row
        if ostatus == ORDER_STATUS_WAITING_PAYMENT:
            cur.execute("ROLLBACK")
            raise ValueError("انتقال مرحله‌ی بعدی سفارش فقط بعد از تایید پرداخت مجاز است.")
        if ostatus == ORDER_STATUS_PAYMENT_CONFIRMED:
            nxt = ORDER_STATUS_READY_HANDOVER if _delivery_is_in_person(delivery) else ORDER_STATUS_PREPARING
        elif ostatus == ORDER_STATUS_READY_HANDOVER:
            nxt = ORDER_STATUS_HANDOVER_DONE
        elif ostatus == ORDER_STATUS_PREPARING:
            nxt = ORDER_STATUS_SHIPPED
        elif ostatus in (ORDER_STATUS_HANDOVER_DONE, ORDER_STATUS_SHIPPED):
            cur.execute("COMMIT")
            return {"order_id": order_id, "status": ostatus, "changed": False}
        else:
            cur.execute("ROLLBACK")
            raise ValueError(f"انتقال غیرمجاز از وضعیت «{ostatus}».")
        cur.execute("UPDATE orders SET status = ? WHERE id = ?", (nxt, order_id))
        if ostatus == ORDER_STATUS_PAYMENT_CONFIRMED:
            tc = get_tracking_case_by_order(order_id, conn)
            if tc is None:
                cur.execute("ROLLBACK")
                raise ValueError(f"Tracking Case برای سفارش #{order_id} یافت نشد.")
            event_type = "ready_for_pickup" if _delivery_is_in_person(delivery) else "preparation_started"
            append_tracking_event(
                conn, tc["id"], event_type,
                f"stage:{order_id}:{ostatus}->{nxt}",
                old_status=ostatus, new_status=nxt,
                description="Order stage advanced", 
            )
            cur.execute(
                "UPDATE tracking_cases SET current_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (nxt, tc["id"]),
            )
        cur.execute("COMMIT")
        return {"order_id": order_id, "status": nxt, "changed": True}
    except Exception:
        try:
            cur.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


# ================================================================
# توابع آزمون‌ها
# ================================================================

def save_exam(provider, subject, grade, exam_date,
              question_file_id=None, question_pages=None,
              answer_file_id=None, answer_pages=None,
              field=None):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO exams
        (provider, subject, grade, exam_date, question_file_id, question_pages,
         answer_file_id, answer_pages, field)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (provider, subject, grade, exam_date, question_file_id, question_pages,
          answer_file_id, answer_pages, field))
    exam_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return exam_id


def get_exam_id_by_details(provider, subject, grade, exam_date):
    conn = connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, question_file_id, question_pages FROM exams
        WHERE provider = ? AND subject = ? AND grade = ? AND exam_date = ?
        ORDER BY id DESC LIMIT 1
    """, (provider, subject, grade, exam_date))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_exam_file_id(exam_id, question_file_id, question_pages):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE exams SET question_file_id = ?, question_pages = ?
        WHERE id = ?
    """, (question_file_id, question_pages, exam_id))
    conn.commit()
    conn.close()


def get_exam_dates(provider, subject, grade):
    """
    همه‌ی تاریخ‌های ثبت‌شده برای یک ترکیب، بدون حذف تکراری.

    این تابع عمداً خام باقی مانده (بدون DISTINCT) چون برای گزارش‌ها و
    بررسی‌های داده به همه‌ی رکوردها نیاز است.
    مرتب‌سازی بر اساس تاریخ شمسی (جدیدترین اول)، و برای تاریخ‌های یکسان بر اساس ID نزولی.
    """
    conn = connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, exam_date FROM exams
        WHERE provider = ? AND subject = ? AND grade = ?
    """, (provider, subject, grade))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()

    # Sort by Persian date (newest first), then by ID DESC for tiebreaking
    rows.sort(key=lambda r: (_persian_date_sort_key(r["exam_date"]), -r["id"]))
    return rows


def get_unique_exam_dates(provider, subject, grade):
    """
    تاریخ‌های یکتا برای نمایش به کاربر.

    چرا این تابع لازم است:
        در دیتابیس برای بعضی تاریخ‌ها بیش از یک رکورد وجود دارد (مثلاً واردکردن
        دوباره‌ی همان آزمون از کانال). چون get_exam_dates ترتیب «id DESC» دارد،
        برای یک تاریخِ تکراری دکمه‌ی یکسان چند بار ساخته می‌شد و کاربر چند
        دکمه‌ی هم‌نام می‌دید.

    این تابع فقط در «نمایش» تکراری‌ها را یکی می‌کند و هیچ داده‌ای را حذف یا
    ادغام نمی‌کند.

    انتخاب اینکه کدام رکورد برای تاریخ تکراری نمایش داده شود:
        دقیقاً همان رکوردی که منطق قبلی انتخاب می‌کرد، یعنی بالاترین id
        (جدیدترین رکورد). با این کار رفتار انتخابِ کاربر دقیقاً مثل قبل
        می‌ماند و فقط دکمه‌ی تکراری از کیبورد حذف می‌شود.

        توجه: اگر دو رکورد یک تاریخ، فایل‌های متفاوتی داشته باشند، این تابع
        نمی‌تواند تشخیص دهد کدام فایل «درست» است؛ این تصمیم داده‌ای است و
        باید جداگانه و با تأیید مالک داده گرفته شود.

    خروجی: دیکشنری‌های {id, exam_date, duplicate_ids}
        duplicate_ids فهرست id رکوردهای هم‌تاریخِ پنهان‌شده است (برای گزارش).
    مرتب‌سازی بر اساس تاریخ شمسی (جدیدترین اول).

    اگر subject = None باشد، فیلتر فقط بر اساس provider و grade اعمال
    می‌شود (برای مسیر آرمان که مستقیماً پایه را انتخاب می‌کند).
    """
    conn = connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if subject is None:
        cursor.execute("""
            SELECT id, exam_date FROM exams
            WHERE provider = ? AND grade = ?
        """, (provider, grade))
    else:
        cursor.execute("""
            SELECT id, exam_date FROM exams
            WHERE provider = ? AND subject = ? AND grade = ?
        """, (provider, subject, grade))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    # Sort by Persian date (newest first), then by ID DESC for tiebreaking
    rows.sort(key=lambda r: (_persian_date_sort_key(r["exam_date"]), -r["id"]))

    result = []
    seen = {}

    for row in rows:
        exam_date = row["exam_date"]
        if exam_date in seen:
            seen[exam_date]["duplicate_ids"].append(row["id"])
            continue
        entry = {"id": row["id"], "exam_date": exam_date, "duplicate_ids": []}
        seen[exam_date] = entry
        result.append(entry)

    return result


def get_maz_exams_by_field(field, grade):
    """
    Maz doping exams for given field and grade (excluding any subject that starts
    with 'آزمون جامع'). Field match is exact after comma split (supports combined
    values like 'ریاضی فیزیک,تجربی'). Dedupe by (subject, parsed date) keeping
    highest id. Sorted by newest parsed date first. Returns list of dicts with id,
    subject, exam_date, label.
    """
    conn = connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, subject, exam_date, field FROM exams
        WHERE provider = ? AND grade = ?
    """, ("ماز", grade))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    target = (field or "").strip()
    target_parts = [p.strip() for p in target.split(",") if p.strip()]
    if not target_parts:
        return []
    filtered = []
    for r in rows:
        subj = r.get("subject") or ""
        if subj.startswith("آزمون جامع"):
            continue
        fval = r.get("field") or ""
        parts = [p.strip() for p in fval.split(",") if p.strip()]
        if any(tp in parts for tp in target_parts):
            filtered.append(r)

    filtered.sort(key=lambda r: (-int(r["id"]),))
    seen = {}
    deduped = []
    for r in filtered:
        key = (r.get("subject") or "", _parse_persian_date(r.get("exam_date") or ""))
        if key in seen:
            continue
        seen[key] = True
        deduped.append(r)

    # _persian_date_sort_key already returns negatives for DESC; do NOT reverse.
    deduped.sort(key=lambda r: (_persian_date_sort_key(r.get("exam_date") or ""), -int(r["id"])))

    out = []
    for r in deduped:
        subj = r.get("subject") or ""
        dt = r.get("exam_date") or ""
        out.append({
            "id": r["id"],
            "subject": subj,
            "exam_date": dt,
            "label": f"{subj} — {dt}",
        })
    return out



def get_exam(exam_id):
    conn = connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM exams WHERE id = ?", (exam_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# ================================================================
# توابع کنکور سراسری
# ================================================================

def get_konkur_exam(exam_type, year, session, subject):
    """
    رکورد آزمون کنکور سراسری را بر اساس ترکیب زیر پیدا می‌کند.
    - exam_type: داخلی یا خارجی
    - year: سال (مثلاً ۱۴۰۴)
    - session: '1' یا '2' یا None
    - subject: ریاضی / تجربی / انسانی
    """
    conn = connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if session:
        cursor.execute("""
            SELECT * FROM exams
            WHERE provider = 'کنکور سراسری'
              AND exam_type = ?
              AND year = ?
              AND session = ?
              AND subject = ?
            ORDER BY id DESC LIMIT 1
        """, (exam_type, year, session, subject))
    else:
        cursor.execute("""
            SELECT * FROM exams
            WHERE provider = 'کنکور سراسری'
              AND exam_type = ?
              AND year = ?
              AND session IS NULL
              AND subject = ?
            ORDER BY id DESC LIMIT 1
        """, (exam_type, year, subject))

    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_konkur_years(exam_type):
    """
    لیست سال‌های کنکور سراسری که در دیتابیس برای یک نوع (داخلی/خارجی) ثبت شده‌اند.
    """
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT year FROM exams
        WHERE provider = 'کنکور سراسری'
          AND exam_type = ?
          AND year IS NOT NULL
        ORDER BY CAST(year AS INTEGER) DESC
    """, (exam_type,))
    rows = [row[0] for row in cursor.fetchall()]
    conn.close()
    return rows


def get_konkur_sessions(exam_type, year):
    """
    لیست نوبت‌های موجود برای یک ترکیب نوع + سال.
    خروجی: لیست رشته‌های نوبت ('1' یا '2') — اگر فقط نوبتی بدون session NULL داشته باشد.
    """
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT session FROM exams
        WHERE provider = 'کنکور سراسری'
          AND exam_type = ?
          AND year = ?
          AND session IS NOT NULL
        ORDER BY CAST(session AS INTEGER) ASC
    """, (exam_type, year))
    rows = [row[0] for row in cursor.fetchall()]
    conn.close()
    return rows


def save_konkur_exam(exam_type, year, session, subject,
                     question_file_id=None, question_pages=None,
                     answer_file_id=None, answer_pages=None,
                     exam_date=None):
    """
    ثبت آزمون کنکور سراسری جدید.
    """
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO exams
        (provider, subject, grade, exam_date, exam_type, year, session,
         question_file_id, question_pages, answer_file_id, answer_pages)
        VALUES ('کنکور سراسری', ?, '-', ?, ?, ?, ?, ?, ?, ?, ?)
    """, (subject, exam_date or '', exam_type, year, session,
          question_file_id, question_pages, answer_file_id, answer_pages))
    exam_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return exam_id


def update_konkur_question_file(exam_id, question_file_id, question_pages):
    """
    به‌روزرسانی file_id و صفحات دفترچه سؤال برای رکورد کنکور.
    """
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE exams
        SET question_file_id = ?, question_pages = ?
        WHERE id = ?
    """, (question_file_id, question_pages, exam_id))
    conn.commit()
    conn.close()


def update_konkur_answer_file(exam_id, answer_file_id, answer_pages):
    """
    به‌روزرسانی file_id و صفحات کلیدنامه برای رکورد کنکور.
    """
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE exams
        SET answer_file_id = ?, answer_pages = ?
        WHERE id = ?
    """, (answer_file_id, answer_pages, exam_id))
    conn.commit()
    conn.close()


def update_konkur_file(exam_id, file_type, file_id, pages):
    """
    به‌روزرسانی یک فایل (سوال یا پاسخ) برای رکورد کنکور.
    file_type: 'question' یا 'answer'
    """
    if file_type == 'question':
        update_konkur_question_file(exam_id, file_id, pages)
    else:
        update_konkur_answer_file(exam_id, file_id, pages)



def exam_exists(provider, subject, grade, exam_date):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM exams
        WHERE provider = ? AND subject = ? AND grade = ? AND exam_date = ?
    """, (provider, subject, grade, exam_date))
    row = cursor.fetchone()
    conn.close()
    return row is not None


def get_all_exams():
    conn = connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM exams ORDER BY provider, subject, grade, id")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]



def get_final_exam_archive(subject):
    """
    پیدا کردن رکورد آرشیو جامع امتحان نهایی برای یک درس خاص.
    فقط رکوردی برمی‌گرداند که:
      provider = 'نهایی'
      grade = 'دوازدهم'
      subject = subject
      is_archive = 1
    """
    conn = connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM exams
        WHERE provider = 'نهایی'
          AND grade = 'دوازدهم'
          AND subject = ?
          AND is_archive = 1
        ORDER BY id DESC LIMIT 1
    """, (subject,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_exam_coverage_summary():
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT provider, subject, grade, COUNT(*)
        FROM exams GROUP BY provider, subject, grade
    """)
    counts = {(row[0], row[1], row[2]): row[3] for row in cursor.fetchall()}
    conn.close()
    return counts


# ================================================================
# توابع جزوه‌ها (برای ثبت دستی توسط ادمین)
# ================================================================

def save_booklet(teacher, subject, grade, chapter, title, has_bw, has_color, price_bw=None, price_color=None):
    """ذخیره جزوه جدید در دیتابیس."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO booklets
        (teacher, subject, grade, chapter, title, has_bw, has_color, price_bw, price_color)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (teacher, subject, grade, chapter, title, int(has_bw), int(has_color), price_bw, price_color))
    booklet_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return booklet_id


def booklet_exists(teacher, subject, grade, chapter, title):
    """بررسی وجود جزوه تکراری."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM booklets
        WHERE teacher = ? AND subject = ? AND grade = ? AND chapter = ? AND title = ?
    """, (teacher, subject, grade, chapter, title))
    row = cursor.fetchone()
    conn.close()
    return row is not None


def get_booklets_by_teacher_grade_chapter(teacher, grade, chapter):
    """دریافت جزوه‌های یک ترکیب استاد/پایه/فصل."""
    conn = connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM booklets
        WHERE teacher = ? AND grade = ? AND chapter = ?
        ORDER BY id
    """, (teacher, grade, chapter))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_booklet_price(teacher, grade, chapter, color):
    """
    دریافت قیمت جزوه از دیتابیس.
    اگر در دیتابیس نباشد، None برمی‌گرداند (برای fallback به JOZVE_PRICES).
    """
    conn = connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if color == "رنگی":
        cursor.execute("""
            SELECT price_color FROM booklets
            WHERE teacher = ? AND grade = ? AND chapter = ? AND has_color = 1
            ORDER BY id DESC LIMIT 1
        """, (teacher, grade, chapter))
    else:
        cursor.execute("""
            SELECT price_bw FROM booklets
            WHERE teacher = ? AND grade = ? AND chapter = ? AND has_bw = 1
            ORDER BY id DESC LIMIT 1
        """, (teacher, grade, chapter))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row and row[0] is not None else None


def get_booklet_options(teacher, grade, chapter):
    """
    دریافت گزینه‌های موجود برای یک ترکیب (سیاه‌وسفید/رنگی).
    برمی‌گرداند لیست تاپل‌های (color, price, label).
    """
    options = []
    # Check DB for registered booklets
    booklets = get_booklets_by_teacher_grade_chapter(teacher, grade, chapter)
    for b in booklets:
        if b.get("has_bw") and b.get("price_bw"):
            options.append(("سیاه‌وسفید", b["price_bw"], f"سیاه‌وسفید — {b['price_bw']:,} تومان".replace(",", "٬")))
        if b.get("has_color") and b.get("price_color"):
            options.append(("رنگی", b["price_color"], f"رنگی — {b['price_color']:,} تومان".replace(",", "٬")))
    return options


# ================================================================
# توابع کد تخفیف
# ================================================================

DISCOUNT_ONE_PER_USER = False


def normalize_discount_code(code):
    if code is None:
        return ""
    text = str(code).strip().casefold()
    persian = "۰۱۲۳۴۵۶۷۸۹"
    arabic = "٠١٢٣٤٥٦٧٨٩"
    trans = {ord(p): str(i) for i, p in enumerate(persian)}
    trans.update({ord(a): str(i) for i, a in enumerate(arabic)})
    return text.translate(trans)

def get_discount_code(code):
    normalized = normalize_discount_code(code)
    conn = connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM discount_codes WHERE lower(code) = lower(?) AND active = 1",
        (normalized,)
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    row = dict(row)
    if row["max_uses"] is not None and row["used_count"] >= row["max_uses"]:
        return None
    row["code"] = normalized
    return row


def increment_discount_usage(code):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("UPDATE discount_codes SET used_count = used_count + 1 WHERE code = ?", (code,))
    conn.commit()
    conn.close()


def add_discount_code(code, percent=None, amount=None, max_uses=None):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO discount_codes (code, percent, amount, max_uses)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET
            percent = excluded.percent,
            amount = excluded.amount,
            max_uses = excluded.max_uses,
            active = 1
    """, (code, percent, amount, max_uses))
    conn.commit()
    conn.close()


def deactivate_discount_code(code):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("UPDATE discount_codes SET active = 0 WHERE code = ?", (code,))
    conn.commit()
    conn.close()


# ================================================================
# توابع علاقه‌مندی به فصل‌ها
# ================================================================

def save_chapter_interest(user_id, teacher, grade, chapter):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO chapter_interest (user_id, teacher, grade, chapter)
        VALUES (?, ?, ?, ?)
    """, (user_id, teacher, grade, chapter))
    conn.commit()
    conn.close()


def get_uninotified_interest(teacher, grade, chapter):
    conn = connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM chapter_interest
        WHERE teacher = ? AND grade = ? AND chapter = ? AND notified = 0
    """, (teacher, grade, chapter))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def mark_interest_notified(ids):
    if not ids:
        return
    conn = connect()
    cursor = conn.cursor()
    placeholders = ",".join("?" for _ in ids)
    cursor.execute(f"UPDATE chapter_interest SET notified = 1 WHERE id IN ({placeholders})", ids)
    conn.commit()
    conn.close()


# ================================================================
# توابع سفارشات کاربر
# ================================================================

def get_orders_by_user(telegram_id, limit=5):
    conn = connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM orders
        WHERE user_id = ? ORDER BY id DESC LIMIT ?
    """, (telegram_id, limit))
    order_rows = cursor.fetchall()
    results = []
    for row in order_rows:
        cursor.execute("SELECT * FROM order_items WHERE order_id = ?", (row["id"],))
        items = cursor.fetchall()
        results.append({
            "order": dict(row),
            "items": [dict(item) for item in items],
        })
    conn.close()
    return results


# ================================================================
# توابع پرداخت‌های تاییدنشده
# ================================================================

def get_unconfirmed_payments_older_than(hours):
    conn = connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    # پرداخت‌های رد‌شده (rejected=1) هرگز در یادآوری «تأیید نشده» نباید بیایند؛
    # آن‌ها منتظر رسید جدید هستند، نه تأیید ادمین.
    cursor.execute("""
        SELECT * FROM payments
        WHERE confirmed = 0 AND reminded = 0
        AND COALESCE(rejected, 0) = 0
        AND datetime(created_at) <= datetime('now', ?)
    """, (f"-{hours} hours",))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def mark_payment_reminded(payment_id):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("UPDATE payments SET reminded = 1 WHERE id = ?", (payment_id,))
    conn.commit()
    conn.close()


# ================================================================
# پاک‌سازی سفارش‌های یتیم (سفارش بدون پرداخت)
#
# «یتیمِ قابل حذف» یعنی سفارشی که **همه‌ی** شرط‌های زیر را داشته باشد:
#   ۱) وضعیتش «در انتظار پرداخت» باشد،
#   ۲) از حداقل سن مشخص‌شده (پیش‌فرض ۷۲ ساعت) قدیمی‌تر باشد،
#   ۳) هیچ رکورد پرداختی نداشته باشد (حتی confirmed=0 هم پرداخت محسوب می‌شود)،
#   ۴) هیچ آیتمی در order_items نداشته باشد  ← محافظ اصلیِ سفارش واقعی مشتری،
#   ۵) هیچ اطلاعات مشتری/سفارشی نداشته باشد (تلفن، آدرس، شیوه‌ی ارسال،
#      مبلغ، تعداد، نام فایل، صفحه، کد تخفیف) ← یعنی یک پوسته‌ی خالی و بی‌مصرف،
#   ۶) شناسه‌اش در PROTECTED_ORDER_IDS نباشد.
#
# نتیجه: هر سفارشی که واقعاً اطلاعاتی از مشتری دارد (حتی اگر پرداخت نکرده باشد)
# هرگز صرفاً به دلیل «پرداخت‌نشدن» حذف نمی‌شود.
# ================================================================

WAITING_PAYMENT_STATUS = "در انتظار پرداخت"

# سفارش‌هایی که تحت هیچ شرایطی نباید حذف شوند (سفارش‌های واقعی مشتریان).
PROTECTED_ORDER_IDS = (2, 3)


def _protected_ids_clause(alias="o"):
    """بخش SQL که سفارش‌های محافظت‌شده را از نامزدها حذف می‌کند."""
    if not PROTECTED_ORDER_IDS:
        return ""
    ids = ", ".join(str(int(i)) for i in PROTECTED_ORDER_IDS)
    return f"AND {alias}.id NOT IN ({ids})\n          "


def _orphan_orders_where(hours):
    """
    شرط مشترک نامزدهای پاک‌سازی.

    تطبیق order_id با الگوی کاما-دار انجام می‌شود، چون payments.order_id از نظر
    ساختار می‌تواند چند شماره سفارش را با کاما نگه دارد.
    """
    return f"""
        WHERE o.status = '{WAITING_PAYMENT_STATUS}'
          AND datetime(o.created_at) <= datetime('now', ?)
          {_protected_ids_clause("o")}
          AND NOT EXISTS (
              SELECT 1 FROM payments p
              WHERE ',' || p.order_id || ',' LIKE '%,' || o.id || ',%'
          )
          AND NOT EXISTS (
              SELECT 1 FROM order_items oi WHERE oi.order_id = o.id
          )
          AND COALESCE(o.phone, '') = ''
          AND COALESCE(o.address, '') = ''
          AND COALESCE(o.delivery, '') = ''
          AND COALESCE(o.file_name, '') = ''
          AND COALESCE(o.discount_code, '') = ''
          AND COALESCE(o.discount_amount, 0) = 0
          AND COALESCE(o.price, 0) = 0
          AND COALESCE(o.pages, 0) = 0
          AND COALESCE(o.copies, 0) = 0
    """


def get_orphan_orders_older_than(hours):
    """
    فهرست سفارش‌های یتیمِ قدیمی — فقط خواندن، برای dry-run و گزارش.
    خروجی: دیکشنری‌هایی با کلیدهای id / user_id / created_at / price /
    discount_code / discount_amount / copies
    """
    conn = connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        f"""SELECT o.id, o.user_id, o.created_at, o.price, o.discount_code,
                   o.discount_amount, o.copies
            FROM orders o
            {_orphan_orders_where(hours)}
            ORDER BY o.id ASC""",
        (f"-{int(hours)} hours",)
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def delete_order_if_orphan(order_id, hours):
    """
    حذف شرطی و اتمیک یک سفارش یتیمِ «خالی».

    شرط‌ها داخل خودِ DELETE تکرار می‌شوند تا اگر در فاصله‌ی «شناسایی نامزد» تا
    «حذف»، پرداختی ثبت شده یا وضعیت سفارش عوض شده باشد، چیزی حذف نشود.

    نکته‌ی مهم: شرط‌های سخت‌گیرانه‌ی _orphan_orders_where (نداشتن آیتم و نداشتن
    اطلاعات مشتری) عیناً داخل DELETE هم آمده‌اند، پس حتی اگر این تابع مستقیم و
    با شماره‌ی سفارش صدا زده شود، سفارش واقعی مشتری حذف نمی‌شود.

    خروجی: dict(id=..., deleted=bool, reason=str)
    """
    conn = connect()
    cursor = conn.cursor()

    try:
        cursor.execute(
            f"""DELETE FROM orders AS o
                WHERE o.id = ?
                  AND o.status = '{WAITING_PAYMENT_STATUS}'
                  AND datetime(o.created_at) <= datetime('now', ?)
                  {_protected_ids_clause("o")}
                  AND NOT EXISTS (
                      SELECT 1 FROM payments p
                      WHERE ',' || p.order_id || ',' LIKE '%,' || o.id || ',%'
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM order_items oi WHERE oi.order_id = o.id
                  )
                  AND COALESCE(o.phone, '') = ''
                  AND COALESCE(o.address, '') = ''
                  AND COALESCE(o.delivery, '') = ''
                  AND COALESCE(o.file_name, '') = ''
                  AND COALESCE(o.discount_code, '') = ''
                  AND COALESCE(o.discount_amount, 0) = 0
                  AND COALESCE(o.price, 0) = 0
                  AND COALESCE(o.pages, 0) = 0
                  AND COALESCE(o.copies, 0) = 0""",
            (order_id, f"-{int(hours)} hours")
        )
        deleted = cursor.rowcount > 0

        if deleted:
            cursor.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
            reason = "deleted"
        else:
            reason = "skipped_not_orphan"

        conn.commit()
        return {"id": order_id, "deleted": deleted, "reason": reason}

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def expire_unpaid_orders(hours=EXPIRY_ORDER_MIN_AGE_HOURS):
    """
    انقضای اتمیک سفارش‌های بدون پرداخت که قدیمی‌تر از `hours` ساعت هستند.

    شرایط انقضا (همه باید در همین تراکنش برقرار باشند):
      ۱) وضعیت سفارش «در انتظار پرداخت» باشد،
      ۲) قدیمی‌تر از `hours` ساعت باشد،
      ۳) هیچ رکوردی در جدول payments برای آن سفارش نداشته باشد،
      ۴) سفارش قبلاً منقضی یا لغو نشده باشد (وضعیت غیر از انتظار پرداخت).

    بررسی شرایط و تغییر وضعیت در یک تراکنش BEGIN IMMEDIATE انجام می‌شود، به‌طوری
    که فقط یک تراکنش می‌تواند بنویسند و دیگران تا committing شدن منتظر می‌مانند.
    ثبت فیش یا تأیید پرداخت هم‌زمان با این جاب نمی‌تواند سفارش را از وضعیت
    انتظار پرداخت خارج کند؛ چرا داخل همین تراکنش عدم وجود پرداخت دوباره
    بررسی می‌شود.

    یک خطا در یک سفارش (مثلاً وجود نداشتن Tracking case) آن سفارش را متوقف
    می‌کند و بقیه سفارش‌ها پردازش می‌شوند؛ تغییرات هر سفارش در همین تراکنش
    ذخیره و در ادامه سفارش‌های بعدی پردازش می‌شود.

    خروجی: {
        "expired": [order_id, ...],
        "errors": [(order_id, error_msg), ...],
        "skipped": [order_id, ...],
        "count": int,
    }
    """
    conn = connect()
    conn.isolation_level = None
    cur = conn.cursor()
    expired = []
    errors = []
    skipped = []
    try:
        cur.execute("BEGIN IMMEDIATE")
        cur.execute(
            f"""
            SELECT o.id, o.user_id, o.created_at
            FROM orders o
            WHERE o.status = ?
              AND datetime(o.created_at) <= datetime('now', ?)
              AND NOT EXISTS (
                  SELECT 1 FROM payments p
                  WHERE ',' || p.order_id || ',' LIKE '%,' || o.id || ',%'
              )
            ORDER BY o.id ASC
            """,
            (ORDER_STATUS_WAITING_PAYMENT, f"-{int(hours)} hours"),
        )
        candidates = cur.fetchall()

        for order_id, user_id, created_at in candidates:
            # بررسی مجدد داخل همین تراکنش: پرداخت ممکن است بین شناسایی
            # nominatedها و اینجا توسط تراکنش دیگری ثبت شده باشد.
            cur.execute(
                "SELECT 1 FROM payments p "
                "WHERE ',' || p.order_id || ',' LIKE '%,' || ? || ',%'",
                (order_id,),
            )
            if cur.fetchone() is not None:
                skipped.append(order_id)
                continue

            # وضعیت را دوباره تأکید می‌کنیم (داخل همین تراکنش تغییر نگرفته است).
            cur.execute("SELECT status FROM orders WHERE id = ?", (order_id,))
            orow = cur.fetchone()
            if orow is None or orow[0] != ORDER_STATUS_WAITING_PAYMENT:
                skipped.append(order_id)
                continue

            tc = get_tracking_case_by_order(order_id, conn)
            if tc is None:
                errors.append((order_id, "tracking case not found"))
                continue

            cur.execute(
                "UPDATE orders SET status = ? WHERE id = ? AND status = ?",
                (ORDER_STATUS_EXPIRED, order_id, ORDER_STATUS_WAITING_PAYMENT),
            )
            if cur.rowcount != 1:
                skipped.append(order_id)
                continue

            cur.execute(
                "UPDATE tracking_cases SET current_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (ORDER_STATUS_EXPIRED, tc["id"]),
            )

            append_tracking_event(
                conn,
                tc["id"],
                "expired",
                f"expired:{order_id}",
                old_status=ORDER_STATUS_WAITING_PAYMENT,
                new_status=ORDER_STATUS_EXPIRED,
                description="Order expired: unpaid for 48 hours",
            )
            expired.append(order_id)

        cur.execute("COMMIT")
    except Exception:
        try:
            cur.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()

    return {
        "expired": expired,
        "errors": errors,
        "skipped": skipped,
        "count": len(expired),
    }


# ================================================================
# توابع واردات از کانال
# ================================================================

def get_processed_message_ids(channel_id):
    """
    برگرداندن پیام‌های واقعاً پردازش‌شده (نه پیام‌هایی که قابل تلاش مجدّد هستند).
    
    فقط پیام‌هایی با status='imported' یا 'duplicate' به عنوان پردازش‌شده در نظر گرفته می‌شوند.
    پیام‌های 'parse_failed'، 'not_found' و 'network_retry' دوباره قابل پردازش هستند.
    """
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT message_id FROM import_progress "
        "WHERE channel_id = ? AND status IN ('imported', 'duplicate')",
        (channel_id,)
    )
    ids = {row[0] for row in cursor.fetchall()}
    conn.close()
    return ids


def mark_message_processed(channel_id, message_id, status):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO import_progress (channel_id, message_id, status)
        VALUES (?, ?, ?)
        ON CONFLICT(channel_id, message_id) DO UPDATE SET status = excluded.status
    """, (channel_id, message_id, status))
    conn.commit()
    conn.close()


def record_network_failure(channel_id, message_id):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO import_progress (channel_id, message_id, status, attempts)
        VALUES (?, ?, 'network_retry', 1)
        ON CONFLICT(channel_id, message_id) DO UPDATE SET
            attempts = attempts + 1
    """, (channel_id, message_id))
    cursor.execute(
        "SELECT attempts FROM import_progress WHERE channel_id = ? AND message_id = ?",
        (channel_id, message_id)
    )
    attempts = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return attempts


def get_orders_by_date(date_str):
    conn = connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT orders.*, users.full_name, users.phone AS reg_phone, users.username
        FROM orders
        LEFT JOIN users ON users.telegram_id = orders.user_id
        WHERE date(orders.created_at, '+3 hours', '+30 minutes') = ?
        ORDER BY orders.id ASC
    """, (date_str,))
    order_rows = cursor.fetchall()
    results = []
    for row in order_rows:
        cursor.execute("SELECT * FROM order_items WHERE order_id = ?", (row["id"],))
        items = cursor.fetchall()
        results.append({
            "order": dict(row),
            "items": [dict(item) for item in items],
        })
    conn.close()
    return results


def get_order_items(order_id):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
    items = cursor.fetchall()
    conn.close()
    return items


def save_order(user_id, teacher, grade, chapter, print_type, delivery, address,
                price=None, pages=None, file_name=None, phone=None):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO orders
        (user_id, teacher, grade, chapter, print_type, copies, delivery, address,
         price, pages, file_name, phone)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, teacher, grade, chapter, print_type, 1, delivery, address,
          price, pages, file_name, phone))
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return order_id


def get_tracking_case_by_order(order_id, conn):
    cur = conn.cursor()
    cur.execute("SELECT id, tracking_code, current_status FROM tracking_cases WHERE order_id = ?", (order_id,))
    row = cur.fetchone()
    if row is None:
        return None
    return {"id": row[0], "tracking_code": row[1], "current_status": row[2]}


def append_tracking_event(conn, tracking_case_id, event_type, idempotency_key,
                          old_status=None, new_status=None, description=None,
                          reason_code=None, actor_id=None, payment_id=None):
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO tracking_events
            (tracking_case_id, event_type, old_status, new_status, description,
             reason_code, actor_id, payment_id, idempotency_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (tracking_case_id, event_type, old_status, new_status, description,
              reason_code, actor_id, payment_id, idempotency_key))
        return cur.lastrowid
    except sqlite3.IntegrityError as e:
        msg = str(e).lower()
        if "unique" in msg and "idempotency" in msg:
            cur.execute("""
                SELECT id, event_type, old_status, new_status, description,
                       reason_code, actor_id, payment_id
                FROM tracking_events
                WHERE tracking_case_id = ? AND idempotency_key = ?
            """, (tracking_case_id, idempotency_key))
            existing = cur.fetchone()
            if existing is not None and existing[1] == event_type:
                return existing[0]
            raise
        raise
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tracking_cases WHERE tracking_code = ?", (tracking_code,))
    row = cur.fetchone()
    if row is None:
        conn.close()
        return None
    columns = [d[0] for d in cur.description]
    case = dict(zip(columns, row))
    cur.execute("SELECT * FROM tracking_events WHERE tracking_case_id = ? ORDER BY created_at, id", (case["id"],))
    cols = [d[0] for d in cur.description]
    case["events"] = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return case
