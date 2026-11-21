import asyncio
from types import SimpleNamespace
import handlers

class FakeMessage:
    def __init__(self):
        self.calls = []

    async def reply_text(self, text, reply_markup=None):
        self.calls.append((text, reply_markup))

class FakeUpdate:
    def __init__(self):
        self.message = FakeMessage()

class FakeContext:
    def __init__(self):
        self.user_data = {
            "exam_browse": {
                "provider": "آرمان",
                "subject": "زیست",
            }
        }

async def run_test(label, fake_rows, expected_state):
    update = FakeUpdate()
    context = FakeContext()
    captured = {}

    original_get = handlers.get_unique_exam_dates
    original_keyboard = handlers.exam_date_keyboard

    def fake_get(provider, subject, grade):
        captured["provider"] = provider
        captured["subject"] = subject
        captured["grade"] = grade
        return fake_rows

    handlers.get_unique_exam_dates = fake_get
    handlers.exam_date_keyboard = lambda rows: ("DATE_KEYBOARD", rows)

    try:
        result = await handlers._load_exam_dates(update, context, "دوازدهم")
    finally:
        handlers.get_unique_exam_dates = original_get
        handlers.exam_date_keyboard = original_keyboard

    assert result == expected_state, (result, expected_state)
    assert captured["provider"] == "آرمان"
    assert captured["subject"] is None, captured
    assert captured["grade"] == "دوازدهم"

    if fake_rows:
        assert context.user_data["exam_browse"]["exam_rows"] == fake_rows
        assert update.message.calls[-1][1] == ("DATE_KEYBOARD", fake_rows)

    print(f"PASS: {label}")
    print(f"  returned state: {result}")
    print(f"  query subject: {captured['subject']}")

async def main():
    await run_test(
        "Arman with no exams",
        [],
        handlers.CHOOSING_EXAM_AHRAM_GRADE
    )
    await run_test(
        "Arman with available exams",
        [{"id": 123, "exam_date": "آزمون آزمایشی"}],
        handlers.CHOOSING_EXAM_DATE
    )

    result = handlers._exam_back_target_before_date({
        "provider": "آرمان",
        "grade": "دوازدهم"
    })
    assert result[0] == handlers.CHOOSING_EXAM_AHRAM_GRADE
    print("PASS: shared back-target helper")

asyncio.run(main())
