from aiogram import types
from aiogram.utils.keyboard import KeyboardBuilder

from db import is_exists_number_info_change


async def get_keyboard_add_archive(plate_number):
    builder = KeyboardBuilder(button_type=types.InlineKeyboardButton)
    result = await is_exists_number_info_change(plate_number)
    if result is not None:
        builder.add(types.InlineKeyboardButton(text='ℹ', callback_data=f"info_change_log:{plate_number}"))
    builder.add(types.InlineKeyboardButton(
        text='Номер проверен. Добавить в архив',
        callback_data=f"add_archive:{plate_number}"
    ))

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=builder.export())
    return keyboard
