import os
import re
import time
import asyncio
import logging
import aiohttp
import configparser
from typing import Any, Union
from datetime import datetime, timezone, timedelta
from collections.abc import Callable, Awaitable

from aiogram.filters import Command, BaseFilter
from db import add_auto_number, add_log_history, get_auto_number_id, \
    get_repeatable_parking, get_stat_numbers, get_general_activity, \
    get_active_users, get_end_day_stats, get_number_detail, \
    is_in_archive_number, set_archive_db, get_number_detail_info_change, \
    get_log_numbers_upload
from aiogram import F, Dispatcher, Bot, types, exceptions
from aiogram.types import BotCommand, BotCommandScopeChat, \
    BotCommandScopeDefault, Message
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.fsm.context import FSMContext
import aioschedule

from main import get_number_auto
from consts import T_RANGE_H
from keyboards import get_add_plate_keyboard, refresh_keyboard, \
    get_active_user_keyboard, get_keyboard_add_archive, \
    get_keyboard_yes_or_no_archive, get_keyboard_stat_numbers, \
    refresh_keyboard_and_text, get_keyboard_upload_excel
from utils import compare_count, read_excel

config = configparser.ConfigParser()

config.read('config.ini')

TOKEN_BOT = config['BOT']['bot_token']

REDIS_DATA_CONNECTION = config['redis']['redis_data_conn']

project_path = os.path.dirname(os.path.abspath(__file__))


logging.basicConfig(level=logging.INFO)
bot = Bot(TOKEN_BOT)
storage = RedisStorage.from_url(REDIS_DATA_CONNECTION)
dp = Dispatcher(storage=storage)

user_commands = [
    BotCommand(command="start", description="Проверить номер"),
]

admin_commands = [
    BotCommand(command="start", description="Проверить номер"),
    BotCommand(command="get_list",
               description="Статистика появления чужих номеров"),
    BotCommand(command="get_stat_numbers",
               description="Статистика отправленных номеров"),
    BotCommand(command="get_general_activity", description="Активность"),
    BotCommand(command="upload_excel",
               description="Загрузка списка"),
    BotCommand(command="get_archive", description="Архив номеров"),
    BotCommand(command="log", description="История добавленных/удалённых номеров")
]


ADMIN_ID = [497503958, 5510958983, 1019064526, 1125759577]


def get_time_now() -> str:
    moscow_timezone = timezone(timedelta(hours=3))
    final_format = f"{(datetime.now(moscow_timezone)).strftime('%H:%M:%S')}" \
                   f" ({(datetime.now(moscow_timezone)).strftime('%d.%m.%Y')})"
    return final_format


class ChatTypeFilter(BaseFilter):
    def __init__(self, chat_type: Union[str, list]):
        self.chat_type = chat_type

    async def __call__(self, message: Message) -> bool:
        if isinstance(self.chat_type, str):
            return message.chat.type == self.chat_type
        else:
            return message.chat.type in self.chat_type


async def set_commands():
    await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())

    for admin in ADMIN_ID:
        if await check_chat_existence(admin):
            await bot.set_my_commands(admin_commands,
                                      scope=BotCommandScopeChat(chat_id=admin))


async def get_photo_bytes(photo: types.PhotoSize) -> bytes:
    try:
        photo_file = await bot.get_file(photo.file_id)

        file_url = f"https://api.telegram.org/file/bot{bot.token}" \
                   f"/{photo_file.file_path}"

        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as response:
                if response.status == 200:
                    photo_bytes = await response.read()
                    return photo_bytes
    except Exception as e:
        print(e)


@dp.message(ChatTypeFilter('private'), Command('start'))
async def start_app(message: Message):
    text = 'Здравствуйте! Отправьте автомобильный номер.\n' \
           'Пример: <b>A542OH99</b>\n\n' \
           '<i>Примечание: регистр не имеет значения.</i>'

    await message.answer(text=text, parse_mode="HTML")

    await message.delete()


