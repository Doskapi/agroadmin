import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { pesos, pesosCompacto } from "../format";

/** Lee los colores del tema actual (claro/oscuro) desde las variables CSS. */
function useTema() {
  const leer = () => {
    const s = getComputedStyle(document.documentElement);
    const v = (n: string) => s.getPropertyValue(n).trim();
    return { serie: v("--series-1"), grid: v("--grid"), texto: v("--text-3"), hover: v("--surface-2") };
  };
  const [tema, setTema] = useState(leer);
  useEffect(() => {
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const fn = () => setTema(leer());
    mq.addEventListener("change", fn);
    return () => mq.removeEventListener("change", fn);
  }, []);
  return tema;
}

interface Punto {
  etiqueta: string;
  valor: number;
  cantidad?: number;
}

function Tip({ active, payload }: { active?: boolean; payload?: { payload: Punto }[] }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="chart-tip">
      <div className="t">{p.etiqueta}</div>
      <div className="v">{pesos(p.valor)}</div>
      {p.cantidad != null && <div className="t">{p.cantidad} comprobante{p.cantidad === 1 ? "" : "s"}</div>}
    </div>
  );
}

const ejeTick = (color: string) => ({ fill: color, fontSize: 12 });

/** Barras verticales para series temporales (gastos por mes). */
export function BarrasTiempo({ datos, alto = 260 }: { datos: Punto[]; alto?: number }) {
  const t = useTema();
  if (!datos.length) return <div className="empty">Sin datos para el período</div>;
  return (
    <ResponsiveContainer width="100%" height={alto}>
      <BarChart data={datos} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
        <CartesianGrid vertical={false} stroke={t.grid} />
        <XAxis dataKey="etiqueta" tickLine={false} axisLine={{ stroke: t.grid }} tick={ejeTick(t.texto)} />
        <YAxis tickFormatter={pesosCompacto} tickLine={false} axisLine={false} tick={ejeTick(t.texto)} width={70} />
        <Tooltip content={<Tip />} cursor={{ fill: t.hover }} />
        <Bar dataKey="valor" fill={t.serie} radius={[4, 4, 0, 0]} maxBarSize={32} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Barras horizontales ordenadas para comparar categorías (rubros, proveedores...). */
export function BarrasRanking({ datos }: { datos: Punto[] }) {
  const t = useTema();
  if (!datos.length) return <div className="empty">Sin datos para el período</div>;
  const alto = Math.max(120, datos.length * 34 + 24);
  return (
    <ResponsiveContainer width="100%" height={alto}>
      <BarChart data={datos} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid horizontal={false} stroke={t.grid} />
        <XAxis type="number" tickFormatter={pesosCompacto} tickLine={false} axisLine={false} tick={ejeTick(t.texto)} />
        <YAxis type="category" dataKey="etiqueta" width={150} tickLine={false} axisLine={false} tick={ejeTick(t.texto)}
          tickFormatter={(s: string) => (s.length > 22 ? `${s.slice(0, 21)}…` : s)} />
        <Tooltip content={<Tip />} cursor={{ fill: t.hover }} />
        <Bar dataKey="valor" fill={t.serie} radius={[0, 4, 4, 0]} maxBarSize={20} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}
