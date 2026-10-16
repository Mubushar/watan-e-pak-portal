import { useMutation, useQuery, useQueryClient, type UseQueryOptions } from "@tanstack/react-query";
import { toast } from "sonner";
import { get, type Query } from "@/lib/api";

/** GET a backend path with React Query. Pass `null` as the path to disable the query. */
export function useApi<T = unknown>(path: string | null | undefined, query?: Query, options?: Omit<UseQueryOptions<T, Error>, "queryKey" | "queryFn">) {
  return useQuery<T, Error>({
    queryKey: [path, query ?? {}],
    queryFn: ({ signal }) => get<T>(path!, query, { signal }),
    enabled: !!path && (options?.enabled ?? true),
    ...options,
  });
}

interface MutateOptions<TRes> {
  /** Query-key path prefixes to refetch after success, e.g. ["/me/listings"]. */
  invalidate?: string[];
  success?: string | ((res: TRes) => string);
  onSuccess?: (res: TRes) => void;
}

/** Wrap a write call with toasts + cache invalidation (same contract as the web portal). */
export function useMutate<TVars = void, TRes = unknown>(fn: (vars: TVars) => Promise<TRes>, opts: MutateOptions<TRes> = {}) {
  const qc = useQueryClient();
  return useMutation<TRes, Error, TVars>({
    mutationFn: fn,
    onSuccess: (res) => {
      if (opts.invalidate?.length)
        qc.invalidateQueries({
          predicate: (q) => typeof q.queryKey[0] === "string" && opts.invalidate!.some((p) => (q.queryKey[0] as string).startsWith(p)),
        });
      if (opts.success) toast.success(typeof opts.success === "function" ? opts.success(res) : opts.success);
      opts.onSuccess?.(res);
    },
    onError: (e) => toast.error(e.message || "Something went wrong"),
  });
}
