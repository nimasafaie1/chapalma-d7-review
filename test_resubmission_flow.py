"""DEPRECATED / منسوخ — این تست دیگر اجرا نمی‌شود.

دلیل انسداد:
  • این فایل از `handlers.receive_resubmitted_receipt` استفاده می‌کرد که در
    بازطراحی حذف شد؛ مسیر رسید مجدد اکنون از `handlers.receive_receipt`
    (وضعیت WAITING_RECEIPT) و تابع `database.get_payment_by_order` می‌گذرد.
  • همچنین از `database.reject_payment` (نسخهٔ قدیمی) استفاده می‌کرد که حذف شده
    و با نسخهٔ اتمیک جدید در `database.py` جایگزین شده است.

جایگزین:
  • `tests/test_reject_idempotency.py` — S4: «رد رسید قبلی و تأیید رسید جدید»
    (ساخت پرداخت جدید، حفظ پرداخت رد‌شده، تأیید موفق پرداخت جدید).
  • سوئیت ۲۳تستی `%TEMP%/kilo/test_keyboard.py` — Test 21 (Preserve old
    payment when new receipt arrives).
  • `handlers.receive_receipt` — جلوگیری از ساخت رسید تکراری با
    `get_payment_by_order`.

این فایل عمداً هیچ تابع منسوخ را احیا نمی‌کند.
"""

import unittest

NOTICE = (
    "test_resubmission_flow: DEPRECATED/SKIPPED — "
    "removed API receive_resubmitted_receipt and old reject_payment; "
    "see tests/test_reject_idempotency.py and handlers.receive_receipt."
)


class TestResubmissionFlowDeprecated(unittest.TestCase):
    @unittest.skip(NOTICE)
    def test_deprecated(self):
        pass


def run():
    print(NOTICE)


if __name__ == "__main__":
    run()