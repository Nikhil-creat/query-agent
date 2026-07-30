import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Send,
  Database,
  Terminal,
  Sparkles,
  AlertTriangle,
  Radio,
  MessageSquarePlus,
} from "lucide-react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
const CHART_COLORS = ["#7c6cf0", "#3ec9b7", "#f2b807", "#ef5a5a", "#5b8def"];

/* -------------------------------------------------------------------------
   Demo dataset: a small synthetic sales table, generated deterministically
   (no Math.random) so every demo run tells the same coherent story. This
   is what the UI runs against when no backend is reachable -- see
   runDemoAgent() below for the local NL "agent" that answers questions
   about it without calling the real LLM.
   ---------------------------------------------------------------------- */

const REGIONS = ["NA", "EMEA", "APAC", "LATAM"];
const PRODUCTS = [
  { name: "Aurora", price: 120 },
  { name: "Nimbus", price: 75 },
  { name: "Vertex", price: 200 },
];
const MONTHS = ["2026-01", "2026-02", "2026-03"];

const DEMO_DATA = [];
MONTHS.forEach((month, mi) => {
  REGIONS.forEach((region, ri) => {
    PRODUCTS.forEach((product, pi) => {
      const units = 18 + ((ri * 7 + pi * 5 + mi * 4) % 22);
      const growth = 1 + mi * 0.09;
      const revenue = Math.round(units * product.price * growth);
      DEMO_DATA.push({ month, region, product: product.name, units, revenue });
    });
  });
});

const DEMO_SCHEMA = [
  { col: "month", dtype: "text", sample: "2026-01" },
  { col: "region", dtype: "text", sample: "NA, EMEA" },
  { col: "product", dtype: "text", sample: "Aurora" },
  { col: "units", dtype: "int", sample: "18" },
  { col: "revenue", dtype: "int", sample: "2160" },
];

function sum(arr, key) {
  return arr.reduce((a, r) => a + r[key], 0);
}
function groupSum(data, groupKey, valueKey) {
  const map = {};
  data.forEach((r) => {
    map[r[groupKey]] = (map[r[groupKey]] || 0) + r[valueKey];
  });
  return Object.entries(map).map(([k, v]) => ({ [groupKey]: k, [valueKey]: v }));
}

const UNSAFE_PATTERN = /\b(delete|drop|update|insert|truncate|alter)\b/i;

