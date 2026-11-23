<?php

declare(strict_types=1);

use PHPUnit\Framework\TestCase;

final class StrUtilsTest extends TestCase
{
    private StrUtils $strings;

    protected function setUp(): void
    {
        $this->strings = new StrUtils();
    }

    public function testCyrillicPalindrome(): void
    {
        self::assertTrue($this->strings->isPalindrome('А роза упала на лапу Азора'));
    }

    public function testNonPalindrome(): void
    {
        self::assertFalse($this->strings->isPalindrome('hello world'));
    }

    public function testWordCount(): void
    {
        self::assertSame(3, $this->strings->wordCount('one two three'));
    }

    public function testWordCountForBlankString(): void
    {
        self::assertSame(0, $this->strings->wordCount('   '));
    }
}