@dp.message(ChatTypeFilter('private'), Command('get_list'))
async def not_registered_number(message: Message, state: FSMContext):
    if await check_chat_existence(message.from_user.id):
        if message.from_user.id in ADMIN_ID:
            numbers, total_count = await get_repeatable_parking(is_own=False,
                                                                is_archive=False)
            text = '<b>Статистика по чужим номерам</b>\n\n' \
                   '1. Список отображает количество зафиксированных ' \
                   'парковок* автомобиля.\n' \
                   '2. Список содержит автомобильные номера, которых нет в базе.' \
                   '\n\n' \
                   '*<i>Парковкой считается новое фиксирование ' \
                   f'автомобиля по истечении {T_RANGE_H} ' \
                   f'часов от предыдущего.</i>\n\n'

            current_page = 1
            keyboard = await get_add_plate_keyboard(is_own=False,
                                                    is_archive=False,
                                                    current_page=current_page)
            text += f'\nОбщее количество обнаруженных ' \
                    f'незарегистрированных номеров (включая дубли): ' \
                    f'{compare_count(total_count)}'
            sent_message = await message.answer(text=text, reply_markup=keyboard,
                                                parse_mode='HTML')
            sent_message_id = sent_message.message_id
            await state.update_data({f'{sent_message_id}': current_page})
            await state.update_data({f'{sent_message_id}_is_own': False})
            await state.update_data({f'{sent_message_id}_is_archive': False})
            print(sent_message_id)
        else:
            await message.answer(text='У Вас нет доступа к этой команде!')
        await message.delete()


@dp.message(ChatTypeFilter('private'), Command('get_archive'))
async def get_archive(message: Message, state: FSMContext):
    if await check_chat_existence(message.from_user.id):
        if message.from_user.id in ADMIN_ID:
            numbers, total_count = await get_repeatable_parking(is_own=False,
                                                                is_archive=True)
            text = '<b>Статистика по архивным номерам</b>\n\n' \
                   '1. Список отображает количество зафиксированных ' \
                   'парковок* архивного автомобиля.\n' \
                   '2. Список содержит автомобильные номера, ' \
                   'которые были добавлены в архив. Номер уйдёт из архива, ' \
                   'если его внесут в список через отправку Excel-файла или ' \
                   'же при новой фиксации. Через отправку файла ' \
                   'он станет своим, а через новую фиксацию он будет ' \
                   'отображаться в статистике по чужим номерам.' \
                   '\n\n' \
                   '*<i>Парковкой считается новое фиксирование ' \
                   f'автомобиля по истечении {T_RANGE_H} ' \
                   f'часов от предыдущего.</i>\n\n'

            current_page = 1
            keyboard = await get_add_plate_keyboard(is_own=False,
                                                    is_archive=True,
                                                    current_page=current_page)
            text += f'\nОбщее количество обнаруженных ' \
                    f'незарегистрированных номеров в архиве(включая дубли): ' \
                    f'{compare_count(total_count)}\n'
            text += '<i>Примечение: ⚠️(n) - номер выбывал из архива, где <b>n</b> - '\
                    'количество выбываний</i>'

            sent_message = await message.answer(text=text, reply_markup=keyboard,
                                                parse_mode='HTML')
            sent_message_id = sent_message.message_id
            await state.update_data({f'{sent_message_id}': current_page})
            await state.update_data({f'{sent_message_id}_is_own': False})
            await state.update_data({f'{sent_message_id}_is_archive': True})
        else:
            await message.answer(text='У Вас нет доступа к этой команде!')
        await message.delete()


@dp.message(ChatTypeFilter('private'), Command('upload_excel'))
async def upload_excel(message: Message, state: FSMContext):
    if await check_chat_existence(message.from_user.id):
        if message.from_user.id in [497503958, 1125759577]:
            agenda = types.FSInputFile(
                f"example_files{os.sep}auto_number.xlsx",
                filename='Демонстрационный пример.xlsx')

            doc_id = await bot.send_document(
                message.from_user.id,
                document=agenda,
                caption="Отправьте актуальный список автомобильных номеров "
                        "в формате Excel-файла.\n\n*Внимание! "
                        "Необходимо отправить список со всеми номерами. "
                        "Если в каком-то поле будет ошибка, то система "
                        "подскажет, где необходимо внести изменения.*\n\n"
                        "_Примечание: все изменения фиксируются "
                        "системой логирования._",
                parse_mode='MarkDown')
            print(doc_id)
            await state.update_data(upload_number_excel=True)
        else:
            await message.answer(text='У Вас нет доступа к этой команде!')
        await message.delete()


