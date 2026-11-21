"""DEPRECATED / منسوخ — این تست دیگر اجرا نمی‌شود.

دلیل انسداد:
  • این فایل از `handlers.handle_receipt_button` و `database.reject_payment`
    استفاده می‌کرد؛ هر دو در بازطراحی حذف/جایگزین شدند.
  • `database.reject_payment` دیگر وجود ندارد و منطق رد به
    `database.reject_payment` (نسخهٔ اتمیک جدید) و
    `handlers.handle_receipt_callback` منتقل شده است.
  • callbackهای `receipt:*` دیگر وجود ندارند.

جایگزین:
  • `tests/test_reject_idempotency.py` — پوشش کامل idempotency/concurrency:
    - رد تك‌سفارشی و چندسفارشی
    - رد→تأیید (تأیید مسدود)
    - تأیید→رد (رد مسدود)
    - رد رسید قبلی و تأیید رسید جدید
    - Callback تکراری پس از پایان عملیات
    - ۲۰ تکرار برای هر سناریوی هم‌زمان (Barrier + Thread)
  • سوئیت ۲۳تستی `%TEMP%/kilo/test_keyboard.py` — Test 4/19/20/21.

این فایل عمداً هیچ تابع منسوخ را احیا نمی‌کند.
"""

import unittest

NOTICE = (
    "test_payment_rejection: DEPRECATED/SKIPPED — "
    "removed APIs handle_receipt_button/database.reject_payment; "
    "see tests/test_reject_idempotency.py."
)


class TestPaymentRejectionDeprecated(unittest.TestCase):
    @unittest.skip(NOTICE)
    def test_deprecated(self):
        pass


def run():
    print(NOTICE)


if __name__ == "__main__":
    run()