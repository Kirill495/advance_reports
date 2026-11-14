"""Детерминированная транслитерация латинского ФИО в кириллицу (паспортная схема).

Используется для билетов с заграничным паспортом, где ФИО напечатано латиницей.
Правила соответствуют паспортной транслитерации (GOST R 52535.1-2006): «iu»→ю,
«ia»→я, «iy»→ий, а также распространённые диграфы «ch»→ч, «sh»→ш, «ts»→ц и т.д.

Замечание: библиотека `transliterate` здесь не подходит — её базовый ru-маппинг
соответствует ISO 9 («й»→j, «ы»→y, «ю»→ju), из-за чего «Sivitskiy»→«Сивицкиы»,
«Krasiukova»→«Красиукова», что не совпадает с паспортной транслитерацией РЖД.
"""

# Диграфы (сначала самые длинные). Ключи в нижнем регистре.
_DIGRAPHS = [
    ("shch", "щ"), ("sch", "щ"),
    ("zh", "ж"), ("kh", "х"),
    ("ts", "ц"), ("ch", "ч"), ("sh", "ш"),
    ("yu", "ю"), ("ya", "я"),
    ("iu", "ю"), ("ia", "я"),
    ("iy", "ий"), ("yy", "ый"), ("oy", "ой"),
    ("ey", "ей"), ("ay", "ай"), ("uy", "уй"),
]

# Одиночные буквы: латиница → кириллица (нижний регистр).
_SINGLE = str.maketrans({
    "a": "а", "b": "б", "v": "в", "g": "г", "d": "д",
    "e": "е", "z": "з", "i": "и", "j": "й", "k": "к",
    "l": "л", "m": "м", "n": "н", "o": "о", "p": "п",
    "r": "р", "s": "с", "t": "т", "u": "у", "f": "ф",
    "h": "х", "c": "ц", "y": "ы",
})


def to_cyrillic_fio(latin_name):
    """'GRACHEV ALEKSANDR DMITRIEVICH' → {'surname':'Грачев','name':'Александр','patronymic':'Дмитриевич'}.

    Возвращает None, если ввод пустой.
    """
    words = (latin_name or "").split()
    if not words:
        return None
    cyr_words = []
    for w in words:
        s = w.lower()
        for latin, cyr in _DIGRAPHS:
            s = s.replace(latin, cyr)
        s = s.translate(_SINGLE)
        cyr_words.append(s.title())
    return {
        "surname": cyr_words[0],
        "name": cyr_words[1] if len(cyr_words) > 1 else "",
        "patronymic": cyr_words[2] if len(cyr_words) > 2 else "",
    }
