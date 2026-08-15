// Compatibility facade: feature code can keep importing from `api/queries`
// while query implementations remain grouped by browser-facing domain.
export * from './queries/admin';
export * from './queries/conversations';
export * from './queries/participation';
export * from './queries/results';
export * from './queries/session';