@dp.message(ChatTypeFilter('private'), F.document)
async def handle_excel_document(message: types.Message, state: FSMContext):
    if await check_chat_existence(message.from_user.id):
        if message.from_user.id in [497503958, 1125759577]:
            data = await state.get_data()
            is_ready = data.get('upload_number_excel')
            if is_ready:
                if message.document.mime_type == 'application/vnd.openxmlformats-' \
                                                 'officedocument.spreadsheetml.sheet':
                    file_info = await bot.get_file(message.document.file_id)
                    file_path = file_info.file_path
                    file_bytes = await bot.download_file(file_path)
                    text = await read_excel(file_bytes, message.from_user.id)

                    if "Данные были успешно загружены!" in text:
                        await state.update_data(upload_number_excel=False)

                    await message.answer(text=text, parse_mode='HTML')


async def template_stat_numbers(cp):
    text = "<b>Ежедневная статистика по количеству " \
           "отправленных номеров (чужих и своих)</b>\n\n"

    stat_numbers, total_count = await get_stat_numbers(cp)

    for date, count in stat_numbers:
        text += f"📅 <b>{date}</b> | " \
                f"<b>{compare_count(count)}</b>\n"

    text += f"\nОбщее количество отправленных номеров: " \
            f"<b>{compare_count(total_count)}</b>"
    return text


@dp.message(ChatTypeFilter('private'), Command('get_stat_numbers'))
async def stat_numbers(message: Message, state: FSMContext):
    if await check_chat_existence(message.from_user.id):
        if message.from_user.id in ADMIN_ID:
            current_page = 1
            text = await template_stat_numbers(current_page)

            keyboard = await get_keyboard_stat_numbers(current_page)

            sent_message = await message.answer(text=text, parse_mode='HTML',
                                                reply_markup=keyboard)
            sent_message_id = sent_message.message_id
            await state.update_data({f'{sent_message_id}': 1})
        else:
            await message.answer(text='У Вас нет доступа к этой команде!')
        await message.delete()


@dp.message(ChatTypeFilter('private'), Command('get_general_activity'))
async def general_activity(message: Message):
    if await check_chat_existence(message.from_user.id):
        if message.from_user.id in ADMIN_ID:
            s_key = StorageKey(bot_id=bot.id, chat_id=0,
                               user_id=0)

            data = await dp.storage.get_data(key=s_key)

            if data and data.get('activity_users'):
                text = data.get('activity_users')

            else:
                text = "<b>Общая активность</b>\n\n" \
                       "Список отображает активность пользователей " \
                       "по вводу номеров\n\n"
                users = await get_general_activity()

                for user in users:

                    chat = await check_chat_existence(user[0])

                    if chat and chat.type == 'private':
                        first_name = chat.first_name
                        last_name = chat.last_name
                        username = chat.username
                        text += f'👤<b>{first_name} ' \
                                f'{last_name if last_name else ""}</b> ' \
                                f'{"".join(["@", username]) if username else ""} '\
                                \
                                f'| {compare_count(user[1])} ' \
                                f'<a href="tg://user?id={user[0]}">📧</a> \n'
                    else:
                        text += f'👤<b>{user[0]}</b> ' \
                                \
                                f'| {compare_count(user[1])} ' \
                                f'<a href="tg://user?id={user[0]}">📧</a> \n'
                await dp.storage.update_data(
                    key=s_key,
                    data={'activity_users': text})
            current_page = 1
            keyboard = await get_active_user_keyboard(current_page)

            await message.answer(text=text, parse_mode='HTML')

            #
            # for first_name, last_name, count in users:
            #     text += f"{first_name} {last_name} | {compare_count(count)}"
        else:
            await message.answer(text='У Вас нет доступа к этой команде!')
        await message.delete()


