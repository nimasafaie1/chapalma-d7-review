"""
جدول قیمت‌ها.
هر عدد به تومان است.
"""

# --------------------------------------------------------------------------
# قیمت چاپ برای «جزوه دلخواه» (فایلی که خود کاربر آپلود می‌کند)
# --------------------------------------------------------------------------
CUSTOM_PRINT_PRICES = {
    ("رنگی", "پشت‌ورو"): 13500,
    ("رنگی", "تک‌رو"): 10000,
    ("سیاه‌وسفید", "پشت‌ورو"): 7500,
    ("سیاه‌وسفید", "تک‌رو"): 5000,
}

DELIVERY_FEE = 50000
# --------------------------------------------------------------------------
# صحافی
# --------------------------------------------------------------------------
BINDING_PAGE_THRESHOLD = 150
BINDING_SPIRAL_PRICE_NORMAL = 100000
BINDING_SPIRAL_PRICE_LARGE = 150000
BINDING_STAPLE_PRICE = 0


def get_binding_options(pages: int):
    if pages and pages > BINDING_PAGE_THRESHOLD:
        return [
            ("صحافی سیمی", BINDING_SPIRAL_PRICE_LARGE),
            ("بدون صحافی", 0),
        ]
    return [
        ("صحافی سیمی", BINDING_SPIRAL_PRICE_NORMAL),
        ("منگنه", BINDING_STAPLE_PRICE),
        ("بدون صحافی", 0),
    ]


TEACHERS = ["امامی", "کوشکی", "نظری"]
GRADES = ["دهم", "یازدهم", "دوازدهم"]
CHAPTERS = ["فصل ۱", "فصل ۲", "فصل ۳"]

# --------------------------------------------------------------------------
# آزمون‌ها (قلمچی / ماز / امتحان نهایی)
# --------------------------------------------------------------------------
EXAM_PROVIDERS = ["قلمچی", "ماز", "امتحان نهایی", "خیلی سبز", "آرمان"]

# درس‌های عمومی برای قلمچی و امتحان نهایی
EXAM_SUBJECTS = ["تجربی", "ریاضی", "انسانی"]

# ================================================================
# 📚 درس‌های اختصاصی ماز (دوپینگ)
# ================================================================

MAZ_SUBJECTS = {
    "دهم": ["ریاضی دهم", "فیزیک دهم", "زیست دهم", "زمین دهم", "شیمی دهم", "آزمون جامع دهم"],
    "یازدهم": ["ریاضی یازدهم", "فیزیک یازدهم", "زیست یازدهم", "شیمی یازدهم", "آزمون جامع یازدهم"],
    "دوازدهم": ["ریاضی دوازدهم", "فیزیک دوازدهم", "زیست دوازدهم", "شیمی دوازدهم", "آزمون جامع دوازدهم"],
}

# ================================================================
# امتحان نهایی
# ================================================================

FINAL_EXAM_PROVIDER_DB = "نهایی"
FINAL_EXAM_PROVIDER_DISPLAY = "امتحان نهایی"
FINAL_EXAM_PROVIDER = FINAL_EXAM_PROVIDER_DISPLAY
FINAL_EXAM_GRADE = "دوازدهم"
FINAL_EXAM_SUBJECTS = ["ریاضی", "تجربی", "انسانی", "هنر", "زبان"]

FINAL_EXAM_PROVIDER_MAP = {
    "امتحان نهایی": "نهایی",
    "نهایی": "نهایی",
}

# دروس آرشیو جامع امتحان نهایی (هر درس یک PDF جامع چندساله)
FINAL_EXAM_ARCHIVE_SUBJECTS = [
    "انگلیسی ۳",
    "فارسی ۳",
    "فیزیک ۳",
    "گسسته",
    "هندسه ۳",
    "ریاضی ۳",
    "ریاضی و آمار ۳",
    "شیمی ۳",
    "تاریخ ۳",
    "زیست‌شناسی ۳",
]

FINAL_EXAM_ARCHIVE_BUTTON = "📚 آرشیو جامع امتحان نهایی"


