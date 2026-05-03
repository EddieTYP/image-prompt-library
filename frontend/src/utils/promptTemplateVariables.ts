export interface PromptTemplateVariable {
  key: string;
  token: string;
  start: number;
  end: number;
}

function isEscaped(input: string, index: number): boolean {
  let slashCount = 0;
  for (let cursor = index - 1; cursor >= 0 && input[cursor] === '\\'; cursor -= 1) slashCount += 1;
  return slashCount % 2 === 1;
}

function isMalformedPlaceholderBody(body: string): boolean {
  return body.includes('{{') || body.includes('}}');
}

export function extractPromptTemplateVariableRecords(prompt: string): PromptTemplateVariable[] {
  const variables: PromptTemplateVariable[] = [];
  const seen = new Set<string>();
  const pattern = /{{([\s\S]*?)}}/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(prompt)) !== null) {
    const token = match[0];
    const start = match.index;
    const end = start + token.length;
    if (isEscaped(prompt, start)) continue;
    const key = match[1].trim();
    if (!key || isMalformedPlaceholderBody(match[1])) continue;
    if (seen.has(key)) continue;
    seen.add(key);
    variables.push({ key, token, start, end });
  }
  return variables;
}

export function extractPromptTemplateVariables(prompt: string): string[] {
  return extractPromptTemplateVariableRecords(prompt).map(variable => variable.key);
}
