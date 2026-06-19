import { ref, computed, type Ref } from "vue";

type Rule<T> = (value: T, ctx: Record<string, unknown>) => string | null;

export interface FieldRules<T = unknown> {
  rules: Rule<T>[];
  value: Ref<T>;
}

export function useFormValidation(fields: Record<string, FieldRules>) {
  const touched = ref<Record<string, boolean>>({});
  const errors = ref<Record<string, string | null>>({});

  function validateField(key: string): string | null {
    const field = fields[key];
    if (!field) return null;

    for (const rule of field.rules) {
      const msg = rule(field.value.value, {});
      if (msg) {
        errors.value[key] = msg;
        return msg;
      }
    }
    errors.value[key] = null;
    return null;
  }

  function validateAll(): boolean {
    let ok = true;
    for (const key of Object.keys(fields)) {
      touched.value[key] = true;
      if (validateField(key)) ok = false;
    }
    return ok;
  }

  function touch(key: string) {
    touched.value[key] = true;
    validateField(key);
  }

  function reset() {
    touched.value = {};
    errors.value = {};
  }

  const isValid = computed(() => Object.values(errors.value).every((e) => !e));
  const firstErrorKey = computed(() => Object.keys(errors.value).find((k) => errors.value[k]));

  return {
    errors: computed(() => errors.value),
    touched: computed(() => touched.value),
    isValid,
    firstErrorKey,
    validateField,
    validateAll,
    touch,
    reset,
  };
}

export function required(msg = "此项为必填"): Rule<unknown> {
  return (v) => {
    if (v === undefined || v === null || v === "" || (Array.isArray(v) && v.length === 0)) return msg;
    return null;
  };
}

export function minLength(n: number, msg?: string): Rule<string> {
  return (v) => ((v as string)?.length < n ? msg || `至少需要 ${n} 个字符` : null);
}

export function range(min: number, max: number, msg?: string): Rule<number> {
  return (v) => {
    const n = Number(v);
    if (Number.isNaN(n) || n < min || n > max) return msg || `请输入 ${min} 到 ${max} 之间的数值`;
    return null;
  };
}

export function positiveInteger(msg = "请输入大于 0 的整数"): Rule<number> {
  return (v) => {
    const n = Number(v);
    if (!Number.isInteger(n) || n <= 0) return msg;
    return null;
  };
}

export function nonNegativeInteger(msg = "请输入大于等于 0 的整数"): Rule<number> {
  return (v) => {
    const n = Number(v);
    if (!Number.isInteger(n) || n < 0) return msg;
    return null;
  };
}