def get_exam_subjects(provider: str, grade: str = None):
    """لیست درس‌های موجود برای یک مؤسسه‌ی آزمون را برمی‌گرداند."""
    if provider == "ماز" and grade:
        return MAZ_SUBJECTS.get(grade, [])
    if provider in FINAL_EXAM_PROVIDER_MAP:
        return FINAL_EXAM_SUBJECTS
    return EXAM_SUBJECTS


def is_final_exam_provider(provider: str) -> bool:
    return provider in FINAL_EXAM_PROVIDER_MAP


# ================================================================
# کنکور سراسری
# ================================================================

KONKUR_PROVIDER = "کنکور سراسری"
KONKUR_TYPES = ["داخلی", "خارجی"]
KONKUR_SUBJECTS = ["ریاضی", "تجربی", "انسانی"]
KONKUR_SESSIONS = ["نوبت اول", "نوبت دوم"]

# سال‌هایی که در آرشیو وجود دارند (فقط برای محدودیت اولیه)
KONKUR_YEARS = ["1400", "1401", "1402", "1403", "1404"]

# سال‌هایی که نوبت ندارند
KONKUR_NO_SESSION_YEARS = ["1400", "1401"]

# سال‌هایی که نوبت دارند (فقط داخلی)
KONKUR_SESSION_YEARS = ["1402", "1403", "1404"]


def get_konkur_sessions(exam_type, year):
    """
    لیست نوبت‌های موجود برای یک ترکیب نوع + سال.
    - داخلی ۱۴۰۰ و ۱۴۰۱: نوبت ندارد → []
    - داخلی ۱۴۰۲ به بعد: نوبت دارد → ["نوبت اول", "نوبت دوم"]
    - خارجی: نوبت ندارد → []
    """
    if exam_type == KONKUR_TYPES[0] and year in KONKUR_SESSION_YEARS:
        return list(KONKUR_SESSIONS)
    return []


def get_konkur_session_value(label):
    """تبدیل برچسب نوبت به مقدار دیتابیسی."""
    return {
        "نوبت اول": "1",
        "نوبت دوم": "2",
    }.get(label)


def get_konkur_session_label(value):
    """تبدیل مقدار دیتابیسی به برچسب نمایشی."""
    return {
        "1": "نوبت اول",
        "2": "نوبت دوم",
    }.get(value, value)


def get_final_exam_provider_db(display_name: str) -> str:
    return FINAL_EXAM_PROVIDER_MAP.get(display_name, display_name)


def get_exam_print_price_per_page(side: str = "پشت‌ورو"):
    return 7000


def _empty_grade():
    return {chapter: None for chapter in CHAPTERS}


def _empty_teacher():
    return {grade: _empty_grade() for grade in GRADES}


# --------------------------------------------------------------------------
# قیمت جزوه‌های آماده
# --------------------------------------------------------------------------
JOZVE_PRICES = {teacher: _empty_teacher() for teacher in TEACHERS}

JOZVE_PRICES["امامی"]["دهم"]["فصل ۱"] = {"رنگی": 620000, "سیاه‌وسفید": 410000}
JOZVE_PRICES["امامی"]["دهم"]["فصل ۳"] = {"رنگی": 555000, "سیاه‌وسفید": 355000}
JOZVE_PRICES["امامی"]["دهم"]["فصل ۲"] = {"رنگی": 655000, "سیاه‌وسفید": 415000}
JOZVE_PRICES["امامی"]["یازدهم"]["فصل ۱"] = {"رنگی": 1100000, "سیاه‌وسفید": 650000}
JOZVE_PRICES["امامی"]["دوازدهم"]["فصل ۱"] = {"رنگی": 780000, "سیاه‌وسفید": 540000}
JOZVE_PRICES["امامی"]["دوازدهم"]["فصل ۲"] = {"رنگی": 800000, "سیاه‌وسفید": 450000}


def get_jozve_price(teacher: str, grade: str, chapter: str, color: str):
    # First check database for admin-registered booklets
    from database import get_booklet_price
    db_price = get_booklet_price(teacher, grade, chapter, color)
    if db_price is not None:
        return db_price
    
    # Fallback to hardcoded JOZVE_PRICES
    try:
        prices = JOZVE_PRICES[teacher][grade][chapter]
    except KeyError:
        return None
    if not prices:
        return None
    return prices.get(color)


