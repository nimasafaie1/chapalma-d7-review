from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove
import re

from prices import (
    TEACHERS,
    GRADES,
    CHAPTERS,
    EXAM_PROVIDERS,
    EXAM_SUBJECTS,
    FINAL_EXAM_PROVIDER,
    FINAL_EXAM_GRADE,
    FINAL_EXAM_ARCHIVE_BUTTON,
    get_exam_subjects,
    is_final_exam_provider,
    get_delivery_location_labels,
    MAZ_SUBJECTS,
    KONKUR_PROVIDER,
    KONKUR_TYPES,
    KONKUR_SUBJECTS,
    KONKUR_SESSIONS,
)

TEACHER_EMOJI = {
    "امامی": "📘",
    "کوشکی": "📗",
    "نظری": "📙",
}

PROVIDER_EMOJI = {
    "قلمچی": "🟢",
    "ماز": "🔵",
    "امتحان نهایی": "🎓",
    "خیلی سبز": "💚",
}

SUBJECT_EMOJI = {
    "ریاضی": "📐",
    "فیزیک": "⚡",
    "زیست": "🧬",
    "شیمی": "🧪",
    "زمین": "🌍",
    "تجربی": "🧪",
    "انسانی": "📖",
    "هنر": "🎨",
    "زبان": "🌐",
    "آزمون جامع": "📚",
    "دوپینگ ماز": "📘",
    "آزمون‌های جامع": "📚",
    "ریاضی فیزیک": "📐",
    "خیلی سبز": "💚",
}

CUSTOM_FILE_BUTTON = "📎 ارسال جزوه دلخواه"
EXAMS_BUTTON = "📚 آزمون‌ها"
RESTART_BUTTON = "🔁 شروع از اول"
BACK_BUTTON = "⬅️ بازگشت"
ADD_MORE_BUTTON = "➕ افزودن جزوه دیگر"
FINISH_ORDER_BUTTON = "✅ پایان سفارش و ادامه به تحویل"
HAVE_DISCOUNT_BUTTON = "🎟️ کد تخفیف دارم"
NO_DISCOUNT_BUTTON = "➡️ ندارم، ادامه بده"
PRINT_THIS_FILE_BUTTON = "🖨 پرینت این فایل"
WITH_ANSWER_BUTTON = "✅ همراه پاسخنامه"
ONLY_QUESTION_BUTTON = "📄 فقط دفترچه سؤال"
CUSTOM_QUANTITY_BUTTON = "🔢 عدد دلخواه"
ADMIN_SKIP_BUTTON = "⏭ رد کردن (پاسخنامه ندارد)"


def admin_skip_keyboard():
    keyboard = [[ADMIN_SKIP_BUTTON]] + _nav_rows()
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def _nav_rows(include_back: bool = True):
    rows = []
    if include_back:
        rows.append([BACK_BUTTON])
    rows.append([RESTART_BUTTON])
    return rows


def add_more_keyboard():
    keyboard = [[ADD_MORE_BUTTON], [FINISH_ORDER_BUTTON]] + _nav_rows()
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def discount_prompt_keyboard():
    keyboard = [[HAVE_DISCOUNT_BUTTON], [NO_DISCOUNT_BUTTON]] + _nav_rows()
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def restart_keyboard():
    keyboard = _nav_rows()
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def teacher_label(teacher: str) -> str:
    return f"{TEACHER_EMOJI.get(teacher, '📘')} جزوه استاد {teacher}"


def teacher_from_label(text: str):
    for teacher in TEACHERS:
        if text == teacher_label(teacher):
            return teacher
    return None


def main_keyboard():
    keyboard = [[teacher_label(teacher)] for teacher in TEACHERS]
    keyboard.append([EXAMS_BUTTON])
    keyboard.append([CUSTOM_FILE_BUTTON])
    keyboard.append([RESTART_BUTTON])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def grade_keyboard():
    keyboard = [[f"🔹 پایه {grade}"] for grade in GRADES] + _nav_rows()
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def grade_from_label(text: str):
    text = (text or "").strip()
    # قبول کردن متن دکمه با ایموجی یا بدون ایموجی
    for grade in GRADES:
        if text in (f"🔹 پایه {grade}", f"پایه {grade}", grade):
            return grade
    return None


