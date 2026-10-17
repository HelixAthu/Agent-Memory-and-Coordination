import { useState } from "react";
import { ShieldCheck, Gauge, CheckCircle2, XCircle } from "lucide-react";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "../ui/card";
import { checkIsolation, runAdminLoadTest } from "../../lib/api";

interface ProofPanelProps {
  tenant: string;
}

export function ProofPanel({ tenant }: ProofPanelProps): JSX.Element {
  // Isolation State
  const [isolationLoading, setIsolationLoading] = useState(false);
  const [isolationChecks, setIsolationChecks] = useState<any[] | null>(null);
  const [isolationError, setIsolationError] = useState<string | null>(null);

  // Load Test State
  const [loadLoading, setLoadLoading] = useState(false);
  const [loadResult, setLoadResult] = useState<any | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const handleRunIsolation = async () => {
    setIsolationLoading(true);
    setIsolationError(null);
    try {
      const data = await checkIsolation(tenant);
      setIsolationChecks(data);
    } catch (err: any) {
      setIsolationError(err.message || "Isolation check failed");
    } finally {
      setIsolationLoading(false);
    }
  };

  const handleRunLoadTest = async () => {
    setLoadLoading(true);
    setLoadError(null);
    try {
      const res = await runAdminLoadTest(true);
      setLoadResult(res);
    } catch (err: any) {
      setLoadError(err.message || "Load test failed");
    } finally {
      setLoadLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* 1. Isolation Proof Card */}
      <Card className="bg-slate-900/70 border-slate-800">
        <CardHeader className="p-3 pb-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <ShieldCheck className="h-4 w-4 text-emerald-400" />
              <CardTitle className="text-xs font-semibold text-foreground uppercase tracking-wide">
                Tenant & User Isolation Proof
              </CardTitle>
            </div>
            <Button
              size="sm"
              variant="default"
              className="h-6 text-[11px] px-2.5 bg-emerald-700 hover:bg-emerald-600"
              onClick={handleRunIsolation}
              disabled={isolationLoading}
            >
              {isolationLoading ? "Verifying..." : "Run Isolation Check"}
            </Button>
          </div>
          <CardDescription className="text-[10px] text-slate-400">
            Enforces strict per-tenant graph partitions, role allowlists, and cross-user boundaries.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-3 pt-1 space-y-1.5">
          {isolationError && (
            <p className="text-[11px] text-rose-400 font-mono">{isolationError}</p>
          )}

          {isolationChecks === null ? (
            <p className="text-[11px] text-muted-foreground italic text-center py-2">
              Click &quot;Run Isolation Check&quot; to verify G13 security boundaries.
            </p>
          ) : (
            <div className="space-y-1.5">
              {isolationChecks.map((c, i) => (
                <div
                  key={i}
                  className="flex items-start justify-between gap-2 p-2 rounded bg-slate-950/60 border border-slate-850 text-xs"
                >
                  <div className="flex items-start gap-1.5">
                    {c.passed ? (
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 mt-0.5 shrink-0" />
                    ) : (
                      <XCircle className="h-3.5 w-3.5 text-rose-400 mt-0.5 shrink-0" />
                    )}
                    <div>
                      <p className="font-mono text-[11px] font-semibold text-slate-200">
                        {c.name}
                      </p>
                      <p className="text-[10px] text-slate-400">{c.detail}</p>
                    </div>
                  </div>
                  <Badge
                    variant="secondary"
                    className={`text-[9px] px-1 py-0 shrink-0 ${
                      c.passed
                        ? "bg-emerald-950 text-emerald-300 border border-emerald-700/60"
                        : "bg-rose-950 text-rose-300 border border-rose-700/60"
                    }`}
                  >
                    {c.passed ? "PASS" : "FAIL"}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* 2. Concurrency Load Test Proof Card */}
      <Card className="bg-slate-900/70 border-slate-800">
        <CardHeader className="p-3 pb-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <Gauge className="h-4 w-4 text-blue-400" />
              <CardTitle className="text-xs font-semibold text-foreground uppercase tracking-wide">
                Concurrency & Load Proof
              </CardTitle>
            </div>
            <Button
              size="sm"
              variant="default"
              className="h-6 text-[11px] px-2.5 bg-blue-700 hover:bg-blue-600"
              onClick={handleRunLoadTest}
              disabled={loadLoading}
            >
              {loadLoading ? "Running C1-C5..." : "Run Load Test"}
            </Button>
          </div>
          <CardDescription className="text-[10px] text-slate-400">
            Executes high-concurrency race condition tests (C1-C5) under atomic CAS locks.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-3 pt-1 space-y-2">
          {loadError && (
            <p className="text-[11px] text-rose-400 font-mono">{loadError}</p>
          )}

          {loadResult === null ? (
            <p className="text-[11px] text-muted-foreground italic text-center py-2">
              Click &quot;Run Load Test&quot; to measure live throughput and latency.
            </p>
          ) : (
            <div className="space-y-2.5">
              {/* Throughput metrics banner */}
              <div className="grid grid-cols-3 gap-2 text-center p-2 rounded bg-slate-950/80 border border-slate-800">
                <div>
                  <span className="text-[10px] text-muted-foreground uppercase">Throughput</span>
                  <p className="text-sm font-bold text-blue-400 font-mono">{loadResult.ops_per_s} ops/s</p>
                </div>
                <div>
                  <span className="text-[10px] text-muted-foreground uppercase">Total Ops</span>
                  <p className="text-sm font-bold text-foreground font-mono">{loadResult.ops}</p>
                </div>
                <div>
                  <span className="text-[10px] text-muted-foreground uppercase">Wall Time</span>
                  <p className="text-sm font-bold text-foreground font-mono">{loadResult.seconds}s</p>
                </div>
              </div>

              {/* Latency table */}
              {loadResult.latency && (
                <div className="p-2 rounded bg-slate-950/60 border border-slate-850">
                  <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide block mb-1">
                    Latency Profile (ms)
                  </span>
                  <div className="grid grid-cols-4 text-center text-[11px] font-mono">
                    <span className="text-muted-foreground text-left">Metric</span>
                    <span className="text-slate-300">p50</span>
                    <span className="text-slate-300">p95</span>
                    <span className="text-slate-300">p99</span>

                    <span className="text-left text-slate-400">Overall</span>
                    <span>{loadResult.latency.p50}</span>
                    <span>{loadResult.latency.p95}</span>
                    <span>{loadResult.latency.p99}</span>

                    <span className="text-left text-slate-400">Reads</span>
                    <span>{loadResult.read_latency?.p50 ?? 0}</span>
                    <span>{loadResult.read_latency?.p95 ?? 0}</span>
                    <span>{loadResult.read_latency?.p99 ?? 0}</span>

                    <span className="text-left text-slate-400">Writes</span>
                    <span>{loadResult.write_latency?.p50 ?? 0}</span>
                    <span>{loadResult.write_latency?.p95 ?? 0}</span>
                    <span>{loadResult.write_latency?.p99 ?? 0}</span>
                  </div>
                </div>
              )}

              {/* Invariants Checks C1-C5 */}
              <div className="space-y-1">
                {loadResult.checks?.map((c: any) => (
                  <div
                    key={c.id}
                    className="flex items-center justify-between p-1.5 rounded bg-slate-950/60 border border-slate-850 text-xs"
                  >
                    <div className="flex items-center gap-1.5 truncate pr-2">
                      <span className="font-mono text-blue-400 font-bold text-[11px]">{c.id}</span>
                      <span className="text-slate-300 truncate text-[11px]">{c.name}</span>
                    </div>
                    <Badge
                      variant="secondary"
                      className={`text-[9px] px-1 py-0 shrink-0 ${
                        c.passed
                          ? "bg-emerald-950 text-emerald-300 border border-emerald-700/60"
                          : "bg-rose-950 text-rose-300 border border-rose-700/60"
                      }`}
                    >
                      {c.passed ? "PASS" : "FAIL"}
                    </Badge>
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
