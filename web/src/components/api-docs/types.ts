import type { ReactNode } from "react";

/** HTTP verb an endpoint accepts. */
export type Method = "GET" | "POST" | "PATCH" | "DELETE";

export interface Ep {
  method: Method;
  path: string;
  title: string;
  desc: string;
  curl: string;
  body?: string;
  res?: string;
  notes?: string[];
  tryIt?: boolean;
}

/** One tab of the catalogue: a label, an icon, optional intro content, and its endpoints. */
export interface Group {
  key: string;
  label: string;
  icon: ReactNode;
  extra?: ReactNode;
  endpoints: Ep[];
}
