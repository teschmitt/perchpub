import jsQR from 'jsqr';
import QRCode from 'qrcode';
import { describe, expect, it } from 'vitest';
import { ENROLL_QR_EC_LEVEL, buildEnrollQrPayload, enrollQrSegments } from './enrollment';

const SESSION = {
	session_id: '550e8400-e29b-41d4-a716-446655440000',
	auth_token: 'aVeryLong_one-time_secret_token_urlsafe_xyz123',
	ca_pin: 'a'.repeat(64),
	expires_at: '2026-07-01T12:05:00.000Z'
};

/**
 * Encode the session exactly as the wizard does (the shared `enrollQrSegments`
 * input at the shared EC level), rasterize the module matrix into an RGBA image
 * with a quiet zone, and decode it back with a standard QR reader — the
 * conformance round-trip from the perchstation contract §7.
 */
function encodeAndDecode(session: typeof SESSION): string {
	const qr = QRCode.create(enrollQrSegments(session), {
		errorCorrectionLevel: ENROLL_QR_EC_LEVEL
	});
	const size = qr.modules.size;
	const quiet = 4;
	const scale = 4;
	const dim = (size + quiet * 2) * scale;
	const rgba = new Uint8ClampedArray(dim * dim * 4).fill(255); // white canvas
	for (let r = 0; r < size; r++) {
		for (let c = 0; c < size; c++) {
			if (!qr.modules.get(r, c)) continue; // light module → leave white
			for (let dy = 0; dy < scale; dy++) {
				for (let dx = 0; dx < scale; dx++) {
					const y = (quiet + r) * scale + dy;
					const x = (quiet + c) * scale + dx;
					const i = (y * dim + x) * 4;
					rgba[i] = 0;
					rgba[i + 1] = 0;
					rgba[i + 2] = 0;
					rgba[i + 3] = 255;
				}
			}
		}
	}
	const result = jsQR(rgba, dim, dim);
	if (!result) throw new Error('QR decode failed');
	return result.data;
}

describe('buildEnrollQrPayload', () => {
	it('encodes exactly the three perchstation contract fields, nothing else', () => {
		const parsed = JSON.parse(buildEnrollQrPayload(SESSION));
		expect(Object.keys(parsed).sort()).toEqual(['auth_token', 'ca_pin', 'session_id']);
		// The QR carries a pin, never the chain / keypair / CSR / expiry.
		expect(parsed).not.toHaveProperty('ca_chain_pem');
		expect(parsed).not.toHaveProperty('csr_pem');
		expect(parsed).not.toHaveProperty('expires_at');
	});

	it('emits compact JSON (no whitespace) to conserve QR capacity', () => {
		const payload = buildEnrollQrPayload(SESSION);
		expect(payload).not.toMatch(/\n|\t| {2}/);
	});
});

describe('enrollQrSegments', () => {
	it('encodes the payload as a single byte-mode segment (contract §4)', () => {
		// A bare-string input lets qrcode auto-split into mixed numeric/byte
		// segments; the explicit byte segment guarantees one byte-mode symbol.
		const qr = QRCode.create(enrollQrSegments(SESSION), {
			errorCorrectionLevel: ENROLL_QR_EC_LEVEL
		});
		expect(qr.segments.map((s) => s.mode.id)).toEqual(['Byte']);
	});

	it('round-trips byte-for-byte through a real QR encode/decode', () => {
		const decoded = encodeAndDecode(SESSION);
		expect(decoded).toBe(buildEnrollQrPayload(SESSION));
		const parsed = JSON.parse(decoded);
		expect(parsed.session_id).toBe(SESSION.session_id);
		expect(parsed.auth_token).toBe(SESSION.auth_token);
		expect(parsed.ca_pin).toBe(SESSION.ca_pin);
	});
});