def is_chapter_available(teacher: str, grade: str, chapter: str) -> bool:
    # First check database for admin-registered booklets
    from database import get_booklets_by_teacher_grade_chapter
    booklets = get_booklets_by_teacher_grade_chapter(teacher, grade, chapter)
    if booklets:
        return True
    
    # Fallback to hardcoded JOZVE_PRICES
    try:
        prices = JOZVE_PRICES[teacher][grade][chapter]
    except KeyError:
        return False
    return bool(prices)


def get_custom_print_price(color: str, side: str):
    return CUSTOM_PRINT_PRICES[(color, side)]


def get_delivery_fee():
    return DELIVERY_FEE


def format_price_persian(price):
    if price is None:
        return "هماهنگی با ادمین"
    formatted = f"{price:,}".replace(",", "٬")
    return f"{_to_persian_digits(formatted)} تومان"


def _to_persian_digits(value: str) -> str:
    mapping = str.maketrans({
        "0": "۰", "1": "۱", "2": "۲", "3": "۳", "4": "۴",
        "5": "۵", "6": "۶", "7": "۷", "8": "۸", "9": "۹"
    })
    return value.translate(mapping)


def get_delivery_location_labels(teacher=None):
    if teacher == "امامی" or teacher is None:
        return [
            f"🏫 ارسال به آموزشگاه پگاه و پویا ({format_price_persian(get_delivery_fee())} هزینه ارسال)",
            "🏠 ارسال به آدرس شخصی (هزینه ارسال با خود شماست)",
        ]
    return ["🏠 ارسال به آدرس شخصی (هزینه ارسال با خود شماست)"]


def format_price(price):
    if price is None:
        return "هماهنگی با ادمین"
    return f"{price:,} تومان".replace(",", "٬")


# --------------------------------------------------------------------------
# توابع جزوه‌های استاد نظری (خوانده شده از دیتابیس)
# --------------------------------------------------------------------------

def get_nazari_booklet_options(grade: str):
    """
    گزینه‌های جزوه‌های استاد نظری برای یک پایه خاص را از دیتابیس برمی‌گرداند.
    خروجی: لیست تاپل‌های (title, price, label)
    """
    from database import get_booklets_by_teacher_grade_chapter
    
    options = []
    # جزوه‌های نظری در دیتابیس با subject="نظری" ذخیره می‌شوند.
    # چون در جریان ادمین chapter انتخاب می‌شود، باید تمام فصل‌ها را بررسی کنیم.
    # اما برای نمایش به کاربر، فقط title و قیمت مهم است.
    for chapter in CHAPTERS:
        booklets = get_booklets_by_teacher_grade_chapter("نظری", grade, chapter)
        for b in booklets:
            if b.get("has_bw") and b.get("price_bw") is not None:
                options.append((
                    b["title"],
                    b["price_bw"],
                    f"📖 {b['title']} — {b['price_bw']:,} تومان".replace(",", "٬")
                ))
            if b.get("has_color") and b.get("price_color") is not None:
                options.append((
                    b["title"],
                    b["price_color"],
                    f"📖 {b['title']} (رنگی) — {b['price_color']:,} تومان".replace(",", "٬")
                ))
    return options


def get_nazari_booklet_price(booklet_name: str, grade: str):
    """
    قیمت یک جزوه خاص استاد نظری را برای یک پایه از دیتابیس برمی‌گرداند.
    """
    from database import get_booklets_by_teacher_grade_chapter
    
    for chapter in CHAPTERS:
        booklets = get_booklets_by_teacher_grade_chapter("نظری", grade, chapter)
        for b in booklets:
            if b["title"] == booklet_name:
                # اگر هم رنگی و هم سیاه‌سفید دارد، اولویت با رنگی (یا هرکدام که قیمت داشته باشد)
                if b.get("has_color") and b.get("price_color") is not None:
                    return b["price_color"]
                if b.get("has_bw") and b.get("price_bw") is not None:
                    return b["price_bw"]
    return None


def get_nazari_booklet_from_label(text: str, grade: str):
    """
    بر اساس متن دکمه انتخاب شده توسط کاربر، نام جزوه و قیمت را برمی‌گرداند.
    """
    for booklet_name, price, label in get_nazari_booklet_options(grade):
        if text == label:
            return booklet_name, price
    return None
