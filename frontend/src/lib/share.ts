import type { components } from '$lib/api/schema';
import { absoluteMediaUrl } from '$lib/media';
import { formatConfidence, formatDate, stationLabel } from '$lib/format';

type ObservationPublic = components['schemas']['ObservationPublic'];

export interface ShareMeta {
	/** Page/`og:title` — species + capturing station. */
	title: string;
	/** `og:description` — observed date and confidence. */
	description: string;
	/** Absolute `og:image` URL (the `/media/{object_name}` on the public base). */
	image: string;
	/** Absolute canonical `og:url` for this observation. */
	url: string;
}

/**
 * Build the Open Graph / share-preview metadata for an observation detail page,
 * resolving absolute URLs against the public site `base` (`PUBLIC_SITE_URL`, or
 * the request origin in dev). Pure so the SSR head can be asserted in a unit test
 * without a backend.
 */
export function observationShareMeta(observation: ObservationPublic, base: string): ShareMeta {
	const species = observation.species?.scientific_name ?? 'Unclassified';
	const station = stationLabel(observation.station);
	const confidence = formatConfidence(observation.confidence_score);
	const descriptionParts = [`Observed ${formatDate(observation.observed_at)}`];
	if (confidence) {
		descriptionParts.push(`${confidence} confidence`);
	}
	return {
		title: `${species} at ${station}`,
		description: descriptionParts.join(' · '),
		image: absoluteMediaUrl(observation.object_name, base),
		url: `${base.replace(/\/+$/, '')}/observations/${observation.id}`
	};
}
