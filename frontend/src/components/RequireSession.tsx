import { Center, Loader } from "@mantine/core";
import { type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useMe } from "@/api/auth";
import { ApiError } from "@/api/client";

interface Props {
  children: ReactNode;
}

/**
 * Guard for authenticated routes. While `useMe()` is loading, render a
 * full-page spinner. On 401, redirect to /login while preserving the
 * intended target as `?from=` so we can return there after login.
 */
export function RequireSession({ children }: Props) {
  const me = useMe();
  const location = useLocation();

  if (me.isPending) {
    return (
      <Center mih="100vh">
        <Loader />
      </Center>
    );
  }

  const unauthenticated =
    me.isError && me.error instanceof ApiError && me.error.status === 401;

  if (unauthenticated || !me.data) {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: location.pathname + location.search }}
      />
    );
  }

  return <>{children}</>;
}
