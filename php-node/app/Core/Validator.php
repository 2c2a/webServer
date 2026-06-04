<?php

declare(strict_types=1);

namespace App\Core;

/**
 * 输入验证器
 */
class Validator
{
    /** @var array 待验证数据 */
    private readonly array $data;

    /** @var array 验证规则 */
    private readonly array $rules;

    /** @var array<string, string[]> 验证错误 */
    private array $errors = [];

    /** @var array<string, string> 自定义错误消息 */
    private array $customMessages = [];

    /** @var array<string, string> 字段显示名称 */
    private array $fieldNames = [];

    public function __construct(array $data, array $rules, array $messages = [], array $fieldNames = [])
    {
        $this->data = $data;
        $this->rules = $rules;
        $this->customMessages = $messages;
        $this->fieldNames = $fieldNames;
    }

    /**
     * 创建验证器实例
     */
    public static function make(array $data, array $rules, array $messages = [], array $fieldNames = []): static
    {
        return new static($data, $rules, $messages, $fieldNames);
    }

    /**
     * 执行验证
     */
    public function validate(): bool
    {
        $this->errors = [];

        foreach ($this->rules as $field => $fieldRules) {
            $fieldRules = is_array($fieldRules) ? $fieldRules : explode('|', $fieldRules);

            foreach ($fieldRules as $rule) {
                $this->applyRule($field, $rule);
            }
        }

        return empty($this->errors);
    }

    /**
     * 验证是否失败
     */
    public function fails(): bool
    {
        if (empty($this->errors)) {
            $this->validate();
        }

        return !empty($this->errors);
    }

    /**
     * 验证是否通过
     */
    public function passes(): bool
    {
        return !$this->fails();
    }

    /**
     * 获取所有错误
     */
    public function errors(): array
    {
        return $this->errors;
    }

    /**
     * 获取第一个错误
     */
    public function firstError(): ?string
    {
        if (empty($this->errors)) {
            return null;
        }

        $firstField = array_key_first($this->errors);
        return $this->errors[$firstField][0] ?? null;
    }

    /**
     * 获取指定字段的第一个错误
     */
    public function first(string $field): ?string
    {
        return $this->errors[$field][0] ?? null;
    }

    /**
     * 获取指定字段的所有错误
     */
    public function get(string $field): array
    {
        return $this->errors[$field] ?? [];
    }

    /**
     * 是否有指定字段的错误
     */
    public function has(string $field): bool
    {
        return isset($this->errors[$field]);
    }

    /**
     * 应用单条验证规则
     */
    private function applyRule(string $field, string $rule): void
    {
        // 解析规则名和参数 (如: min:8 → name=min, params=[8])
        $params = [];
        if (str_contains($rule, ':')) {
            [$rule, $paramStr] = explode(':', $rule, 2);
            $params = explode(',', $paramStr);
        }

        $value = $this->data[$field] ?? null;
        $fieldName = $this->fieldNames[$field] ?? $field;

        $isValid = match ($rule) {
            'required'     => $this->validateRequired($value),
            'email'        => $this->validateEmail($value),
            'min'          => $this->validateMin($value, (int) $params[0]),
            'max'          => $this->validateMax($value, (int) $params[0]),
            'between'      => $this->validateBetween($value, (int) $params[0], (int) ($params[1] ?? 0)),
            'confirmed'    => $this->validateConfirmed($field, $value),
            'regex'        => $this->validateRegex($value, $params[0] ?? ''),
            'in'           => $this->validateIn($value, $params),
            'alpha'        => $this->validateAlpha($value),
            'alphanumeric' => $this->validateAlphanumeric($value),
            'unique'       => $this->validateUnique($field, $value, $params),
            'length'       => $this->validateLength($value, (int) $params[0]),
            'integer'      => $this->validateInteger($value),
            'numeric'      => $this->validateNumeric($value),
            'url'          => $this->validateUrl($value),
            'ip'           => $this->validateIp($value),
            'date'         => $this->validateDate($value),
            default        => true,
        };

        if (!$isValid) {
            $message = $this->customMessages["{$field}.{$rule}"]
                ?? $this->customMessages[$field]
                ?? $this->getDefaultMessage($rule, $fieldName, $params);

            $this->errors[$field][] = $message;
        }
    }

    /**
     * 验证必填
     */
    private function validateRequired(mixed $value): bool
    {
        if ($value === null) {
            return false;
        }
        if (is_string($value) && trim($value) === '') {
            return false;
        }
        if (is_array($value) && empty($value)) {
            return false;
        }
        return true;
    }

    /**
     * 验证邮箱
     */
    private function validateEmail(mixed $value): bool
    {
        if ($value === null || $value === '') {
            return true; // 非必填时允许空
        }
        return filter_var($value, FILTER_VALIDATE_EMAIL) !== false;
    }

    /**
     * 验证最小值/长度
     */
    private function validateMin(mixed $value, int $min): bool
    {
        if ($value === null || $value === '') {
            return true;
        }

        if (is_numeric($value)) {
            return (float) $value >= $min;
        }

        if (is_string($value)) {
            return mb_strlen($value) >= $min;
        }

        if (is_array($value)) {
            return count($value) >= $min;
        }

        return false;
    }

