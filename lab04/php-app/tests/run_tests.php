<?php

/**
 * Модульные тесты проекта php-app.
 *
 * Запуск:  php tests/run_tests.php
 * Код возврата: 0 — все тесты прошли, 1 — есть провалы.
 * Вместо Composer/PHPUnit используется простой self-contained
 * рантайм (на агенте установлен только php-cli).
 */

require_once __DIR__ . '/../src/Calculator.php';
require_once __DIR__ . '/../src/StrUtils.php';

class TestRunner
{
    private int $passed = 0;
    private int $failed = 0;

    public function assertSame($expected, $actual, string $name): void
    {
        if ($expected === $actual) {
            $this->passed++;
            echo "[PASS] {$name}\n";
        } else {
            $this->failed++;
            echo "[FAIL] {$name}: expected " . var_export($expected, true)
                . ", got " . var_export($actual, true) . "\n";
        }
    }

    public function assertTrue(bool $condition, string $name): void
    {
        $this->assertSame(true, $condition, $name);
    }

    public function summary(): int
    {
        echo "\n{$this->passed} passed, {$this->failed} failed\n";
        return $this->failed === 0 ? 0 : 1;
    }
}

$t = new TestRunner();
$calc = new Calculator();
$str = new StrUtils();

// --- Calculator ---
$t->assertSame(4.0, $calc->add(2, 2), 'Calculator::add(2, 2) == 4');
$t->assertSame(0.0, $calc->add(-2, 2), 'Calculator::add(-2, 2) == 0');
$t->assertSame(3.0, $calc->subtract(5, 2), 'Calculator::subtract(5, 2) == 3');
$t->assertSame(6.0, $calc->multiply(2, 3), 'Calculator::multiply(2, 3) == 6');
$t->assertSame(2.5, $calc->divide(5, 2), 'Calculator::divide(5, 2) == 2.5');

// деление на ноль должно бросать исключение
try {
    $calc->divide(1, 0);
    $t->assertTrue(false, 'Calculator::divide(1, 0) throws DivisionByZeroError');
} catch (DivisionByZeroError $e) {
    $t->assertTrue(true, 'Calculator::divide(1, 0) throws DivisionByZeroError');
}

// --- StrUtils ---
$t->assertTrue($str->isPalindrome('А роза упала на лапу Азора'), 'StrUtils::isPalindrome(palindrome) == true');
$t->assertTrue(!$str->isPalindrome('hello world'), 'StrUtils::isPalindrome("hello world") == false');
$t->assertSame(3, $str->wordCount('one two three'), 'StrUtils::wordCount("one two three") == 3');
$t->assertSame(0, $str->wordCount('   '), 'StrUtils::wordCount("   ") == 0');

exit($t->summary());
