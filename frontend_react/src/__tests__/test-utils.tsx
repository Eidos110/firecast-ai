/**
 * Shared Vitest utilities for component integration tests that exercise
 * react-query hooks (PLAN §4 TAHAP D #8).
 *
 * `renderWithQueryClient` wraps any JSX in a fresh `QueryClientProvider` so
 * `useQuery` / `useMutation` chains don't pollute each other across tests.
 * We always use a fresh client per render — sharing clients causes cross-test
 * cache bleed (a retry-on-pending from one test can fire in the next).
 */
import { render } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

export function makeTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        staleTime: 0,
        refetchOnWindowFocus: false,
      },
      mutations: { retry: false },
    },
  });
}

export function renderWithQueryClient(node: ReactNode) {
  const queryClient = makeTestQueryClient();
  const utils = render(
    <QueryClientProvider client={queryClient}>
      {node}
    </QueryClientProvider>,
  );
  return { ...utils, queryClient };
}