def chapter_keyboard(grade: str, teacher: str = None):
    from prices import is_chapter_available

    keyboard = []
    for chapter in CHAPTERS:
        note = ""
        if teacher == "امامی" and grade == "دهم" and chapter == "فصل ۳":
            note = " (مخصوص سال دوازدهم)"

        if teacher and not is_chapter_available(teacher, grade, chapter):
            keyboard.append([f"🔒 {chapter} {grade} (به‌زودی)"])
        else:
            keyboard.append([f"📄 {chapter} {grade}{note}"])

    keyboard += _nav_rows()
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def chapter_from_label(text: str, grade: str):
    for chapter in CHAPTERS:
        if text in (
            f"📄 {chapter} {grade}",
            f"📄 {chapter} {grade} (مخصوص سال دوازدهم)",
            f"🔒 {chapter} {grade} (به‌زودی)",
        ):
            return chapter
    return None


def is_chapter_locked_label(text: str, grade: str) -> bool:
    for chapter in CHAPTERS:
        if text == f"🔒 {chapter} {grade} (به‌زودی)":
            return True
    return False


def color_keyboard(price_color: int, price_bw):
    from prices import format_price

    keyboard = [
        [f"🌈 چاپ رنگی ({format_price(price_color)})"],
        [f"⚫ چاپ سیاه‌وسفید ({format_price(price_bw)})"],
    ] + _nav_rows()
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def nazari_booklet_keyboard(grade: str):
    from prices import get_nazari_booklet_options
    
    options = get_nazari_booklet_options(grade)
    if not options:
        keyboard = [["❌ برای این پایه هنوز جزوه‌ای ثبت نشده است"]] + _nav_rows()
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    keyboard = [[label] for _, _, label in options] + _nav_rows()
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def nazari_booklet_from_label(text: str, grade: str):
    from prices import get_nazari_booklet_from_label
    return get_nazari_booklet_from_label(text, grade)


COLOR_OPTIONS = ["رنگی", "سیاه‌وسفید"]


def color_from_label(text: str):
    if text.startswith("🌈 چاپ رنگی"):
        return "رنگی"
    if text.startswith("⚫ چاپ سیاه‌وسفید"):
        return "سیاه‌وسفید"
    return None


def delivery_keyboard():
    keyboard = [
        ["🏪 تحویل حضوری"],
        ["🚚 ارسال (هزینه جداگانه دارد)"],
    ] + _nav_rows()
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def delivery_location_keyboard(teacher=None):
    keyboard = [[label] for label in get_delivery_location_labels(teacher)] + _nav_rows()
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


FILE_OPTIONS = [
    ("رنگی", "پشت‌ورو", "🌈 رنگی - پشت و رو"),
    ("رنگی", "تک‌رو", "🌈 رنگی - تک رو"),
    ("سیاه‌وسفید", "پشت‌ورو", "⚫ سیاه‌وسفید - پشت و رو"),
    ("سیاه‌وسفید", "تک‌رو", "⚫ سیاه‌وسفید - تک رو"),
]


def file_option_keyboard():
    keyboard = [[label] for _, _, label in FILE_OPTIONS] + _nav_rows()
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def _binding_label(name: str, price: int) -> str:
    from prices import format_price

    icons = {
        "صحافی سیمی": "📎",
        "منگنه": "📌",
        "بدون صحافی": "🚫",
    }
    icon = icons.get(name, "•")

    if price == 0:
        return f"{icon} {name} (رایگان)"
    return f"{icon} {name} ({format_price(price)})"


def binding_keyboard(pages: int):
    from prices import get_binding_options

    options = get_binding_options(pages)
    keyboard = [[_binding_label(name, price)] for name, price in options] + _nav_rows()
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def binding_from_label(text: str, pages: int):
    from prices import get_binding_options

    options = get_binding_options(pages)
    for name, price in options:
        if text == _binding_label(name, price):
            return name, price
    return None


def file_option_from_label(text: str):
    for color, side, label in FILE_OPTIONS:
        if text == label:
            return color, side
    return None


# ---------------------------------------------------------------------------
# مرور آزمون‌ها (قلمچی / ماز / امتحان نهایی)
# ---------------------------------------------------------------------------

def provider_label(provider: str) -> str:
    return f"{PROVIDER_EMOJI.get(provider, '📚')} {provider}"


def provider_from_label(text: str):
    for provider in EXAM_PROVIDERS:
        if text == provider_label(provider):
            return provider
    return None


