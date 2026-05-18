"""Конвертеры SPICE-форматов (T006 Resolved #4, T102)."""

from __future__ import annotations

import re

_PWRS_HEAD = re.compile(r'(?<![A-Za-z0-9_])pwrs\s*\(', re.IGNORECASE)


def convert_ayumi_to_ngspice(text: str) -> str:
    """
    Заменить `^` на `**` во всём тексте Ayumi-модели.

    Ayumi-модели используют PSpice-синтаксис степени (`x^y`),
    ngspice требует HSPICE-style (`x**y`). Глобальная замена
    безопасна для всех существующих Ayumi-моделей: `^` не
    встречается в комментариях (Ayumi-комментарии — `*`) и в
    строковых литералах SPICE их нет.

    Known limitation (W2): если пользователь добавит в комментарий
    что-то вроде `* P = U^2/R` — `^` будет искажён. На реальных
    моделях это не случается; правится через ручной edit файла.
    """
    return text.replace('^', '**')


def convert_pwrs_to_ngspice(text: str) -> str:
    """
    Заменить PSpice `PWRS(x, y)` на ngspice `sgn(x)*pwr(abs(x), y)`.

    PWRS(x,y) = sign(x) · |x|^y — signed power, PSpice extension.
    ngspice 45 без `--compatibility-mode=psa` падает с
    `no such function 'pwrs'`. Замена функционально эквивалентна и
    не требует переключения симулятора в pspice-mode.

    Парсер char-by-char с балансом скобок: поддерживает вложенные
    скобки в аргументах (V(P,K), V(7) и т.п.), несколько PWRS в
    одном выражении, рекурсивно обрабатывает PWRS внутри PWRS.
    Регистр игнорируется. `MYPWRS(` и подобные identifier-суффиксы
    не матчатся.

    Идемпотентна: после первого прохода в результате нет PWRS,
    повторное применение → no-op.
    """
    out: list[str] = []
    pos = 0
    while True:
        match = _PWRS_HEAD.search(text, pos)
        if match is None:
            out.append(text[pos:])
            break
        out.append(text[pos : match.start()])
        depth = 1
        comma_at = -1
        end_at = -1
        i = match.end()
        while i < len(text):
            char = text[i]
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
                if depth == 0:
                    end_at = i
                    break
            elif char == ',' and depth == 1 and comma_at == -1:
                comma_at = i
            i += 1
        if end_at == -1 or comma_at == -1:
            # Парный `)` / `,` не найден — оставляем сегмент как есть и
            # сдвигаемся за `pwrs(`, чтобы не уйти в бесконечный цикл.
            out.append(text[match.start() : match.end()])
            pos = match.end()
            continue
        expr1 = convert_pwrs_to_ngspice(text[match.end() : comma_at].strip())
        expr2 = convert_pwrs_to_ngspice(text[comma_at + 1 : end_at].strip())
        out.append(f'sgn({expr1})*pwr(abs({expr1}),{expr2})')
        pos = end_at + 1
    return ''.join(out)
