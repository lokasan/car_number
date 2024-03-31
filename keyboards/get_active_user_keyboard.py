from aiogram import types
from aiogram.utils.keyboard import KeyboardBuilder
import math

from utils import compare_count
from db import get_general_activity, get_general_activity_offset


async def get_active_user_keyboard(current_page=1):
    builder = KeyboardBuilder(button_type=types.InlineKeyboardButton)

    limit = 10
    total_accounts = len((await get_general_activity())[0])
    total_pages = math.ceil(total_accounts / 10)

    users = await get_general_activity_offset(current_page, limit)

    for user in users:
        builder.row(
            types.InlineKeyboardButton(
                text=f'{user[0]}' \
                    f'{"" if len(str(user[0])) == 9 else "  "} | ' \
                    f'{compare_count(user[1])}',
                callback_data=f'get_user_data:{user[0]}', url=f'tg://user?id={user[0]}'
            ), width=1
        )

    left_button = types.InlineKeyboardButton(text='⬅',
                                             callback_data="active_user_left")
    right_button = types.InlineKeyboardButton(text='➡',
                                              callback_data="actitve_user_right")

    if current_page == 1 and total_pages != 1:
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
