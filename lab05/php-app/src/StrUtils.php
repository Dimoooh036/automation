<?php

/**
 * Модуль для работы со строками — второй тестируемый модуль проекта.
 */
class StrUtils
{
    /**
     * Возвращает true, если строка — палиндром
     * (сравниваются только буквы и цифры, регистр не учитывается).
     */
    /**
     * strtolower в PHP работает только с ASCII, поэтому для кириллицы
     * используем явную таблицу соответствия (без расширения mbstring).
     */
    private const CYRILLIC_UPPER_TO_LOWER = [
        'А' => 'а', 'Б' => 'б', 'В' => 'в', 'Г' => 'г', 'Д' => 'д',
        'Е' => 'е', 'Ё' => 'ё', 'Ж' => 'ж', 'З' => 'з', 'И' => 'и',
        'Й' => 'й', 'К' => 'к', 'Л' => 'л', 'М' => 'м', 'Н' => 'н',
        'О' => 'о', 'П' => 'п', 'Р' => 'р', 'С' => 'с', 'Т' => 'т',
        'У' => 'у', 'Ф' => 'ф', 'Х' => 'х', 'Ц' => 'ц', 'Ч' => 'ч',
        'Ш' => 'ш', 'Щ' => 'щ', 'Ъ' => 'ъ', 'Ы' => 'ы', 'Ь' => 'ь',
        'Э' => 'э', 'Ю' => 'ю', 'Я' => 'я',
    ];

    public function isPalindrome(string $s): bool
    {
        // Убираем всё, кроме букв и цифр (поддержка Unicode через PCRE)
        $normalized = preg_replace('/[^\p{L}\p{N}]/u', '', $s);
        $normalized = strtr(strtolower((string)$normalized), self::CYRILLIC_UPPER_TO_LOWER);
        if ($normalized === '') {
            return false;
        }
        // strrev работает побайтово и ломает многобайтовый UTF-8,
        // поэтому разбиваем на символы через PCRE и разворачиваем массив
        $chars = preg_split('//u', $normalized, -1, PREG_SPLIT_NO_EMPTY);
        $reversed = implode('', array_reverse($chars));
        return $normalized === $reversed;
    }

    /**
     * Считает слова в строке (слова разделены пробелами).
     */
    public function wordCount(string $s): int
    {
        $trimmed = trim($s);
        if ($trimmed === '') {
            return 0;
        }
        return count(preg_split('/\s+/', $trimmed));
    }
}