function runDemoAgent(question) {
  const q = question.toLowerCase();

  if (UNSAFE_PATTERN.test(q)) {
    return {
      generated_sql: "DELETE FROM sales WHERE 1=1",
      sql_rejected_reason:
        "Only SELECT statements are allowed. The agent blocks anything that isn't a read-only query before it ever reaches the database.",
    };
  }

  if (/trend|over time|monthly|by month/.test(q)) {
    const data = groupSum(DEMO_DATA, "month", "revenue").sort((a, b) =>
      a.month.localeCompare(b.month)
    );
    return {
      generated_sql:
        "SELECT month, SUM(revenue) AS revenue FROM sales GROUP BY month ORDER BY month;",
      chart_type: "line",
      chart_config: { x_key: "month", y_key: "revenue" },
      result_preview: data,
      insight_text: `Revenue climbed from $${data[0].revenue.toLocaleString()} in ${data[0].month} to $${data[data.length - 1].revenue.toLocaleString()} in ${data[data.length - 1].month} — a steady month-over-month increase across the quarter.`,
    };
  }

  if (/region/.test(q)) {
    const data = groupSum(DEMO_DATA, "region", "revenue").sort(
      (a, b) => b.revenue - a.revenue
    );
    return {
      generated_sql:
        "SELECT region, SUM(revenue) AS revenue FROM sales GROUP BY region ORDER BY revenue DESC;",
      chart_type: "bar",
      chart_config: { x_key: "region", y_key: "revenue" },
      result_preview: data,
      insight_text: `${data[0].region} leads with $${data[0].revenue.toLocaleString()} in revenue, ahead of ${data[1].region} at $${data[1].revenue.toLocaleString()}.`,
    };
  }

  if (/product/.test(q)) {
    const data = groupSum(DEMO_DATA, "product", "revenue").sort(
      (a, b) => b.revenue - a.revenue
    );
    return {
      generated_sql:
        "SELECT product, SUM(revenue) AS revenue FROM sales GROUP BY product ORDER BY revenue DESC;",
      chart_type: "bar",
      chart_config: { x_key: "product", y_key: "revenue" },
      result_preview: data,
      insight_text: `${data[0].product} is the top performer at $${data[0].revenue.toLocaleString()} in total revenue across all regions.`,
    };
  }

  if (/average|avg|order value/.test(q)) {
    const avg = sum(DEMO_DATA, "revenue") / DEMO_DATA.length;
    return {
      generated_sql: "SELECT AVG(revenue) AS avg_order_value FROM sales;",
      chart_type: "none",
      result_preview: [{ avg_order_value: Math.round(avg) }],
      insight_text: `The average order value across all recorded sales is $${Math.round(avg).toLocaleString()}.`,
    };
  }

  if (/share|percentage|pie|split/.test(q)) {
    const data = groupSum(DEMO_DATA, "region", "revenue");
    return {
      generated_sql:
        "SELECT region, SUM(revenue) AS revenue FROM sales GROUP BY region;",
      chart_type: "pie",
      chart_config: { x_key: "region", y_key: "revenue" },
      result_preview: data,
      insight_text: `Revenue is split across ${data.length} regions, with no single region making up more than half the total.`,
    };
  }

  // Fallback: overall summary
  const totalRevenue = sum(DEMO_DATA, "revenue");
  const totalUnits = sum(DEMO_DATA, "units");
  return {
    generated_sql: "SELECT SUM(revenue) AS total_revenue, SUM(units) AS total_units FROM sales;",
    chart_type: "table",
    result_preview: [{ total_revenue: totalRevenue, total_units: totalUnits }],
    insight_text: `Across Q1 2026, total revenue was $${totalRevenue.toLocaleString()} from ${totalUnits.toLocaleString()} units sold. Try asking about a specific region, product, or the trend over time.`,
  };
}

/* --------------------------------- UI ----------------------------------- */

