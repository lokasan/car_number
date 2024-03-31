import re
import os
import json
import pytz
import datetime
import openpyxl

from db import add_auto_number, update_plate_numbers_list


def check_correct(value):
    pattern = r'^(?:[А-ЯA-Z]|[а-яa-z])\d{3}' \
              r'(?:[А-ЯA-Z]|[а-яa-z]){2}\d{2,3}$'
    if re.match(pattern, value) is not None:
        return True


def change_format(value):
    translation_table = str.maketrans("АВЕКМНОРСТУХ", "ABEKMHOPCTYX")
    number = value.upper()
    return number.translate(translation_table)


def get_current_time(timezone='Europe/Moscow'):
    moscow_tz = pytz.timezone(timezone)
    current_time = datetime.datetime.now(moscow_tz)
    return current_time.strftime('%d%m%Y%H%M%S')


async def read_excel(file_bytes, tg_user_id):
    try:
        errors = []

        plate_numbers = []

        workbook = openpyxl.load_workbook(file_bytes)
        sheet = workbook.active
        for row_number, row in enumerate(sheet.iter_rows(), 1):
            print(row[0].value)
            if row[0].value is None:
                continue
            cell = row[0]
            is_correct = check_correct(str(cell.value).strip())

            if is_correct:
                plate_numbers.append(change_format(str(cell.value)))
                # change_format to latin
            else:
                errors.append((row_number, str(cell.value)))
        if errors:
            text = 'Были найдены ошибки! Исправьте их и отправьте файл заново:\n'

            for error in errors:
                text += f'Строка <b>{error[0]}</b> значение <b>{error[1]}</b>\n'

            text += '\nПринимаются только российские номера (не служебные)'

            return text

        actual_number = list(set(plate_numbers))

        await update_plate_numbers_list(tg_user_id, actual_number)

        file_path = f'log_history{os.sep}{get_current_time()}' \
                    f'_{tg_user_id}_update_numbers.json'

        data = {'update_numbers': {
            'tg_user_id': tg_user_id,
            'numbers': actual_number
        }}

        with open(file_path, 'w+', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        # Create function get from database info plate of numbers
        # Create check

        return "Данные были успешно загружены!"

    except Exception as e:
        print(f"Ошибка при чтении строки из Excel-файла: {e}")