async def template_upload_excel_log(cp):
    text = "*История списка номеров*\n"
    text += "Содержит информацию об изменениях номеров в списке " \
            "(добавленных и удалённых)\n\n"
    log_uploaded_numbers = await get_log_numbers_upload(cp)

    user_ids = {}

    for log_up_num in log_uploaded_numbers:
        if user_ids.get(str(log_up_num[0])) is None:

            chat = await check_chat_existence(log_up_num[0])

            if chat and chat.type == 'private':
                user_ids[f'{log_up_num[0]}'] = chat.first_name
            else:
                user_ids[f'{log_up_num[0]}'] = f'(Пользователь не в боте) id: {log_up_num[0]}'

        text += f"[{user_ids[f'{log_up_num[0]}']}]" \
                f"(tg://user?id={log_up_num[0]}) {log_up_num[3]}\n"

        text += f"Добавленные номера\n{log_up_num[1]}\n" if log_up_num[
            1] else ''

        text += f"Удалённые номера\n{log_up_num[2]}\n\n" if log_up_num[
            2] else ''
    return text


@dp.message(ChatTypeFilter('private'), Command('log'))
async def story_log(message: Message, state: FSMContext):
    if await check_chat_existence(message.from_user.id):
        if message.from_user.id in ADMIN_ID:
            text = "*История списка номеров*\n"
            text += "Содержит информацию об изменениях номеров в списке " \
                    "(добавленных и удалённых)\n\n"
            current_page = 1
            text = await template_upload_excel_log(current_page)

            keyboard = await get_keyboard_upload_excel(current_page)

            if len(text) > 4095:
                for x in range(0, len(text), 4095):
                    sent_message = await message.answer(text=text[x:x+4095],
                                                        parse_mode='markdown'
                                                        )

            else:
                sent_message = await message.answer(text=text, parse_mode='markdown'
                                                    )

            await refresh_keyboard(bot, message.from_user.id,
                                   sent_message.message_id, keyboard)

            sent_message_id = sent_message.message_id
            await state.update_data({f'{sent_message_id}': 1})

        else:
            await message.answer('У Вас нет доступа к команде!')
        await message.delete()


@dp.message(ChatTypeFilter('private'), F.photo)
async def handle_photo(message: Message):
    if await check_chat_existence(message.from_user.id):
        photo = message.photo[-1]
        photo_bytes = await get_photo_bytes(photo)

        if photo_bytes:
            number_auto, img = get_number_auto(photo_bytes)
            await message.answer(text=number_auto)


@dp.message(ChatTypeFilter('private'), F.text)
async def handle_auto_number(message: Message):
    if await check_chat_existence(message.from_user.id):
        pattern = r'^(?:[А-ЯA-Z]|[а-яa-z])\d{3}' \
                  r'(?:[А-ЯA-Z]|[а-яa-z]){2}\d{1,3}$'
        if re.match(pattern, message.text) is not None:
            translation_table = str.maketrans("АВЕКМНОРСТУХ", "ABEKMHOPCTYX")
            number = message.text.upper()
            translated_text = number.translate(translation_table)

            auto_number_id, is_own, is_archive = await get_auto_number_id(translated_text)
            if not auto_number_id:
                auto_number_id = await add_auto_number(translated_text, False)

            result = await add_log_history(message.from_user.id, auto_number_id)
            is_us_or_not = "🟢" if is_own else "🔴"
            if result:
                await message.answer(
                    f"Благодарим за отправку автомобильного номера "
                    f"<b>{translated_text}</b> {is_us_or_not}\n\n"
                    f"<i>Время фиксации: {get_time_now()}</i>", parse_mode="HTML")
                # reset redis data
                s_key = StorageKey(bot_id=bot.id, chat_id=0,
                                   user_id=0)
                await dp.storage.update_data(
                    key=s_key,
                    data={'activity_users': None})
            else:
                await message.answer('Сегодня этот номер уже был зафиксирован')
        else:
            await message.answer(
                f"<b>Ошибка!</b>\nВы ввели: <b>{message.text}</b>"
                f"\nПринимаются номера только "
                f"российского формата. Повторите ввод.", parse_mode="HTML")


