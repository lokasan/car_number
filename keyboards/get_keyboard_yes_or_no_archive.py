from aiogram import types
from aiogram.utils.keyboard import KeyboardBuilder


async def get_keyboard_yes_or_no_archive(number_plate):
    builder = KeyboardBuilder(button_type=types.InlineKeyboardButton)
    builder.row(
        types.InlineKeyboardButton(
            text='Да',
            callback_data=f'confirm_add_archive_btn:{number_plate}'),
        types.InlineKeyboardButton(
            text='Нет',
            callback_data=f'disable_add_archive_btn:{number_plate}'
        ))

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=builder.export())
    return keyboard
