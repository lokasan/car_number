from aiogram import types
from aiogram.utils.keyboard import KeyboardBuilder
import math

from utils import compare_count
from db import get_repeatable_parking_offset, get_repeatable_parking


async def get_add_plate_keyboard(is_own, is_archive, current_page=1):
    builder = KeyboardBuilder(button_type=types.InlineKeyboardButton)

    limit = 10
    total_accounts = len((await get_repeatable_parking(is_own, is_archive))[0])
    total_pages = math.ceil(total_accounts / 10)

    numbers = await get_repeatable_parking_offset(is_own, is_archive, current_page, limit)

    for number in numbers:
        builder.row(
            types.InlineKeyboardButton(
                text=f'🚘{number[0]}' \
                    f'{"" if len(number[0]) == 9 else "  "} | ' \
                    f'{compare_count(number[1])} {f"⚠️{number[2]}" if number[2] else ""}',
                callback_data=f'get_numbers_data:{number[0]}'
            ), width=1
        )

    left_button = types.InlineKeyboardButton(text='⬅',
                                             callback_data="numbers_left")
    right_button = types.InlineKeyboardButton(text='➡',
                                              callback_data="numbers_right")

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
