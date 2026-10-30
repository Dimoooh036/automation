<?php

/**
 * Простой калькулятор — тестируемый модуль проекта.
 */
class Calculator
{
    public function add(float $a, float $b): float
    {
        return $a + $b;
    }

    public function subtract(float $a, float $b): float
    {
        return $a - $b;
    }

    public function multiply(float $a, float $b): float
    {
        return $a * $b;
    }

    /**
     * Деление. При делении на ноль выбрасывает DivisionByZeroError.
     */
    public function divide(float $a, float $b): float
    {
        if ($b == 0.0) {
            throw new DivisionByZeroError('Division by zero');
        }
        return $a / $b;
    }
}
