import { useEffect, useRef } from "react";
import cytoscape, { type Core } from "cytoscape";
import dagre from "cytoscape-dagre";

cytoscape.use(dagre);

interface Props {
  nodes: { id: string; label: string; type: string }[];
  edges: { from: string; to: string; relation: string; confidence: number }[];
}

const TYPE_COLORS: Record<string, string> = {
  LegalElement: "#f59e0b",
  Fact: "#2563eb",
  Evidence: "#16a34a",
  EvidenceChunk: "#86efac",
  Person: "#ec4899",
  Material: "#8b5cf6",
  Risk: "#dc2626",
};

export function EvidenceGraph({ nodes, edges }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const cy = cytoscape({
      container: containerRef.current,
      elements: [
        ...nodes.map((n) => ({
          data: {
            id: n.id,
            label: `${n.label}`,
            type: n.type,
          },
        })),
        ...edges.map((e) => ({
          data: {
            id: `${e.from}->${e.to}`,
            source: e.from,
            target: e.to,
            label: e.relation,
            confidence: e.confidence,
          },
        })),
      ],
      style: [
        {
          selector: "node",
          style: {
            "background-color": (el) => TYPE_COLORS[el.data("type")] || "#6b7280",
            label: "data(label)",
            "text-valign": "bottom",
            "text-halign": "center",
            "font-size": "10px",
            "text-wrap": "wrap",
            "text-max-width": "120px",
            color: "#374151",
          },
        },
        {
          selector: "edge",
          style: {
            width: 2,
            "line-color": (el) => (el.data("confidence") > 0.7 ? "#16a34a" : "#f59e0b"),
            "target-arrow-color": (el) => (el.data("confidence") > 0.7 ? "#16a34a" : "#f59e0b"),
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            label: "data(label)",
            "font-size": "9px",
            color: "#9ca3af",
          },
        },
      ],
      layout: {
        name: "dagre",
      } as any,
      wheelSensitivity: 0.3,
    });

    cyRef.current = cy;
    return () => cy.destroy();
  }, [nodes, edges]);

  return (
    <div className="bg-white rounded-lg border p-4">
      <h3 className="font-semibold text-gray-700 mb-3">知识图谱</h3>
      <div
        ref={containerRef}
        className="w-full rounded border bg-gray-50"
        style={{ height: 500 }}
      />
      <div className="flex gap-4 mt-2 text-xs text-gray-400">
        {Object.entries(TYPE_COLORS).slice(0, 6).map(([type, color]) => (
          <span key={type} className="flex items-center gap-1">
            <span className="w-3 h-3 rounded-full" style={{ background: color }} />
            {type}
          </span>
        ))}
      </div>
    </div>
  );
}
