import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

interface Props { label: string; }

export function ComingSoonScheme({ label }: Props) {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/" className="text-slate-500 hover:text-slate-700">
          <ArrowLeft size={18} />
        </Link>
        <h1 className="text-2xl font-bold tracking-tight">{label}</h1>
        <span className="text-[10px] uppercase tracking-wider text-slate-500 px-2 py-1 rounded bg-slate-100">
          Coming soon
        </span>
      </div>
      <div className="card p-8 text-slate-600">
        This scheme is not yet active. Check back soon.
      </div>
    </div>
  );
}
