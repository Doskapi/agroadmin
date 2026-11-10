import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
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

type Formato = (v: number) => string;

function Tip({ active, payload, formato = pesos }: { active?: boolean; payload?: { payload: Punto }[]; formato?: Formato }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="chart-tip">
      <div className="t">{p.etiqueta}</div>
      <div className="v">{formato(p.valor)}</div>
      {p.cantidad != null && <div className="t">{p.cantidad} comprobante{p.cantidad === 1 ? "" : "s"}</div>}
    </div>
  );
}

const ejeTick = (color: string) => ({ fill: color, fontSize: 12 });

/** Barras verticales para series temporales (gastos por mes). */
export function BarrasTiempo({ datos, alto = 260, formato = pesos, compacto = pesosCompacto }: {
  datos: Punto[]; alto?: number; formato?: Formato; compacto?: Formato;
}) {
  const t = useTema();
  if (!datos.length) return <div className="empty">Sin datos para el período</div>;
  return (
    <ResponsiveContainer width="100%" height={alto}>
      <BarChart data={datos} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
        <CartesianGrid vertical={false} stroke={t.grid} />
        <XAxis dataKey="etiqueta" tickLine={false} axisLine={{ stroke: t.grid }} tick={ejeTick(t.texto)} />
        <YAxis tickFormatter={compacto} tickLine={false} axisLine={false} tick={ejeTick(t.texto)} width={70} />
        <Tooltip content={<Tip formato={formato} />} cursor={{ fill: t.hover }} />
        <Bar dataKey="valor" fill={t.serie} radius={[4, 4, 0, 0]} maxBarSize={32} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Barras horizontales ordenadas para comparar categorías (rubros, proveedores...). */
export function BarrasRanking({ datos, formato = pesos, compacto = pesosCompacto }: {
  datos: Punto[]; formato?: Formato; compacto?: Formato;
}) {
  const t = useTema();
  if (!datos.length) return <div className="empty">Sin datos para el período</div>;
  const alto = Math.max(120, datos.length * 34 + 24);
  return (
    <ResponsiveContainer width="100%" height={alto}>
      <BarChart data={datos} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid horizontal={false} stroke={t.grid} />
        <XAxis type="number" tickFormatter={compacto} tickLine={false} axisLine={false} tick={ejeTick(t.texto)} />
        <YAxis type="category" dataKey="etiqueta" width={150} tickLine={false} axisLine={false} tick={ejeTick(t.texto)}
          tickFormatter={(s: string) => (s.length > 22 ? `${s.slice(0, 21)}…` : s)} />
        <Tooltip content={<Tip formato={formato} />} cursor={{ fill: t.hover }} />
        <Bar dataKey="valor" fill={t.serie} radius={[0, 4, 4, 0]} maxBarSize={20} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Línea de precios en el tiempo (un punto por compra). */
export function LineaPrecios({ datos, alto = 240 }: { datos: Punto[]; alto?: number }) {
  const t = useTema();
  if (datos.length < 2) return <div className="empty">Hace falta más de una compra con precio para ver la evolución</div>;
  return (
    <ResponsiveContainer width="100%" height={alto}>
      <LineChart data={datos} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
        <CartesianGrid vertical={false} stroke={t.grid} />
        <XAxis dataKey="etiqueta" tickLine={false} axisLine={{ stroke: t.grid }} tick={ejeTick(t.texto)} />
        <YAxis tickFormatter={pesosCompacto} tickLine={false} axisLine={false} tick={ejeTick(t.texto)} width={70} />
        <Tooltip content={<Tip />} />
        <Line dataKey="valor" stroke={t.serie} strokeWidth={2} dot={{ r: 3, fill: t.serie }} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
