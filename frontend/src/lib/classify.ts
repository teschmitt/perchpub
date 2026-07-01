import type { components } from '$lib/api/schema';

export type ClassifyTaskStatus = components['schemas']['ClassifyTaskStatus'];
type ClassifyTaskPublic = components['schemas']['ClassifyTaskPublic'];

/** Visual treatment for a classify-task status. `failed` is styled distinctly. */
export type ClassifyBadgeVariant = 'pending' | 'progress' | 'success' | 'failed';

export interface ClassifyStatusBadge {
	label: string;
	variant: ClassifyBadgeVariant;
}

/**
 * Map a `ClassifyTaskStatus` to its display label and visual variant. `Failed`
 * carries a distinct (`failed`) variant so the component can style it apart from
 * the in-flight / succeeded states.
 */
const BADGES: Record<ClassifyTaskStatus, ClassifyStatusBadge> = {
	Prepared: { label: 'Prepared', variant: 'pending' },
	Queued: { label: 'Queued', variant: 'pending' },
	Processing: { label: 'Processing', variant: 'progress' },
	Success: { label: 'Success', variant: 'success' },
	Failed: { label: 'Failed', variant: 'failed' }
};

export function classifyStatusBadge(status: ClassifyTaskStatus): ClassifyStatusBadge {
	return BADGES[status];
}

/**
 * Tailwind classes per badge variant. `failed` maps to the destructive token so it
 * reads apart from the in-flight (pending/progress) and succeeded states — the
 * "Failed styled distinctly" contract, kept here so it is unit-testable.
 */
const VARIANT_CLASS: Record<ClassifyBadgeVariant, string> = {
	pending: 'bg-muted text-muted-foreground',
	progress: 'bg-accent text-accent-foreground',
	success: 'bg-primary/10 text-primary',
	failed: 'bg-destructive/10 text-destructive'
};

export function classifyBadgeClass(variant: ClassifyBadgeVariant): string {
	return VARIANT_CLASS[variant];
}

/** Type guard: is `value` one of the `ClassifyTaskStatus` members? */
export function isClassifyStatus(value: unknown): value is ClassifyTaskStatus {
	return typeof value === 'string' && value in BADGES;
}

/**
 * The status of an observation's most-recent classify task, or `null` when it
 * has none. `GET /classify-task/?observation={id}` returns tasks ordered
 * `created_at DESC, id DESC`, so the first row is the most recent.
 */
export function latestClassifyStatus(
	tasks: Pick<ClassifyTaskPublic, 'status'>[]
): ClassifyTaskStatus | null {
	return tasks.length > 0 ? tasks[0].status : null;
}
