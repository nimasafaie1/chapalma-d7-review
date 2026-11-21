import asyncio
import handlers

class FakeMessage:
    def __init__(self):
        self.text = handlers.BACK_BUTTON
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
                "grade": "دوازدهم",
                "exam_rows": []
            }
        }

async def main():
    update = FakeUpdate()
    context = FakeContext()

    result = await handlers.choose_exam_date(update, context)

    print("Returned state:", result)
    print("Expected state:", handlers.CHOOSING_EXAM_AHRAM_GRADE)
    print("State matches:", result == handlers.CHOOSING_EXAM_AHRAM_GRADE)
    print("Message count:", len(update.message.calls))

    assert result == handlers.CHOOSING_EXAM_AHRAM_GRADE
    assert update.message.calls

    print("PASS: Arman back navigation")

asyncio.run(main())
