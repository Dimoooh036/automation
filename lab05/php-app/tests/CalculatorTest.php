<?php

declare(strict_types=1);

use PHPUnit\Framework\TestCase;

final class CalculatorTest extends TestCase
{
    private Calculator $calculator;

    protected function setUp(): void
    {
        $this->calculator = new Calculator();
    }

    public function testAdd(): void
    {
        self::assertSame(4.0, $this->calculator->add(2, 2));
        self::assertSame(0.0, $this->calculator->add(-2, 2));
    }

    public function testSubtract(): void
    {
        self::assertSame(3.0, $this->calculator->subtract(5, 2));
    }

    public function testMultiply(): void
    {
        self::assertSame(6.0, $this->calculator->multiply(2, 3));
    }

    public function testDivide(): void
    {
        self::assertSame(2.5, $this->calculator->divide(5, 2));
    }

    public function testDivideByZeroThrowsException(): void
    {
        $this->expectException(DivisionByZeroError::class);
        $this->calculator->divide(1, 0);
    }
}
