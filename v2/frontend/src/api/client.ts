import createClient from 'openapi-fetch';

import type {paths} from './schema';

export const api = createClient<paths>({
  baseUrl: new URL('/api/v1', globalThis.location.origin).toString(),
  credentials: 'same-origin',
});

export class ApiContractError extends Error {
  constructor(
    message: string,
    readonly code: string,
    readonly details?: unknown,
  ) {
    super(message);
    this.name = 'ApiContractError';
  }
}

export async function requireApiData<T>(
  request: Promise<{data?: T; error?: unknown}>,
): Promise<T> {
  const {data, error} = await request;
  if (data !== undefined) return data;
  const payload = error as {
    error?: {code?: string; message?: string; details?: unknown};
  };
  throw new ApiContractError(
    payload.error?.message ?? 'The request could not be completed.',
    payload.error?.code ?? 'unknown_error',
    payload.error?.details,
  );
}