async def update_flood_start_time(s_key, duration=2):
    """Update the start time of anti-flood for the user.

    :param s_key: StorageKey instance
    :param duration: Anti-flood duration in seconds
    :return: None.
    """
    current_time = int(time.time())
    await dp.storage.update_data(
        key=s_key,
        data={f"{s_key.user_id}_start": current_time + duration})


async def get_flood_start_time(s_key):
    """Get start time of anti-flood for the user.

    :param s_key: StorageKey instance
    :return: Start time of anti-flood or None if not in anti-flood
    """
    data = await dp.storage.get_data(key=s_key)
    if data:
        return data.get(f'{s_key.user_id}_start')
    return None


async def is_flood(bot_id, chat_id, user_id):
    """Check if the user is in anti-flood.

    :param bot_id: Bot id
    :param chat_id: Chat id
    :param user_id: User id
    :return: True if flood, False otherwise
    """
    s_key = StorageKey(bot_id=bot_id, chat_id=chat_id,
                       user_id=user_id)

    start_time = await get_flood_start_time(s_key)
    if start_time is None or start_time < int(time.time()):
        await update_flood_start_time(s_key)
        return False
    return True


@dp.message.outer_middleware()
async def anti_flood(
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any]):
    """Anti_flood system for control user.

    :param handler: Callable[[types.Message, dict[str, Any]], Awaitable[Any]]
    :param event: types.Message
    :param data: dict[str, Any]
    :return: await handler(event, data)
    """
    status_flood = await is_flood(bot.id, event.chat.id, event.from_user.id)

    if status_flood:
        return

    return await handler(event, data)


@dp.callback_query(
    F.data.in_({'plate_numbers', 'numbers_left', 'numbers_right'}))
async def plate_numbers(query: types.CallbackQuery,
                        state: FSMContext):
    await state.update_data(message_id=query.message.message_id)
    if query.data == "plate_numbers":
        current_page = 1
        await state.update_data({f'{query.message.message_id}': current_page})
        keyboard = await get_add_plate_keyboard(False, False, current_page)

        await refresh_keyboard(bot, query.message.chat.id,
                               query.message.message_id, keyboard)

    elif query.data == "numbers_left":
        data = await state.get_data()
        cp = data.get(f'{query.message.message_id}')
        is_own = data.get(f'{query.message.message_id}_is_own')
        is_archive = data.get(f'{query.message.message_id}_is_archive')
        if cp > 1:
            cp -= 1
            await state.update_data({f'{query.message.message_id}': cp})

        keyboard = await get_add_plate_keyboard(is_own, is_archive, cp)

        await refresh_keyboard(bot, query.message.chat.id,
                               query.message.message_id, keyboard)

    elif query.data == "numbers_right":
        data = await state.get_data()
        cp = data.get(f'{query.message.message_id}')
        is_own = data.get(f'{query.message.message_id}_is_own')
        is_archive = data.get(f'{query.message.message_id}_is_archive')

        cp += 1
        await state.update_data({f'{query.message.message_id}': cp})
        keyboard = await get_add_plate_keyboard(is_own, is_archive, cp)
        await refresh_keyboard(bot, query.message.chat.id,
                               query.message.message_id, keyboard)


@dp.callback_query(F.data.in_({'stat_numbers_left', 'stat_numbers_right'}))
async def stat_numbers_arrow(query: types.CallbackQuery, state: FSMContext):
    if await check_chat_existence(query.from_user.id):
        if query.data == 'stat_numbers_left':
            data = await state.get_data()
            cp = data.get(f'{query.message.message_id}')
            if cp > 1:
                cp -= 1
                await state.update_data({f'{query.message.message_id}': cp})

            text = await template_stat_numbers(cp)

            keyboard = await get_keyboard_stat_numbers(cp)

            await refresh_keyboard_and_text(bot, query.message.chat.id,
                                   query.message.message_id, text, keyboard)

        elif query.data == "stat_numbers_right":
            data = await state.get_data()
            cp = data.get(f'{query.message.message_id}')

            cp += 1
            await state.update_data({f'{query.message.message_id}': cp})
            text = await template_stat_numbers(cp)
            keyboard = await get_keyboard_stat_numbers(cp)
            await refresh_keyboard_and_text(bot, query.message.chat.id,
                                            query.message.message_id, text,
                                            keyboard)