function ChartRenderer({ chartType, config, data }) {
  if (!data || data.length === 0) return null;
  const xKey = config?.x_key;
  const yKey = config?.y_key;

  if (chartType === "bar" && xKey && yKey) {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#262c3d" vertical={false} />
          <XAxis dataKey={xKey} stroke="#5c6478" fontSize={11} tickLine={false} />
          <YAxis stroke="#5c6478" fontSize={11} tickLine={false} axisLine={false} />
          <Tooltip
            contentStyle={{
              background: "#1a1e2b",
              border: "1px solid #262c3d",
              borderRadius: 8,
              fontSize: 12,
            }}
          />
          <Bar dataKey={yKey} fill="#7c6cf0" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    );
  }

  if (chartType === "line" && xKey && yKey) {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#262c3d" vertical={false} />
          <XAxis dataKey={xKey} stroke="#5c6478" fontSize={11} tickLine={false} />
          <YAxis stroke="#5c6478" fontSize={11} tickLine={false} axisLine={false} />
          <Tooltip
            contentStyle={{
              background: "#1a1e2b",
              border: "1px solid #262c3d",
              borderRadius: 8,
              fontSize: 12,
            }}
          />
          <Line type="monotone" dataKey={yKey} stroke="#3ec9b7" strokeWidth={2.5} dot={{ r: 3 }} />
        </LineChart>
      </ResponsiveContainer>
    );
  }

  if (chartType === "pie" && xKey && yKey) {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={data} dataKey={yKey} nameKey={xKey} outerRadius={78} innerRadius={40}>
            {data.map((_, i) => (
              <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              background: "#1a1e2b",
              border: "1px solid #262c3d",
              borderRadius: 8,
              fontSize: 12,
            }}
          />
        </PieChart>
      </ResponsiveContainer>
    );
  }

  // table / none / unrecognized -> fall through to table view
  const columns = Object.keys(data[0]);
  return (
    <div className="table-wrap" style={{ height: "100%" }}>
      <table className="result-table">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.slice(0, 30).map((row, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c}>{typeof row[c] === "number" ? row[c].toLocaleString() : String(row[c])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const STAGE_LABELS = ["Generating SQL…", "Running query…", "Analyzing results…"];

function Receipt({ index, question, status, stage, result }) {
  const rejected = result?.sql_rejected_reason;
  const data = result?.result_preview;

  return (
    <div className="receipt">
      <div className="receipt-question">
        <span className="receipt-index">Q{index}</span>
        <div className="receipt-question-text">{question}</div>
      </div>

      {status === "pending" && (
        <div className="receipt-body">
          <div className="trace-step active">
            <Terminal size={13} />
            <span>
              {STAGE_LABELS[stage]}
              <span className="thinking-dot">.</span>
              <span className="thinking-dot">.</span>
              <span className="thinking-dot">.</span>
            </span>
          </div>
        </div>
      )}

      {status === "done" && (
        <div className="receipt-body">
          {result?.generated_sql && (
            <div className="sql-block">
              <div className="sql-block-label">
                <Terminal size={11} /> Generated SQL
              </div>
              <pre>{result.generated_sql}</pre>
            </div>
          )}

          {rejected && (
            <div className="rejected-block">
              <AlertTriangle size={16} />
              <span>{rejected}</span>
            </div>
          )}

          {!rejected && data && data.length > 0 && (
            <div className="chart-wrap">
              <ChartRenderer
                chartType={result.chart_type}
                config={result.chart_config}
                data={data}
              />
            </div>
          )}

          {!rejected && result?.insight_text && (
            <div className="insight-row">
              <Sparkles size={15} />
              <span>{result.insight_text}</span>
            </div>
          )}

          {!rejected && (
            <div className="receipt-meta">
              <span>{data?.length ?? 0} row{(data?.length ?? 0) === 1 ? "" : "s"}</span>
              <span>SQLite</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const SUGGESTIONS = [
  "What's total revenue by region?",
  "Show me the monthly revenue trend",
  "Which product performs best?",
  "What's the average order value?",
  "Try: delete all the sales data",
];

export default function App() {
  const [mode, setMode] = useState("checking"); // 'checking' | 'demo' | 'live'
  const [datasetId, setDatasetId] = useState(null);
  const [receipts, setReceipts] = useState([]);
  const [input, setInput] = useState("");
  const feedEndRef = useRef(null);

  useEffect(() => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 1200);
    fetch(`${API_BASE}/api/datasets`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((datasets) => {
        clearTimeout(timeout);
        if (datasets && datasets.length > 0) {
          setDatasetId(datasets[0].id);
          setMode("live");
        } else {
          setMode("demo");
        }
      })
      .catch(() => setMode("demo"));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    feedEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [receipts]);

  const busy = receipts.some((r) => r.status === "pending");

  async function handleAsk(question) {
    if (!question.trim() || busy) return;
    setInput("");
    const id = Date.now();
    setReceipts((prev) => [...prev, { id, question, status: "pending", stage: 0 }]);

    if (mode === "live") {
      try {
        const res = await fetch(`${API_BASE}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ dataset_id: datasetId, question }),
        });
        const data = await res.json();
        setReceipts((prev) =>
          prev.map((r) =>
            r.id === id
              ? {
                  ...r,
                  status: "done",
                  result: {
                    generated_sql: data.generated_sql,
                    sql_rejected_reason: data.sql_rejected_reason,
                    chart_type: data.chart_type,
                    chart_config: data.chart_config_json,
                    result_preview: data.result_preview_json,
                    insight_text: data.insight_text,
                  },
                }
              : r
          )
        );
      } catch (e) {
        setReceipts((prev) =>
          prev.map((r) =>
            r.id === id
              ? { ...r, status: "done", result: { sql_rejected_reason: "Could not reach the backend." } }
              : r
          )
        );
      }
      return;
    }

    // DEMO mode: step through the same stages the real pipeline goes
    // through, then resolve with the local demo agent's answer.
    let stage = 0;
    const stageTimer = setInterval(() => {
      stage += 1;
      if (stage < STAGE_LABELS.length) {
        setReceipts((prev) => prev.map((r) => (r.id === id ? { ...r, stage } : r)));
      }
    }, 420);

    setTimeout(() => {
      clearInterval(stageTimer);
      const result = runDemoAgent(question);
      setReceipts((prev) =>
        prev.map((r) => (r.id === id ? { ...r, status: "done", result } : r))
      );
    }, 420 * STAGE_LABELS.length);
  }

  function handleSubmit(e) {
    e.preventDefault();
    handleAsk(input);
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Database size={17} />
          </div>
          <div>
            <div className="brand-name">Query</div>
            <div className="brand-sub">chat with your data</div>
          </div>
        </div>

        <div className={`mode-badge ${mode === "live" ? "live" : "demo"}`}>
          <span className="dot" />
          {mode === "checking" && "Connecting…"}
          {mode === "live" && "Live — connected to backend"}
          {mode === "demo" && "Demo mode — sample dataset"}
        </div>

        <div>
          <div className="panel-label">Dataset</div>
          <div className="dataset-card">
            <div className="dataset-card-title">Retail Sales — Q1 2026</div>
            <div className="dataset-card-meta">{DEMO_DATA.length} rows · 5 columns</div>
            {DEMO_SCHEMA.map((s) => (
              <div className="schema-row" key={s.col}>
                <span className="schema-col">{s.col}</span>
                <span className="schema-type">{s.dtype}</span>
              </div>
            ))}
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
          <div className="panel-label">History</div>
          <div className="history-list">
            {receipts.length === 0 && (
              <div className="sidebar-footer">Your questions will show up here.</div>
            )}
            {receipts.map((r, i) => (
              <div className="history-item" key={r.id} title={r.question}>
                Q{i + 1} · {r.question}
              </div>
            ))}
          </div>
        </div>

        <div className="sidebar-footer">
          Every answer shows the exact SQL the agent ran — nothing is hidden
          between your question and the result.
        </div>
      </aside>

      <main className="main">
        <div className="topbar">
          <div className="topbar-title">
            Retail Sales — Q1 2026
            <span>ask a question in plain English</span>
          </div>
          <Radio size={16} color={mode === "live" ? "#3ec9b7" : "#f2b807"} />
        </div>

        <div className="feed">
          {receipts.length === 0 && (
            <div className="empty-state">
              <MessageSquarePlus size={26} style={{ marginBottom: 10, opacity: 0.6 }} />
              <h2>Ask anything about this dataset</h2>
              <p>
                The agent turns your question into SQL, runs it, and explains
                what it found — showing its work at every step.
              </p>
              <div className="suggestion-chips">
                {SUGGESTIONS.map((s) => (
                  <button className="chip" key={s} onClick={() => handleAsk(s)}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {receipts.map((r, i) => (
            <Receipt
              key={r.id}
              index={i + 1}
              question={r.question}
              status={r.status}
              stage={r.stage}
              result={r.result}
            />
          ))}
          <div ref={feedEndRef} />
        </div>

        <form className="composer" onSubmit={handleSubmit}>
          <div className="composer-inner">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask a question about this data…"
            />
            <button type="submit" className="send-btn" disabled={!input.trim() || busy}>
              <Send size={15} />
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}
