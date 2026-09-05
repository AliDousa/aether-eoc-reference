/**
 * A Zod resolver for React Hook Form.
 *
 * This replaces `@hookform/resolvers`, which is a thin adapter for our one
 * form but requires `ajv@^8` while ESLint 9 requires `ajv@^6`. npm writes a
 * lockfile for that pair which it then rejects under `npm ci`, so CI could not
 * install strictly. Owning twenty lines is a better trade than either
 * weakening CI to `npm install` or carrying a dependency tree for one form.
 *
 * The resolver contract is small and stable: given the raw form values, return
 * either the parsed values or a map of field errors — never both.
 */

import type { FieldErrors, FieldValues, Resolver } from "react-hook-form";
import type { ZodType } from "zod";

export function zodResolver<TFieldValues extends FieldValues>(
  schema: ZodType,
): Resolver<TFieldValues> {
  return async (values) => {
    const parsed = schema.safeParse(values);

    if (parsed.success) {
      return { values: parsed.data as TFieldValues, errors: {} };
    }

    const errors: Record<string, { type: string; message: string }> = {};
    for (const issue of parsed.error.issues) {
      const path = issue.path.join(".");
      // Keep the first error per field. Forms show one message at a time, and
      // the first is the one the operator hits first.
      if (path && !(path in errors)) {
        errors[path] = { type: issue.code, message: issue.message };
      }
    }

    return { values: {}, errors: errors as FieldErrors<TFieldValues> };
  };
}