@dp.callback_query(F.data.in_({'upload_excel_left', 'upload_excel_right'}))
async def upload_excel_arrow(query: types.CallbackQuery, state: FSMContext):
    if await check_chat_existence(query.from_user.id):
        if query.data == 'upload_excel_left':
            data = await state.get_data()
            cp = data.get(f'{query.message.message_id}')
            if cp > 1:
                cp -= 1
                await state.update_data({f'{query.message.message_id}': cp})

            text = await template_upload_excel_log(cp)

            keyboard = await get_keyboard_upload_excel(cp)

            await refresh_keyboard_and_text(bot, query.message.chat.id,
                                            query.message.message_id, text,
                                            keyboard, "markdown")

        elif query.data == "upload_excel_right":
            data = await state.get_data()
            cp = data.get(f'{query.message.message_id}')

            cp += 1
            await state.update_data({f'{query.message.message_id}': cp})
            text = await template_upload_excel_log(cp)
            keyboard = await get_keyboard_upload_excel(cp)
            await refresh_keyboard_and_text(bot, query.message.chat.id,
                                            query.message.message_id, text,
                                            keyboard, "markdown")


@dp.callback_query(F.data.startswith('get_numbers_data:'))
async def numbers_detail(query: types.CallbackQuery):
    if await check_chat_existence(query.from_user.id):
        data = query.data.split(':')
        for number_plate in data[1:]:
            dates = await get_number_detail(number_plate)

            is_archive = await is_in_archive_number(number_plate)

            text = f'Все фиксации номера <b>{number_plate}</b>\n\n'

            for numeric, date in enumerate(dates, 1):
                text += f'📅 <b>{date}</b>\n'

            await bot.send_message(
                chat_id=query.from_user.id, text=text, parse_mode="HTML",
                reply_markup=
                await get_keyboard_add_archive(number_plate) if not
                is_archive else types.InlineKeyboardMarkup(
                    inline_keyboard=
                    [
                        [
                            types.InlineKeyboardButton(
                                text='ℹ',
                                callback_data=f'info_change_log:{number_plate}')
                        ]
                    ]
                ))


@dp.callback_query(F.data.startswith('info_change_log'))
async def info_log_change_number(query: types.CallbackQuery):
    if await check_chat_existence(query.from_user.id):
        data = query.data.split(':')
        number_plate = data[-1]

        action_annotation = {'add': 'Добавление в базу',
                               'delete': 'Удаление из базы',
                               'archive': 'Добавление в архив'}

        result = await get_number_detail_info_change(number_plate)

        text = f'История действий с номером <b>{number_plate}</b>\n\n'

        user_ids = {}

        for story in result:
            if user_ids.get(str(story[0])) is None:
                ##
                chat = await check_chat_existence(story[0])
                if chat:
                    if chat.type == 'private':
                        user_ids[f'{story[0]}'] = chat.first_name
                        username = chat.username
                        text += f"<b>{story[3]}</b> {action_annotation.get(story[1].value)} " \
                                f"<a href='tg://user?id={story[0]}'>{chat.first_name if chat.first_name else ''}</a> " \
                                f"{f'@{username}' if username else ''}\n\n"
                        print("TEXT", text)
                else:

                    user_id = story[0]
                    text += f"<b>{story[3]}</b> {action_annotation.get(story[1].value)} " \
                            f"<i><a href='tg://user?id={story[0]}'>(Пользователя нет в боте)</a></i> " \
                            f"{f'tg id: {user_id}' if user_id else ''}\n\n"
                    print("TEXT", text)

        await bot.send_message(chat_id=query.from_user.id, text=text, parse_mode="HTML")


