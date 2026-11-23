<?php

declare(strict_types=1);

/**
 * Загрузчик тестов: Composer autoload (PHPUnit) или прямое подключение
 * классов, если зависимости ещё не установлены.
 */

$autoload = __DIR__ . '/../vendor/autoload.php';

if (is_file($autoload)) {
    require_once $autoload;
} else {
    require_once __DIR__ . '/../src/Calculator.php';
    require_once __DIR__ . '/../src/StrUtils.php';
}