def exam_provider_keyboard():
    """کیبورد انتخاب مؤسسه آزمون — شامل کنکور سراسری به صورت جداگانه."""
    keyboard = [[provider_label(p)] for p in EXAM_PROVIDERS]
    keyboard.append([KONKUR_PROVIDER_BUTTON])
    keyboard.append([FINAL_EXAM_ARCHIVE_BUTTON])
    keyboard += _nav_rows()
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def final_exam_archive_keyboard():
    """کیبورد انتخاب درس آرشیو جامع امتحان نهایی."""
    from prices import FINAL_EXAM_ARCHIVE_SUBJECTS

    emoji_map = {
        "انگلیسی": "🌐",
        "فارسی": "📖",
        "فیزیک": "⚡",
        "گسسته": "📚",
        "هندسه": "📐",
        "ریاضی": "📐",
        "شیمی": "🧪",
        "تاریخ": "📅",
        "زیست": "🧬",
    }

    keyboard = []
    for s in FINAL_EXAM_ARCHIVE_SUBJECTS:
        emoji = "📘"
        for key, icon in emoji_map.items():
            if s.startswith(key):
                emoji = icon
                break
        keyboard.append([f"{emoji} {s}"])

    keyboard += _nav_rows()
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def final_exam_archive_from_label(text: str):
    """استخراج درس آرشیو از برچسب نمایشی."""
    from prices import FINAL_EXAM_ARCHIVE_SUBJECTS

    for s in FINAL_EXAM_ARCHIVE_SUBJECTS:
        if text.endswith(f" {s}") or text == s:
            return s
    return None


def subject_label(subject: str) -> str:
    """برچسب درس/رشته با ایموجی مناسب"""
    emoji_map = {
        "ریاضی": "📐",
        "فیزیک": "⚡",
        "زیست": "🧬",
        "شیمی": "🧪",
        "زمین": "🌍",
        "تجربی": "🧪",
        "انسانی": "📖",
        "هنر": "🎨",
        "زبان": "🌐",
        "آزمون جامع": "📚",
        "دوپینگ ماز": "📘",
        "آزمون‌های جامع": "📚",
        "ریاضی فیزیک": "📐",
    }
    
    for key in emoji_map:
        if subject.startswith(key):
            return f"{emoji_map[key]} {subject}"
    
    return f"📘 {subject}"


def exam_subject_keyboard(provider=None, grade=None):
    from prices import get_exam_subjects
    
    subjects = get_exam_subjects(provider, grade) if provider else EXAM_SUBJECTS
    
    if not subjects:
        return restart_keyboard()
    
    keyboard = [[subject_label(s)] for s in subjects] + _nav_rows()
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# ===== تابع اصلاح‌شده با پارامتر grade =====
def subject_from_label(text: str, provider=None, grade=None):
    subjects = get_exam_subjects(provider, grade) if provider else EXAM_SUBJECTS
    for subject in subjects:
        if text == subject_label(subject):
            return subject
    return None

def exam_grade_keyboard():
    keyboard = [[f"🎓 {grade}"] for grade in GRADES] + _nav_rows()
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def exam_grade_from_label(text: str):
    for grade in GRADES:
        if text == f"🎓 {grade}":
            return grade
    return None


def exam_date_label(row_or_date) -> str:
    if isinstance(row_or_date, dict):
        if row_or_date.get("label"):
            return row_or_date["label"]
        return f"📅 {row_or_date.get('exam_date', '')}"
    return f"📅 {row_or_date}"


def exam_date_keyboard(exam_rows):
    keyboard = [[exam_date_label(row)] for row in exam_rows] + _nav_rows()
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def exam_date_from_label(text: str, exam_rows):
    for row in exam_rows:
        if text == exam_date_label(row):
            return row["id"]
    return None


def exam_admin_field_keyboard():
    """کیبورد انتخاب رشته برای ادمین ماز (مشترک)."""
    keyboard = [
        ["📐 ریاضی فیزیک"],
        ["🧪 تجربی"],
        ["📖 انسانی"],
        ["هم ریاضی فیزیک هم تجربی"],
    ] + _nav_rows()
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def exam_after_file_keyboard():
    keyboard = [[PRINT_THIS_FILE_BUTTON]] + _nav_rows()
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def exam_answer_keyboard():
    keyboard = [[WITH_ANSWER_BUTTON], [ONLY_QUESTION_BUTTON]] + _nav_rows()
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def exam_quantity_keyboard():
    keyboard = [
        ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"],
        ["6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"],
        [CUSTOM_QUANTITY_BUTTON],
    ] + _nav_rows()
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