@dp.callback_query(F.data.startswith('add_archive:'))
async def set_archive(query: types.CallbackQuery):
    if await check_chat_existence(query.from_user.id):
        data = query.data.split(':')
        number_plate = data[-1]

        is_archive = await is_in_archive_number(number_plate)
        if is_archive:
            await bot.send_message(query.from_user.id,
                                   text=f"Номер <b>{number_plate}</b> уже добавлен в архив!",
                                   parse_mode='HTML')
        else:
            await bot.send_message(
                chat_id=query.from_user.id,
                text=f'Вы уверены, что хотите добавить номер <b>{number_plate}</b> в архив?',
                reply_markup=await get_keyboard_yes_or_no_archive(number_plate),
                parse_mode="HTML")


@dp.callback_query(F.data.startswith('confirm_add_archive_btn:'))
async def confirm_set_archive(query: types.CallbackQuery):
    if await check_chat_existence(query.from_user.id):
        data = query.data.split(':')
        number_plate = data[-1]

        is_archive = await is_in_archive_number(number_plate)

        if is_archive:
            await bot.send_message(query.from_user.id,
                                   text=f"Номер <b>{number_plate}</b> уже добавлен в архив!",
                                   parse_mode='HTML')
        else:
            await set_archive_db(query.from_user.id, number_plate)

            await bot.send_message(chat_id=query.from_user.id,
                                   text=f'Номер <b>{number_plate}</b> был добавлен в архив!', parse_mode='HTML')


@dp.callback_query(F.data.startswith('disable_add_archive_btn:'))
async def disable_set_archive(query: types.CallbackQuery):
    if await check_chat_existence(query.from_user.id):
        data = query.data.split(':')
        number_plate = data[-1]

        await bot.send_message(chat_id=query.from_user.id, text=f'Отмена помещения номера <b>{number_plate}</b> в архив!', parse_mode='HTML')
        await bot.delete_message(chat_id=query.from_user.id, message_id=query.message.message_id)


async def send_day_stat():
    users = await get_active_users()
    actual_day, today_numbers, all_numbers, other_numbers = \
        await get_end_day_stats()
    # for user in users:
    try:
        if await check_chat_existence(-1001626590170):
            await bot.send_message(
                chat_id=-1001626590170,
                message_thread_id=2,
                text=f'Отчёт за *{actual_day}*\n'
                     f'Всего проверено {compare_count(today_numbers)} '
                     f'номеров.\n'
                     f'Обнаружено незарегистрированных {compare_count(other_numbers)}.\n\n'
                     f'Благодарим за вашу активность!\n\n'
                     f'Для желающих принять участие: [Нажмите сюда](https://t.me/checker_autobot?start=start)',
                parse_mode="markdown")
            print('Сообщение отправлено')
            for user in ADMIN_ID:
                if await check_chat_existence(user):
                    await bot.send_message(
                        chat_id=user,
                        text=f'Отчёт за *{actual_day}*\n'
                             f'Всего проверено {compare_count(today_numbers)} '
                             f'номеров.\n'
                             f'Обнаружено незарегистрированных {compare_count(other_numbers)}.\n\n'
                             f'Благодарим за вашу активность!\n\n',
                        parse_mode="markdown")
                    print(f'Сообщение отправлено {user}')
    except Exception:
        print('error')


async def scheduler():
    aioschedule.every().day.at("23:59").do(send_day_stat)
    while True:
        await aioschedule.run_pending()
        await asyncio.sleep(1)


async def on_startup():
    print('Bot is start')
    asyncio.create_task(scheduler())
    await set_commands()


async def on_shutdown(dp):
    await dp.storage.close()
    await bot.session.close()


async def check_chat_existence(chat_id):
    try:
        chat = await bot.get_chat(chat_id)
        return chat
    except (exceptions.TelegramBadRequest, exceptions.TelegramNotFound):
        return False


async def main():
    dp.startup.register(on_startup)
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await on_shutdown(dp)


if __name__ == "__main__":
    asyncio.run(main())
