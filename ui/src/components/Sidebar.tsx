import { NavLink } from "react-router-dom";

const nav = [
  { to: "/", label: "案件管理", icon: "📋" },
  { to: "/materials", label: "卷宗接入", icon: "📁" },
  { to: "/evidence", label: "证据片段", icon: "🔎" },
  { to: "/analysis", label: "证据链分析", icon: "⚖️" },
  { to: "/review", label: "人工复核", icon: "✅" },
  { to: "/report", label: "报告查看", icon: "📝" },
];

export function Sidebar() {
  return (
    <aside className="w-56 bg-[var(--color-primary)] text-white flex flex-col shrink-0">
      <div className="p-4 border-b border-white/10">
        <h1 className="text-sm font-bold tracking-wide opacity-90">
          司法证据链 Agent
        </h1>
        <p className="text-[10px] text-white/40 mt-0.5">多模态证据分析工作台</p>
      </div>
      <nav className="flex-1 p-3 space-y-0.5">
        {nav.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded text-sm transition-colors ${
                isActive
                  ? "bg-white/15 text-white font-medium"
                  : "text-white/70 hover:bg-white/10 hover:text-white"
              }`
            }
          >
            <span className="text-base">{icon}</span>
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="p-4 border-t border-white/10 text-[10px] text-white/40 leading-relaxed">
        教育工具 · 非法律建议<br />
        任何结论绑定原始证据来源
      </div>
    </aside>
  );
}
