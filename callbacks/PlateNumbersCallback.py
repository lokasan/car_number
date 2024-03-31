from aiogram.filters.callback_data import CallbackData


class PlateNumbersCallback(CallbackData, prefix='plate'):
    foo: str