_QUANTITY_DIGIT_LABELS = {
    "1️⃣": 1, "2️⃣": 2, "3️⃣": 3, "4️⃣": 4, "5️⃣": 5,
    "6️⃣": 6, "7️⃣": 7, "8️⃣": 8, "9️⃣": 9, "🔟": 10,
}


def quantity_from_label(text: str):
    return _QUANTITY_DIGIT_LABELS.get(text)


def remove_keyboard():
    return ReplyKeyboardRemove()


# ================================================================
# 📚 کیبوردهای ماز (دوپینگ و جامع)
# ================================================================

def exam_maz_type_keyboard():
    """کیبورد انتخاب نوع ماز: دوپینگ یا جامع"""
    keyboard = [
        ["📘 دوپینگ ماز"],
        ["📚 آزمون‌های جامع"],
    ] + _nav_rows()
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def exam_field_keyboard():
    """کیبورد انتخاب رشته تحصیلی"""
    keyboard = [
        ["🧪 تجربی"],
        ["📐 ریاضی فیزیک"],
        ["📖 انسانی"],
        ["هم ریاضی فیزیک هم تجربی"],
    ] + _nav_rows()
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def exam_maz_grade_keyboard():
    """کیبورد انتخاب پایه برای ماز"""
    keyboard = [
        [f"🎓 {grade}"] for grade in GRADES
    ] + _nav_rows()
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# ================================================================
# 🎓 کیبوردهای کنکور سراسری
# ================================================================

KONKUR_PROVIDER_BUTTON = "🎓 کنکور سراسری"


def konkur_type_keyboard():
    """کیبورد انتخاب نوع کنکور: داخلی یا خارجی"""
    from prices import KONKUR_TYPES

    keyboard = [
        [f"🇮🇷 {t}"] if t == "داخلی" else [f"🌍 {t}"]
        for t in KONKUR_TYPES
    ] + _nav_rows()
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def konkur_type_from_label(text: str):
    """استخراج نوع کنکور از برچسب نمایشی."""
    for t in KONKUR_TYPES:
        if text == f"🇮🇷 {t}" or text == f"🌍 {t}":
            return t
    return None


def konkur_year_keyboard(exam_type: str):
    """کیبورد انتخاب سال کنکور — سال‌ها به صورت داینامیک از دیتابیس خوانده می‌شوند."""
    from database import get_konkur_years

    years = get_konkur_years(exam_type)
    if not years:
        from prices import KONKUR_YEARS
        years = KONKUR_YEARS

    keyboard = [[f"📅 {y}"] for y in years] + _nav_rows()
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def konkur_year_from_label(text: str):
    """استخراج سال از برچسب نمایشی (مثلاً «📅 ۱۴۰۴» → «1404»)."""
    match = re.search(r"(1[3-9]\d\d)", text)
    if match:
        return match.group(1)
    return None


def konkur_session_keyboard():
    """کیبورد انتخاب نوبت کنکور."""
    from prices import KONKUR_SESSIONS

    keyboard = [[label] for label in KONKUR_SESSIONS] + _nav_rows()
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def konkur_subject_keyboard():
    """کیبورد انتخاب رشته کنکور (ریاضی / تجربی / انسانی)."""
    from prices import KONKUR_SUBJECTS

    emoji_map = {"ریاضی": "📐", "تجربی": "🧪", "انسانی": "📖"}
    keyboard = [[f"{emoji_map.get(s, '📘')} {s}"] for s in KONKUR_SUBJECTS] + _nav_rows()
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def konkur_subject_from_label(text: str):
    """استخراج رشته از برچسب نمایشی."""
    from prices import KONKUR_SUBJECTS

    for s in KONKUR_SUBJECTS:
        if text.endswith(f" {s}") or text == s:
            return s
    return None


def konkur_action_keyboard(has_answer: bool = False):
    """کیبورد انتخاب عمل after انتخاب رشته."""
    keyboard = []
    keyboard.append(["📘 دریافت دفترچه آزمون"])
    if has_answer:
        keyboard.append(["📕 دریافت کلیدنامه"])
    keyboard += _nav_rows()
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def konkur_action_from_label(text: str):
    """تشخیص دکمه انتخاب‌شده در کیورد عملیات."""
    if text == "📘 دریافت دفترچه آزمون":
        return "question"
    if text == "📕 دریافت کلیدنامه":
        return "answer"
    return None