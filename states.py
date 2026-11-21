# مراحل ثبت‌نام
NAME = 1

# مراحل سفارش جزوه‌های آماده (استاد امامی / کوشکی / نظری)
CHOOSING_GRADE = 10
CHOOSING_CHAPTER = 11
CHOOSING_COLOR = 12
CHOOSING_NAZARI_GRADE = 13
CHOOSING_NAZARI_BOOKLET = 14
CHOOSING_ADD_MORE = 15
ORDER_ENTRY = 16

# مراحل مشترک تحویل سفارش (چه جزوه آماده چه فایل دلخواه)
CHOOSING_DISCOUNT = 18
WAITING_DISCOUNT_CODE = 19
CHOOSING_DELIVERY = 20
CHOOSING_DELIVERY_LOCATION = 21
WAITING_ADDRESS = 22
WAITING_PHONE = 23
WAITING_RECEIPT = 24

# مراحل ارسال جزوه دلخواه (آپلود فایل ورد / پی‌دی‌اف)
WAITING_FILE = 30
CHOOSING_FILE_OPTION = 31
CHOOSING_BINDING = 32

# مراحل مرور آزمون‌ها (قلمچی / ماز / امتحان نهایی) توسط دانش‌آموز
CHOOSING_EXAM_PROVIDER = 40
CHOOSING_EXAM_SUBJECT = 41
CHOOSING_EXAM_GRADE = 42
CHOOSING_EXAM_DATE = 43
CHOOSING_EXAM_ACTION = 44
CHOOSING_EXAM_ANSWER_INCLUDE = 45
CHOOSING_EXAM_QUANTITY = 46
WAITING_EXAM_QUANTITY_CUSTOM = 47

# مراحل ماز (دوپینگ و جامع)
CHOOSING_EXAM_MAZ_TYPE = 56
CHOOSING_EXAM_MAZ_FIELD = 57          # انتخاب رشته (تجربی، ریاضی فیزیک، انسانی)
CHOOSING_EXAM_MAZ_GRADE = 58          # انتخاب پایه (دهم، یازدهم، دوازدهم)

# مراحل خیلی سبز
# توجه: ۶۰ قبلاً هم‌زمان برای CHOOSING_KONKUR_TYPE هم استفاده می‌شد و باعث می‌شد
# مرحله‌ی «رشته» خیلی سبز با هندلر کنکور جایگزین شود (نمایش «داخلی/خارجی»).
CHOOSING_EXAM_KHEILI_GRADE = 59
CHOOSING_EXAM_KHEILI_FIELD = 66

# مراحل ثبت آزمون جدید توسط ادمین (مکالمه‌ی جدا، فقط داخل گروه)
ADMIN_EXAM_PROVIDER = 50
ADMIN_EXAM_FIELD = 68
ADMIN_EXAM_SUBJECT = 51
ADMIN_EXAM_GRADE = 52
ADMIN_EXAM_DATE = 53
ADMIN_EXAM_QUESTION_FILE = 54
ADMIN_EXAM_ANSWER_FILE = 55

# مراحل ثبت جزوه جدید توسط ادمین (مکالمه‌ی جدا، فقط داخل گروه)
ADMIN_BOOKLET_TEACHER = 70
ADMIN_BOOKLET_SUBJECT = 71
ADMIN_BOOKLET_GRADE = 72
ADMIN_BOOKLET_CHAPTER = 73
ADMIN_BOOKLET_TITLE = 74
ADMIN_BOOKLET_VERSIONS = 75

# مراحل مرور کنکور سراسری توسط دانش‌آموز
CHOOSING_KONKUR_TYPE = 60
CHOOSING_KONKUR_YEAR = 61
CHOOSING_KONKUR_SESSION = 62
CHOOSING_KONKUR_SUBJECT = 63
CHOOSING_KONKUR_ACTION = 64

# مراحل آرشیو جامع امتحان نهایی
CHOOSING_EXAM_FINAL_ARCHIVE = 65

# مراحل آرمان — انتخاب پایه (دهم/یازدهم/دوازدهم) بدون درس فیلتر
CHOOSING_EXAM_AHRAM_GRADE = 67


# ---------------------------------------------------------------------------
# گارد یکتایی شماره‌های حالت
# اگر دو حالت شماره‌ی یکسان داشته باشند، در دیکشنری ConversationHandler یکی
# بی‌صدا روی دیگری می‌نشیند و مسیر اشتباه اجرا می‌شود؛ پس همان لحظه خطا می‌دهیم.
# ---------------------------------------------------------------------------
_state_numbers: dict = {}
for _name, _value in list(globals().items()):
    if _name.isupper() and isinstance(_value, int) and not _name.startswith("_"):
        if _value in _state_numbers:
            raise RuntimeError(
                f"شماره حالت تکراری است: {_name} و {_state_numbers[_value]} هر دو = {_value}"
            )
        _state_numbers[_value] = _name