    /**
     * 验证最大值/长度
     */
    private function validateMax(mixed $value, int $max): bool
    {
        if ($value === null || $value === '') {
            return true;
        }

        if (is_numeric($value)) {
            return (float) $value <= $max;
        }

        if (is_string($value)) {
            return mb_strlen($value) <= $max;
        }

        if (is_array($value)) {
            return count($value) <= $max;
        }

        return false;
    }

    /**
     * 验证范围
     */
    private function validateBetween(mixed $value, int $min, int $max): bool
    {
        if ($value === null || $value === '') {
            return true;
        }

        if (is_numeric($value)) {
            $num = (float) $value;
            return $num >= $min && $num <= $max;
        }

        if (is_string($value)) {
            $len = mb_strlen($value);
            return $len >= $min && $len <= $max;
        }

        return false;
    }

    /**
     * 验证确认字段（如密码确认）
     */
    private function validateConfirmed(string $field, mixed $value): bool
    {
        $confirmField = $field . '_confirmation';
        $confirmValue = $this->data[$confirmField] ?? null;

        return $value === $confirmValue;
    }

    /**
     * 验证正则表达式
     */
    private function validateRegex(mixed $value, string $pattern): bool
    {
        if ($value === null || $value === '') {
            return true;
        }

        return preg_match('/' . $pattern . '/', (string) $value) === 1;
    }

    /**
     * 验证值在列表中
     */
    private function validateIn(mixed $value, array $list): bool
    {
        if ($value === null || $value === '') {
            return true;
        }

        return in_array((string) $value, $list, true);
    }

    /**
     * 验证纯字母
     */
    private function validateAlpha(mixed $value): bool
    {
        if ($value === null || $value === '') {
            return true;
        }

        return preg_match('/^[a-zA-Z]+$/', (string) $value) === 1;
    }

    /**
     * 验证字母数字
     */
    private function validateAlphanumeric(mixed $value): bool
    {
        if ($value === null || $value === '') {
            return true;
        }

        return preg_match('/^[a-zA-Z0-9]+$/', (string) $value) === 1;
    }

    /**
     * 验证唯一性（数据库）
     */
    private function validateUnique(string $field, mixed $value, array $params): bool
    {
        if ($value === null || $value === '') {
            return true;
        }

        $table = $params[0] ?? $field;
        $column = $params[1] ?? $field;
        $exceptId = $params[2] ?? null;

        try {
            $db = Database::getInstance();
            $sql = "SELECT 1 FROM \"{$table}\" WHERE \"{$column}\" = :value";
            $sqlParams = [':value' => $value];

            if ($exceptId !== null) {
                $sql .= ' AND id != :except_id';
                $sqlParams[':except_id'] = $exceptId;
            }

            $result = $db->fetch($sql, $sqlParams);
            return $result === null;
        } catch (\Throwable) {
            return true; // 数据库不可用时跳过唯一性检查
        }
    }

    /**
     * 验证固定长度
     */
    private function validateLength(mixed $value, int $length): bool
    {
        if ($value === null || $value === '') {
            return true;
        }

        return mb_strlen((string) $value) === $length;
    }

    /**
     * 验证整数
     */
    private function validateInteger(mixed $value): bool
    {
        if ($value === null || $value === '') {
            return true;
        }

        return filter_var($value, FILTER_VALIDATE_INT) !== false;
    }

    /**
     * 验证数值
     */
    private function validateNumeric(mixed $value): bool
    {
        if ($value === null || $value === '') {
            return true;
        }

        return is_numeric($value);
    }

    /**
     * 验证 URL
     */
    private function validateUrl(mixed $value): bool
    {
        if ($value === null || $value === '') {
            return true;
        }

        return filter_var($value, FILTER_VALIDATE_URL) !== false;
    }

    /**
     * 验证 IP 地址
     */
    private function validateIp(mixed $value): bool
    {
        if ($value === null || $value === '') {
            return true;
        }

        return filter_var($value, FILTER_VALIDATE_IP) !== false;
    }

    /**
     * 验证日期
     */
    private function validateDate(mixed $value): bool
    {
        if ($value === null || $value === '') {
            return true;
        }

        if (!is_string($value)) {
            return false;
        }

        return strtotime($value) !== false;
    }

    /**
     * 获取默认错误消息
     */
    private function getDefaultMessage(string $rule, string $field, array $params): string
    {
        return match ($rule) {
            'required'     => "{$field} 不能为空",
            'email'        => "{$field} 必须是有效的邮箱地址",
            'min'          => "{$field} 最小值为 {$params[0]}",
            'max'          => "{$field} 最大值为 {$params[0]}",
            'between'      => "{$field} 必须在 {$params[0]} 和 {$params[1]} 之间",
            'confirmed'    => "{$field} 两次输入不一致",
            'regex'        => "{$field} 格式不正确",
            'in'           => "{$field} 的值无效",
            'alpha'        => "{$field} 只能包含字母",
            'alphanumeric' => "{$field} 只能包含字母和数字",
            'unique'       => "{$field} 已经存在",
            'length'       => "{$field} 长度必须为 {$params[0]}",
            'integer'      => "{$field} 必须是整数",
            'numeric'      => "{$field} 必须是数字",
            'url'          => "{$field} 必须是有效的 URL",
            'ip'           => "{$field} 必须是有效的 IP 地址",
            'date'         => "{$field} 必须是有效的日期",
            default        => "{$field} 验证失败",
        };
    }
}
