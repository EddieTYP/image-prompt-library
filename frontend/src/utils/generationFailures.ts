export type GenerationFailureKind =
  | 'policy_violation'
  | 'rate_limited'
  | 'provider_unavailable'
  | 'auth_required'
  | 'unknown';

type GenerationFailureSource = {
  metadata?: Record<string, unknown>;
};

const FAILURE_GUIDANCE: Record<GenerationFailureKind, { title: string; guidance: string }> = {
  policy_violation: {
    title: 'Cannot generate this image',
    guidance: 'The provider refused this request because it may violate policy. Try changing the prompt.',
  },
  rate_limited: {
    title: 'Generation is temporarily rate limited',
    guidance: 'Please wait a bit before trying again.',
  },
  provider_unavailable: {
    title: 'Provider is temporarily unavailable',
    guidance: 'The provider is temporarily unavailable. Please try again shortly.',
  },
  auth_required: {
    title: 'Provider connection needs attention',
    guidance: 'Reconnect in Config → Providers before retrying.',
  },
  unknown: {
    title: 'Generation failed',
    guidance: 'You can retry the job or adjust the prompt.',
  },
};

export function generationFailure(job: GenerationFailureSource) {
  const rawKind = job.metadata?.error_kind;
  const kind: GenerationFailureKind = typeof rawKind === 'string' && Object.hasOwn(FAILURE_GUIDANCE, rawKind)
    ? rawKind as GenerationFailureKind
    : 'unknown';
  return { kind, ...FAILURE_GUIDANCE[kind] };
}
