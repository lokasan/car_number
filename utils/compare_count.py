COUNT_PARKING = {'1': '1️⃣', '2': '2️⃣', '3': '3️⃣', '4': '4️⃣',
                 '5': '5️⃣', '6': '6️⃣', '7': '7️⃣',
                 '8': '8️⃣', '9': '9️⃣', '0': '0️⃣'}


def compare_count(count):
    if count is None:
        count = '0'
    count_s = list(str(count))
    return "".join([COUNT_PARKING[s] for s in count_s])
