from aiogram import types
from aiogram.utils.keyboard import KeyboardBuilder
import math

from consts.consts import LIMIT_STAT_NUMBERS
from db import get_stat_numbers_dates_count


async def get_keyboard_stat_numbers(current_page=1):
    builder = KeyboardBuilder(button_type=types.InlineKeyboardButton)

    total_dates = await get_stat_numbers_dates_count()
    print(total_dates, 'total_dates')

    total_pages = math.ceil(total_dates / LIMIT_STAT_NUMBERS)

    left_button = types.InlineKeyboardButton(
        text='⬅',
        callback_data="stat_numbers_left")
    right_button = types.InlineKeyboardButton(
        text='➡',
        callback_data="stat_numbers_right")

    if current_page == 1 and total_pages > 1:
        builder.row(types.InlineKeyboardButton(
            text=f"Страница {current_page}/{total_pages}",
            callback_data="refresh_accounts"), right_button,
            width=2)
    elif current_page > 1 and current_page == total_pages:
        builder.row(types.InlineKeyboardButton(
            text=f"Страница {current_page}/{total_pages}",
            callback_data="refresh_accounts"), left_button,
            width=2)
    elif 1 < current_page < total_pages:
        builder.row(
            left_button,
            right_button, width=2
        )

        builder.row(
            types.InlineKeyboardButton(
                text=f"Страница {current_page}/{total_pages}",
                callback_data="refresh_accounts")
        )
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=builder.export())
    return keyboard
