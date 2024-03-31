async def refresh_keyboard_and_text(bot, chat_id, message_id, text, keyboard,
                                    parse_mode="HTML"):
    try:
        await bot.edit_message_text(chat_id=chat_id,
                                    message_id=message_id, text=text,
                                    parse_mode=parse_mode)
        await bot.edit_message_reply_markup(chat_id=chat_id,
                                            message_id=message_id,
                                            reply_markup=keyboard)
    except Exception as e:
        print(e)


async def refresh_keyboard(bot, chat_id, message_id, keyboard):
    try:
        await bot.edit_message_reply_markup(chat_id=chat_id,
                                            message_id=message_id,
                                            reply_markup=keyboard)
    except Exception as e:
        print(e)
