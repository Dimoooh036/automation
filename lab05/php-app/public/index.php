<?php

declare(strict_types=1);

/**
 * Точка входа PHP приложения, размещаемого на тестовом сервере.
 * Работает и с Composer autoload, и без него.
 */

$autoload = __DIR__ . '/../vendor/autoload.php';

if (is_file($autoload)) {
    require_once $autoload;
} else {
    require_once __DIR__ . '/../src/Calculator.php';
    require_once __DIR__ . '/../src/StrUtils.php';
}

$calculator = new Calculator();
$strings = new StrUtils();

$checks = [
    '2 + 2 = 4' => $calculator->add(2, 2) === 4.0,
    '5 / 2 = 2.5' => $calculator->divide(5, 2) === 2.5,
    'Деление на ноль' => false,
    'Палиндром «А роза упала на лапу Азора»' => $strings->isPalindrome('А роза упала на лапу Азора'),
    'Слов в строке «one two three»' => $strings->wordCount('one two three') === 3,
];

try {
    $calculator->divide(1, 0);
} catch (DivisionByZeroError) {
    $checks['Деление на ноль'] = true;
}

$passed = count(array_filter($checks));
$total = count($checks);

function e(string $value): string
{
    return htmlspecialchars($value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}
?>
<!doctype html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>PHP App — lab05</title>
    <style>
        body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; margin: 0; background: #f4f6fb; color: #1f2937; }
        main { max-width: 760px; margin: 40px auto; padding: 32px; background: #fff; border-radius: 14px; box-shadow: 0 12px 32px rgba(15, 23, 42, .08); }
        h1 { margin-top: 0; font-size: 1.7rem; }
        .badge { display: inline-block; padding: 6px 12px; border-radius: 999px; background: #dcfce7; color: #166534; font-weight: 600; }
        ul { list-style: none; padding: 0; }
        li { display: flex; justify-content: space-between; gap: 16px; padding: 10px 0; border-bottom: 1px solid #e5e7eb; }
        li:last-child { border-bottom: 0; }
        .ok { color: #15803d; font-weight: 600; }
        .fail { color: #b91c1c; font-weight: 600; }
        code { background: #f3f4f6; padding: 2px 6px; border-radius: 6px; }
        footer { margin-top: 24px; color: #6b7280; font-size: .9rem; }
    </style>
</head>
<body>
<main>
    <h1>PHP-приложение развёрнуто на тестовом сервере</h1>
    <p><span class="badge"><?= $passed ?> / <?= $total ?> проверок пройдено</span></p>

    <ul>
        <?php foreach ($checks as $name => $ok): ?>
            <li>
                <span><?= e($name) ?></span>
                <span class="<?= $ok ? 'ok' : 'fail' ?>"><?= $ok ? 'OK' : 'FAIL' ?></span>
            </li>
        <?php endforeach; ?>
    </ul>

    <footer>
        PHP <?= e(PHP_VERSION) ?> · сервер <?= e($_SERVER['SERVER_NAME'] ?? 'test-server') ?> ·
        хост <code><?= e(gethostname() ?: 'unknown') ?></code>
    </footer>
</main>
</body>
</html>
